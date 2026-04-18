#!/usr/bin/env python3
"""Drive one trashbot 'eye' display based on commands on stdin.

(This is a subprocess because pygame only drives one display at a time.)"""

import asyncclick as click
import dataclasses
import logging
import ok_logging_setup
import os
import pygame
import re
import sys
import threading
import trashbot.emoji_list


@dataclasses.dataclass
class DisplayContext:
    rf_emoji: dict[int, trashbot.emoji_list.Emoji]
    temp_square: pygame.Surface


LINE_FORMAT = re.compile(r"E(?P<rfcode>\d+)")

STDIN_LINE_EVENT = pygame.event.custom_type()

_log: logging.Logger


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--force-console/--no-force-console", default=True)
@click.option("--fullscreen/--no-fullscreen", default=True)
@click.option("--screen", type=int, default=0)
@click.option("--size", type=int, nargs=2, default=(0, 0))
def main(debug, force_console, fullscreen, screen, size):
    global _log
    ok_logging_setup.install({"OK_LOGGING_LEVEL": "debug" if debug else "info"})
    ok_logging_setup.skip_traceback_for(pygame.error)
    _log = logging.getLogger(f"trashbot.display_eye_worker[{screen}]")

    _log.info("👁️ Opening eye display...")
    if force_console:
        os.environ["SDL_VIDEODRIVER"] = "wayland"
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
    pygame.display.init()
    if force_console and (driver := pygame.display.get_driver()) != "wayland":
        ok_logging_setup.exit(f'Display driver "{driver}" != "wayland"')

    flags = pygame.FULLSCREEN if fullscreen else 0
    pygame.display.set_mode(flags=flags, display=screen)
    pygame.display.set_allow_screensaver(False)
    pygame.display.set_caption(f"Trashbot Eye {screen}")
    pygame.mouse.set_visible(False)

    surf = pygame.display.get_surface()
    (width, height), bpp = surf.get_size(), surf.get_bitsize()
    _log.info(f"🖥️ Opened screen {screen} at {width}x{height} {bpp}bpp")

    min_dim = min(width, height)
    context = DisplayContext(
        rf_emoji={e.rf_code: e for e in trashbot.emoji_list.load(screen=surf)},
        temp_square=pygame.Surface((min_dim, min_dim), flags=pygame.SRCALPHA),
    )

    threading.Thread(target=stdin_reader_thread, daemon=True).start()

    while True:
        ev = pygame.event.wait()
        if ev.type == pygame.QUIT:
            _log.info("❌ QUIT event received, stopping")
            break

        elif ev.type == STDIN_LINE_EVENT:
            if ev.text is None:
                _log.info("❌ EOF from stdin, stopping")
                break

            handle_stdin_line(context, ev.text)


def stdin_reader_thread():
    _log.debug("stdin reader thread starting...")
    for line in sys.stdin:
        _log.debug("stdin: %r", line)
        pygame.event.post(pygame.event.Event(STDIN_LINE_EVENT, text=line))

    _log.debug("stdin reader reporting EOF")
    pygame.event.post(pygame.event.Event(STDIN_LINE_EVENT, text=None))  # EOF


def handle_stdin_line(context: DisplayContext, line: str):
    line = line.strip()
    parsed = LINE_FORMAT.fullmatch(line)
    if not parsed:
        _log.error('Bad stdin line: "%s"', line)
        return

    emo: trashbot.emoji_list.Emoji | None = None
    if rfcode_text := parsed.group("rfcode"):
        if not (emo := context.rf_emoji.get(int(rfcode_text))):
            _log.error("Bad emoji rfcode: %s", rfcode_text)
            return

    if screen := pygame.display.get_surface():
        if emo and emo.image:
            scr_w, scr_h = screen.get_size()
            tsq = context.temp_square
            tsq_w, tsq_h = tsq.get_size()
            blit_pos = ((scr_w - tsq_w) // 2, (scr_h - tsq_h) // 2)
            pygame.transform.scale(emo.image, (tsq_w, tsq_h), dest_surface=tsq)
            screen.fill((0, 0, 0))
            screen.blit(tsq, blit_pos)

        pygame.display.flip()


if __name__ == "__main__":
    main()
