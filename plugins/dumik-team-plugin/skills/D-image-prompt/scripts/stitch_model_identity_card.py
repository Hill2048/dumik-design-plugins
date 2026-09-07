#!/usr/bin/env python3
"""Stitch a 3:4 three-view board and 1:1 close-up board into one 16:9 card."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageColor, ImageOps


def parse_ratio(value: str) -> float:
    try:
        width, height = (int(part) for part in value.split(":", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("ratio must look like 16:9") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("ratio values must be positive")
    return width / height


def load_rgb(path: Path, background: tuple[int, int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (*background, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB")


def resize_to_height(image: Image.Image, height: int) -> Image.Image:
    if image.height == height:
        return image
    width = max(1, round(image.width * height / image.height))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def save_image(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(output, quality=95, subsampling=0, optimize=True)
    else:
        image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stitch two clean model identity-card panels without redrawing them."
    )
    parser.add_argument("--three-view", type=Path, required=True)
    parser.add_argument("--closeups", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ratio", type=parse_ratio, default=parse_ratio("16:9"))
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--background", default="#FFFFFF")
    args = parser.parse_args()

    if args.gap < 0:
        parser.error("--gap must be zero or positive")

    background = ImageColor.getrgb(args.background)
    three_view = load_rgb(args.three_view, background)
    closeups = load_rgb(args.closeups, background)

    # Use the lower source height so the default path never upscales either panel.
    panel_height = min(three_view.height, closeups.height)
    three_view = resize_to_height(three_view, panel_height)
    closeups = resize_to_height(closeups, panel_height)

    joined_width = three_view.width + args.gap + closeups.width
    joined = Image.new("RGB", (joined_width, panel_height), background)
    joined.paste(three_view, (0, 0))
    joined.paste(closeups, (three_view.width + args.gap, 0))

    target_width = max(joined.width, math.ceil(joined.height * args.ratio))
    target_height = max(joined.height, math.ceil(joined.width / args.ratio))
    final = Image.new("RGB", (target_width, target_height), background)
    offset = ((target_width - joined.width) // 2, (target_height - joined.height) // 2)
    final.paste(joined, offset)
    save_image(final, args.out)

    print(
        f"saved={args.out} size={final.width}x{final.height} "
        f"three_view={three_view.width}x{three_view.height} "
        f"closeups={closeups.width}x{closeups.height}"
    )


if __name__ == "__main__":
    main()
