#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK 洗图预处理与批量脱壳引擎（单张/批量一体 · 纯中文命名 · 零项目垃圾）。

解决传统洗图三大痛点：
1. 竞品主体色块脱壳（--erase-box）：用荧光洋红 #FF00FF 实心盖掉原参考图里的竞品产品，只留构图/光影骨架，彻底杜绝抄竞品轮廓。
2. 竞品文案/水印背景色抹除（--text-box）：自动吸取选框周边边缘平均背景色平滑覆盖文字与水印，不留脏字残留。
3. 画幅自动扩充留白（--target-ratio 9:16）：若灵感图是 1:1 或 3:4 而项目需 9:16，自动按顶部/底部边缘色柔和延展画布，自然留出顶部 PS 排字区。
4. 支持 0~1 百分比坐标与像素坐标自动识别，大幅提升给框效率。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


DEFAULT_MASK_COLOR = "#FF00FF"
RATIO_MAP: dict[str, float] = {
    "9:16": 9 / 16,
    "3:4": 3 / 4,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "16:9": 16 / 9,
    "2:3": 2 / 3,
    "3:2": 3 / 2,
}


def resolve_box(raw_box: list[float], img_size: tuple[int, int]) -> list[int]:
    """自动识别 0~1 百分比坐标或绝对像素坐标，转为合法整数像素框 [x1, y1, x2, y2]。"""
    W, H = img_size
    x1, y1, x2, y2 = [float(v) for v in raw_box]
    if 0.0 <= x1 <= 1.0 and 0.0 <= y1 <= 1.0 and 0.0 <= x2 <= 1.0 and 0.0 <= y2 <= 1.0 and max(x2, y2) <= 1.0:
        x1, x2 = x1 * W, x2 * W
        y1, y2 = y1 * H, y2 * H
    ix1 = max(0, min(W, int(round(x1))))
    iy1 = max(0, min(H, int(round(y1))))
    ix2 = max(0, min(W, int(round(x2))))
    iy2 = max(0, min(H, int(round(y2))))
    if ix2 <= ix1 or iy2 <= iy1:
        raise ValueError(f"非法坐标框: {raw_box} -> [{ix1}, {iy1}, {ix2}, {iy2}]")
    return [ix1, iy1, ix2, iy2]


