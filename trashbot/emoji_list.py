"""Loader for the database of supported emoji and images (in pygame)."""

import csv
import dataclasses
import importlib.resources
import logging
import pygame
import trashbot.resources


@dataclasses.dataclass(frozen=True, order=False, slots=True)
class Emoji:
    rf_code: int
    unicode: str
    name: str
    group: str
    subgroup: str
    order: int
    image: pygame.Surface | None


_log = logging.getLogger(__name__)

SPRITE_W, SPRITE_H = 32, 32


def load() -> list[Emoji]:
    resource_files = importlib.resources.files(trashbot.resources)
    emoji_list_ref = resource_files / "emoji_list.csv"
    emoji_sheet_ref = resource_files / "emoji_sheet.png"
    _log.info("🤪 Loading %s + %s", emoji_list_ref.name, emoji_sheet_ref.name)
    with emoji_list_ref.open("r") as emoji_list_file:
        rows = list(csv.DictReader(emoji_list_file))

    with importlib.resources.as_file(emoji_sheet_ref) as emoji_sheet_path:
        sheet = pygame.image.load(str(emoji_sheet_path))
        if pygame.display.get_init():
            sheet = sheet.convert_alpha()

    included = sorted(
        (r for r in rows if r["status"] == "included"),
        key=lambda r: int(r["rf_code"]),
    )

    sheet_cols = sheet.get_size()[0] // SPRITE_W
    loaded_emoji: list[Emoji] = []
    for i, row in enumerate(included):
        col, r = i % sheet_cols, i // sheet_cols
        rect = pygame.Rect(col * SPRITE_W, r * SPRITE_H, SPRITE_W, SPRITE_H)
        text = "".join(chr(int(cp, 16)) for cp in row["codepoints"].split())
        loaded_emoji.append(
            Emoji(
                rf_code=int(row["rf_code"]),
                unicode=text,
                name=row["name"],
                group=row["group"],
                subgroup=row["subgroup"],
                order=int(row["order"]),
                image=sheet.subsurface(rect),
            )
        )

    return loaded_emoji
