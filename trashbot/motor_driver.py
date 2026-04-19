# Driver for ODrive left/right tread motors for Trashbot

import asyncio
import dataclasses
import importlib.resources
import json
import logging
import math
import odrive
import odrive.exceptions
import odrive.legacy_config
import odrive.libodrive
import odrive.runtime_device
import odrive.utils
import struct

import trashbot

_log = logging.getLogger(__name__)

_gold_firmware = (0, 6, 11, 0)

_odrive_exc = (
    odrive.exceptions.DeviceException,
    odrive.libodrive.DeviceLostException,
    odrive.libodrive.TransportException,
    TimeoutError,
)


class MotorError(Exception):
    pass


@dataclasses.dataclass(order=False, slots=True)
class Motor:
    odrive: odrive.runtime_device.RuntimeDevice
    config: dict = dataclasses.field(repr=False)
    firmware: list[int]

    bus_volts: float = 0.0
    is_active: bool = False
    state: str = ""
    reason: str = ""
    errors: set[str] = dataclasses.field(default_factory=set)
    timeout_count: int = 0

    command_vel: float = 0.0
    command_fresh: bool = False

    estim_vel: float = 0.0
    feed_torq: float = 0.0
    integ_torq: float = 0.0

    def __str__(self):
        return f"M{self.odrive.effective_node_id}:{self.odrive.serial_number}"

    def debug_str(self):
        status_words = [
            self.state,
            *(f"why+now:{e}" for e in self.errors & {self.reason}),
            *(f"why:{e}" for e in {self.reason} - self.errors if e),
            *(f"now:{e}" for e in self.errors - {self.reason}),
        ]
        return (
            f"M{self.odrive.effective_node_id} {self.debug_emoji()}"
            f" C{self.command_vel:+.1f}"
            f" A{self.estim_vel:+.1f}"
            f" F{self.feed_torq:+05.1f}"
            f" I{self.integ_torq:+05.1f}"
            f" {self.bus_volts:+.1f}V"
            f" {' '.join(status_words)}"
        )

    def debug_emoji(self):
        if not self.is_active and self.estim_vel <= -0.01:
            return "⬅️" + ("⛔" if self.state == "ESTOP" else "💤")
        elif not self.is_active and self.estim_vel >= 0.01:
            return ("⛔" if self.state == "ESTOP" else "💤") + "➡️"
        elif not self.is_active:
            return "⛔" if self.state == "ESTOP" else "💤"
        elif self.command_vel <= -0.001 and self.estim_vel <= -0.001:
            return "◀️⬅️"
        elif self.command_vel <= -0.001 and -0.01 <= self.estim_vel <= 0.01:
            return "◀️🔷"
        elif self.command_vel <= -0.001:
            return "◀️⚠️➡️"
        elif self.command_vel >= 0.001 and self.estim_vel >= 0.001:
            return "➡️▶️"
        elif self.command_vel >= 0.001 and -0.01 < self.estim_vel < 0.01:
            return "🔷▶️"
        elif self.command_vel >= 0.001:
            return "⬅️⚠️▶️"
        elif self.estim_vel <= -0.01:
            return "⬅️⚠️⏹️"
        elif self.estim_vel >= 0.01:
            return "⏹️⚠️➡️"
        else:
            return "⏹️🔷"


