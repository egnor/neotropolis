"""Local server for preview.html.

Serves emoji/ at the root and maps /joypixels/<file> to the JoyPixels asset
archive, so the preview can reference both without symlinks or copies.

Usage: python emoji/serve.py [port]
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent.resolve()
JOYPIXELS_DIR = (HERE.parent.parent / "joypixels-10.0-emoji" / "png" / "unicode" / "128").resolve()
JOY_PREFIX = "/joypixels/"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        # Strip query/fragment before matching
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith(JOY_PREFIX):
            rel = clean[len(JOY_PREFIX):].lstrip("/")
            target = (JOYPIXELS_DIR / rel).resolve()
            # Prevent path traversal outside JOYPIXELS_DIR
            if JOYPIXELS_DIR in target.parents or target == JOYPIXELS_DIR:
                return str(target)
            return str(JOYPIXELS_DIR / "_forbidden_")
        return super().translate_path(path)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(Handler, directory=str(HERE))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving emoji/ at http://127.0.0.1:{port}/preview.html")
        print(f"  joypixels assets at {JOY_PREFIX}<file>.png  (from {JOYPIXELS_DIR})")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
