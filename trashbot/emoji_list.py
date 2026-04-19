"""Loader for the database of supported emoji and images (in pygame)."""

import csv
import dataclasses
import importlib.resources
import logging
import pygame
import pyzipper
import trashbot


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


def load(screen: pygame.Surface | None = None) -> list[Emoji]:
    _log.info("🤪 Loading emoji...")
    trashbot_files = importlib.resources.files(trashbot)
    emoji_list_ref = trashbot_files / "emoji_list.csv"
    with emoji_list_ref.open("r") as emoji_list_file:
        emoji_list_rows = list(csv.DictReader(emoji_list_file))

    joypixels_ref = trashbot_files / "media/joypixels-png-unicode-32.zip"
    with joypixels_ref.open("rb") as joypixels_file:
        joypixels_zip = pyzipper.AESZipFile(joypixels_file)
        joypixels_zip.setpassword(b"joypixels")

        debug_text = []
        loaded_emoji: list[Emoji] = []
        for row in emoji_list_rows:
            if row["status"] != "included":
                continue

            if image_name := row["joypixels_file"]:
                with joypixels_zip.open(image_name) as image_file:
                    surface = pygame.image.load(image_file, namehint=image_name)
                if screen:
                    surface = surface.convert_alpha(screen)
            else:
                surface = None

            text = "".join(chr(int(cp, 16)) for cp in row["codepoints"].split())
            emoji = Emoji(
                rf_code=int(row["rf_code"]),
                unicode=text,
                name=row["name"],
                group=row["group"],
                subgroup=row["subgroup"],
                order=int(row["order"]),
                image=surface,
            )
            loaded_emoji.append(emoji)
            debug_text.append(text)
            if len(debug_text) >= 25:
                _log.debug("%s ...", "".join(debug_text))
                debug_text = []

        if debug_text:
            _log.debug("".join(debug_text))
        _log.info("😋 Done loading emoji")

    return loaded_emoji
