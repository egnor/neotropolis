#!/usr/bin/env python3

import asyncclick as click
import json
import logging
import ok_logging_setup
import ok_serial
import os
import platform
import select
import time

import trashbot.radio_driver


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--bot", is_flag=True)
@click.option("--base", is_flag=True)
@click.option("--port")
@click.option("--baud", type=int)
def main(debug, bot, base, port=None, baud=0):
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})
    ok_logging_setup.skip_traceback_for(ok_serial.SerialException)

    if bot and base:
        raise click.ClickException("Set only one of --bot or --base")
    if not (bot or base):
        node = platform.node().split(".")[0]
        bot, base = (node == "trashbot"), (node == "trashbase")
    if bot:
        port = port or trashbot.radio_driver.BOT_PORT
        baud = baud or trashbot.radio_driver.BOT_BAUD
    if base:
        port = port or trashbot.radio_driver.BASE_PORT
        baud = baud or trashbot.radio_driver.BASE_BAUD
    if not (port and baud):
        raise click.ClickException("Set --bot OR --base OR --port and --baud")

    logging.info(f"📻 Connecting to {port} {baud}bps...")
    serial = ok_serial.SerialConnection(match=port, baud=baud)
    radio = trashbot.radio_driver.RadioDriver(serial)

    stdin_buffer = bytearray()
    while True:
        while frame := radio.poll_frame():
            print(json.dumps(to_pod(frame)))

        rfd, _, _ = select.select([0], [], [], 0)
        if 0 in rfd:
            if not (input := os.read(0, 256)):
                logging.warning("EOF reached, stopping")
                break

            stdin_buffer.extend(input)
            while (value := consume_json_line(stdin_buffer)) is not None:
                logging.info("Sending: %s", value)
                try:
                    radio.send_frame(**value)
                except Exception as exc:
                    logging.error("Sending frame: %s", exc)

        time.sleep(0.01)


def to_pod(o):
    if isinstance(o, dict):
        return {k: to_pod(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [to_pod(v) for v in o]
    if isinstance(o, (bytes, bytearray)):
        return o.hex()
    return o


def consume_json_line(buffer):
    while (nl_index := buffer.find(b"\n")) >= 0:
        line = bytes(buffer[:nl_index])
        del buffer[: nl_index + 1]
        try:
            return json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logging.error("Bad input: %s (%s)", line, exc)
    return None


if __name__ == "__main__":
    main()
