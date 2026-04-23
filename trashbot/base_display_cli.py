#!/usr/bin/env python3

import asyncclick as click
import json
import ok_logging_setup
import sys

import trashbot.base_display_driver
import trashbot.emoji_list


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--console/--no-console", is_flag=True, default=True)
async def main(debug, console):
    ok_logging_options = {"OK_LOGGING_LEVEL": "debug" if debug else "info"}
    ok_logging_setup.install(ok_logging_options)
    ok_logging_setup.install_asyncio_handler()

    emojis = trashbot.emoji_list.load()
    driver = trashbot.base_display_driver.BaseDisplayDriver(
        emojis=emojis, console=console
    )

    while line := sys.stdin.readline():
        request = json.loads(line)
        if not isinstance(request, dict):
            raise TypeError("Bad request line type: %s", type(request))
        driver.set_display(request)


if __name__ == "__main__":
    main()
