"""Driver for a StreamDeck XL as an emoji keyboard"""

import dataclasses
import importlib.resources
import io
import logging
import os
import pygame
import pygame.gfxdraw
import StreamDeck.Devices.StreamDeck

import trashbot.emoji_list
import trashbot.resources

GROUP_LABELS = {
    "Smileys & Emotion": "😍",
    "People & Body": "🧑",
    "Animals & Nature": "🐱",
    "Food & Drink": "🧀",
    "Travel & Places": "🚀",
    "Activities": "⚽",
    "Objects": "💡",
    "Symbols": "⁉️",
}

EmojiList = list[trashbot.emoji_list.Emoji]


@dataclasses.dataclass(order=False)
class EmojiGroup:
    label: trashbot.emoji_list.Emoji
    emojis: EmojiList = dataclasses.field(default_factory=list)
    start_emoji: int = 0


class EmojiInputDriver:
    def __init__(
        self,
        dev: StreamDeck.Devices.StreamDeck.StreamDeck,
        emojis: EmojiList,
    ):
        """Initializes with an streamdeck device and an emoji list"""

        self.dev = dev
        self.emojis = emojis
        if not dev.is_open():
            dev.open()

        self._rows, self._cols = dev.key_layout()
        self._log = logging.getLogger(f"{__name__}[{dev.id()}]")
        self._log.info(f"🎛️ {dev.deck_type()}: {dev.get_serial_number()}")

        kif = dev.key_image_format()
        self._namehint = f"image.{kif['format'].lower()}"
        self._temp_image = pygame.Surface(kif["size"]).convert(emojis[0].image)
        self._temp_bytesio = io.BytesIO()

        str_emoji = {e.unicode: e for e in emojis}
        self._groups = [EmojiGroup(str_emoji[v]) for v in GROUP_LABELS.values()]

        name_index = {v: i for i, v in enumerate(GROUP_LABELS.keys())}
        for emoji in emojis:
            if (gi := name_index.get(emoji.group)) is not None:
                self._groups[gi].emojis.append(emoji)

        self._emoji_images: dict[str, pygame.Surface] = {}
        self._emoji_bytes: dict[str, bytes] = {}
        for em in self.emojis:
            self._emoji_images[em.unicode] = self._xform_image(em.image, 0.8)
            self._temp_image.fill((0, 0, 0))
            self._temp_image.blit(self._emoji_images[em.unicode])
            self._emoji_bytes[em.unicode] = self._to_bytes(self._temp_image)

        self._icon_bytes: dict[tuple[str, int], bytes] = {}
        for icon in ("U", "D"):
            for active in (-1, 0, 1):
                self._icon_bytes[icon, active] = self._make_icon(icon, active)

        pygame.font.init()
        resource_files = importlib.resources.files(trashbot.resources)
        font_ref = resource_files / "NorwesterPro-Square.otf"
        with importlib.resources.as_file(font_ref) as font_path:
            self._log.debug("loading %s", font_path.name)
            pager_font = pygame.font.Font(font_path, 128)

        self._pager_bytes: dict[tuple[int, int, int], bytes] = {}
        psize = (self._cols - 1) * (self._rows - 1)
        pcounts = set((len(g.emojis) - 1) // psize + 1 for g in self._groups)
        for pcount in pcounts:
            for pshow in range(1, pcount + 1):
                for active in (0, 1):
                    pager = self._make_pager(pshow, pcount, active, pager_font)
                    self._pager_bytes[pshow, pcount, active] = pager

        self._key_pressed = -1
        self._show_group = 0
        self._pick_group_emoji = (0, 0)

        dev.reset()
        dev.set_brightness(100)
        dev.set_poll_frequency(50)
        self._update_header()
        self._update_body()
        self._update_scroll()
        dev.set_key_callback_async(self._key_callback)  # type: ignore[arg-type]

    def picked_emoji(self) -> trashbot.emoji_list.Emoji:
        if not self.dev.is_open():
            self._log.critical("StreamDeck device lost")
            os._exit(1)

        group_index, emoji_index = self._pick_group_emoji
        group = self._groups[group_index]
        return group.emojis[emoji_index]

    async def _key_callback(self, _dev, key: int, down: bool) -> None:
        # https://github.com/abcminiuser/python-elgato-streamdeck/issues/171
        try:
            await self._handle_key(key, down)
        except BaseException:
            self._log.exception("Uncaught exception in key callback")
            os._exit(1)

    async def _handle_key(self, key: int, down: bool) -> None:
        if down == (key == self._key_pressed):
            return  # dup press or untracked rolloff

        col, row = key % self._cols, key // self._cols
        old_key, self._key_pressed = self._key_pressed, key if down else -1
        if old_key >= 0:
            old_col, old_row = old_key % self._cols, old_key // self._cols
            self._log.debug(f"OFF key[{old_key}] ({old_col}, {old_row})")
            if old_col == self._cols - 1 and 1 <= old_row < self._rows:
                self._log.debug("  OFF scroll")
                self._update_scroll()

        if not down:
            return  # release is handled above, press is handled below

        self._log.debug(f"ON  key[{key}] ({col}, {row})")

        if row == 0 and 0 <= col < len(self._groups):
            if col != self._show_group:
                old_group, self._show_group = self._show_group, col
                self._groups[self._show_group].start_emoji = 0
                self._log.debug(f"  group {old_group} -> {self._show_group}")
                self._update_header_cell(old_group)
                self._update_header_cell(self._show_group)
                self._update_body()
                self._update_scroll()

        group = self._groups[self._show_group]
        psize = (self._cols - 1) * (self._rows - 1)
        if (col, row) == (self._cols - 1, 1):
            if group.start_emoji > 0:
                group.start_emoji = max(0, group.start_emoji - psize)
                self._log.debug(f"  scroll UP: {group.start_emoji}")
                self._update_scroll()
                self._update_body()
            else:
                self._log.debug("  scroll UP BONK")  # do not flash button

        if (col, row) == (self._cols - 1, 2):
            self._log.debug("  scroll RESET")
            if group.start_emoji != 0:
                group.start_emoji = 0
                self._update_body()
            self._update_scroll()  # always flash the button

        if (col, row) == (self._cols - 1, self._rows - 1):
            if group.start_emoji + psize < len(group.emojis):
                group.start_emoji += psize
                self._log.debug(f"  scroll DOWN: {group.start_emoji}")
                self._update_scroll()
                self._update_body()
            else:
                self._log.debug("  scroll DOWN BONK")  # do not flash button

        if col < self._cols - 1 and row > 0:
            emoji_index = group.start_emoji + (row - 1) * (self._cols - 1) + col
            if emoji_index < len(group.emojis):
                old_pick = self._pick_group_emoji
                self._pick_group_emoji = (self._show_group, emoji_index)
                self._log.debug(f"  pick {group.emojis[emoji_index].unicode}")
                self._update_body_cell(*old_pick)
                self._update_body_cell(*self._pick_group_emoji)
                self._log.info(f"{group.emojis[emoji_index].unicode} picked")

    def _update_header(self):
        for gi in range(len(self._groups)):
            self._update_header_cell(group_index=gi)

    def _update_header_cell(self, group_index: int):
        is_active = group_index == self._show_group
        self._set_key_emoji(
            col=group_index,
            row=0,
            color=(255, 255, 255) if is_active else (96, 96, 96),
            emoji=self._groups[group_index].label,
        )

    def _update_body(self):
        group = self._groups[self._show_group]
        end_emoji = group.start_emoji + (self._rows - 1) * (self._cols - 1)
        for emoji_index in range(group.start_emoji, end_emoji):
            self._update_body_cell(self._show_group, emoji_index)

    def _update_body_cell(self, group_index: int, emoji_index: int):
        if group_index != self._show_group:
            return

        group = self._groups[group_index]
        col = (emoji_index - group.start_emoji) % (self._cols - 1)
        row = (emoji_index - group.start_emoji) // (self._cols - 1) + 1
        if not 1 <= row < self._rows:
            return

        is_active = (group_index, emoji_index) == self._pick_group_emoji
        color = (192, 192, 192) if is_active else (0, 0, 0)
        emojis = group.emojis
        emoji = emojis[emoji_index] if emoji_index < len(emojis) else None
        self._set_key_emoji(col=col, row=row, color=color, emoji=emoji)

    def _update_scroll(self):
        group = self._groups[self._show_group]
        psize = (self._cols - 1) * (self._rows - 1)
        pshow = group.start_emoji // psize + 1
        pcount = (len(group.emojis) - 1) // psize + 1
        k_pos = self._key_pressed
        u_pos, p_pos, d_pos = (r * self._cols - 1 for r in (2, 3, self._rows))
        u_act = 1 if k_pos == u_pos else -1 if pshow <= 1 else 0
        p_act = 1 if k_pos == p_pos else 0
        d_act = 1 if k_pos == d_pos else -1 if pshow >= pcount else 0
        self.dev.set_key_image(u_pos, self._icon_bytes["U", u_act])
        self.dev.set_key_image(p_pos, self._pager_bytes[pshow, pcount, p_act])
        self.dev.set_key_image(d_pos, self._icon_bytes["D", d_act])

    def _set_key_emoji(
        self,
        *,
        col: int,
        row: int,
        color: tuple[int, int, int],
        emoji: trashbot.emoji_list.Emoji | None,
    ):
        assert 0 <= col < self._cols and 0 <= row < self._rows
        pos = col + self._cols * row
        if color == (0, 0, 0) and emoji:
            self.dev.set_key_image(pos, self._emoji_bytes[emoji.unicode])
        else:
            self._temp_image.fill(color)
            if emoji:
                self._temp_image.blit(self._emoji_images[emoji.unicode])
            self.dev.set_key_image(pos, self._to_bytes(self._temp_image))

    def _make_icon(self, icon: str, active: int):
        w, h = self.dev.key_image_format()["size"]
        im = pygame.Surface((w, h))
        bg_color = (192, 192, 192) if active > 0 else (96, 96, 96)
        fg_color = (128, 128, 128) if active < 0 else (255, 255, 255)
        if icon == "U":
            poly = [
                (w // 2, h // 4),
                (w * 3 // 4, h * 3 // 4),
                (w // 4, h * 3 // 4),
            ]
        elif icon == "D":
            poly = [
                (w // 4, h // 4),
                (w * 3 // 4, h // 4),
                (w // 2, h * 3 // 4),
            ]
        else:
            raise ValueError(f"Bad scroll icon: {icon}")

        im.fill(bg_color)
        pygame.gfxdraw.filled_polygon(im, poly, fg_color)
        pygame.gfxdraw.aapolygon(im, poly, fg_color)
        return self._to_bytes(self._xform_image(im, scale=1.0))

    def _make_pager(
        self, page: int, count: int, active: int, font: pygame.font.Font
    ):
        w, h = self.dev.key_image_format()["size"]
        im = pygame.Surface((w, h))
        im.fill((192, 192, 192) if active else (96, 96, 96))

        text_im = font.render(f"{page}/{count}", True, (255, 255, 255))
        text_im = self._xform_image(text_im, scale=0.8)
        tw, th = text_im.get_size()
        im.blit(text_im, ((w - tw) // 2, (h - th) // 2))
        return self._to_bytes(im)

    def _xform_image(self, im: pygame.Surface, scale: float) -> pygame.Surface:
        """Converts an image to StreamDeck size and orientation"""

        kif = self.dev.key_image_format()
        kw, kh = kif["size"]

        zoom = min(kw, kh) / max(im.get_size()) * scale
        xform = pygame.transform.rotozoom(im, kif["rotation"], zoom)
        xform = pygame.transform.flip(xform, *kif["flip"])
        xw, xh = xform.get_size()
        out = pygame.Surface((kw, kh), flags=pygame.SRCALPHA).convert(xform)
        out.blit(xform, ((kw - xw) // 2, (kh - xh) // 2))
        return out

    def _to_bytes(self, image) -> bytes:
        """Returns StreamDeck-formatted bytes for an image"""

        assert image.get_size() == self._temp_image.get_size()
        self._temp_bytesio.seek(0)
        self._temp_bytesio.truncate()
        pygame.image.save(image, self._temp_bytesio, self._namehint)
        return self._temp_bytesio.getvalue()
