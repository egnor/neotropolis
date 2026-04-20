#!/usr/bin/env python3
"""Drive one trashbot 'eye' display based on commands on stdin.

(This is a subprocess because pygame only drives one display at a time.)"""

import asyncclick as click
import dataclasses
import importlib
import json
import logging
import ok_logging_setup
import os
import pygame
import sys
import threading
import trashbot.emoji_list
import trashbot.resources


@dataclasses.dataclass
class DisplayContext:
    caption_font: pygame.font.Font
    request_line: str
    rfcode_emoji: dict[int, trashbot.emoji_list.Emoji]
    temp_square: pygame.Surface


STDIN_LINE_EVENT = pygame.event.custom_type()

REDRAW_EVENT = pygame.event.custom_type()


@click.command()
@click.option("--debug", is_flag=True)
@click.option("--force-console/--no-force-console", default=True)
@click.option("--fullscreen/--no-fullscreen", default=True)
@click.option("--screen", type=int, default=0)
@click.option("--size", type=int, nargs=2, default=(0, 0))
def main(debug, force_console, fullscreen, screen, size):
    logging_options = {
        "OK_LOGGING_LEVEL": "debug" if debug else "info",
        "OK_LOGGING_PREFIX": f"eye{screen}> ",
    }
    ok_logging_setup.install(logging_options)
    ok_logging_setup.skip_traceback_for(pygame.error)

    logging.info("👁️ Opening eye display...")
    os.environ["SDL_NO_SIGNAL_HANDLERS"] = "1"
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

    surface = pygame.display.get_surface()
    (width, height), bpp = surface.get_size(), surface.get_bitsize()
    logging.info(f"🖥️ Opened screen {screen} at {width}x{height} {bpp}bpp")

    resource_files = importlib.resources.files(trashbot.resources)
    font_ref = resource_files / "NorwesterPro-Square.otf"
    pygame.font.init()
    with importlib.resources.as_file(font_ref) as font_path:
        logging.info("🔠 Loading %s", font_path.name)
        caption_font = pygame.font.Font(font_path, 70)

    rfcode_emoji = {e.rf_code: e for e in trashbot.emoji_list.load()}

    min_dim = min(width, height)
    temp_square = pygame.Surface((min_dim, min_dim), flags=pygame.SRCALPHA)

    context = DisplayContext(
        caption_font=caption_font,
        request_line="",
        rfcode_emoji=rfcode_emoji,
        temp_square=temp_square,
    )

    threading.Thread(target=stdin_reader_thread, daemon=True).start()
    logging.debug("sending ready message")
    sys.stdout.write('{"ready":true}\n')
    redraw_pending = False
    while True:
        ev = pygame.event.wait()
        if ev.type == pygame.QUIT:
            logging.info("❌ QUIT event received, stopping")
            break

        elif ev.type == STDIN_LINE_EVENT:
            if ev.text is None:
                logging.info("❌ EOF from stdin, stopping")
                break
            elif ev.text != context.request_line:  # de-dup and debounce redraw
                context.request_line = ev.text
                if not redraw_pending:
                    pygame.time.set_timer(REDRAW_EVENT, 20, loops=1)
                    redraw_pending = True

        elif ev.type == REDRAW_EVENT:
            redraw_display(context)
            redraw_pending = False


def stdin_reader_thread():
    logging.debug("stdin reader thread starting...")
    for line in sys.stdin:
        logging.debug("stdin: %r", line)
        pygame.event.post(pygame.event.Event(STDIN_LINE_EVENT, text=line))

    logging.debug("stdin reader reporting EOF")
    pygame.event.post(pygame.event.Event(STDIN_LINE_EVENT, text=None))  # EOF


def redraw_display(context: DisplayContext):
    request = json.loads(context.request_line)
    if not isinstance(request, dict):
        raise TypeError("Bad request line type: %s", type(request))

    if not (screen := pygame.display.get_surface()):
        raise ValueError("No pygame display surface")

    screen.fill((0, 0, 0))
    scr_w, scr_h = screen.get_size()

    rf_code = int(request.pop("rf_code", 0)) or None
    emoji = rf_code and context.rfcode_emoji[rf_code]
    if emoji and emoji.image:
        tsq = context.temp_square
        tsq_w, tsq_h = tsq.get_size()
        tsq_pos = ((scr_w - tsq_w) // 2, (scr_h - tsq_h) // 2)
        pygame.transform.scale(emoji.image, (tsq_w, tsq_h), dest_surface=tsq)
        screen.blit(tsq, tsq_pos)

    caption_text = request.pop("caption", "")
    if caption_text:
        cap = context.caption_font.render(caption_text, True, (255, 255, 255))
        cap_w, cap_h = cap.get_size()
        cap_x, cap_y = (scr_w - cap_w) // 2, scr_h - cap_h
        cap_rect = pygame.Rect(0, cap_y, scr_w, cap_h)
        screen.fill((64, 64, 64), cap_rect, pygame.BLEND_MULT)
        screen.blit(cap, (cap_x, cap_y))

    pygame.display.flip()

    if request:
        raise ValueError("Leftover request fields: %s", request)


if __name__ == "__main__":
    main()
