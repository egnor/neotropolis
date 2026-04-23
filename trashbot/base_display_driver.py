"""Driver for Trashbot base station display interface"""

import importlib.resources
import logging
import os
import pygame

import trashbot.emoji_list
import trashbot.resources

_log = logging.getLogger(__name__)


class BaseDisplayDriver:
    def __init__(self, emojis=list[trashbot.emoji_list.Emoji], console=True):
        _log.info("🏠️ Opening base station display...")
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
        _log.info(f"🖥️ Opened display at {width}x{height} {bpp}bpp")

        image_filename = "base_display.png"
        resource_files = importlib.resources.files(trashbot.resources)
        with (resource_files / image_filename).open("rb") as f:
            _log.debug("loading %s ...", image_filename)
            self._base_image = pygame.image.load(f, namehint=image_filename)

        self._request = {"init": False}

    def run_display(self, req: dict):
        """Runs the pygame event loop and updates the display if needed"""

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                logging.info("❌ QUIT event received, stopping")
                raise SystemExit()

        if req == self._request:
            return

        rf_codes = [int(v) for v in list(req.pop("rf_codes", [0, 0]))]
        vars = {str(k): str(v) for k, v in dict(req.pop("vars", {})).items()}
        if req:
            raise ValueError(f"Leftover request fields: {req!r}")

        screen = pygame.display.get_surface()
        screen.fill((0, 0, 0))

        (w, h), (bw, bh) = screen.get_size(), self._base_image.get_size()
        screen.blit(self._base_image, ((w - bw) // 2, (h - bh) // 2))

        pygame.display.flip()
        self._request = {**req}
