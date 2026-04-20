import asyncclick as click
import asyncio
import ok_logging_setup
import ok_serial
import logging
import time

import trashbot.crsf_protocol
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
    ok_logging_setup.skip_traceback_for(trashbot.gamepad_driver.GamepadError)
    ok_logging_setup.skip_traceback_for(ok_serial.SerialException)

    gdriver = trashbot.gamepad_driver.connect()

    logging.info("📻 Connecting to radio...")
    serial = ok_serial.SerialConnection(
        match=trashbot.radio_driver.BASE_PORT,
        baud=trashbot.radio_driver.BASE_BAUD,
    )
    rdriver = trashbot.radio_driver.RadioDriver(serial)

    start_mtime = time.monotonic()
    print_mtime = start_mtime + 0.01
    transmit_mtime = start_mtime

    logging.info("🔁 Starting main loop...")
    command_status = "Ini"
    while True:
        await asyncio.sleep(0.01)
        while gdriver.poll_event():
            pass
        while rdriver.poll_frame():
            pass

        mtime = time.monotonic()
        if mtime >= print_mtime:
            print_mtime += 1.0
            rx_mode = rdriver.recent.get("FlightMode")
            rx_text = "RX " + (rx_mode.flight_mode if rx_mode else "N/A")
            logging.info("\nTRASHBASE: command %s; %s", command_status, rx_text)
            logging.info("📻 %s", rdriver.debug_str())
            rdriver.counts.clear()

        if mtime >= transmit_mtime:
            transmit_mtime += 0.01
            command_status = transmit_command(
                mtime=mtime,
                prev_status=command_status,
                gdriver=gdriver,
                rdriver=rdriver,
            )


def transmit_command(
    *,
    mtime: float,
    prev_status: str,
    gdriver: trashbot.gamepad_driver.GamepadDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    from_frac = trashbot.crsf_protocol.channel_from_signed_fraction
    channels = [from_frac(0)] * 16
    channels[4] = from_frac(1)  # armed

    rx_mode = rdriver.recent.get("FlightMode")
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
    elif (left_y := gdriver.recent.get("LY")) is None:
        command_status = "!LY"
    elif (right_x := gdriver.recent.get("RX")) is None:
        command_status = "!RX"
    elif not any(gdriver.recent.get(b) for b in ("LB", "LT", "RB", "RT")):
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

    from_code = trashbot.crsf_protocol.channel_from_rf_code
    channels[1] = from_code(100, bits=10)
    channels[3] = from_code(100, bits=10)

    rdriver.send_frame(type="RCChannelsPacked", channels=channels)
    return command_status


if __name__ == "__main__":
    main()
