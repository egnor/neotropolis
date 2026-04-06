#!/usr/bin/env python3
"""
Sends a magic USB request to trigger DFU (Device Firmware Update) mode
any USB-connected ODrive should go into DFU if it boots with this running
https://docs.odriverobotics.com/v/latest/guides/firmware-update.html#dfu-recovery
"""

import usb.core
import usb.util

while True:
    print(f"scanning...")
    devices = list(
        usb.core.find(find_all=True, idVendor=0x1209, idProduct=0x0D32)
    )
    print(f"found {len(devices)} ODrives...")

    bootloader_odrives = []
    for device in devices:
        try:
            if usb.util.get_string(device, device.iProduct).endswith(
                " Bootloader"
            ):
                bootloader_odrives.append(device)
        except ValueError:
            pass
        except usb.core.USBError as e:
            print(f"USBError: {str(e)}")

    if len(bootloader_odrives) > 0:
        print(
            f"sending FORCE DFU command to {len(bootloader_odrives)} devices..."
        )
    for device in bootloader_odrives:
        try:
            # Send a vendor setup request
            request_type = usb.util.build_request_type(
                usb.util.CTRL_OUT,
                usb.util.CTRL_TYPE_VENDOR,
                usb.util.CTRL_RECIPIENT_DEVICE,
            )
            request = 0x0D  # vendor code: ODrive
            value = 0x0001  # command: force DFU
            index = 0x00

            device.ctrl_transfer(request_type, request, value, index)
        except usb.core.USBError as e:
            print(f"USBError: {str(e)}")
