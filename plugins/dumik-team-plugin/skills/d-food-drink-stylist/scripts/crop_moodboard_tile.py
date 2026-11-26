#!/usr/bin/env python3
"""Crop a single 1024x1024 HD reference tile from any built-in DUMIK 3x3 moodboard (1-based tile index 1..9)."""
import argparse
import sys
from pathlib import Path
from PIL import Image

def resolve_board(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_file():
        return p
    skill_dir = Path(__file__).resolve().parent.parent
    candidates = [
        skill_dir / "assets" / "moodboards" / name_or_path,
        skill_dir.parent / "d-image-director" / "assets" / "moodboards" / name_or_path,
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"Moodboard not found: {name_or_path}")

def main() -> int:
    parser = argparse.ArgumentParser(description="Crop one 1024x1024 HD tile from a built-in 3x3 moodboard.")
    parser.add_argument("--board", required=True, help="Moodboard filename or full path")
    parser.add_argument("--tile", type=int, required=True, help="1-based tile index (1..9, left-to-right, top-to-bottom)")
    parser.add_argument("--out", required=True, help="Output path for cropped reference image")
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--pad", type=int, default=12)
    args = parser.parse_args()

    board_path = resolve_board(args.board)
    total = args.cols * args.rows
    if not (1 <= args.tile <= total):
        raise ValueError(f"--tile must be between 1 and {total}")

    r, c = divmod(args.tile - 1, args.cols)
    im = Image.open(board_path).convert("RGB")
    W, H = im.size
    tw = (W - (args.cols + 1) * args.pad) // args.cols
    th = (H - (args.rows + 1) * args.pad) // args.rows
    x0 = args.pad + c * (tw + args.pad)
    y0 = args.pad + r * (th + args.pad)
    tile = im.crop((x0, y0, x0 + tw, y0 + th))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tile.save(out_path, quality=92)
    print(f"OK cropped {board_path.name} tile #{args.tile} (r{r+1}c{c+1}, {tile.size[0]}x{tile.size[1]}) -> {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
