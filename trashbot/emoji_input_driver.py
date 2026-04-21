"""Use a StreamDeck XL as an emoji keyboard."""

import io
import logging
import pygame
import StreamDeck.Devices.StreamDeck

import trashbot.emoji_list

_log = logging.getLogger(__name__)


class EmojiInputDriver:
    def __init__(
        self,
        device: StreamDeck.Devices.StreamDeck.StreamDeck,
        emojis: list[trashbot.emoji_list.Emoji],
    ):
        """Initializes with an streamdeck device and an emoji list"""

        assert device.is_open()
        kif = device.key_image_format()
        kw, kh = kif["size"]

        self.device = device
        self.emojis = emojis
        self.namehint = f"image.{kif['format'].lower()}"
        self.temp_image = pygame.Surface((kw, kh)).convert(emojis[0].image)
        self.temp_bytesio = io.BytesIO()

        _log.info(
            f"🎛️ {device.deck_type()} "
            f"id={device.id()} ser={device.get_serial_number()}"
        )

        _log.info(f"🖼️ Converting {len(emojis)} emoji to {kw}x{kh}")
        self.emoji_xform = {}
        for emoji in emojis:
            emoji_size = emoji.image.get_size()
            rot = kif["rotation"]
            zoom = min(kw / emoji_size[0], kh / emoji_size[1]) * 0.8
            xform = pygame.transform.rotozoom(emoji.image, rot, zoom)
            xform = pygame.transform.flip(xform, *kif["flip"])
            xw, xh = xform.get_size()
            final = pygame.Surface((kw, kh), flags=pygame.SRCALPHA)
            final = final.convert(emoji.image)
            final.blit(xform, ((kw - xw) // 2, (kh - xh) // 2))
            self.emoji_xform[emoji.rf_code] = final

        self.emoji_bytes = {}
        for emoji in emojis:
            # image = self.emoji_xform[emoji.rf_code]
            self.temp_image.fill((128, 128, 128))
            self.temp_image.blit(self.emoji_xform[emoji.rf_code])
            self.emoji_bytes[emoji.rf_code] = self._key_bytes(self.temp_image)

        self.device.set_key_image(0, self.emoji_bytes[100])

    def _key_bytes(self, image) -> bytes:
        assert image.get_size() == self.temp_image.get_size()
        self.temp_bytesio.seek(0)
        self.temp_bytesio.truncate()
        pygame.image.save(image, self.temp_bytesio, self.namehint)
        return self.temp_bytesio.getvalue()
