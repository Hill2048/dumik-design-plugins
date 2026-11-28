#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK 设定集素材预处理与极速裁图辅助工具（零额外依赖，纯 Pillow + numpy）：

1. stitch-white   : 将 2~6 张产品不同视角白底图自动去多余白边、等高对齐拼成「多视图白底身份卡」。
2. compress-refs  : 扫描设定集目录，将超过体积/尺寸阈值的超限大图无损压出 2K 轻量传输版（<原名>_轻量2K.jpg）。
3. auto-white     : 纯白底五视图/多视角拼图全自动检测切分（0.05s 识别每只产品边界，按左到右、上到下编号 #1..#N）。
4. grid-overlay   : 给复杂场景图叠一层 10x10 百分比标尺网格（落 %TEMP%），让视觉定位 1 次报准坐标不返工。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def trim_white_border(img: Image.Image, white_thresh: int = 245, pad_ratio: float = 0.04) -> Image.Image:
    """自动裁掉白底图四周多余纯白留白，仅保留干净极小边距。"""
    rgb = img.convert("RGB")
    arr = np.asarray(rgb)
    non_white = np.any(arr < white_thresh, axis=2)
    ys, xs = np.where(non_white)
    if len(xs) == 0 or len(ys) == 0:
        return rgb
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad_ratio), int(bh * pad_ratio)
    W, H = rgb.size
    return rgb.crop((max(0, x1 - px), max(0, y1 - py), min(W, x2 + px), min(H, y2 + py)))


