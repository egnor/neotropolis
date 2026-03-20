#!/usr/bin/env python3
"""
Spams a magic CAN packet to trigger DFU (Device Firmware Update) mode
any CAN-connected ODrive should go into DFU if it boots with this running
https://docs.odriverobotics.com/v/latest/guides/firmware-update.html#recovering-from-unbootable-firmware
"""

import can
import time

with can.interface.Bus("can0", interface="socketcan") as bus:
    print("spamming DFU request packet...")
    while True:
        bus.send(
            can.Message(
                arbitration_id=0,
                data=[0xA8, 0x94, 0x18, 0x5C, 0xA8, 0xE6, 0x0C, 0x56],
                is_extended_id=False,
            )
        )
        time.sleep(0.02)
