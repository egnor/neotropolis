#!/usr/bin/env python3

import asyncclick as click
import asyncio
import ok_logging_setup
import ok_serial
import logging
import time

import trashbot.motor_driver
import trashbot.radio_driver


@click.command()
@click.option("--debug", is_flag=True)
async def main(debug):
    ok_logging_options = {
        "OK_LOGGING_LEVEL": "debug" if debug else "info",
        "OK_LOGGING_REPEAT_PER_MINUTE": 60,
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

    start_mtime = time.monotonic()
    motor_mtime = start_mtime
    print_mtime = start_mtime
    telemetry_mtime = start_mtime
    unready_mtime = start_mtime

    logging.info("🔄 Starting main loop...")
    command_status = "Ini"
    while True:
        await asyncio.sleep(0.01)
        mtime = time.monotonic()

        while rdriver.poll_frame():
            pass

        if mtime >= motor_mtime:
            motor_mtime += 0.05
            vels = [0, 0]
            if not (channels := rdriver.recent.get("RCChannelsPacked")):
                command_status = "!RC"
            elif channels.mtime < mtime - 0.1:
                command_status = "Old"
            elif channels.scaled_values[4] < 0.1:
                command_status = "!Arm"
            elif any(abs(v) > 1.0 for v in channels.scaled_values[:5]):
                command_status = "Inv"
            elif command_status != "Ok" and channels.scaled_values[2] > 0.05:
                command_status = "Thr+"
            elif command_status != "Ok" and channels.scaled_values[2] < -0.05:
                command_status = "Thr-"
            elif command_status != "Ok" and channels.scaled_values[0] > 0.05:
                command_status = "Rot+"
            elif command_status != "Ok" and channels.scaled_values[0] < -0.05:
                command_status = "Rot-"
            elif unready_mtime > mtime - 2.0:
                command_status = "Wait"
            else:
                command_status = "Ok"
                throttle = channels.scaled_values[2]
                rotate = channels.scaled_values[0]
                vels = [throttle * 10 - rotate * 5, throttle * 10 + rotate * 5]
                vels = [0 if abs(v) < 0.1 else v for v in vels]

            if command_status not in ("Wait", "Ok"):
                unready_mtime = mtime

            for mo, vel in zip(mdriver.motors, vels):
                mo.command_vel = vel
                mo.command_fresh = True

            await mdriver.refresh()

        if mtime >= telemetry_mtime:
            telemetry_mtime += 0.1
            send_telemetry(
                command_status=command_status,
                mdriver=mdriver,
                rdriver=rdriver,
            )

        if mtime >= print_mtime:
            print_mtime += 1.0
            logging.info("\nTRASHBOT COMMAND: %s", command_status)
            for mo in mdriver.motors:
                logging.info(f"⚙️ {mo.debug_str()}")


def abbrev(text):
    if "_" in text:
        return "".join(w[:2].title() for w in text.split("_"))
    return text[:3].title()


def send_telemetry(*, command_status, mdriver, rdriver):
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


if __name__ == "__main__":
    main()
