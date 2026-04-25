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

        resource_files = importlib.resources.files(trashbot.resources)
        image_ref = resource_files / "base_display.png"
        with image_ref.open("rb") as f:
            _log.debug("loading %s", image_ref.name)
            self._base_image = pygame.image.load(f, namehint=image_ref.name)

        pygame.font.init()
        font_ref = resource_files / "NorwesterPro-Square.otf"
        with importlib.resources.as_file(font_ref) as font_path:
            logging.debug("loading %s", font_path.name)
            self._vars_font = pygame.font.Font(font_path, 55)

        self._rf_emojis = {e.rf_code: e for e in emojis}
        self._request = {"init": False}

    def run_display(self, req: dict):
        """Runs the pygame event loop and updates the display if needed"""

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                logging.info("❌ QUIT event received, stopping")
                raise SystemExit()
            elif ev.type == pygame.KEYDOWN and (ev.mod & pygame.KMOD_CTRL):
                if ev.key == pygame.K_q:
                    logging.info("🚪 Ctrl-Q pressed, exiting to desktop")
                    raise SystemExit(42)
                elif ev.key == pygame.K_r:
                    logging.info("🔄 Ctrl-R pressed, restarting")
                    raise SystemExit(1)

        if req == self._request:
            return

        rf_codes = [int(v) for v in list(req.pop("rf_codes", [0, 0]))]
        vars = {str(k): str(v) for k, v in dict(req.pop("vars", {})).items()}
        if req:
            raise ValueError(f"Leftover request fields: {req!r}")

        # black background
        screen = pygame.display.get_surface()
        assert screen is not None
        screen.fill((0, 0, 0))

        # emoji layer
        emos = [self._rf_emojis.get(rf) for rf in rf_codes] + [None, None]
        if emo_a := emos[1]:  # order is reversed for front view
            emo_xf = pygame.transform.rotozoom(emo_a.image, 10, 5)
            ew, eh = emo_xf.get_size()
            screen.blit(emo_xf, (1006 - ew // 2, 434 - eh // 2))
        if emo_b := emos[0]:
            emo_xf = pygame.transform.rotozoom(emo_b.image, -10, 5)
            ew, eh = emo_xf.get_size()
            screen.blit(emo_xf, (1313 - ew // 2, 434 - eh // 2))

        # static image overlay
        (w, h), (bw, bh) = screen.get_size(), self._base_image.get_size()
        screen.blit(self._base_image, ((w - bw) // 2, (h - bh) // 2))

        # telemetry variables
        for i, (name, val) in enumerate(vars.items()):
            name_im = self._vars_font.render(name, True, (192, 192, 192))
            if val.startswith("~"):
                val_im = self._vars_font.render(val[1:], True, (128, 128, 128))
            else:
                val_im = self._vars_font.render(val, True, (255, 204, 0))
            screen.blit(name_im, (1550, 350 + i * 60))
            screen.blit(val_im, (1725, 350 + i * 60))

        pygame.display.flip()
        self._request = {**req}