def detect_white_bg_slots(img: Image.Image, white_thresh: int = 242, min_area_ratio: float = 0.015) -> list[list[int]]:
    """
    自动检测纯白底多视图拼图中的各个独立产品区域，按从上到下、从左到右返回 [x1, y1, x2, y2] 列表。
    适用于 1~6 格横向/网格白底五视图，无需人工手算像素坐标。
    """
    rgb = img.convert("RGB")
    W, H = rgb.size
    # Downsample for fast connected-interval projection
    scale = max(1, max(W, H) // 600)
    small = rgb.resize((max(1, W // scale), max(1, H // scale)), Image.BILINEAR)
    arr = np.asarray(small)
    mask = np.any(arr < white_thresh, axis=2)
    sh, sw = mask.shape

    def _split_runs(vec: np.ndarray, min_gap: int = 4) -> list[tuple[int, int]]:
        runs: list[tuple[int, int]] = []
        in_run = False
        start = 0
        for i, val in enumerate(vec):
            if val and not in_run:
                start = i
                in_run = True
            elif not val and in_run:
                runs.append((start, i))
                in_run = False
        if in_run:
            runs.append((start, len(vec)))
        # Merge runs separated by tiny gaps
        merged: list[tuple[int, int]] = []
        for s, e in runs:
            if merged and s - merged[-1][1] < min_gap:
                merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        return merged

    # First split horizontally into rows, then each row vertically into columns
    row_active = mask.any(axis=1)
    row_bands = _split_runs(row_active, min_gap=max(4, sh // 60))
    boxes: list[list[int]] = []
    min_pixels = int(W * H * min_area_ratio)

    for ry1, ry2 in row_bands:
        sub = mask[ry1:ry2, :]
        col_active = sub.any(axis=0)
        col_bands = _split_runs(col_active, min_gap=max(4, sw // 60))
        for cx1, cx2 in col_bands:
            cell = sub[:, cx1:cx2]
            ys, xs = np.where(cell)
            if len(xs) == 0:
                continue
            gx1 = max(0, (cx1 + int(xs.min())) * scale)
            gy1 = max(0, (ry1 + int(ys.min())) * scale)
            gx2 = min(W, (cx1 + int(xs.max()) + 1) * scale)
            gy2 = min(H, (ry1 + int(ys.max()) + 1) * scale)
            if (gx2 - gx1) * (gy2 - gy1) >= min_pixels:
                boxes.append([gx1, gy1, gx2, gy2])
    return boxes


def stitch_white_identity_card(
    image_paths: list[Path],
    out_path: Path,
    labels: list[str] | None = None,
    target_height: int = 900,
    max_width: int = 2560,
) -> dict[str, Any]:
    """将 2~6 张产品白底图自动去白边、等高居中横排拼成标准「多视图白底身份卡」。"""
    if not image_paths:
        raise ValueError("至少需要 1 张白底图")

    trimmed: list[Image.Image] = []
    for p in image_paths:
        with Image.open(p) as im:
            t = trim_white_border(im)
            ratio = target_height / max(1, t.height)
            nw = max(1, int(round(t.width * ratio)))
            trimmed.append(t.resize((nw, target_height), Image.LANCZOS))

    pad = 40
    label_h = 36 if labels else 0
    total_w = sum(im.width for im in trimmed) + pad * (len(trimmed) + 1)
    total_h = target_height + pad * 2 + label_h

    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    x = pad
    for idx, im in enumerate(trimmed):
        canvas.paste(im, (x, pad))
        if labels and idx < len(labels) and labels[idx]:
            draw.text((x + 8, pad + target_height + 8), labels[idx], fill=(90, 90, 95))
        x += im.width + pad

    if canvas.width > max_width:
        scale = max_width / canvas.width
        canvas = canvas.resize((max_width, max(1, int(round(canvas.height * scale)))), Image.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in (".jpg", ".jpeg"):
        canvas.save(out_path, quality=93, optimize=True)
    else:
        canvas.save(out_path)
    return {"status": "ok", "out": str(out_path), "size": [canvas.width, canvas.height], "count": len(trimmed)}


def compress_oversized_refs(
    target_dir: Path,
    max_mb: float = 4.0,
    max_edge: int = 2048,
    quality: int = 90,
) -> dict[str, Any]:
    """扫描设定集目录，把超限大图旁出 <原名>_轻量2K.jpg（不覆盖原文件）。"""
    processed: list[dict[str, Any]] = []
    skipped: int = 0
    max_bytes = int(max_mb * 1024 * 1024)

    for p in sorted(target_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        if "_轻量2K" in p.stem:
            continue
        size_bytes = p.stat().st_size
        with Image.open(p) as im:
            w, h = im.size
            if size_bytes <= max_bytes and max(w, h) <= max_edge:
                skipped += 1
                continue
            rgb = im.convert("RGB")
            if max(w, h) > max_edge:
                rgb.thumbnail((max_edge, max_edge), Image.LANCZOS)
            out_p = p.with_name(f"{p.stem}_轻量2K.jpg")
            rgb.save(out_p, quality=quality, optimize=True)
            processed.append(
                {
                    "source": str(p),
                    "source_mb": round(size_bytes / (1024 * 1024), 2),
                    "saved": str(out_p),
                    "saved_mb": round(out_p.stat().st_size / (1024 * 1024), 2),
                    "size": [rgb.width, rgb.height],
                }
            )
    return {"status": "ok", "compressed_count": len(processed), "skipped_count": skipped, "files": processed}


def make_grid_overlay(image_path: Path, out_path: Path | None = None, divisions: int = 10) -> Path:
    """在图片上叠加半透明 10x10 百分比标尺网格（0.1~0.9 刻度），方便视觉 1 次给准框坐标。"""
    with Image.open(image_path) as im:
        rgba = im.convert("RGBA")
        W, H = rgba.size
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for i in range(1, divisions):
            frac = i / divisions
            x = int(round(W * frac))
            y = int(round(H * frac))
            line_col = (255, 60, 60, 150) if i % 2 == 0 else (255, 220, 40, 110)
            draw.line([(x, 0), (x, H)], fill=line_col, width=2)
            draw.line([(0, y), (W, y)], fill=line_col, width=2)
            draw.rectangle([x + 2, 4, x + 36, 20], fill=(0, 0, 0, 170))
            draw.text((x + 5, 6), f"{frac:.1f}", fill=(255, 255, 255, 255))
            draw.rectangle([4, y + 2, 38, y + 18], fill=(0, 0, 0, 170))
            draw.text((7, y + 4), f"{frac:.1f}", fill=(255, 255, 255, 255))
        merged = Image.alpha_composite(rgba, overlay).convert("RGB")

    if out_path is None:
        out_dir = Path(tempfile.gettempdir()) / "dumik-runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{image_path.stem}_坐标网格.jpg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.save(out_path, quality=88)
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DUMIK 设定集白底拼图、大图瘦身与极速裁图标尺工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sw = sub.add_parser("stitch-white", help="将多张产品白底图拼成多视图白底身份卡")
    sw.add_argument("--out", required=True, help="输出路径（如 设定集/白底图/00_产品_多视图白底身份卡.jpg）")
    sw.add_argument("--labels", default="", help="可选逗号分隔视角标签（如 正视,侧视,顶视）")
    sw.add_argument("images", nargs="+", help="白底图路径列表")

    cr = sub.add_parser("compress-refs", help="扫描设定集超限大图并生成 2K 轻量传输版")
    cr.add_argument("--dir", required=True, help="待扫描目录（如 设定集）")
    cr.add_argument("--max-mb", type=float, default=4.0)
    cr.add_argument("--max-edge", type=int, default=2048)

    aw = sub.add_parser("auto-white", help="自动检测五视图白底图中每只产品的边界框（#1..#N）")
    aw.add_argument("--image", required=True, help="多视图白底图路径")

    go = sub.add_parser("grid-overlay", help="为复杂场景图叠加 10x10 百分比标尺网格（落 %%TEMP%%）")
    go.add_argument("--image", required=True, help="场景图路径")
    go.add_argument("--out", default="", help="可选输出路径")

    args = ap.parse_args(argv)
    if args.cmd == "stitch-white":
        lbls = [s.strip() for s in args.labels.split(",")] if args.labels else None
        res = stitch_white_identity_card([Path(p) for p in args.images], Path(args.out), labels=lbls)
    elif args.cmd == "compress-refs":
        res = compress_oversized_refs(Path(args.dir), max_mb=args.max_mb, max_edge=args.max_edge)
    elif args.cmd == "auto-white":
        with Image.open(Path(args.image)) as im:
            slots = detect_white_bg_slots(im)
        res = {"status": "ok", "count": len(slots), "slots": [{"slot": i + 1, "box": b} for i, b in enumerate(slots)]}
    else:
        saved = make_grid_overlay(Path(args.image), Path(args.out) if args.out else None)
        res = {"status": "ok", "grid_image": str(saved)}

    print(json.dumps(res, ensure_ascii=False, indent=2))
    try:
        scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import dumik_telemetry

        dumik_telemetry.report_event_async(event="invoke", skill="d-image-director", mode=f"prep-{args.cmd}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
