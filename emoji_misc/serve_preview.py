#!/usr/bin/env python3
"""Local server for preview.html.

Serves HTML at the root, the emoji list at /emoji_list.json, and the JoyPixels
assets at /joypixels/<code>.png to assist emoji curation.
"""

import argparse
import csv
import http
import http.server
import importlib.resources
import json
import pathlib
import threading
import trashbot.resources
import urllib
import zipfile

VARIATION_SELECTOR_16 = 0xFE0F
ZWJ = 0x200D


def joypixels_key(codepoints_str: str) -> str:
    cps = [int(c, 16) for c in codepoints_str.split()]
    kept = [c for c in cps if c not in (VARIATION_SELECTOR_16, ZWJ)]
    return "-".join(f"{c:04x}" for c in kept)

HTML_PATH = "/"
EMOJI_JSON_PATH = "/emoji_list.json"
JOYPIXELS_PREFIX = "/joypixels/"

HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Emoji curation preview</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; background: #fafafa; }
  header { position: sticky; top: 0; background: #fafafa; padding: 0.5rem 0;
           border-bottom: 1px solid #ccc; z-index: 10; }
  header label { margin-right: 1rem; font-size: 0.9rem; }
  #counts { font-size: 0.85rem; color: #555; margin-left: 0.5rem; }
  h2 { margin: 1.5rem 0 0.25rem; font-size: 1.1rem; }
  h3 { margin: 0.75rem 0 0.25rem; font-size: 0.9rem; color: #666;
       text-transform: uppercase; letter-spacing: 0.05em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 4px; }
  .cell { position: relative; padding: 4px; border: 1px solid transparent;
          border-radius: 4px; text-align: center; font-size: 0.65rem;
          line-height: 1.1; word-break: break-word; }
  .cell img { width: 64px; height: 64px; display: block; margin: 0 auto 2px;
              image-rendering: pixelated; }
  .cell.candidate { background: #e8f5e9; border-color: #a5d6a7; }
  .cell.included  { background: #bbdefb; border-color: #64b5f6; }
  .cell.excluded  { background: #f5f5f5; border-color: #e0e0e0; opacity: 0.55; }
  .cell .rfcode { color: #666; font-weight: bold; }
  .cell .name { color: #000; }
  .cell .cp { color: #999; font-family: monospace; font-size: 0.6rem; }
  .cell .reason { color: #b71c1c; font-style: italic; }
</style>
</head>
<body>
<header>
  <strong>Emoji curation</strong>
  <label>Status:
    <select id="f-status">
      <option value="all">all</option>
      <option value="candidate" selected>candidate</option>
      <option value="included">included</option>
      <option value="excluded">excluded</option>
    </select>
  </label>
  <label>Reason:
    <select id="f-reason"><option value="">(any)</option></select>
  </label>
  <label>Group:
    <select id="f-group"><option value="">(any)</option></select>
  </label>
  <label><input type="checkbox" id="f-meta"> show codepoints/reason</label>
  <span id="counts"></span>
</header>
<main id="out">loading…</main>

<script>
const JOYPIXELS_PREFIX = "/joypixels/";

function render(rows) {
  const fStatus = document.getElementById("f-status").value;
  const fReason = document.getElementById("f-reason").value;
  const fGroup = document.getElementById("f-group").value;
  const showMeta = document.getElementById("f-meta").checked;
  const out = document.getElementById("out");
  out.innerHTML = "";

  const filtered = rows.filter(r =>
    (fStatus === "all" || r.status === fStatus) &&
    (fReason === "" || r.reason === fReason) &&
    (fGroup === "" || r.group === fGroup)
  );

  document.getElementById("counts").textContent =
    `showing ${filtered.length} of ${rows.length}`;

  let curGroup = null, curSub = null, gridEl = null;
  for (const r of filtered) {
    if (r.group !== curGroup) {
      const h2 = document.createElement("h2");
      h2.textContent = r.group;
      out.appendChild(h2);
      curGroup = r.group; curSub = null;
    }
    if (r.subgroup !== curSub) {
      const h3 = document.createElement("h3");
      h3.textContent = r.subgroup;
      out.appendChild(h3);
      gridEl = document.createElement("div");
      gridEl.className = "grid";
      out.appendChild(gridEl);
      curSub = r.subgroup;
    }
    const cell = document.createElement("div");
    cell.className = `cell ${r.status}`;
    cell.title = `${r.name}\n${r.codepoints}\nstatus: ${r.status}${r.reason ? " (" + r.reason + ")" : ""}`;
    let html = "";
    html += `<div class="rfcode">${r.rf_code ? `RF ${r.rf_code}` : "-"}</div>`;
    html += `<img src="${JOYPIXELS_PREFIX}${r.codepoints}" loading="lazy" alt="${r.name}">`;
    html += `<div class="name">${r.name}</div>`;
    if (showMeta) {
      html += `<div class="cp">${r.codepoints}</div>`;
      if (r.reason) html += `<div class="reason">${r.reason}</div>`;
    }
    cell.innerHTML = html;
    gridEl.appendChild(cell);
  }
}

(async () => {
  const rows = await (await fetch("emoji_list.json")).json();
  // Populate filter dropdowns
  const reasonSel = document.getElementById("f-reason");
  const groupSel = document.getElementById("f-group");
  for (const v of [...new Set(rows.map(r => r.reason).filter(Boolean))].sort()) {
    reasonSel.add(new Option(v, v));
  }
  for (const v of [...new Set(rows.map(r => r.group))]) {
    groupSel.add(new Option(v, v));
  }
  ["f-status", "f-reason", "f-group", "f-meta"].forEach(id =>
    document.getElementById(id).addEventListener("change", () => render(rows)));
  render(rows);
})();
</script>
</body>
</html>
"""


DEFAULT_ZIP = pathlib.Path(__file__).parent.parent.parent / "joypixels-10.0-emoji.zip"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--joypixels-zip",
        type=pathlib.Path,
        default=DEFAULT_ZIP,
        help=f"path to joypixels release zip (default: {DEFAULT_ZIP})",
    )
    args = ap.parse_args()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urllib.parse.urlsplit(self.path)
            if parts.path == HTML_PATH:
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_utf8)))
                self.end_headers()
                self.wfile.write(html_utf8)

            elif parts.path == EMOJI_JSON_PATH:
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(emoji_list_utf8)))
                self.end_headers()
                self.wfile.write(emoji_list_utf8)

            elif parts.path.startswith(JOYPIXELS_PREFIX):
                codepoints = urllib.parse.unquote(parts.path[len(JOYPIXELS_PREFIX):])
                name = f"png/unicode/128/{joypixels_key(codepoints)}.png"
                with joypixels_lock:  # ZipFile is not thread-safe for reads
                    try:
                        img = joypixels_zip.read(name)
                    except KeyError:
                        self.send_response(http.HTTPStatus.NOT_FOUND)
                        self.end_headers()
                        return
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(img)))
                self.end_headers()
                self.wfile.write(img)

            else:
                self.send_response(http.HTTPStatus.NOT_FOUND)
                self.end_headers()

    resource_files = importlib.resources.files(trashbot.resources)
    with (resource_files / "emoji_list.csv").open("r") as list_csv:
        emoji_list = list(csv.DictReader(list_csv))

    joypixels_zip = zipfile.ZipFile(args.joypixels_zip, "r")
    joypixels_lock = threading.Lock()

    html_utf8 = HTML.encode("utf-8")
    emoji_list_utf8 = json.dumps(emoji_list).encode("utf-8")

    with http.server.ThreadingHTTPServer(("127.0.0.1", 8000), Handler) as httpd:
        print(f"serving at http://127.0.0.1:8000{HTML_PATH}")
        print(f"  list at {EMOJI_JSON_PATH}")
        print(f"  images from {args.joypixels_zip} at {JOYPIXELS_PREFIX}<codepoints>")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
