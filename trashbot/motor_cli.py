#!/usr/bin/env python3

import asyncclick as click
import asyncio
import ok_logging_setup
import time

import trashbot.motor_driver


@click.group()
@click.option("--debug", is_flag=True)
def main(debug):
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})
    ok_logging_setup.skip_traceback_for(trashbot.motor_driver.MotorError)


@main.command()
async def check_command():
    driver = await trashbot.motor_driver.connect()
    await driver.refresh()
    for mot in driver.motors:
        print(mot.debug_str())


@main.command()
@click.argument("vel", default=0.0)
@click.argument("vel2", type=float, default=None)
@click.option("--secs", default=2.0)
async def go_command(vel, vel2, secs):
    driver = await trashbot.motor_driver.connect()
    stop_mt = time.monotonic() + secs
    print_mt = time.monotonic()
    driver.motors[0].command_vel = vel
    driver.motors[1].command_vel = vel2 if vel2 is not None else vel
    while True:
        if (mt := time.monotonic()) >= stop_mt:
            break

        driver.motors[0].command_fresh = driver.motors[1].command_fresh = True
        await driver.refresh()

        if (mt >= print_mt):
            print_mt += 0.25
            print(f"MOTOR GO {stop_mt - mt:.2f}s REMAINING")
            for mot in driver.motors:
                print(f"  {mot.debug_str()}")

        await asyncio.sleep(0.05)

@main.command()
async def fix_configs_command():
    driver = await trashbot.motor_driver.connect(allow_config_errors=True)
    await driver.fix_configs()


if __name__ == "__main__":
    main()
