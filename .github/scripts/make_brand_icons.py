#!/usr/bin/env python3
"""Build Home Assistant brand icons from the official Christie site icon.

Official source (also stored as base64 under .github/brand-src/):

https://www.christiedigital.com/apple-touch-icon.png

This is the 152x152 PNG published as the apple-touch-icon on
christiedigital.com (the square chevron mark browsers show as the site
icon). See .github/brand-src/SOURCE.md.

The official mark is already on a square canvas, so logo.png is omitted;
Home Assistant falls back to the icon. dark_icon uses the same official
asset.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".github" / "brand-src"
DEST = ROOT / "custom_components" / "christie_griffyn" / "brand"

OFFICIAL = SRC / "christie-apple-touch-icon.png.b64"
SOURCES = {
    "icon": OFFICIAL,
    "dark_icon": OFFICIAL,
}


def load_source(path: Path) -> Image.Image:
    data = base64.b64decode("".join(path.read_text().split()))
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    # Official PNG keeps residual RGB in fully transparent pixels.
    # Clear those so they cannot halo when the icon is composited.
    pixels = im.load()
    width, height = im.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return im


def fit_square(im: Image.Image, size: int) -> Image.Image:
    # The official asset already sits on a square canvas with its
    # intended padding, so it is not trimmed further.
    if im.size != (size, size):
        im = im.resize((size, size), Image.Resampling.LANCZOS)
    return im


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for stem, src in SOURCES.items():
        original = load_source(src)
        for name, size in ((f"{stem}.png", 256), (f"{stem}@2x.png", 512)):
            path = DEST / name
            icon = fit_square(original, size)
            icon.save(path, format="PNG", optimize=True, compress_level=9)
            print(f"wrote {path} ({size}x{size}, {path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
