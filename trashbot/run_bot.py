#!/usr/bin/env python3

import asyncclick as click
import asyncio
import ok_logging_setup
import ok_serial
import logging
import time

import trashbot.crsf_protocol
import trashbot.bot_display_driver
import trashbot.motor_driver
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
    ok_logging_setup.skip_traceback_for(ok_serial.SerialException)
    ok_logging_setup.skip_traceback_for(trashbot.motor_driver.MotorError)

    logging.info("📻️ Connecting to radio...")
    serial = ok_serial.SerialConnection(
        match=trashbot.radio_driver.BOT_PORT,
        baud=trashbot.radio_driver.BOT_BAUD,
    )
    rdriver = trashbot.radio_driver.RadioDriver(serial)

    logging.info("⚙️ Connecting to motors...")
    mdriver = await trashbot.motor_driver.connect()

    logging.info("👀 Connecting to displays...")
    ddriver = trashbot.bot_display_driver.BotDisplayDriver()

    start_mtime = time.monotonic()
    ready_mtime = 0

    display_mtime = start_mtime + 0.01
    motor_mtime = start_mtime + 0.02
    print_mtime = start_mtime + 0.03
    telemetry_mtime = start_mtime + 0.04

    logging.info("🔄 Starting main loop...")
    command_status = "Ini"
    while True:
        await asyncio.sleep(0.01)
        mtime = time.monotonic()

        while rdriver.poll_frame():
            pass

        if mtime >= display_mtime:
            display_mtime += 0.05
            update_displays(
                mtime=mtime,
                command_status=command_status,
                ddriver=ddriver,
                mdriver=mdriver,
                rdriver=rdriver,
            )

        if mtime >= motor_mtime:
            motor_mtime += 0.05
            command_status = await command_motor(
                mtime=mtime,
                prev_status=command_status,
                please_wait=(not ready_mtime) or mtime < ready_mtime,
                mdriver=mdriver,
                rdriver=rdriver,
            )

            if command_status not in ("Wait", "OK"):
                ready_mtime = mtime + 2.0

        if mtime >= print_mtime:
            print_mtime += 1.0
            logging.info("\nTRASHBOT: command %s", command_status)
            for mo in mdriver.motors:
                logging.info(f"⚙️ {mo.debug_str()}")

        if mtime >= telemetry_mtime:
            telemetry_mtime += 0.1
            send_telemetry(
                command_status=command_status,
                mdriver=mdriver,
                rdriver=rdriver,
            )


def abbrev(text: str):
    if "_" in text:
        return "".join(w[:2].title() for w in text.split("_"))
    return text[:3].title()


async def command_motor(
    *,
    mtime: float,
    prev_status: str,
    please_wait: bool,
    mdriver: trashbot.motor_driver.MotorDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    get_frac = trashbot.crsf_protocol.signed_fraction_from_channel

    if not (rc := rdriver.recent.get("RCChannelsPacked")):
        command_status = "Off"
    elif rc.mtime < mtime - 0.1:
        command_status = "Lost"
    elif get_frac(rc.channels[4]) < 0.1:
        command_status = "!Arm"
    elif abs(throttle := get_frac(rc.channels[2])) > 1.0:
        command_status = "!Thr"
    elif prev_status != "OK" and throttle > 0.05:
        command_status = "Thr+"
    elif prev_status != "OK" and throttle < -0.05:
        command_status = "Thr-"
    elif abs(rotate := get_frac(rc.channels[0])) > 1.0:
        command_status = "!Rot"
    elif prev_status != "OK" and rotate > 0.05:
        command_status = "Rot+"
    elif prev_status != "OK" and rotate < -0.05:
        command_status = "Rot-"
    elif not all(mo.is_active for mo in mdriver.motors):
        command_status = "On"
    elif please_wait:
        command_status = "Wait"
    else:
        command_status = "OK"

    if command_status == "OK":
        vels = [throttle * 10 - rotate * 5, throttle * 10 + rotate * 5]
        vels = [0 if abs(v) < 0.1 else v for v in vels]
    else:
        vels = [0, 0]

    for mo, vel in zip(mdriver.motors, vels):
        mo.command_vel = vel
        mo.command_fresh = True

    await mdriver.refresh()
    return command_status


def send_telemetry(
    *,
    command_status: str,
    mdriver: trashbot.motor_driver.MotorDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    text = command_status
    if not all(mo.is_active for mo in mdriver.motors):
        motor_states = [abbrev(mo.state) for mo in mdriver.motors]
        if all(ms == motor_states[0] for ms in motor_states[1:]):
            text += f" M:{motor_states[0]}"
        else:
            text += f" M:{'/'.join(motor_states)}"

    motor_errors = set.union(*(mo.errors for mo in mdriver.motors))
    if motor_errors:
        text += f" E:{','.join(motor_errors)}"

    while len(text) > 15:
        text = " ".join(text.split()[:-1]) + ">"

    rdriver.send_frame(type="FlightMode", flight_mode=text)

    rdriver.send_frame(
        type="BatterySensor",
        voltage_v=min(mo.bus_volts for mo in mdriver.motors),
        current_a=0,  # TODO: maybe capture motor current?
        capacity_used_mah=0,  # no battery model
        remaining_pct=0,  # no battery model
    )


def update_displays(
    *,
    mtime: float,
    command_status: str,
    ddriver: trashbot.bot_display_driver.BotDisplayDriver,
    mdriver: trashbot.motor_driver.MotorDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    caption_words = []
    if command_status != "OK":
        caption_words.append(f"Remote {command_status}")
    if any(mo.state == "ESTOP" for mo in mdriver.motors):
        caption_words.append("E-Stop Pressed")
    elif any(mo.errors for mo in mdriver.motors):
        caption_words.append("Motor Issue")
    elif any(mo.state == "IDLE" for mo in mdriver.motors):
        caption_words.append("Motor Idle")

    if not (rc := rdriver.recent.get("RCChannelsPacked")):
        rf_codes = (0, 0)
    else:
        get_code = trashbot.crsf_protocol.rf_code_from_channel
        rf_codes = (
            get_code(rc.channels[3], bits=10),
            get_code(rc.channels[1], bits=10),
        )

    caption_text = " / ".join(caption_words).upper()  # font has no good lcase
    for eye, rf_code in enumerate(rf_codes):
        request = {"rf_code": rf_code, "caption": caption_text}
        ddriver.set_display(eye, request)


if __name__ == "__main__":
    main()
