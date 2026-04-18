#!/usr/bin/env python3
"""Updates trashbot/emoji_list.csv to assign rf_code values."""

import csv
import importlib.resources
import trashbot

def main() -> None:
    emoji_list_ref = importlib.resources.files(trashbot) / "emoji_list.csv"
    with emoji_list_ref.open("r") as file:
        emoji_list = list(csv.DictReader(file))

    avail_ids = set(range(1, 1024))
    for row in emoji_list:
        if row["status"] == "included":
            if row["rf_code"]:
                avail_ids.discard(int(row["rf_code"]))
        else:
            row["rf_code"] = ""

    avail_list = list(sorted(avail_ids, reverse=True))
    print(f"{len(avail_ids)} free, {len(emoji_list)} rows, assigning...")
    for row in emoji_list:
        if row["status"] == "included" and not row["rf_code"]:
            row["rf_code"] = str(avail_list.pop())

    with importlib.resources.as_file(emoji_list_ref) as path:
        with path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=emoji_list[0].keys())
            writer.writeheader()
            for row in emoji_list:
                writer.writerow(row)


if __name__ == "__main__":
    main()
