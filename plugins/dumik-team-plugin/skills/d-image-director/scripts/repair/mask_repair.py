#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK 产品细节修复引擎（产品外扩切图 + 局部高对比色块破惰性 + 外扩边羽化贴回）。

核心思路：
1. 以 `product_box` 向外扩展（默认 20%）并轻微吸附到标准比例池（1:1 / 3:4 / 4:3 / 9:16 / 16:9），
   把 AI 的 2K 分辨率集中砸在产品本体与待修细节上，且外扩边界落在背景平滑区。
2. 在切出的产品外扩图上，将具体不对的 `defect_boxes` 实心涂上高对比色块（默认荧光洋红 #FF00FF），
   彻底抹除旧的错误结构先验，打破生图模型“照抄原图”的惰性。
3. 中间产物（切片、带色块图、联系表、DesignFlow 并发任务 JSON）默认全部落在系统 `%TEMP%\\dumik-runs\\`，
   项目目录零运行垃圾。
4. AI 修完后，按记录的 `crop_box` 在外扩边做羽化无损贴回原整图，未动区域 100% 保留原像素。

用法：
  单张准备：
    python mask_repair.py prepare-single --image 原图.png --white-ref 白底图.png \
      --product-box 300 400 900 1100 --defect-box 720 520 880 760 \
      --defect-desc "把手弯折角度偏圆，按白底图还原方圆角 D 型扁平一体焊把"

  单张贴回：
    python mask_repair.py paste-single --meta <temp>/meta.json \
      --repaired 修好的外扩图.png --out 制作/S01/候选_01_repaired.png

  批量准备（manifest JSON 可放在 %TEMP%）：
    python mask_repair.py prepare-batch --manifest <temp>/manifest.json --project-root .

  批量贴回：
    python mask_repair.py paste-batch --workdir <temp>/repair-xxx --repaired-dir <dir>
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

# Target aspect ratios supported natively by Gemini Banana / DesignFlow
RATIO_POOL: list[tuple[str, float]] = [
    ("1:1", 1.0),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("2:3", 2 / 3),
    ("3:2", 3 / 2),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
]

DEFAULT_MASK_COLOR = "#FF00FF"  # High-contrast magenta (rarely matches cookware/metal)
REPAIR_MODEL_PRIORITY: list[str] = ["seedream-5.5", "seedream-5-pro", "banana2.1"]


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _parse_hex_color(color_str: str) -> tuple[int, int, int, int]:
    c = color_str.strip().lstrip("#")
    if len(c) == 6:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
    if len(c) == 8:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16))
    raise ValueError(f"非法颜色值: {color_str}（请使用 #RRGGBB 如 #FF00FF）")


def _nearest_ratio(w: int, h: int) -> tuple[str, float]:
    actual = w / h if h > 0 else 1.0
    return min(RATIO_POOL, key=lambda kv: abs(kv[1] - actual))