def _parse_hex_rgb(color_str: str) -> tuple[int, int, int]:
    c = color_str.strip().lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _sample_border_color(arr: np.ndarray, box: list[int]) -> tuple[int, int, int]:
    H, W, _ = arr.shape
    x1, y1, x2, y2 = box
    margin = 6
    samples = []
    if y1 >= margin:
        samples.append(arr[y1 - margin : y1, x1:x2].reshape(-1, 3))
    if y2 + margin <= H:
        samples.append(arr[y2 : y2 + margin, x1:x2].reshape(-1, 3))
    if x1 >= margin:
        samples.append(arr[y1:y2, x1 - margin : x1].reshape(-1, 3))
    if x2 + margin <= W:
        samples.append(arr[y1:y2, x2 : x2 + margin].reshape(-1, 3))
    if not samples:
        med = np.median(arr[y1:y2, x1:x2].reshape(-1, 3), axis=0)
    else:
        med = np.median(np.concatenate(samples, axis=0), axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def pad_canvas_to_ratio(
    img: Image.Image,
    target_ratio: str,
    top_bias: float = 0.72,
) -> tuple[Image.Image, dict[str, int]]:
    """
    将参考图按边缘平均色平滑延展到目标比例（默认偏向顶部留白 72%，自然留出电商详情页顶部 PS 压字区）。
    返回 (扩充后图像, 偏移字典 {pad_left, pad_top, pad_right, pad_bottom})。
    """
    if not target_ratio or target_ratio not in RATIO_MAP:
        return img.convert("RGB"), {"pad_left": 0, "pad_top": 0, "pad_right": 0, "pad_bottom": 0}

    rgb = img.convert("RGB")
    W, H = rgb.size
    tr = RATIO_MAP[target_ratio]
    cur = W / H if H > 0 else 1.0
    if abs(cur - tr) / tr <= 0.04:
        return rgb, {"pad_left": 0, "pad_top": 0, "pad_right": 0, "pad_bottom": 0}

    arr = np.asarray(rgb)
    pad_l = pad_t = pad_r = pad_b = 0

    if cur > tr:
        # Too wide -> expand vertically (top + bottom)
        new_h = int(round(W / tr))
        delta = max(0, new_h - H)
        pad_t = int(round(delta * top_bias))
        pad_b = delta - pad_t
        top_col = tuple(int(v) for v in np.median(arr[: min(12, H), :, :].reshape(-1, 3), axis=0))
        bot_col = tuple(int(v) for v in np.median(arr[max(0, H - 12) :, :, :].reshape(-1, 3), axis=0))
        canvas = Image.new("RGB", (W, new_h), top_col)
        if pad_b > 0:
            ImageDraw.Draw(canvas).rectangle([0, pad_t + H, W, new_h], fill=bot_col)
        canvas.paste(rgb, (0, pad_t))
    else:
        # Too tall -> expand horizontally
        new_w = int(round(H * tr))
        delta = max(0, new_w - W)
        pad_l = delta // 2
        pad_r = delta - pad_l
        left_col = tuple(int(v) for v in np.median(arr[:, : min(12, W), :].reshape(-1, 3), axis=0))
        right_col = tuple(int(v) for v in np.median(arr[:, max(0, W - 12) :, :].reshape(-1, 3), axis=0))
        canvas = Image.new("RGB", (new_w, H), left_col)
        if pad_r > 0:
            ImageDraw.Draw(canvas).rectangle([pad_l + W, 0, new_w, H], fill=right_col)
        canvas.paste(rgb, (pad_l, 0))

    return canvas, {"pad_left": pad_l, "pad_top": pad_t, "pad_right": pad_r, "pad_bottom": pad_b}


def prepare_washed_image(
    ref_img: Image.Image,
    *,
    erase_boxes: list[list[float]] | None = None,
    text_boxes: list[list[float]] | None = None,
    target_ratio: str = "9:16",
    top_bias: float = 0.72,
    mask_color: str = DEFAULT_MASK_COLOR,
) -> tuple[Image.Image, dict[str, Any]]:
    """执行洗图脱壳：先抹文字水印、再涂竞品主体洋红色块，最后按需平滑扩充画幅至目标比例。"""
    rgb = ref_img.convert("RGB")
    W, H = rgb.size
    arr = np.asarray(rgb)
    out = rgb.copy()
    draw = ImageDraw.Draw(out)

    # 1. Erase text/watermarks with sampled local background color
    resolved_text: list[list[int]] = []
    for tb in (text_boxes or []):
        b = resolve_box(tb, (W, H))
        bg = _sample_border_color(arr, b)
        draw.rectangle(b, fill=bg)
        resolved_text.append(b)

    # 2. Cover competitor product with solid high-contrast mask color
    resolved_erase: list[list[int]] = []
    mask_rgb = _parse_hex_rgb(mask_color)
    for eb in (erase_boxes or []):
        b = resolve_box(eb, (W, H))
        draw.rectangle(b, fill=mask_rgb)
        resolved_erase.append(b)

    # 3. Expand canvas to target ratio cleanly
    final_img, pads = pad_canvas_to_ratio(out, target_ratio=target_ratio, top_bias=top_bias)
    meta = {
        "source_size": [W, H],
        "final_size": [final_img.width, final_img.height],
        "target_ratio": target_ratio,
        "pads": pads,
        "erase_boxes": resolved_erase,
        "text_boxes": resolved_text,
        "mask_color": mask_color.upper(),
    }
    return final_img, meta


def build_wash_prompt(
    product_desc: str,
    style_desc: str = "",
    has_mask: bool = True,
    mask_color: str = DEFAULT_MASK_COLOR,
) -> str:
    """生成符合瘦身红线（<=300字、无Markdown噪音）的洗图提示词。"""
    color_label = "荧光洋红" if mask_color.upper() == "#FF00FF" else f"纯色（{mask_color.upper()}）"
    style_part = f"整体调性与材质对齐：{style_desc.strip()}。" if style_desc.strip() else ""
    mask_part = (
        f"彻底清除@图1中的{color_label}色块，在该位置严格按@图2精准置入我们的产品：{product_desc.strip()}，"
        if has_mask
        else f"将@图1中的主体产品彻底替换为@图2的产品：{product_desc.strip()}，"
    )
    return (
        f"沿用@图1的构图框架、机位角度、光线方向与空间层次，顶部自然延展为干净低反差留白区供后期排版。"
        f"{mask_part}透视比例与周边受光、反射及接触阴影完全融合。{style_part}"
        f"彻底去除原图竞品造型、Logo、文字与水印，严禁残留{color_label}色块或生成额外排版文案。"
    )


def make_wash_preview(pairs: list[tuple[str, Image.Image, Image.Image]], out_path: Path) -> None:
    if not pairs:
        return
    thumb = 340
    pad = 16
    header_h = 28
    row_h = thumb + header_h + pad
    sheet = Image.new("RGB", (thumb * 2 + pad * 3, row_h * len(pairs) + pad), (28, 28, 32))
    draw = ImageDraw.Draw(sheet)
    for idx, (label, orig, washed) in enumerate(pairs):
        y0 = pad + idx * row_h
        draw.text((pad, y0 + 4), f"[{idx + 1}] {label}  (Left: Original | Right: Washed)", fill=(235, 235, 240))
        for col, im in enumerate((orig, washed)):
            cp = im.convert("RGB")
            cp.thumbnail((thumb, thumb), Image.LANCZOS)
            x0 = pad + col * (thumb + pad) + (thumb - cp.width) // 2
            y_img = y0 + header_h + (thumb - cp.height) // 2
            sheet.paste(cp, (x0, y_img))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=90)


