#!/usr/bin/env python3
"""Build the curation TSV from emoji-test.txt + JoyPixels asset directory.

Reads:
  emoji-test.txt          (Unicode UTS #51 v16.0 test data)
  ../../joypixels-10.0-emoji/png/unicode/128/*.png

Writes:
  emoji_list.tsv      (one row per fully-qualified emoji)

Columns:
  rf_code                 — assigned later, blank for now
  codepoints              — original UTS #51 sequence (e.g. "1F600", "2764 FE0F")
  name                    — UTS #51 name
  group, subgroup         — UTS #51 taxonomy
  order                   — index within emoji-test.txt (canonical sort key)
  joypixels_file          — basename of JoyPixels PNG, or empty if not present
  status                  — "candidate", "excluded", or "included"
  reason                  — short tag explaining auto-exclusion (or blank)
"""

import csv
import pathlib

HERE = pathlib.Path(__file__).parent
TEST_FILE = HERE / "emoji-test.txt"
JOYPIXELS_DIR = (
    HERE.parent.parent / "joypixels-10.0-emoji" / "png" / "unicode" / "128"
)
OUT_CSV = HERE / "emoji_list.csv"

SKIN_TONES = {0x1F3FB, 0x1F3FC, 0x1F3FD, 0x1F3FE, 0x1F3FF}
HAIR_COMPONENTS = {0x1F9B0, 0x1F9B1, 0x1F9B2, 0x1F9B3}
REGIONAL_INDICATORS = set(range(0x1F1E6, 0x1F1FF + 1))
SUBDIVISION_TAGS = set(range(0xE0020, 0xE007F + 1))
GENDER_SIGNS = {0x2640, 0x2642}
ZWJ = 0x200D
VARIATION_SELECTOR_16 = 0xFE0F


def joypixels_key(codepoints: list[int]) -> str:
    """JoyPixels filename stem: lowercase hex joined by '-', stripping FE0F and ZWJ."""
    kept = [c for c in codepoints if c not in (VARIATION_SELECTOR_16, ZWJ)]
    return "-".join(f"{c:04x}" for c in kept)


def classify(codepoints: list[int], group: str) -> tuple[str, str]:
    """Return (status, reason) for auto-exclusion logic."""
    cp_set = set(codepoints)
    if group == "Component":
        return "excluded", "component"
    if cp_set & REGIONAL_INDICATORS:
        return "excluded", "flag"
    if cp_set & SUBDIVISION_TAGS:
        return "excluded", "flag_subdivision"
    if cp_set & SKIN_TONES:
        return "excluded", "skin_tone_variant"
    if cp_set & HAIR_COMPONENTS:
        return "excluded", "hair_variant"
    if ZWJ in cp_set:
        return "excluded", "zwj_sequence"
    if cp_set & GENDER_SIGNS:
        return "excluded", "gender_variant"
    return "candidate", ""


def parse() -> list[dict]:
    rows: list[dict] = []
    group = subgroup = ""
    order = 0
    for raw in TEST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("# group:"):
            group = line.split(":", 1)[1].strip()
            continue
        if line.startswith("# subgroup:"):
            subgroup = line.split(":", 1)[1].strip()
            continue
        if not line or line.startswith("#"):
            continue
        # "1F600 ; fully-qualified # 😀 E1.0 grinning face"
        data, _, comment = raw.partition("#")
        cps_str, _, status = data.partition(";")
        if status.strip() != "fully-qualified":
            continue
        codepoints = [int(c, 16) for c in cps_str.split()]
        # comment is " 😀 E1.0 grinning face" — strip glyph + version, keep name
        parts = comment.strip().split(None, 2)
        name = parts[2] if len(parts) >= 3 else ""
        rows.append(
            {
                "codepoints": " ".join(f"{c:04X}" for c in codepoints),
                "name": name,
                "group": group,
                "subgroup": subgroup,
                "order": order,
                "_codepoints_int": codepoints,
            }
        )
        order += 1
    return rows


def main() -> None:
    joypixels_files = {p.stem for p in JOYPIXELS_DIR.glob("*.png")}
    rows = parse()

    candidates = excluded = missing = 0
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as out_file:
        fields = [
            "rf_code",
            "codepoints",
            "name",
            "group",
            "subgroup",
            "order",
            "joypixels_file",
            "status",
            "reason",
        ]

        out_writer = csv.DictWriter(out_file, fieldnames=fields)

        for row in rows:
            codepoints = row.pop("_codepoints_int")
            key = joypixels_key(codepoints)
            joy_file = f"{key}.png" if key in joypixels_files else ""
            status, reason = classify(codepoints, row["group"])
            if not joy_file and status == "candidate":
                status, reason = "excluded", "no_joypixels"
                missing += 1
            if status == "candidate":
                candidates += 1
            else:
                excluded += 1
            row["rf_code"] = ""
            row["joypixels_file"] = joy_file
            row["status"] = status
            row["reason"] = reason
            out_writer.writerow(row)

    print(f"wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"  candidates: {candidates}")
    print(f"  excluded:   {excluded}  (of which no_joypixels: {missing})")


if __name__ == "__main__":
    main()
