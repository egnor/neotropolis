import asyncclick as click
import asyncio
import atexit
import ok_logging_setup
import ok_serial
import logging
import StreamDeck.DeviceManager
import time

import trashbot.crsf_protocol
import trashbot.emoji_input_driver
import trashbot.emoji_list
import trashbot.gamepad_driver
import trashbot.radio_driver


@click.command()
@click.option("--debug", is_flag=True)
async def main(debug):
    ok_logging_options = {
        "OK_LOGGING_LEVEL": "debug" if debug else "info",
        "OK_LOGGING_REPEAT_PER_MINUTE": 60,  # we repeat status a lot
        "OK_LOGGING_TIME_FORMAT": "%H:%M:%S",
    }
    ok_logging_setup.install(ok_logging_options)
    ok_logging_setup.install_asyncio_handler()

    # EMOJI KEYBOARDS
    emoji_list = trashbot.emoji_list.load()
    logging.info("🔎 Searching for Stream Decks...")
    streamdeck_manager = StreamDeck.DeviceManager.DeviceManager()
    streamdeck_list = streamdeck_manager.enumerate()
    # shut down threads before LibUSBHIDAPI.py's atexit to avoid messy crashes
    atexit.register(lambda: [d.__del__() for d in streamdeck_list])

    if (streamdeck_count := len(streamdeck_list)) != 2:
        ok_logging_setup.exit(f"Found {streamdeck_count} StreamDecks (not 2)")
    emoji_inputs = [
        trashbot.emoji_input_driver.EmojiInputDriver(d, emoji_list)
        for d in sorted(streamdeck_list, key=lambda d: d.id())
    ]

    # GAMEPAD
    gamepad = trashbot.gamepad_driver.connect()

    # RADIO
    logging.info("📻 Connecting to radio...")
    serial = ok_serial.SerialConnection(
        match=trashbot.radio_driver.BASE_PORT,
        baud=trashbot.radio_driver.BASE_BAUD,
    )
    radio = trashbot.radio_driver.RadioDriver(serial)

    # MAIN LOOP
    logging.info("🔁 Starting main loop...")
    start_mtime = time.monotonic()
    print_mtime = start_mtime + 0.01
    transmit_mtime = start_mtime
    command_status = "Ini"
    while True:
        await asyncio.sleep(0.01)
        while gamepad.poll_event():
            pass
        while radio.poll_frame():
            pass

        mtime = time.monotonic()
        if mtime >= print_mtime:
            print_mtime += 1.0
            rx_mode = radio.recent.get("FlightMode")
            rx_text = "RX " + (rx_mode.flight_mode if rx_mode else "N/A")
            logging.info("\nTRASHBASE: command %s; %s", command_status, rx_text)
            logging.info("📻 %s", radio.debug_str())
            radio.counts.clear()

        if mtime >= transmit_mtime:
            transmit_mtime += 0.01
            command_status = transmit_command(
                mtime=mtime,
                prev_status=command_status,
                emoji_inputs=emoji_inputs,
                gamepad=gamepad,
                radio=radio,
            )


def transmit_command(
    *,
    mtime: float,
    prev_status: str,
    emoji_inputs: list[trashbot.emoji_input_driver.EmojiInputDriver],
    gamepad: trashbot.gamepad_driver.GamepadDriver,
    radio: trashbot.radio_driver.RadioDriver,
):
    from_frac = trashbot.crsf_protocol.channel_from_signed_fraction
    channels = [from_frac(0)] * 16
    channels[4] = from_frac(1)  # armed

    rx_mode = radio.recent.get("FlightMode")
    rx_word = rx_mode.flight_mode.split()[0] if rx_mode else ""

    if not rx_word:
        command_status = "!RX"
        channels[4] = from_frac(-1)  # disarm until RX seen (stale OK)
    elif rx_word == "!RX":
        command_status = "RX!RX"
        channels[4] = from_frac(-1)  # disarm until RX round trip (stale OK)
    elif rx_word != "OK":
        # zero motion (but arm) when RX is not OK
        command_status = "RX!OK"
    elif (left_y := gamepad.recent.get("LY")) is None:
        command_status = "!LY"
    elif (right_x := gamepad.recent.get("RX")) is None:
        command_status = "!RX"
    elif not any(gamepad.recent.get(b) for b in ("LB", "LT", "RB", "RT")):
        command_status = "!Trig"  # zero motion (but arm) without trigger
    elif prev_status != "OK" and left_y > 0.05:
        command_status = "LY+"
    elif prev_status != "OK" and left_y < -0.05:
        command_status = "LY-"
    elif prev_status != "OK" and right_x > 0.05:
        command_status = "RX+"
    elif prev_status != "OK" and right_x < -0.05:
        command_status = "RX-"
    else:
        command_status = "OK"
        throttle = -left_y if abs(left_y) > 0.05 else 0
        rotate = right_x if abs(right_x) > 0.05 else 0
        channels[0] = from_frac(rotate)
        channels[2] = from_frac(throttle)

    assert len(emoji_inputs) == 2
    for input, ch in zip(emoji_inputs, (1, 3)):
        emoji = input.picked_emoji()
        rf_code = emoji.rf_code if emoji else 0
        ch_code = trashbot.crsf_protocol.channel_from_rf_code(rf_code, bits=10)
        channels[ch] = ch_code

    radio.send_frame(type="RCChannelsPacked", channels=channels)
    return command_status


if __name__ == "__main__":
    main()
