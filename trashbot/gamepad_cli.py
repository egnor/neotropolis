#!/usr/bin/env python3

import asyncclick as click
import evdev
import ok_logging_setup
import time

import trashbot.gamepad_driver


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--device", help="Event device path (e.g. /dev/input/event9)")
def main(debug, device):
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})

    if device:
        dev = evdev.InputDevice(device)
        caps = dev.capabilities()
        gamepad = trashbot.gamepad_driver.GamepadDriver(dev=dev, caps=caps)
    else:
        gamepad = trashbot.gamepad_driver.connect()

    while True:
        while event := gamepad.poll_event():
            print(event)
        time.sleep(0.01)


if __name__ == "__main__":
    main()
