"""Driver for Trashbot base station display interface"""

import logging
import os
import pygame

import trashbot.emoji_list

_log = logging.getLogger(__name__)


class BaseDisplayDriver:
    def __init__(self, emojis=list[trashbot.emoji_list.Emoji], console=True):
        logging.info("🏠️ Opening base station display...")
        os.environ["SDL_NO_SIGNAL_HANDLERS"] = "1"
        if console:
            os.environ["SDL_VIDEODRIVER"] = "wayland"
            os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        pygame.display.init()
        if (driver := pygame.display.get_driver()) in ("offscreen", "dummy"):
            raise pygame.error(f'Display driver is "{driver}"')

        flags = pygame.FULLSCREEN if console else 0
        pygame.display.set_mode((1920, 1080), flags=flags)
        pygame.display.set_allow_screensaver(False)
        pygame.display.set_caption("Trashbot Base Station")
        pygame.mouse.set_visible(False)

        surface = pygame.display.get_surface()
        (width, height), bpp = surface.get_size(), surface.get_bitsize()
        logging.info(f"🖥️ Opened display at {width}x{height} {bpp}bpp")

    def set_display(self, request: dict):
        pass
