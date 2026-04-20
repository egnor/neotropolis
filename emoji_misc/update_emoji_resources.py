#!/usr/bin/env python3
"""
Updates trashbot/resources/emoji_list.csv (rf_code assignments) and rebuilds
trashbot/resources/emoji_sheet.png (32x32 sprite sheet of included emoji,
in rf_code order).

Reads PNG assets from JoyPixels release (default: ../joypixels-10.0-emoji.zip).
"""

import argparse
import csv
import io
import os
import pathlib
import sys
import zipfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

HERE = pathlib.Path(__file__).parent
CSV_PATH = HERE.parent / "trashbot" / "resources" / "emoji_list.csv"
SHEET_PATH = HERE.parent / "trashbot" / "resources" / "emoji_sheet.png"
DEFAULT_ZIP = HERE.parent.parent / "joypixels-10.0-emoji.zip"

SPRITE_SIZE = 32
SHEET_COLS = 32

CSV_FIELDS = [
    "rf_code",
    "codepoints",
    "name",
    "group",
    "subgroup",
    "order",
    "status",
    "reason",
]

VARIATION_SELECTOR_16 = 0xFE0F
ZWJ = 0x200D


def joypixels_key(codepoints_str: str) -> str:
    """JoyPixels filename stem (strips FE0F and ZWJ, lowercase hex, '-' joined)."""
    cps = [int(c, 16) for c in codepoints_str.split()]
    kept = [c for c in cps if c not in (VARIATION_SELECTOR_16, ZWJ)]
    return "-".join(f"{c:04x}" for c in kept)


def assign_rf_codes(rows: list[dict]) -> None:
    avail = set(range(1, 1024))
    for row in rows:
        if row["status"] == "included" and row["rf_code"]:
            avail.discard(int(row["rf_code"]))
        elif row["status"] != "included":
            row["rf_code"] = ""

    avail_list = sorted(avail, reverse=True)
    for row in rows:
        if row["status"] == "included" and not row["rf_code"]:
            row["rf_code"] = str(avail_list.pop())


def build_sheet(rows: list[dict], zip_path: pathlib.Path) -> pygame.Surface:
    included = sorted(
        (r for r in rows if r["status"] == "included"),
        key=lambda r: int(r["rf_code"]),
    )
    n_rows = (len(included) + SHEET_COLS - 1) // SHEET_COLS
    sheet = pygame.Surface(
        (SHEET_COLS * SPRITE_SIZE, n_rows * SPRITE_SIZE), flags=pygame.SRCALPHA
    )
    sheet.fill((0, 0, 0, 0))

    with zipfile.ZipFile(zip_path, "r") as zf:
        for i, row in enumerate(included):
            name = f"png/unicode/{SPRITE_SIZE}/{joypixels_key(row['codepoints'])}.png"
            try:
                data = zf.read(name)
            except KeyError:
                sys.exit(f"missing in zip: {name} (rf_code={row['rf_code']}, {row['name']})")
            img = pygame.image.load(io.BytesIO(data), name)
            if img.get_size() != (SPRITE_SIZE, SPRITE_SIZE):
                sys.exit(f"{name} is {img.get_size()}, expected {SPRITE_SIZE}²")
            col, r = i % SHEET_COLS, i // SHEET_COLS
            sheet.blit(img, (col * SPRITE_SIZE, r * SPRITE_SIZE))

    return sheet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--joypixels-zip",
        type=pathlib.Path,
        default=DEFAULT_ZIP,
        help=f"path to joypixels release zip (default: {DEFAULT_ZIP})",
    )
    args = ap.parse_args()

    with CSV_PATH.open("r", newline="") as f:
        rows = list(csv.DictReader(f))

    assign_rf_codes(rows)

    pygame.init()
    sheet = build_sheet(rows, args.joypixels_zip)
    pygame.image.save(sheet, str(SHEET_PATH))

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    included = sum(1 for r in rows if r["status"] == "included")
    print(f"wrote {CSV_PATH} ({len(rows)} rows, {included} included)")
    print(f"wrote {SHEET_PATH} ({sheet.get_width()}x{sheet.get_height()})")


if __name__ == "__main__":
    main()