def compute_expanded_crop_box(
    img_size: tuple[int, int],
    product_box: list[int],
    pad: float = 0.20,
    snap_ratio: bool = True,
) -> tuple[list[int], str]:
    """围绕产品框外扩 pad 比例，并按需轻微扩展到最接近的标准比例池。"""
    W, H = img_size
    x1, y1, x2, y2 = [int(v) for v in product_box]
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"非法 product_box: {product_box}")

    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad), int(bh * pad)
    cx1, cy1 = _clamp(x1 - px, 0, W), _clamp(y1 - py, 0, H)
    cx2, cy2 = _clamp(x2 + px, 0, W), _clamp(y2 + py, 0, H)

    cw, ch = cx2 - cx1, cy2 - cy1
    ratio_name, target_r = _nearest_ratio(cw, ch)

    if snap_ratio and ch > 0:
        cur_r = cw / ch
        # Only expand outward slightly so we never clip the padded product
        if cur_r < target_r:
            desired_w = min(W, int(round(ch * target_r)))
            delta = desired_w - cw
            cx1 = _clamp(cx1 - delta // 2, 0, W)
            cx2 = _clamp(cx1 + desired_w, 0, W)
            cx1 = _clamp(cx2 - desired_w, 0, W)
        elif cur_r > target_r:
            desired_h = min(H, int(round(cw / target_r)))
            delta = desired_h - ch
            cy1 = _clamp(cy1 - delta // 2, 0, H)
            cy2 = _clamp(cy1 + desired_h, 0, H)
            cy1 = _clamp(cy2 - desired_h, 0, H)

    ratio_name, _ = _nearest_ratio(cx2 - cx1, cy2 - cy1)
    return [cx1, cy1, cx2, cy2], ratio_name


def build_masked_crop(
    img: Image.Image,
    product_box: list[int],
    defect_boxes: list[list[int]],
    pad: float = 0.20,
    mask_color: str = DEFAULT_MASK_COLOR,
    snap_ratio: bool = True,
) -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    """
    返回 (clean_crop, masked_crop, meta):
    - clean_crop: 产品外扩干净特写（用于联系表左图对照）
    - masked_crop: 在 defect_boxes 区域填高对比实心色块的待修图（发给生图模型 @图1）
    - meta: 坐标与比例元数据（用于贴回原整图）
    """
    rgba = img.convert("RGBA")
    W, H = rgba.size
    crop_box, ratio_name = compute_expanded_crop_box((W, H), product_box, pad=pad, snap_ratio=snap_ratio)
    cx1, cy1, cx2, cy2 = crop_box

    clean_crop = rgba.crop((cx1, cy1, cx2, cy2))
    masked_crop = clean_crop.copy()
    draw = ImageDraw.Draw(masked_crop)
    fill_rgba = _parse_hex_color(mask_color)

    local_defects: list[list[int]] = []
    cw, ch = clean_crop.size
    for dbox in defect_boxes:
        dx1, dy1, dx2, dy2 = [int(v) for v in dbox]
        lx1 = _clamp(dx1 - cx1, 0, cw)
        ly1 = _clamp(dy1 - cy1, 0, ch)
        lx2 = _clamp(dx2 - cx1, 0, cw)
        ly2 = _clamp(dy2 - cy1, 0, ch)
        if lx2 > lx1 and ly2 > ly1:
            draw.rectangle([lx1, ly1, lx2, ly2], fill=fill_rgba)
            local_defects.append([lx1, ly1, lx2, ly2])

    meta = {
        "source_size": [W, H],
        "product_box": [int(v) for v in product_box],
        "crop_box": crop_box,
        "crop_size": [cw, ch],
        "ratio": ratio_name,
        "pad_ratio": pad,
        "mask_color": mask_color.upper(),
        "defect_boxes_global": [[int(v) for v in b] for b in defect_boxes],
        "defect_boxes_local": local_defects,
    }
    return clean_crop, masked_crop, meta


def _build_feather_mask(tw: int, th: int, feather: int) -> Image.Image:
    f = max(0, min(int(feather), tw // 4, th // 4))
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rectangle([f, f, tw - f, th - f], fill=255)
    if f > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(f / 2))
    return mask


def paste_back_smooth(
    base_img: Image.Image,
    repaired_img: Image.Image,
    crop_box: list[int],
    feather: int = 28,
) -> Image.Image:
    """将修好的产品外扩图缩放对齐回 crop_box，在外扩背景边平滑羽化贴回原整图。"""
    base = base_img.convert("RGBA")
    repaired = repaired_img.convert("RGBA")
    cx1, cy1, cx2, cy2 = [int(v) for v in crop_box]
    tw, th = cx2 - cx1, cy2 - cy1

    if repaired.size != (tw, th):
        repaired = repaired.resize((tw, th), Image.LANCZOS)

    mask = _build_feather_mask(tw, th, feather)
    base.paste(repaired, (cx1, cy1), mask)
    return base


def _pack_pascal_string(name: str, pad_multiple: int = 4) -> bytes:
    raw = name.encode("ascii", errors="replace")[:255]
    data = bytes([len(raw)]) + raw
    rem = len(data) % pad_multiple
    if rem:
        data += b"\x00" * (pad_multiple - rem)
    return data


def _pack_unicode_layer_name(name: str) -> bytes:
    utf16 = name.encode("utf-16-be")
    body = struct.pack(">I", len(name)) + utf16
    if len(body) % 2:
        body += b"\x00"
    return b"8BIMluni" + struct.pack(">I", len(body)) + body


def save_layered_psd(
    base_img: Image.Image,
    repaired_imgs: Image.Image | list[Image.Image],
    crop_box: list[int],
    out_path: Path,
    feather: int = 28,
) -> None:
    """
    零外部依赖写出标准 Adobe Photoshop 多图层可编辑蒙版 PSD（8-bit RGB）：
    - 底层「原图」：完整原始整图
    - 顶层「修复候选_01」「修复候选_02」…：各自对齐到 crop_box 并附带独立可编辑羽化图层蒙版（channel_id=-2）
      默认仅第 1 个候选层可见（flags=0），其余候选层默认隐藏（flags=2），进 PS 点小眼睛 1 秒切换或混拼。
    - 同时写入合成预览图（以第 1 个候选合成），支持 Windows 缩略图、Eagle、飞书与 Photoshop 直接打开。
    """
    candidates = repaired_imgs if isinstance(repaired_imgs, list) else [repaired_imgs]
    if not candidates:
        raise ValueError("至少需要 1 张修复候选图")

    base_rgb = base_img.convert("RGB")
    W, H = base_rgb.size
    cx1, cy1, cx2, cy2 = [int(v) for v in crop_box]
    tw, th = cx2 - cx1, cy2 - cy1

    rep_rgbs: list[Image.Image] = []
    for cand in candidates:
        r = cand.convert("RGB")
        if r.size != (tw, th):
            r = r.resize((tw, th), Image.LANCZOS)
        rep_rgbs.append(r)

    mask_l = _build_feather_mask(tw, th, feather)

    # Merged composite preview uses the first candidate
    merged = base_rgb.copy()
    merged.paste(rep_rgbs[0], (cx1, cy1), mask_l)

    def _layer_record_and_channels(
        top: int,
        left: int,
        bottom: int,
        right: int,
        ascii_name: str,
        unicode_name: str,
        rgb_img: Image.Image,
        user_mask: Image.Image | None = None,
        visible: bool = True,
    ) -> tuple[bytes, bytes]:
        r_ch, g_ch, b_ch = rgb_img.split()
        ch_pairs: list[tuple[int, bytes]] = [
            (0, r_ch.tobytes()),
            (1, g_ch.tobytes()),
            (2, b_ch.tobytes()),
        ]
        if user_mask is not None:
            ch_pairs.append((-2, user_mask.tobytes()))

        rec = bytearray()
        rec += struct.pack(">iiii", top, left, bottom, right)
        rec += struct.pack(">H", len(ch_pairs))
        ch_blobs = bytearray()
        for cid, raw_bytes in ch_pairs:
            ch_len = 2 + len(raw_bytes)
            rec += struct.pack(">hI", cid, ch_len)
            ch_blobs += struct.pack(">H", 0) + raw_bytes

        rec += b"8BIMnorm"
        # PSD layer flags bit 1 (value 2) = hidden/invisible
        flags = 0 if visible else 2
        rec += struct.pack(">BBBB", 255, 0, flags, 0)

        extra = bytearray()
        if user_mask is not None:
            mask_hdr = struct.pack(">iiiiBBH", top, left, bottom, right, 0, 0, 0)
            extra += struct.pack(">I", len(mask_hdr)) + mask_hdr
        else:
            extra += struct.pack(">I", 0)
        extra += struct.pack(">I", 0)
        extra += _pack_pascal_string(ascii_name, 4)
        extra += _pack_unicode_layer_name(unicode_name)

        rec += struct.pack(">I", len(extra)) + extra
        return bytes(rec), bytes(ch_blobs)

    records: list[bytes] = []
    channels: list[bytes] = []
    rec0, ch0 = _layer_record_and_channels(0, 0, H, W, "Base", "原图", base_rgb, None, visible=True)
    records.append(rec0)
    channels.append(ch0)

    for idx, rep_rgb in enumerate(rep_rgbs, start=1):
        a_name = "Repaired" if len(rep_rgbs) == 1 else f"Repaired_{idx:02d}"
        u_name = "局部修复" if len(rep_rgbs) == 1 else f"修复候选_{idx:02d}"
        rec_i, ch_i = _layer_record_and_channels(
            cy1, cx1, cy2, cx2, a_name, u_name, rep_rgb, mask_l, visible=(idx == 1)
        )
        records.append(rec_i)
        channels.append(ch_i)

    layer_info = struct.pack(">h", len(records)) + b"".join(records) + b"".join(channels)
    if len(layer_info) % 2:
        layer_info += b"\x00"

    layer_and_mask = struct.pack(">I", len(layer_info)) + layer_info + struct.pack(">I", 0)

    mr, mg, mb = merged.split()
    merged_data = struct.pack(">H", 0) + mr.tobytes() + mg.tobytes() + mb.tobytes()

    header = b"8BPS" + struct.pack(">H6sHIIHH", 1, b"\x00" * 6, 3, H, W, 8, 3)
    color_mode = struct.pack(">I", 0)
    image_resources = struct.pack(">I", 0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header)
        f.write(color_mode)
        f.write(image_resources)
        f.write(struct.pack(">I", len(layer_and_mask)))
        f.write(layer_and_mask)
        f.write(merged_data)


def save_pasted_output(
    base_img: Image.Image,
    repaired_imgs: Image.Image | list[Image.Image],
    crop_box: list[int],
    out_path: Path,
    feather: int = 28,
) -> None:
    """按输出扩展名自动保存为多候选分层 PSD、无损 TIFF 或 PNG/JPG。"""
    ext = out_path.suffix.lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if ext == ".psd":
        save_layered_psd(base_img, repaired_imgs, crop_box, out_path, feather=feather)
        return
    primary = repaired_imgs[0] if isinstance(repaired_imgs, list) else repaired_imgs
    final_im = paste_back_smooth(base_img, primary, crop_box, feather=feather)
    if ext in (".tif", ".tiff"):
        final_im.convert("RGB").save(out_path, format="TIFF", compression="tiff_lzw")
    elif ext in (".jpg", ".jpeg"):
        final_im.convert("RGB").save(out_path, quality=95)
    else:
        final_im.save(out_path)


def build_repair_prompt(defect_desc: str, mask_color: str = DEFAULT_MASK_COLOR) -> str:
    """生成符合瘦身红线（<=250字、无Markdown噪音）的局部色块修复提示词。"""
    color_label = "荧光洋红" if mask_color.upper() == "#FF00FF" else f"纯色（{mask_color.upper()}）"
    desc = (defect_desc or "产品局部结构与表面细节").strip()
    return (
        f"保持@图1中所有未涂色区域的产品主体、构图、背景、光影与色温完全不变。"
        f"彻底清除@图1中的{color_label}色块，严格对照@图2的产品真实结构、比例与材质，在色块位置重新绘制：{desc}。"
        f"新绘制的局部必须与@图1周围的受光方向、反射质感、景深和阴影边缘无缝自然融合。"
        f"严禁残留任何{color_label}色块边缘、改变未涂色区域或额外生成文字与杂物。"
    )


def crop_white_ref(
    white_img: Image.Image,
    white_box: list[int],
    pad: float = 0.08,
    target_ratio: str = "",
) -> Image.Image:
    """从五视图或多角度白底图中裁出最匹配待修角度的单只/局部白底参考，并轻度扩白边对齐目标比例防幻觉。"""
    rgb = white_img.convert("RGB")
    W, H = rgb.size
    x1, y1, x2, y2 = [int(v) for v in white_box]
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"非法 white_box: {white_box}")
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad), int(bh * pad)
    cx1, cy1 = _clamp(x1 - px, 0, W), _clamp(y1 - py, 0, H)
    cx2, cy2 = _clamp(x2 + px, 0, W), _clamp(y2 + py, 0, H)
    cropped = rgb.crop((cx1, cy1, cx2, cy2))

    # Optional white-canvas pad to match the repair crop's aspect ratio cleanly
    ratio_map = dict(RATIO_POOL)
    if target_ratio in ratio_map:
        tr = ratio_map[target_ratio]
        cw, ch = cropped.size
        cur = cw / ch if ch > 0 else 1.0
        if abs(cur - tr) / tr > 0.10:
            if cur < tr:
                nw, nh = int(round(ch * tr)), ch
            else:
                nw, nh = cw, int(round(cw / tr))
            canvas = Image.new("RGB", (nw, nh), (255, 255, 255))
            canvas.paste(cropped, ((nw - cw) // 2, (nh - ch) // 2))
            return canvas
    return cropped


def make_contact_sheet(pairs: list[tuple[Any, ...]], out_path: Path) -> None:
    """将多个 (标签, 原切片, 涂色块切片[, 裁切白底参考]) 拼成联系表方便 5 秒目视复核。"""
    if not pairs:
        return
    cols = max(len(p) - 1 for p in pairs)
    thumb = 320 if cols >= 3 else 360
    pad = 16
    header_h = 28
    row_h = thumb + header_h + pad
    sheet_w = thumb * cols + pad * (cols + 1)
    sheet_h = row_h * len(pairs) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (28, 28, 32))
    draw = ImageDraw.Draw(sheet)

    for idx, entry in enumerate(pairs):
        label = str(entry[0])
        imgs = list(entry[1:])
        y0 = pad + idx * row_h
        col_desc = "Left: Clean | Mid: Masked | Right: Matched Ref" if len(imgs) >= 3 else "Left: Clean | Right: Masked"
        draw.text((pad, y0 + 4), f"[{idx + 1}] {label}  ({col_desc})", fill=(235, 235, 240))
        for col, im in enumerate(imgs):
            if im is None:
                continue
            cp = im.convert("RGB")
            cp.thumbnail((thumb, thumb), Image.LANCZOS)
            x0 = pad + col * (thumb + pad) + (thumb - cp.width) // 2
            y_img = y0 + header_h + (thumb - cp.height) // 2
            sheet.paste(cp, (x0, y_img))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def _default_temp_workdir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(tempfile.gettempdir()) / "dumik-runs" / f"repair-{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_path(root: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (root / p).resolve()


def cmd_prepare_single(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir) if args.workdir else _default_temp_workdir()
    workdir.mkdir(parents=True, exist_ok=True)

    img_path = Path(args.image).resolve()
    white_ref = Path(args.white_ref).resolve()
    with Image.open(img_path) as im:
        clean_crop, masked_crop, meta = build_masked_crop(
            im,
            product_box=args.product_box,
            defect_boxes=args.defect_box,
            pad=args.pad,
            mask_color=args.mask_color,
            snap_ratio=not args.no_snap_ratio,
        )

    stem = args.name or img_path.stem
    clean_path = workdir / f"{stem}_原切片.png"
    masked_path = workdir / f"{stem}_遮罩图.png"
    meta_path = workdir / f"{stem}_meta.json"
    sheet_path = workdir / f"{stem}_预览图.png"

    clean_crop.save(clean_path)
    masked_crop.save(masked_path)

    effective_refs: list[str] = []
    preview_ref_img: Image.Image | None = None
    white_boxes = args.white_box or []
    if white_boxes:
        with Image.open(white_ref) as wim:
            for ridx, wbox in enumerate(white_boxes, start=1):
                rcrop = crop_white_ref(wim, wbox, target_ratio=meta["ratio"])
                rpath = workdir / f"{stem}_白底参考_{ridx:02d}.png"
                rcrop.save(rpath)
                effective_refs.append(str(rpath))
                if preview_ref_img is None:
                    preview_ref_img = rcrop.copy()
    else:
        effective_refs.append(str(white_ref))
        with Image.open(white_ref) as wim:
            preview_ref_img = wim.convert("RGB").copy()

    make_contact_sheet([(stem, clean_crop, masked_crop, preview_ref_img)], sheet_path)

    prompt = build_repair_prompt(args.defect_desc, mask_color=args.mask_color)
    meta.update(
        {
            "image_id": stem,
            "source_image": str(img_path),
            "white_ref": str(white_ref),
            "white_ref_crops": effective_refs,
            "clean_crop": str(clean_path),
            "masked_crop": str(masked_path),
            "preview_sheet": str(sheet_path),
            "prompt": prompt,
        }
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    source_warning = ""
    if ("_已修复" in img_path.stem) or ("_repaired" in img_path.stem.lower()):
        source_warning = (
            "检测到待修源图已是修复产物；若为重修同一部位或修独立新部位，请改用最开始的原始干净图作为 --image，避免多轮串联导致整图偏红发糊。"
        )

    result = {
        "status": "prepared",
        "workdir": str(workdir),
        "meta_path": str(meta_path),
        "preview_sheet": str(sheet_path),
        "source_warning": source_warning,
        "designflow_item": {
            "prompt": prompt,
            "ratio": meta["ratio"],
            "sizePreset": "2K",
            "count": 2,
            "models": [REPAIR_MODEL_PRIORITY[0]],
            "modelPriority": REPAIR_MODEL_PRIORITY,
            "referenceFiles": [str(masked_path), *effective_refs],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_paste_single(args: argparse.Namespace) -> int:
    meta_path = Path(args.meta).resolve()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    src_path = Path(meta["source_image"])
    fmt_ext = "." + args.format.lstrip(".").lower() if args.format else ".psd"
    out_path = Path(args.out).resolve() if args.out else src_path.with_name(f"{src_path.stem}_已修复{fmt_ext}")

    rep_paths = [Path(p).resolve() for p in args.repaired]
    rep_imgs: list[Image.Image] = []
    try:
        with Image.open(src_path) as base_im:
            for rp in rep_paths:
                rep_imgs.append(Image.open(rp))
            save_pasted_output(base_im, rep_imgs, meta["crop_box"], out_path, feather=args.feather)
    finally:
        for im in rep_imgs:
            im.close()

    if args.cleanup:
        shutil.rmtree(meta_path.parent, ignore_errors=True)

    print(
        json.dumps(
            {
                "status": "pasted",
                "out": str(out_path),
                "format": out_path.suffix.lstrip("."),
                "candidate_layers": len(rep_paths),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_prepare_batch(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    workdir = Path(args.workdir) if args.workdir else _default_temp_workdir()
    workdir.mkdir(parents=True, exist_ok=True)

    designflow_items: list[dict[str, Any]] = []
    meta_entries: list[dict[str, Any]] = []
    pairs: list[tuple[str, Image.Image, Image.Image]] = []

    for item in manifest.get("items", []):
        if item.get("verdict") in ("passed", "reroll"):
            continue
        img_id = str(item["image_id"])
        img_path = _resolve_path(root, item["image_path"])
        white_ref = _resolve_path(root, item["white_ref"])
        product_box = item["product_box"]
        defect_boxes = item.get("defect_boxes") or []
        if not defect_boxes:
            continue

        pad = float(item.get("pad", args.pad))
        mask_color = str(item.get("mask_color", args.mask_color))
        defect_desc = str(item.get("defect_desc", ""))

        with Image.open(img_path) as im:
            clean_crop, masked_crop, meta = build_masked_crop(
                im,
                product_box=product_box,
                defect_boxes=defect_boxes,
                pad=pad,
                mask_color=mask_color,
                snap_ratio=not args.no_snap_ratio,
            )

        slug = img_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
        clean_path = workdir / f"{slug}_原切片.png"
        masked_path = workdir / f"{slug}_遮罩图.png"
        clean_crop.save(clean_path)
        masked_crop.save(masked_path)

        effective_refs: list[str] = []
        preview_ref_img: Image.Image | None = None
        wboxes = item.get("white_boxes") or ([item["white_box"]] if item.get("white_box") else [])
        if wboxes:
            with Image.open(white_ref) as wim:
                for ridx, wbox in enumerate(wboxes, start=1):
                    rcrop = crop_white_ref(wim, wbox, target_ratio=meta["ratio"])
                    rpath = workdir / f"{slug}_白底参考_{ridx:02d}.png"
                    rcrop.save(rpath)
                    effective_refs.append(str(rpath))
                    if preview_ref_img is None:
                        preview_ref_img = rcrop.copy()
        else:
            effective_refs.append(str(white_ref))
            with Image.open(white_ref) as wim:
                preview_ref_img = wim.convert("RGB").copy()

        pairs.append((img_id, clean_crop, masked_crop, preview_ref_img))

        prompt = build_repair_prompt(defect_desc, mask_color=mask_color)
        meta.update(
            {
                "image_id": img_id,
                "slug": slug,
                "source_image": str(img_path),
                "white_ref": str(white_ref),
                "white_ref_crops": effective_refs,
                "clean_crop": str(clean_path),
                "masked_crop": str(masked_path),
                "out_path": str(_resolve_path(root, item["out_path"])) if item.get("out_path") else str(img_path.with_name(f"{img_path.stem}_已修复.psd")),
                "prompt": prompt,
            }
        )
        meta_entries.append(meta)
        designflow_items.append(
            {
                "id": img_id,
                "prompt": prompt,
                "ratio": meta["ratio"],
                "sizePreset": "2K",
                "count": int(item.get("count", 2)),
                "models": [str(item.get("model", REPAIR_MODEL_PRIORITY[0]))],
                "modelPriority": REPAIR_MODEL_PRIORITY,
                "referenceFiles": [str(masked_path), *effective_refs],
            }
        )

    sheet_path = workdir / "色块联系表.png"
    make_contact_sheet(pairs, sheet_path)

    batch_meta_path = workdir / "batch_meta.json"
    batch_meta_path.write_text(json.dumps({"items": meta_entries}, ensure_ascii=False, indent=2), encoding="utf-8")

    df_jobs_path = workdir / "designflow_items.json"
    df_jobs_path.write_text(json.dumps({"items": designflow_items}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "prepared_batch",
                "count": len(meta_entries),
                "workdir": str(workdir),
                "contact_sheet": str(sheet_path),
                "batch_meta": str(batch_meta_path),
                "designflow_items": str(df_jobs_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_paste_batch(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    batch_meta = json.loads((workdir / "batch_meta.json").read_text(encoding="utf-8"))
    repaired_dir = Path(args.repaired_dir).resolve()
    outputs: list[str] = []
    missing: list[str] = []

    for entry in batch_meta.get("items", []):
        slug = entry["slug"]
        cands: list[Path] = []
        # Collect numbered candidates (<slug>_01.png, <slug>_02.png, ...) or single (<slug>.png / <slug>_repaired.png)
        for p in sorted(repaired_dir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            stem = p.stem
            if stem == slug or stem == f"{slug}_已修复" or stem == f"{slug}_repaired" or stem.startswith(f"{slug}_"):
                cands.append(p)
        if not cands:
            missing.append(entry["image_id"])
            continue

        src_path = Path(entry["source_image"])
        out_path = Path(entry["out_path"])
        if args.format:
            out_path = out_path.with_suffix("." + args.format.lstrip(".").lower())
        rep_imgs: list[Image.Image] = []
        try:
            with Image.open(src_path) as base_im:
                for cp in cands:
                    rep_imgs.append(Image.open(cp))
                save_pasted_output(base_im, rep_imgs, entry["crop_box"], out_path, feather=args.feather)
        finally:
            for im in rep_imgs:
                im.close()
        outputs.append(str(out_path))

    if args.cleanup and not missing:
        shutil.rmtree(workdir, ignore_errors=True)

    print(json.dumps({"status": "pasted_batch", "count": len(outputs), "outputs": outputs, "missing": missing}, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DUMIK 产品外扩切图 + 局部色块修复脚本（单张/批量一体，零项目垃圾）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("prepare-single", help="单张切产品外扩图并涂高对比色块")
    ps.add_argument("--image", required=True, help="待修原整图路径")
    ps.add_argument("--white-ref", required=True, help="设定集白底基准图路径")
    ps.add_argument("--white-box", nargs=4, type=int, action="append", metavar=("X1", "Y1", "X2", "Y2"), help="可选：从多视角/五视图白底图中裁出最匹配角度与状态的单只区域（可多次传入），自动对齐目标比例防幻觉")
    ps.add_argument("--product-box", nargs=4, type=int, required=True, metavar=("X1", "Y1", "X2", "Y2"))
    ps.add_argument("--defect-box", nargs=4, type=int, action="append", required=True, metavar=("X1", "Y1", "X2", "Y2"), help="可重复传入多个偏差区域框")
    ps.add_argument("--defect-desc", required=True, help="一句话描述色块处按白底图应还原的具体细节")
    ps.add_argument("--pad", type=float, default=0.20, help="产品外扩比例（默认 0.20）")
    ps.add_argument("--mask-color", default=DEFAULT_MASK_COLOR, help="色块颜色（默认 #FF00FF 荧光洋红）")
    ps.add_argument("--no-snap-ratio", action="store_true", help="禁用自动吸附到标准比例池")
    ps.add_argument("--name", default="", help="输出文件名前缀")
    ps.add_argument("--workdir", default="", help="临时工作目录（默认 %%TEMP%%\\dumik-runs\\repair-*）")
    ps.set_defaults(func=cmd_prepare_single)

    pts = sub.add_parser("paste-single", help="单张修好后外扩边羽化无损贴回原整图（支持多候选叠进同一分层 PSD）")
    pts.add_argument("--meta", required=True, help="prepare-single 产出的 *_meta.json")
    pts.add_argument("--repaired", action="append", required=True, help="AI 修好的产品外扩图（可多次传入，自动叠进同一分层 PSD）")
    pts.add_argument("--out", default="", help="最终输出路径（默认同目录 *_repaired.psd，可指定 .psd/.tif/.png）")
    pts.add_argument("--format", default="psd", choices=["psd", "tif", "tiff", "png", "jpg"], help="未指定 --out 时的默认输出格式（默认 psd 分层蒙版）")
    pts.add_argument("--feather", type=int, default=28, help="外扩边羽化像素（默认 28）")
    pts.add_argument("--cleanup", action="store_true", help="贴回完成后清理临时工作目录")
    pts.set_defaults(func=cmd_paste_single)

    pb = sub.add_parser("prepare-batch", help="批量切产品外扩图、涂色块并生成联系表与并发任务")
    pb.add_argument("--manifest", required=True, help="修复清单 JSON（建议放 %%TEMP%%）")
    pb.add_argument("--project-root", default=".", help="项目根目录")
    pb.add_argument("--pad", type=float, default=0.20)
    pb.add_argument("--mask-color", default=DEFAULT_MASK_COLOR)
    pb.add_argument("--no-snap-ratio", action="store_true")
    pb.add_argument("--workdir", default="")
    pb.set_defaults(func=cmd_prepare_batch)

    ptb = sub.add_parser("paste-batch", help="批量将修好的产品外扩图无损贴回各自整图")
    ptb.add_argument("--workdir", required=True, help="prepare-batch 产出的临时目录")
    ptb.add_argument("--repaired-dir", required=True, help="存放 AI 修好图的目录（文件名匹配 <slug>.png 或 <slug>_01.png）")
    ptb.add_argument("--format", default="", choices=["", "psd", "tif", "tiff", "png", "jpg"], help="可选强制覆写批量输出格式（如 psd/tif）")
    ptb.add_argument("--feather", type=int, default=28)
    ptb.add_argument("--cleanup", action="store_true", help="全部贴回成功后清理临时目录")
    ptb.set_defaults(func=cmd_paste_batch)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
