# Driver for ODrive left/right tread motors for Trashbot

import asyncio
import dataclasses
import importlib.resources
import json
import logging
import odrive
import odrive.async_tree
import odrive.legacy_config
import struct

import trashbot

log = logging.getLogger(__name__)


class MotorError(Exception):
    pass


@dataclasses.dataclass
class Motor:
    name: str
    odrive: odrive.async_tree.AsyncObject
    config: dict


class MotorDriver:
    async def _connect(self, allow_config_errors=False):
        log.info("🔎 Scanning for motor controllers...")
        devs = await odrive.find_async(interfaces=["can:can0"], count=2)
        if len(devs) != 2:
            raise ValueError(f"Got {len(devs)} devices, expected 2")

        configs = await asyncio.gather(
            *(odrive.legacy_config.backup_config(d) for d in devs)
        )

        node_key = "axis0.config.can.node_id"
        node_ids, configs, devs = zip(
            *sorted((c[node_key], c, d) for c, d in zip(configs, devs))
        )
        if node_ids != (1, 2):
            raise MotorError(f"Unexpected CAN node IDs: {node_ids}")

        self.motors = []
        for conf, dev in zip(configs, devs):
            name = f"M{conf[node_key]} ({await dev.serial_number.read():X})"
            self.motors.append(Motor(name=name, odrive=dev, config=conf))

        gold_str = importlib.resources.read_text(trashbot, "motor_config.json")
        self.gold_config = json.loads(gold_str)

        errors = []
        for motor in self.motors:
            log.debug(f"Checking {motor.name} config...")
            for key, gold_val in self.gold_config.items():
                val = motor.config.get(key)
                if isinstance(gold_val, float):
                    if struct.pack("<f", gold_val) != struct.pack("<f", val):
                        errors.append(f"{motor.name}: {val} != exp {gold_val}")
                elif val != gold_val:
                    errors.append(f"{motor.name}: {val} != exp {gold_val}")

        if errors:
            error_detail = "".join(f"\n  {e}" for e in errors)
            if allow_config_errors:
                log.warning(f"Allowing wrong config:{error_detail}")
            else:
                raise MotorError(f"Wrong config:{error_detail}")

        log.info(f"⚙️ Found {len(self.motors)} motors, config checked")
        return self

    async def fix_config(self):
        for motor in self.motors:
            log.info(f"Updating config: {motor.name}")
            await odrive.legacy_config.apply_config(
                motor.odrive, self.gold_config, throw_on_error=True
            )


async def connect(**kwargs) -> MotorDriver:
    return await MotorDriver()._connect(**kwargs)
