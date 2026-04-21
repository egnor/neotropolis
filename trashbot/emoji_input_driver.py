"""Use a StreamDeck XL as an emoji keyboard."""

import dataclasses
import io
import logging
import pygame
import pygame.gfxdraw
import StreamDeck.Devices.StreamDeck

import trashbot.emoji_list

GROUP_LABELS = {
    "Smileys & Emotion": "🙂",
    "People & Body": "🧑",
    "Animals & Nature": "🐱",
    "Food & Drink": "🧀",
    "Travel & Places": "🚀",
    "Activities": "⚽",
    "Objects": "💡",
    "Symbols": "💕",
}

EmojiList = list[trashbot.emoji_list.Emoji]


@dataclasses.dataclass(frozen=True, order=False)
class EmojiGroup:
    label: trashbot.emoji_list.Emoji
    emojis: EmojiList = dataclasses.field(default_factory=list)
    scroll: int = 0


class EmojiInputDriver:
    def __init__(
        self,
        device: StreamDeck.Devices.StreamDeck.StreamDeck,
        emojis: EmojiList,
    ):
        """Initializes with an streamdeck device and an emoji list"""

        assert device.is_open()
        self.device = device
        self.emojis = emojis

        device.reset()
        self._rows, self._cols = device.key_layout()
        self._log = logging.getLogger(f"{__name__}[{device.id()}]")
        self._log.info(f"🎛️ {device.deck_type()}: {device.get_serial_number()}")

        kif = device.key_image_format()
        self._namehint = f"image.{kif['format'].lower()}"
        self._temp_image = pygame.Surface(kif["size"]).convert(emojis[0].image)
        self._temp_bytesio = io.BytesIO()

        str_emoji = {e.unicode: e for e in emojis}
        self._groups = [EmojiGroup(str_emoji[v]) for v in GROUP_LABELS.values()]

        name_index = {v: i for i, v in enumerate(GROUP_LABELS.keys())}
        for emoji in emojis:
            if (gi := name_index.get(emoji.group)) is not None:
                self._groups[gi].emojis.append(emoji)

        self._emoji_images = self._make_emoji_images()
        self._emoji_bytes = self._make_emoji_bytes()

        self._show_group = 0
        self._pick_group_emoji = (-1, -1)

        self._update_header()
        self._update_body()

    def _update_header(self):
        for gi in range(len(self._groups)):
            self._update_header_cell(group_index=gi)

    def _update_header_cell(self, group_index: int):
        is_active = group_index == self._show_group
        self._set_key(
            col=group_index,
            row=0,
            color=(255, 255, 255) if is_active else (128, 128, 128),
            emoji=self._groups[group_index].label,
        )

    def _update_body(self):
        group = self._groups[self._show_group]
        start = group.scroll * (self._cols - 1)
        end = (group.scroll + self._rows - 1) * (self._cols - 1)
        for emoji_index in range(start, end):
            self._update_body_cell(self._show_group, emoji_index)

    def _update_body_cell(self, group_index: int, emoji_index: int):
        if group_index != self._show_group:
            return

        group = self._groups[group_index]
        col = emoji_index % (self._cols - 1)
        row = emoji_index // (self._cols - 1) - group.scroll + 1
        if not 1 <= row < self._rows:
            return

        is_active = (group_index, emoji_index) == self._pick_group_emoji
        color = (192, 192, 192) if is_active else (0, 0, 0)
        emojis = group.emojis
        emoji = emojis[emoji_index] if emoji_index < len(emojis) else None
        self._set_key(col=col, row=row, color=color, emoji=emoji)

    def _set_key(
        self,
        *,
        col: int,
        row: int,
        color: tuple[int, int, int],
        emoji: trashbot.emoji_list.Emoji | None,
    ):
        if not (0 <= col < self._cols and 0 <= row < self._rows):
            return

        pos = col + self._cols * row
        if color == (0, 0, 0) and emoji:
            self.device.set_key_image(pos, self._emoji_bytes[emoji.unicode])
        else:
            self._temp_image.fill(color)
            if emoji:
                self._temp_image.blit(self._emoji_images[emoji.unicode])
            self.device.set_key_image(pos, self._to_bytes(self._temp_image))

    def _make_emoji_images(self) -> dict[str, pygame.Surface]:
        """Populates self._emoji_images and self._emoji_bytes"""

        kif = self.device.key_image_format()
        kw, kh = kif["size"]
        rot = kif["rotation"]

        self._log.info(f"🖼️ Converting emoji to {kw}x{kh}px")
        out: dict[str, pygame.Surface] = {}
        for emoji in self.emojis:
            # Convert emoji to StreamDeck size and orientation
            emoji_size = emoji.image.get_size()
            zoom = min(kw / emoji_size[0], kh / emoji_size[1]) * 0.8
            xform = pygame.transform.rotozoom(emoji.image, rot, zoom)
            xform = pygame.transform.flip(xform, *kif["flip"])
            xw, xh = xform.get_size()
            final = pygame.Surface((kw, kh), flags=pygame.SRCALPHA)
            final = final.convert(xform)
            final.blit(xform, ((kw - xw) // 2, (kh - xh) // 2))
            out[emoji.unicode] = final

        return out

    def _make_emoji_bytes(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for emoji in self.emojis:
            # Save emoji in StreamDeck format for quick output
            self._temp_image.fill((0, 0, 0))
            self._temp_image.blit(self._emoji_images[emoji.unicode])
            out[emoji.unicode] = self._to_bytes(self._temp_image)

        return out

    def _make_scroll_images(self):
        kif = self.device.key_image_format()
        kw, kh = kif["size"]

        for dir in ("U", "D"):
            for ena in ("Y", "N"):
                pass
        pass

    def _to_bytes(self, image) -> bytes:
        """Returns StreamDeck-formatted bytes for an image"""

        assert image.get_size() == self._temp_image.get_size()
        self._temp_bytesio.seek(0)
        self._temp_bytesio.truncate()
        pygame.image.save(image, self._temp_bytesio, self._namehint)
        return self._temp_bytesio.getvalue()
