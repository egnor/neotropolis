# Driver for ODrive left/right tread motors for Trashbot

import asyncio
import dataclasses
import importlib.resources
import json
import logging
import odrive
import odrive.exceptions
import odrive.legacy_config
import odrive.libodrive
import odrive.runtime_device
import odrive.utils
import struct

import trashbot

_log = logging.getLogger(__name__)

_odrive_exc = (
    odrive.exceptions.DeviceException,
    odrive.libodrive.DeviceLostException,
    odrive.libodrive.TransportException,
    TimeoutError,
)


class MotorError(Exception):
    pass


@dataclasses.dataclass
class Motor:
    odrive: odrive.runtime_device.RuntimeDevice
    config: dict

    def __str__(self):
        return f"M{self.odrive.effective_node_id}:{self.odrive.serial_number}"


class MotorDriver:
    async def _connect(self, allow_config_errors=False):
        _log.info("🔎 Scanning for motor controllers...")
        devs = await odrive.find_async(
            interfaces=["can:can0"],
            count=2,
            return_type=odrive.runtime_device.RuntimeDevice,
        )
        if len(devs) != 2:
            raise ValueError(f"Got {len(self.motors)} devices, expected 2")

        devs = sorted(devs, key=lambda d: d.effective_node_id)
        node_ids = [d.effective_node_id for d in devs]
        if node_ids != [1, 2]:
            raise MotorError(f"Unexpected CAN node IDs: {node_ids}")

        _log.info(f"⚙️ Found {len(devs)} motors, checking configs...")
        try:
            configs = await asyncio.gather(
                *(odrive.legacy_config.backup_config(d) for d in devs)
            )
        except _odrive_exc:
            raise MotorError("Error getting motor configs")

        gold_str = importlib.resources.read_text(trashbot, "motor_config.json")
        self.gold_config = json.loads(gold_str)
        self.motors = [Motor(dev, conf) for dev, conf in zip(devs, configs)]

        errors = []
        for mot in self.motors:
            _log.debug(f"Checking {mot} config...")
            for key, gold in self.gold_config.items():
                val = mot.config.get(key)
                if isinstance(gold, float):
                    if struct.pack("<f", gold) != struct.pack("<f", val):
                        errors.append(f"{mot}: {key} {val} != exp {gold}")
                elif val != gold:
                    errors.append(f"{mot}: {key} {val} != exp {gold}")

        if errors:
            error_detail = "".join(f"\n  {e}" for e in errors)
            if allow_config_errors:
                _log.warning(f"Allowing wrong motor config:{error_detail}")
            else:
                raise MotorError(f"Wrong motor config:{error_detail}")
        else:
            motors_text = ", ".join(str(m) for m in self.motors)
            _log.info(f"✅ Motor configs valid: {motors_text}")
        return self

    async def fix_configs(self):
        for mot in self.motors:
            _log.info(f"🔧 Updating config: {mot}")
            try:
                await odrive.legacy_config.apply_config(
                    mot.odrive, self.gold_config, throw_on_error=True
                )
                _log.debug(f"Saving config to NVRAM: {mot}")
                await odrive.utils.call_rebooting_function(
                    mot.odrive, "save_configuration"
                )
            except _odrive_exc:
                raise MotorError(f"Error updating motor {mot} config")


async def connect(**kwargs) -> MotorDriver:
    return await MotorDriver()._connect(**kwargs)
