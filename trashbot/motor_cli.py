#!/usr/bin/env python3

import asyncclick as click
import ok_logging_setup

import trashbot.motor_driver


@click.group()
@click.option("--debug", is_flag=True)
def main(debug):
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})


@main.command()
async def check_command():
    await trashbot.motor_driver.connect()  # just connect


@main.command()
async def fix_config_command():
    driver = await trashbot.motor_driver.connect(allow_config_errors=True)
    await driver.fix_config()


if __name__ == "__main__":
    main()
