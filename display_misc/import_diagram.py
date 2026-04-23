#!/usr/bin/env python3
"""
Preprocesses a diagram-like image (CAD screencap, schematic, etc) for display:
- Remaps the darkest --dark-percentile of pixels to black
- Remaps the brightest pixel to white
- Squashes alpha values at or below --alpha-floor to 0 (kills scan noise
  and faint anti-alias halo at the image border)
- Trims fully-black edges
- Converts brightness to (straight, non-premultiplied) alpha: each pixel
  is scaled so its brightest channel is 255, and the original brightness
  moves into the alpha channel. Compositing on black reproduces the
  normalized input.
"""

import argparse
import os
import pathlib
import sys

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402


def process(
    src: pathlib.Path,
    dst: pathlib.Path,
    dark_pct: float,
    invert: bool,
    alpha_floor: int,
) -> None:
    surf = pygame.image.load(str(src))
    # array3d drops any input alpha; rgb underneath is used as-is.
    rgb = pygame.surfarray.array3d(surf).astype(np.float32)  # (W, H, 3)
    if invert:
        rgb = 255.0 - rgb
    lum = rgb.max(axis=2)

    dark = float(np.percentile(lum, dark_pct))
    bright = float(lum.max())
    if bright <= dark:
        sys.exit(f"{src}: no dynamic range (dark={dark}, bright={bright})")

    scale = 255.0 / (bright - dark)
    rgb = np.clip((rgb - dark) * scale, 0, 255)
    alpha = rgb.max(axis=2)
    alpha = np.where(alpha <= alpha_floor, 0, alpha)

    mask = alpha > 0
    if not mask.any():
        sys.exit(f"{src}: empty after normalization")
    xs = np.where(mask.any(axis=1))[0]
    ys = np.where(mask.any(axis=0))[0]
    x0, x1 = int(xs[0]), int(xs[-1]) + 1
    y0, y1 = int(ys[0]), int(ys[-1]) + 1

    rgb = rgb[x0:x1, y0:y1]
    alpha = alpha[x0:x1, y0:y1]

    # emit straight (non-premultiplied) alpha: scale each pixel's rgb so
    # its brightest channel is 255, leaving alpha to carry the brightness.
    # compositing on black then reproduces the normalized input.
    safe = np.where(alpha > 0, alpha, 1)
    rgb = np.clip(rgb * 255.0 / safe[..., None], 0, 255).astype(np.uint8)
    alpha = alpha.astype(np.uint8)
    rgba = np.concatenate([rgb, alpha[..., None]], axis=2)  # (W, H, 4)

    w, h = rgba.shape[:2]
    # pygame.image.frombytes expects row-major (H, W, 4)
    out = pygame.image.frombytes(
        rgba.transpose(1, 0, 2).tobytes(), (w, h), "RGBA"
    )
    pygame.image.save(out, str(dst))
    print(
        f"{src} -> {dst}  "
        f"{surf.get_width()}x{surf.get_height()} -> {w}x{h}  "
        f"dark={dark:.1f} bright={bright:.1f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument(
        "--dark-percentile",
        type=float,
        default=5.0,
        help="pixels at or below this brightness percentile map to black",
    )
    ap.add_argument(
        "--invert",
        action="store_true",
        help="negate input first (e.g. for black-lines-on-white CAD output)",
    )
    ap.add_argument(
        "--alpha-floor",
        type=int,
        default=24,
        help="output alpha values at or below this are squashed to 0",
    )
    args = ap.parse_args()

    pygame.init()
    process(
        args.src,
        args.dst,
        args.dark_percentile,
        args.invert,
        args.alpha_floor,
    )


if __name__ == "__main__":
    main()
