#!/usr/bin/env python3
"""Generate PWA and Capacitor app icons (requires qrcode[pil] / Pillow)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_ICONS = ROOT / "static" / "icons"
MOBILE_RESOURCES = ROOT / "mobile" / "resources"


def draw_icon(size: int):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (17, 17, 17, 255))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 6,
        fill=(255, 255, 255, 255),
    )
    letter = "B"
    font_size = size // 2
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.04), letter, fill=(17, 17, 17, 255), font=font)
    return img


def main() -> None:
    STATIC_ICONS.mkdir(parents=True, exist_ok=True)
    MOBILE_RESOURCES.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_icon(size).save(STATIC_ICONS / f"icon-{size}.png", "PNG")
    draw_icon(1024).save(MOBILE_RESOURCES / "icon.png", "PNG")
    print(f"Icons written to {STATIC_ICONS} and {MOBILE_RESOURCES / 'icon.png'}")


if __name__ == "__main__":
    main()
