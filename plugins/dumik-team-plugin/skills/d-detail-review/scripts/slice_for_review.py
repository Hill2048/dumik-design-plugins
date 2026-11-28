#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast parallel slicer for DUMIK detail-page / main-image final review.

Features:
- Multi-threaded strip slicing with crisp Google Sans + MiSans X/Y absolute pixel
  rulers so visual reviewers can read exact [x1, y1, x2, y2] boxes effortlessly.
- Automatic detection of solid-color trailing padding (--skip-blank).
- Optional --auto-skeleton to emit a ready-to-fill review_input JSON skeleton with
  images pre-populated and available Feishu planning reference paths listed.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

LEFT_RULER_W = 74
TOP_RULER_H = 34
BG_RULER = (34, 38, 46)
BORDER_COLOR = (92, 102, 118)
TICK_MAJOR = (235, 240, 248)
TICK_MINOR = (140, 150, 166)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    local_fonts = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    candidates = [
        os.path.join(local_fonts, "GoogleSansFlex-VariableFont_ROND,opsz,slnt,wdth,wght.ttf"),
        r"C:\Windows\Fonts\GoogleSansFlex-VariableFont_ROND,opsz,slnt,wdth,wght.ttf",
        os.path.join(local_fonts, "GoogleSans-Medium.ttf"),
        r"C:\Windows\Fonts\GoogleSans-Medium.ttf",
        r"C:\Windows\Fonts\MiSansVF.ttf",
        os.path.join(local_fonts, "MiSansVF.ttf"),
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for fp in candidates:
        if os.path.isfile(fp):
            try:
                f = ImageFont.truetype(fp, size)
                try:
                    f.set_variation_by_name("Medium")
                except Exception:
                    pass
                return f
            except Exception:
                continue
    return ImageFont.load_default()


def add_rulers(strip: Image.Image, y_offset: int, orig_w: int, font: ImageFont.ImageFont, font_sm: ImageFont.ImageFont) -> Image.Image:
    sw, sh = strip.size
    canvas = Image.new("RGB", (sw + LEFT_RULER_W, sh + TOP_RULER_H), BG_RULER)
    canvas.paste(strip.convert("RGB"), (LEFT_RULER_W, TOP_RULER_H))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, LEFT_RULER_W - 1, TOP_RULER_H - 1], fill=(24, 27, 33))
    draw.text((8, 9), "X\\Y px", fill=(180, 195, 215), font=font_sm)

    draw.line([(LEFT_RULER_W - 1, 0), (LEFT_RULER_W - 1, sh + TOP_RULER_H)], fill=BORDER_COLOR, width=1)
    draw.line([(0, TOP_RULER_H - 1), (sw + LEFT_RULER_W, TOP_RULER_H - 1)], fill=BORDER_COLOR, width=1)

    for x in range(0, orig_w + 1, 50):
        px = min(canvas.width - 1, LEFT_RULER_W + x)
        if x % 100 == 0:
            draw.line([(px, TOP_RULER_H - 12), (px, TOP_RULER_H - 1)], fill=TICK_MAJOR, width=1)
            tx = px + 3 if x + 40 < orig_w else px - 28
            draw.text((tx, 4), str(x), fill=TICK_MAJOR, font=font_sm)
        else:
            draw.line([(px, TOP_RULER_H - 6), (px, TOP_RULER_H - 1)], fill=TICK_MINOR, width=1)

    first_tick = (y_offset // 50) * 50
    for y in range(first_tick, y_offset + sh + 1, 50):
        if y < y_offset:
            continue
        py = TOP_RULER_H + (y - y_offset)
        if py >= canvas.height:
            continue
        if y % 100 == 0:
            draw.line([(LEFT_RULER_W - 12, py), (LEFT_RULER_W - 1, py)], fill=TICK_MAJOR, width=1)
            draw.line([(LEFT_RULER_W, py), (LEFT_RULER_W + 8, py)], fill=(255, 70, 70), width=1)
            draw.line([(canvas.width - 9, py), (canvas.width - 1, py)], fill=(255, 70, 70), width=1)
            draw.text((6, max(TOP_RULER_H + 1, py - 7)), str(y), fill=TICK_MAJOR, font=font)
        else:
            draw.line([(LEFT_RULER_W - 6, py), (LEFT_RULER_W - 1, py)], fill=TICK_MINOR, width=1)

    return canvas


def is_uniform_strip(img: Image.Image) -> bool:
    small = img.convert("RGB").resize((64, 64))
    extrema = small.getextrema()
    return all((hi - lo) <= 6 for lo, hi in extrema)


def slice_image(
    image_path: Path,
    out_dir: Path,
    key: str,
    chunk_height: int,
    overlap: int,
    skip_blank: bool,
    workers: int = 4,
) -> dict:
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    step = max(200, chunk_height - overlap)
    font = load_font(13)
    font_sm = load_font(11)

    jobs: list[tuple[int, int, int]] = []
    y = 0
    idx = 1
    while y < h:
        y2 = min(h, y + chunk_height)
        jobs.append((idx, y, y2))
        idx += 1
        if y2 == h:
            break
        y += step

    def _run_one(job: tuple[int, int, int]) -> dict | None:
        j_idx, jy1, jy2 = job
        crop = im.crop((0, jy1, w, jy2))
        blank = is_uniform_strip(crop)
        if skip_blank and blank and j_idx > 1:
            return None
        ruled = add_rulers(crop, jy1, w, font, font_sm)
        out_path = out_dir / f"{key}_{j_idx:02d}_y{jy1}_y{jy2}.jpg"
        ruled.save(out_path, quality=92, optimize=True)
        return {
            "index": j_idx,
            "y1": jy1,
            "y2": jy2,
            "blank": blank,
            "path": str(out_path),
        }

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as pool:
        results = [r for r in pool.map(_run_one, jobs) if r is not None]
    results.sort(key=lambda r: r["index"])

    content_h = max((r["y2"] for r in results if not r["blank"]), default=h)
    return {
        "key": key,
        "source": str(image_path.resolve()),
        "width": w,
        "height": h,
        "content_height": content_h,
        "ruler_left_px": LEFT_RULER_W,
        "ruler_top_px": TOP_RULER_H,
        "strips": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fast parallel slicer for detail pages with X/Y pixel rulers.")
    parser.add_argument("--images", nargs="+", required=True, help="One or more image paths to slice.")
    parser.add_argument("--out-dir", required=True, help="Temporary output directory for ruled strips.")
    parser.add_argument("--chunk-height", type=int, default=1800, help="Height of each strip in pixels.")
    parser.add_argument("--overlap", type=int, default=150, help="Overlap between adjacent strips in pixels.")
    parser.add_argument("--skip-blank", action="store_true", help="Skip pure solid-color trailing strips.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker threads per image.")
    parser.add_argument("--project-root", default="", help="Optional project root to discover Feishu plan refs for skeleton.")
    parser.add_argument("--auto-skeleton", default="", help="Optional path to emit a starter review_input JSON skeleton.")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for idx, raw in enumerate(args.images, start=1):
        p = Path(raw)
        if not p.is_file():
            raise FileNotFoundError(f"Image not found: {p}")
        key = p.stem if len(p.stem) <= 12 and p.stem.isascii() else f"img{idx}"
        info = slice_image(p, out_dir, key, args.chunk_height, args.overlap, args.skip_blank, workers=args.workers)
        manifest.append(info)
        print(f"[{key}] {p.name} ({info['width']}x{info['height']}, content_y<={info['content_height']}) -> {len(info['strips'])} strips")
        for s in info["strips"]:
            flag = " [BLANK]" if s["blank"] else ""
            print(f"  - y={s['y1']}..{s['y2']}: {s['path']}{flag}")

    manifest_path = out_dir / "slices_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest saved: {manifest_path}")

    if args.auto_skeleton:
        proj = Path(args.project_root).resolve() if args.project_root else None
        plan_refs = []
        if proj and (proj / "素材" / "飞书画布").is_dir():
            plan_refs = sorted(
                p.relative_to(proj).as_posix()
                for p in (proj / "素材" / "飞书画布").glob("*_画布原图.png")
            )
        skeleton = {
            "project_name": proj.name if proj else "详情页终稿",
            "images": [{"key": m["key"], "label": Path(m["source"]).name, "path": m["source"]} for m in manifest],
            "available_plan_refs": plan_refs,
            "issues": [],
        }
        sk_path = Path(args.auto_skeleton)
        sk_path.parent.mkdir(parents=True, exist_ok=True)
        sk_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Skeleton saved: {sk_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
