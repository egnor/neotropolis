#!/usr/bin/env python3

import asyncclick as click
import logging
import ok_logging_setup
import StreamDeck.DeviceManager

import trashbot.emoji_input_driver
import trashbot.emoji_list


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--id", default=None)
def main(debug, id):
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})

    logging.info("🔎 Looking for StreamDeck devices...")
    device_manager = StreamDeck.DeviceManager.DeviceManager()
    device_list = device_manager.enumerate()
    if not device_list:
        ok_logging_setup.exit("No StreamDeck devices found")
    logging.info(
        f"🎛️ {len(device_list)} StreamDeck(s) found"
        + "".join(f"\n  {d.id():<15} {d.deck_type()}" for d in device_list)
    )

    if len(device_list) == 1 and not id:
        device = device_list[0]
    elif not id:
        ok_logging_setup.exit("Pick a device to use with --id=ID")
    elif matching := [d for d in device_list if d.id() == id]:
        device = matching[0]
    else:
        ok_logging_setup.exit(f"No device found with id={id}")

    try:
        device.open()
        emojis = trashbot.emoji_list.load()
        emoji_input = trashbot.emoji_input_driver.EmojiInputDriver(
            device, emojis
        )

    finally:
        device.close()


if __name__ == "__main__":
    main()