class MotorDriver:
    async def _connect(self, can_iface="can0", allow_config_errors=False):
        _log.info(f"🔎 Scanning for motors on {can_iface}...")

        # check for other processes using CAN bus
        try:
            rcvlist_lines = open("/proc/net/can/rcvlist_all").readlines()
        except FileNotFoundError:
            # /proc/net/can doesn't exist before the first socket open
            rcvlist_lines = []

        if any(s.split()[:1] == [can_iface] for s in rcvlist_lines):
            raise MotorError(f"{can_iface} interface in use")

        find_future = odrive.find_async(
            interfaces=[f"can:{can_iface}"],
            count=2,
            return_type=odrive.runtime_device.RuntimeDevice,
        )
        try:
            devs = await asyncio.wait_for(find_future, 5.0)
        except _odrive_exc:
            raise MotorError("Error finding motor devices")
        if len(devs) != 2:
            raise MotorError(f"Got {len(self.motors)} devices, expected 2")

        devs = sorted(devs, key=lambda d: d.effective_node_id)
        node_ids = [d.effective_node_id for d in devs]
        if node_ids != [1, 2]:
            raise MotorError(f"Unexpected CAN node IDs: {node_ids}")

        _log.info(f"⚙️ Found {len(devs)} motors, checking configs...")
        try:
            backup_config = odrive.legacy_config.backup_config
            ver_names = ["major", "minor", "revision", "unreleased"]
            ver_vars = [f"fw_version_{v}" for v in ver_names]
            configs, vers = await asyncio.gather(
                asyncio.gather(*(backup_config(d) for d in devs)),
                asyncio.gather(*(d.read_multiple(ver_vars) for d in devs)),
            )
        except _odrive_exc:
            raise MotorError("Error getting motor configs")

        gold_str = importlib.resources.read_text(trashbot, "motor_config.json")
        self.gold_config = json.loads(gold_str)
        self.motors = [Motor(d, c, v) for d, c, v in zip(devs, configs, vers)]

        errors = []
        for mo in self.motors:
            _log.debug(f"{mo} checking config...")
            if mo.firmware != _gold_firmware:
                errors.append(f"{mo} fw {mo.firmware} != {_gold_firmware}")
            for key, gold in self.gold_config.items():
                val = mo.config.get(key)
                if isinstance(gold, float):
                    if struct.pack("<f", gold) != struct.pack("<f", val):
                        errors.append(f"{mo} {key} {val} != exp {gold}")
                elif val != gold:
                    errors.append(f"{mo} {key} {val} != exp {gold}")

        if errors:
            error_detail = "".join(f"\n  {e}" for e in errors)
            if allow_config_errors:
                _log.warning(f"Allowing motor config mismatch:{error_detail}")
            else:
                raise MotorError(f"Motor config mismatch:{error_detail}")
        else:
            motors_text = ", ".join(str(m) for m in self.motors)
            _log.info(f"✅ Motor configs valid: {motors_text}")
        return self

    async def fix_configs(self):
        for mo in self.motors:
            try:
                _log.info(f"🔧 {mo} updating config")
                await odrive.legacy_config.apply_config(
                    mo.odrive, self.gold_config, throw_on_error=True
                )
                _log.info(f"🔃 {mo} saving and rebooting")
                await odrive.utils.call_rebooting_function(
                    mo.odrive, "save_configuration"
                )
            except _odrive_exc:
                raise MotorError(f"Error updating motor {mo} config")

    async def refresh(self):
        try:
            refresh_tasks = [self._refresh_motor(mo) for mo in self.motors]
            await asyncio.wait_for(asyncio.gather(*refresh_tasks), 0.1)
        except _odrive_exc:
            raise MotorError("Error talking to motor")

    async def _refresh_motor(self, mo):
        try:
            values = await mo.odrive.read_multiple(
                [
                    "axis0.active_errors",
                    "axis0.controller.vel_integrator_torque",
                    "axis0.current_state",
                    "axis0.disarm_reason",
                    "axis0.enable_pin.state",
                    "axis0.vel_estimate",
                    "vbus_voltage",
                ],
                transient=True,
            )
            acode, integ, state, rcode, en, vel, vbus = values
        except TimeoutError:
            _log.warn(f"{mo} timeout in refresh")
            mo.timeout_count += 1
            if mo.timeout_count >= 5:
                raise

        # Interpret motor controller status and error bits
        OError = odrive.enums.ODriveError
        estop = state == odrive.enums.AxisState.IDLE and not en
        mo.is_active = state == odrive.enums.AxisState.CLOSED_LOOP_CONTROL
        mo.state = "ESTOP" if estop else odrive.enums.AxisState(state).name
        mo.reason = OError(rcode).name if rcode else ""
        mo.errors = {e.name for e in OError(acode)}
        mo.bus_volts = vbus

        # Copy (and translate) controller diagnostic variables
        flip = -1 if mo.odrive.effective_node_id == 1 else 1
        mo.estim_vel = vel * flip
        mo.integ_torq = integ * flip

        mo.feed_torq = 0
        if abs(mo.command_vel) >= 0.01:
            mo.feed_torq += math.copysign(10.0, mo.command_vel)
            mo.feed_torq += 1.0 * mo.command_vel

        # Send motor command (zero for safety when not active)
        all_active = all(om.is_active for om in self.motors)
        if mo.command_fresh:
            od = mo.odrive
            if all_active:
                set_vel = mo.command_vel * flip
                set_torq = mo.feed_torq * flip
                await od.write("axis0.controller.input_vel", set_vel)
                await od.write("axis0.controller.input_torque", set_torq)
            else:
                await od.write("axis0.controller.input_vel", 0.0)
                await od.write("axis0.controller.input_torque", 0.0)
                await od.write("axis0.controller.vel_integrator_torque", 0.0)

            await od.call_function("axis0.watchdog_feed")
            mo.command_fresh = False


async def connect(**kwargs) -> MotorDriver:
    return await MotorDriver()._connect(**kwargs)
