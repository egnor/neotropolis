#!/usr/bin/env python3
"""
Sends a CAN command to reboot into DFU (Device Firmware Update) mode
https://docs.odriverobotics.com/v/latest/manual/can-protocol.html#reboot
"""

import argparse
import asyncio
import can

from can_simple_utils import CanSimpleNode


async def main():
    parser = argparse.ArgumentParser(description="Request ODrive DFU via CAN")
    parser.add_argument("-i", "--interface", default="socketcan")
    parser.add_argument("-c", "--channel", default="can0")
    parser.add_argument("--node-id", type=int, required=True)
    args = parser.parse_args()

    print("opening CAN bus...")
    with can.interface.Bus(args.channel, interface=args.interface) as bus:
        with CanSimpleNode(bus=bus, node_id=args.node_id) as node:
            print("sending reboot request with DFU mode...")
            node.reboot_msg(3)

        await asyncio.sleep(0.1)  # make sure message goes out


if __name__ == "__main__":
    asyncio.run(main())
