#!/usr/bin/env python3

import asyncclick as click
import asyncio
import ok_logging_setup
import ok_serial
import logging
import time

import trashbot.eye_display_driver
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

    logging.info("👀 Connecting to eye displays...")
    ddriver = trashbot.eye_display_driver.EyeDisplayDriver()

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
            update_eye_displays(
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
                old_status=command_status,
                please_wait=(not ready_mtime) or mtime < ready_mtime,
                mdriver=mdriver,
                rdriver=rdriver,
            )

            if command_status not in ("Wait", "Ok"):
                ready_mtime = mtime + 2.0

        if mtime >= print_mtime:
            print_mtime += 1.0
            logging.info("\nTRASHBOT COMMAND: %s", command_status)
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
    old_status: str,
    please_wait: bool,
    mdriver: trashbot.motor_driver.MotorDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    if not (channels := rdriver.recent.get("RCChannelsPacked")):
        command_status = "!RC"
    elif channels.mtime < mtime - 0.1:
        command_status = "Old"
    elif channels.scaled_values[4] < 0.1:
        command_status = "!Arm"
    elif any(abs(v) > 1.0 for v in channels.scaled_values[:5]):
        command_status = "Inv"
    elif old_status != "Ok" and channels.scaled_values[2] > 0.05:
        command_status = "Thr+"
    elif old_status != "Ok" and channels.scaled_values[2] < -0.05:
        command_status = "Thr-"
    elif old_status != "Ok" and channels.scaled_values[0] > 0.05:
        command_status = "Rot+"
    elif old_status != "Ok" and channels.scaled_values[0] < -0.05:
        command_status = "Rot-"
    elif please_wait:
        command_status = "Wait"
    else:
        command_status = "Ok"

    if command_status == "Ok":
        assert channels
        throttle = channels.scaled_values[2]
        rotate = channels.scaled_values[0]
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
    if all(mo.is_active for mo in mdriver.motors):
        motor_status = "Go"
    elif all(mo.state == mdriver.motors[0].state for mo in mdriver.motors):
        motor_status = abbrev(mdriver.motors[0].state)
    else:
        motor_status = "/".join(abbrev(mo.state) for mo in mdriver.motors)

    for err in set.union(*(mo.errors for mo in mdriver.motors)):
        motor_status += " " + abbrev(err)

    text = f"C:{command_status} M:{motor_status}"
    while len(text) > 15:
        text = " ".join(text.split()[:-1]) + "+"

    rdriver.send_frame(type="FlightMode", flight_mode=text)

    rdriver.send_frame(
        type="BatterySensor",
        voltage_v=min(mo.bus_volts for mo in mdriver.motors),
        current_a=0,  # TODO: maybe capture motor current?
        capacity_used_mah=0,  # no battery model
        remaining_pct=0,  # no battery model
    )


def update_eye_displays(
    *,
    mtime: float,
    command_status: str,
    ddriver: trashbot.eye_display_driver.EyeDisplayDriver,
    mdriver: trashbot.motor_driver.MotorDriver,
    rdriver: trashbot.radio_driver.RadioDriver,
):
    pass


if __name__ == "__main__":
    main()
