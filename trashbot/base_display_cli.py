#!/usr/bin/env python3

import asyncclick as click
import json
import logging
import ok_logging_setup
import pygame
import queue
import sys
import threading
import time

import trashbot.base_display_driver
import trashbot.emoji_list


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--console/--no-console", is_flag=True, default=True)
async def main(debug, console):
    ok_logging_options = {"OK_LOGGING_LEVEL": "debug" if debug else "info"}
    ok_logging_setup.install(ok_logging_options)
    ok_logging_setup.install_asyncio_handler()
    ok_logging_setup.skip_traceback_for(pygame.error)
    ok_logging_setup.skip_traceback_for(json.JSONDecodeError)

    emojis = trashbot.emoji_list.load()
    driver = trashbot.base_display_driver.BaseDisplayDriver(
        emojis=emojis, console=console
    )

    request = {}
    buffer = queue.SimpleQueue()
    threading.Thread(target=stdin_thread, args=(buffer,), daemon=True).start()
    while True:
        time.sleep(0.01)
        if not buffer.empty():
            if not (line := buffer.get()):
                logging.info("❌ EOF from stdin, stopping")
                break
            if not isinstance(request := json.loads(line), dict):
                raise ValueError(f"Bad request type: {type(request)}")

        driver.run_display(request)


def stdin_thread(buffer: queue.Queue):
    logging.debug("starting stdin thread")
    for line in sys.stdin:
        logging.debug("stdin: %r", line)
        buffer.put(line)

    logging.debug("stdin EOF")
    buffer.put(None)


if __name__ == "__main__":
    main()