def _temp_workdir() -> Path:
    d = Path(tempfile.gettempdir()) / "dumik-runs" / f"洗图_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_single(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir) if args.workdir else _temp_workdir()
    workdir.mkdir(parents=True, exist_ok=True)
    ref_path = Path(args.ref).resolve()
    product_ref = Path(args.product_ref).resolve()

    with Image.open(ref_path) as orig:
        washed_im, meta = prepare_washed_image(
            orig,
            erase_boxes=args.erase_box,
            text_boxes=args.text_box,
            target_ratio=args.target_ratio,
            top_bias=args.top_bias,
            mask_color=args.mask_color,
        )
        stem = args.name or ref_path.stem
        washed_path = workdir / f"{stem}_脱壳底图.png"
        preview_path = workdir / f"{stem}_洗图预览.png"
        washed_im.save(washed_path)
        make_wash_preview([(stem, orig, washed_im)], preview_path)

    prompt = build_wash_prompt(
        args.product_desc,
        style_desc=args.style_desc,
        has_mask=bool(args.erase_box),
        mask_color=args.mask_color,
    )
    res = {
        "status": "prepared",
        "workdir": str(workdir),
        "washed_ref": str(washed_path),
        "preview": str(preview_path),
        "meta": meta,
        "designflow_item": {
            "prompt": prompt,
            "ratio": args.target_ratio,
            "sizePreset": "2K",
            "count": 2,
            "models": ["banana2.1"],
            "referenceFiles": [str(washed_path), str(product_ref)],
        },
    }
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    workdir = Path(args.workdir) if args.workdir else _temp_workdir()
    workdir.mkdir(parents=True, exist_ok=True)

    df_items: list[dict[str, Any]] = []
    pairs: list[tuple[str, Image.Image, Image.Image]] = []

    for item in manifest.get("items", []):
        name = str(item["name"])
        ref_p = Path(item["ref_image"])
        ref_p = ref_p if ref_p.is_absolute() else (root / ref_p).resolve()
        prod_p = Path(item["product_ref"])
        prod_p = prod_p if prod_p.is_absolute() else (root / prod_p).resolve()

        ratio = str(item.get("target_ratio", args.target_ratio))
        erase_boxes = item.get("erase_boxes") or []
        text_boxes = item.get("text_boxes") or []

        with Image.open(ref_p) as orig:
            washed_im, _ = prepare_washed_image(
                orig,
                erase_boxes=erase_boxes,
                text_boxes=text_boxes,
                target_ratio=ratio,
                top_bias=float(item.get("top_bias", args.top_bias)),
                mask_color=str(item.get("mask_color", args.mask_color)),
            )
            slug = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
            washed_path = workdir / f"{slug}_脱壳底图.png"
            washed_im.save(washed_path)
            pairs.append((name, orig.copy(), washed_im))

        prompt = build_wash_prompt(
            str(item.get("product_desc", "")),
            style_desc=str(item.get("style_desc", "")),
            has_mask=bool(erase_boxes),
            mask_color=str(item.get("mask_color", args.mask_color)),
        )
        df_items.append(
            {
                "id": name,
                "prompt": prompt,
                "ratio": ratio,
                "sizePreset": "2K",
                "count": int(item.get("count", 2)),
                "models": [str(item.get("model", "banana2.1"))],
                "referenceFiles": [str(washed_path), str(prod_p)],
            }
        )

    sheet_path = workdir / "洗图联系表.png"
    make_wash_preview(pairs, sheet_path)
    jobs_path = workdir / "洗图并发任务.json"
    jobs_path.write_text(json.dumps({"items": df_items}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "prepared_batch",
                "count": len(df_items),
                "workdir": str(workdir),
                "contact_sheet": str(sheet_path),
                "designflow_items": str(jobs_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DUMIK 洗图预处理与批量脱壳工具（支持百分比/像素坐标）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("single", help="单张参考图脱壳、去字、扩画幅并生成洗图任务")
    s.add_argument("--ref", required=True, help="原灵感/参考图路径")
    s.add_argument("--product-ref", required=True, help="我方产品白底图路径")
    s.add_argument("--product-desc", required=True, help="一句话产品外观描述")
    s.add_argument("--style-desc", default="", help="可选：我方风格/材质调性一句话")
    s.add_argument("--erase-box", nargs=4, type=float, action="append", metavar=("X1", "Y1", "X2", "Y2"), help="竞品主体框（支持 0~1 百分比或像素）")
    s.add_argument("--text-box", nargs=4, type=float, action="append", metavar=("X1", "Y1", "X2", "Y2"), help="竞品文字/水印区（支持 0~1 百分比或像素）")
    s.add_argument("--target-ratio", default="9:16", choices=list(RATIO_MAP.keys()))
    s.add_argument("--top-bias", type=float, default=0.72, help="竖向扩画幅时顶部留白占比（默认 0.72）")
    s.add_argument("--mask-color", default=DEFAULT_MASK_COLOR)
    s.add_argument("--name", default="")
    s.add_argument("--workdir", default="")
    s.set_defaults(func=cmd_single)

    b = sub.add_parser("batch", help="批量洗图脱壳并生成联系表与 DesignFlow 并发任务")
    b.add_argument("--manifest", required=True, help="洗图清单 JSON（放 %TEMP%）")
    b.add_argument("--project-root", default=".")
    b.add_argument("--target-ratio", default="9:16", choices=list(RATIO_MAP.keys()))
    b.add_argument("--top-bias", type=float, default=0.72)
    b.add_argument("--mask-color", default=DEFAULT_MASK_COLOR)
    b.add_argument("--workdir", default="")
    b.set_defaults(func=cmd_batch)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
