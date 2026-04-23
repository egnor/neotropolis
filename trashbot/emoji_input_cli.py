#!/usr/bin/env python3

import asyncclick as click
import asyncio
import logging
import ok_logging_setup
import StreamDeck.DeviceManager

import trashbot.emoji_input_driver
import trashbot.emoji_list


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--id", default=None)
async def main(debug, id):
    ok_logging_options = {"OK_LOGGING_LEVEL": "debug" if debug else "info"}
    ok_logging_setup.install(ok_logging_options)
    ok_logging_setup.install_asyncio_handler()

    logging.info("🔎 Looking for StreamDeck devices...")
    device_manager = StreamDeck.DeviceManager.DeviceManager()
    device_list = device_manager.enumerate()
    if not device_list:
        ok_logging_setup.exit("No StreamDeck devices found")
    logging.info(
        f"🎛️ {len(device_list)} StreamDeck(s) found"
        + "".join(f"\n  {d.id():<10} {d.deck_type()}" for d in device_list)
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
        driver = trashbot.emoji_input_driver.EmojiInputDriver(device, emojis)

        logging.info("⏳ Waiting for input...")
        while True:
            await asyncio.sleep(0.05)
            driver

    finally:
        device.close()


if __name__ == "__main__":
    main()
