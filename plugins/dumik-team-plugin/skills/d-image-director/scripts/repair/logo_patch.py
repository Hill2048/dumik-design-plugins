#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK 精准代码修标 / 贴标与数码屏改色引擎（OpenCV + PS 标准混合模式 + 可选 IOPaint/OpenCV 擦旧字 + 独立图层 PSD）。

适用场景：
1. 修复 AI 生图里写糊/拼错的平面或圆柱曲面丝印 LOGO、铭牌字、包装字（100% 锁定原矢量/透明标字形，0 漂移）。
2. 擦除画面中多余的假按钮小字、旧乱码后无缝贴入真标（优先调用本机 IOPaint LaMa，未装自动无缝降级 OpenCV 修补）。
3. 电子秤 / 家电黑屏数码管 LED 读数无损改色（如白字改荧光橙 + 物理多层光学外发光）。
4. 同步输出融合预览 PNG 与标准 Adobe Photoshop 多图层可编辑 `.psd`（底层原图 + 可选擦除底图 + 顶层独立透明 LOGO 图层，自带真实 PS 混合模式与不透明度）。

常用示例：
  1) 四角透视贴把手/平面丝印标（自动擦除旧残字 + 肌理置换 + 正片叠底 + 输出分层 PSD 与预览 PNG）：
     python logo_patch.py patch-logo \
       --image 原图.png --logo 透明LOGO.png \
       --rotate -90 --trim-logo --tint "#7E8288" \
       --quad 1022.5 666 1034.2 668 1031.8 773.5 1020.2 771.5 \
       --blend multiply --opacity 0.88 --displace 0.6 --softness 0.3 \
       --erase-quad --erase-engine auto \
       --out 输出_加标.psd --preview-png 输出_加标.png

  2) 圆柱曲面贴杯身/瓶身标（开启 cylinder 模式 + 弯曲弧度）：
     python logo_patch.py patch-logo \
       --image 杯子图.png --logo 透明LOGO.png \
       --mode cylinder --cylinder-curve 0.42 --cylinder-axis vertical \
       --quad 0.22 0.35 0.36 0.35 0.36 0.55 0.22 0.55 \
       --blend multiply --opacity 0.85 --displace 0.8 \
       --out 杯身加标.psd --preview-png 杯身加标.png

  3) 仅擦除按钮假字 / 局部乱码：
     python logo_patch.py erase \
       --image 原图.png --box 0.06 0.72 0.11 0.78 --box 0.23 0.78 0.28 0.84 \
       --engine auto --out 去字.psd --preview-png 去字.png

  4) 黑屏 LED 数码字无损改荧光橙（支持多屏）：
     python logo_patch.py recolor-led \
       --image 原图.png --screen-box 0.06 0.70 0.28 0.88 --screen-box 0.56 0.70 0.78 0.88 \
       --color "#FF5E00" --out 荧光橙.psd --preview-png 荧光橙.png
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageFilter

# Adobe Photoshop 4-byte blend mode signature keys
PS_BLEND_KEYS: dict[str, bytes] = {
    "normal": b"norm",
    "multiply": b"mul ",
    "screen": b"scrn",
    "overlay": b"over",
    "soft_light": b"sLit",
    "darken": b"dark",
    "lighten": b"lite",
    "linear_burn": b"lbrn",
}


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def parse_hex_rgb(color_str: str) -> tuple[int, int, int]:
    s = color_str.strip().lstrip("#")
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError(f"非法颜色值: {color_str}（请使用 #RRGGBB 如 #FF5E00）")


def resolve_box(raw_box: list[float | int], img_size: tuple[int, int]) -> list[int]:
    """支持 0~1 百分比坐标或绝对像素坐标，归一化为 [x1, y1, x2, y2]。"""
    if len(raw_box) != 4:
        raise ValueError(f"坐标框必须为 4 个数值: {raw_box}")
    w, h = img_size
    vals = [float(v) for v in raw_box]
    if all(0.0 <= v <= 1.0 for v in vals):
        x1 = _clamp_int(int(round(vals[0] * w)), 0, w)
        y1 = _clamp_int(int(round(vals[1] * h)), 0, h)
        x2 = _clamp_int(int(round(vals[2] * w)), 0, w)
        y2 = _clamp_int(int(round(vals[3] * h)), 0, h)
    else:
        x1 = _clamp_int(int(round(vals[0])), 0, w)
        y1 = _clamp_int(int(round(vals[1])), 0, h)
        x2 = _clamp_int(int(round(vals[2])), 0, w)
        y2 = _clamp_int(int(round(vals[3])), 0, h)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"非法坐标框: {raw_box} -> [{x1}, {y1}, {x2}, {y2}]")
    return [x1, y1, x2, y2]


def resolve_quad(raw_pts: list[float | int], img_size: tuple[int, int]) -> np.ndarray:
    """支持 0~1 百分比或绝对像素 8 数值（顺时针 TL, TR, BR, BL），返回 float32 (4, 2)。"""
    if len(raw_pts) != 8:
        raise ValueError(f"四角坐标必须为 8 个数值 (x1 y1 x2 y2 x3 y3 x4 y4): {raw_pts}")
    w, h = img_size
    vals = [float(v) for v in raw_pts]
    pts = np.array(vals, dtype=np.float32).reshape(4, 2)
    if np.all((pts >= 0.0) & (pts <= 1.0)):
        pts[:, 0] *= float(w)
        pts[:, 1] *= float(h)
    return pts


def prepare_logo_rgba(
    logo_img: Image.Image,
    crop_box: list[float | int] | None = None,
    trim: bool = True,
    rotate_deg: float = 0.0,
    tint_hex: str | None = None,
    drop_reg_mark: bool = False,
) -> Image.Image:
    """预处理透明底 LOGO：可选裁切、去右上角小 ®、紧裁透明边、旋转、重新着色。"""
    rgba = logo_img.convert("RGBA")
    if crop_box is not None:
        bx1, by1, bx2, by2 = resolve_box(crop_box, rgba.size)
        rgba = rgba.crop((bx1, by1, bx2, by2))

    arr = np.array(rgba, dtype=np.uint8)
    if drop_reg_mark and arr.shape[0] > 10 and arr.shape[1] > 10:
        # Remove small isolated component located in the top-right corner (e.g., ® / ™)
        mask = (arr[..., 3] > 20).astype(np.uint8)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        h, w = mask.shape
        total_fg = max(1, int(mask.sum()))
        for lbl in range(1, num_labels):
            x = int(stats[lbl, cv2.CC_STAT_LEFT])
            y = int(stats[lbl, cv2.CC_STAT_TOP])
            cw = int(stats[lbl, cv2.CC_STAT_WIDTH])
            ch = int(stats[lbl, cv2.CC_STAT_HEIGHT])
            area = int(stats[lbl, cv2.CC_STAT_AREA])
            if x > w * 0.85 and (y + ch) < h * 0.35 and area < total_fg * 0.03:
                arr[labels == lbl] = 0

    if trim:
        ys, xs = np.where(arr[..., 3] > 8)
        if len(ys) > 0 and len(xs) > 0:
            arr = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]

    if tint_hex:
        tr, tg, tb = parse_hex_rgb(tint_hex)
        arr = arr.copy()
        arr[..., 0] = tr
        arr[..., 1] = tg
        arr[..., 2] = tb

    out = Image.fromarray(arr, mode="RGBA")
    if abs(rotate_deg) > 1e-4:
        # Upscale before arbitrary rotation for crisp edges, then keep high-res for perspective warp
        hi = out.resize((max(1, out.width * 2), max(1, out.height * 2)), Image.LANCZOS)
        out = hi.rotate(rotate_deg, expand=True, resample=Image.BICUBIC)
        if trim:
            a2 = np.array(out)
            ys, xs = np.where(a2[..., 3] > 8)
            if len(ys) > 0 and len(xs) > 0:
                out = Image.fromarray(a2[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], mode="RGBA")
    return out


def apply_cylindrical_bend(
    logo_rgba: np.ndarray,
    curve: float = 0.40,
    axis: str = "vertical",
    bow: float = 0.08,
) -> np.ndarray:
    """
    OpenCV `cv2.remap` 圆柱曲面投影：
    - axis='vertical': 贴在竖直圆柱面（马克杯/水杯/瓶身），左右边缘按正弦弧面自然透视压缩并略带弧形弯拱；
    - axis='horizontal': 贴在水平圆柱面（横置瓶罐/圆管把手），上下边缘自然弯曲压缩；
    - curve (0..1): 圆柱包覆弧度（0.35~0.55 最接近杯身正面视角）；
    - bow (-0.3..0.3): 俯仰视角导致的弧线上下弯曲量（正值向下微笑弧，负值向上拱弧）。
    """
    if curve <= 1e-4 and abs(bow) <= 1e-4:
        return logo_rgba

    h, w = logo_rgba.shape[:2]
    # Add small vertical/horizontal padding so curved bow never clips strokes
    pad_y = max(4, int(round(h * abs(bow) * 1.4))) if axis == "vertical" else 4
    pad_x = max(4, int(round(w * abs(bow) * 1.4))) if axis == "horizontal" else 4
    padded = cv2.copyMakeBorder(logo_rgba, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    ph, pw = padded.shape[:2]

    gx, gy = np.meshgrid(np.arange(pw, dtype=np.float32), np.arange(ph, dtype=np.float32))
    half_angle = max(0.05, min(1.35, float(curve) * (math.pi / 2.0)))
    sin_max = math.sin(half_angle)

    if axis == "vertical":
        # Normalized horizontal coordinate u in [-1, 1] across original logo span
        cx = (pw - 1) * 0.5
        half_w = max(1.0, (w - 1) * 0.5)
        u = (gx - cx) / half_w
        valid = np.abs(u) <= 1.0
        u_clamped = np.clip(u, -1.0, 1.0)
        # Inverse cylindrical projection: screen x = R * sin(theta) -> theta = arcsin(u * sin_max)
        theta = np.arcsin(np.clip(u_clamped * sin_max, -0.9999, 0.9999))
        src_u = theta / half_angle  # [-1, 1] in flat unwrapped logo
        map_x = cx + src_u * half_w
        # Vertical perspective bow along cylinder rim: cos(theta) drops toward edges
        cos_drop = 1.0 - np.cos(theta)
        max_drop = max(1e-5, 1.0 - math.cos(half_angle))
        bow_shift = (cos_drop / max_drop) * (bow * h)
        map_y = gy - bow_shift
        # Mark outside valid span to -1 so BORDER_CONSTANT makes it transparent
        map_x = np.where(valid, map_x, -10.0).astype(np.float32)
        map_y = np.where(valid, map_y, -10.0).astype(np.float32)
    else:
        cy = (ph - 1) * 0.5
        half_h = max(1.0, (h - 1) * 0.5)
        v = (gy - cy) / half_h
        valid = np.abs(v) <= 1.0
        v_clamped = np.clip(v, -1.0, 1.0)
        theta = np.arcsin(np.clip(v_clamped * sin_max, -0.9999, 0.9999))
        src_v = theta / half_angle
        map_y = cy + src_v * half_h
        cos_drop = 1.0 - np.cos(theta)
        max_drop = max(1e-5, 1.0 - math.cos(half_angle))
        bow_shift = (cos_drop / max_drop) * (bow * w)
        map_x = gx - bow_shift
        map_x = np.where(valid, map_x, -10.0).astype(np.float32)
        map_y = np.where(valid, map_y, -10.0).astype(np.float32)

    warped = cv2.remap(
        padded,
        map_x,
        map_y,
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    # Trim excess transparent border after bend
    ys, xs = np.where(warped[..., 3] > 4)
    if len(ys) > 0 and len(xs) > 0:
        warped = warped[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return warped


def apply_surface_displacement(
    warped_rgba: np.ndarray,
    bg_rgb: np.ndarray,
    strength: float = 0.6,
) -> np.ndarray:
    """
    OpenCV `cv2.remap` 表面肌理置换：
    从目标区域底图提取高频微起伏（如雪花钛结晶、磨砂金属、拉丝纹或布纹），
    驱动贴标像素产生亚像素微位移，消除平直贴纸感。
    """
    if strength <= 1e-4:
        return warped_rgba

    h, w = warped_rgba.shape[:2]
    gray = cv2.cvtColor(bg_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    # High-pass surface height detail (removes slow shading gradients, keeps micro-texture)
    smooth = cv2.GaussianBlur(gray, (0, 0), sigmaX=4.0)
    high = gray - smooth
    # Compute surface gradients dx, dy
    dx = cv2.Sobel(high, cv2.CV_32F, 1, 0, ksize=3) / 128.0
    dy = cv2.Sobel(high, cv2.CV_32F, 0, 1, ksize=3) / 128.0
    # Clamp micro displacement so strokes remain crisp and never break
    max_px = min(2.5, float(strength) * 1.8)
    dx = np.clip(dx * strength, -max_px, max_px)
    dy = np.clip(dy * strength, -max_px, max_px)

    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = (gx + dx).astype(np.float32)
    map_y = (gy + dy).astype(np.float32)
    return cv2.remap(
        warped_rgba,
        map_x,
        map_y,
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def warp_logo_onto_roi(
    logo_rgba_img: Image.Image,
    bg_rgb_full: np.ndarray,
    dst_quad: np.ndarray,
    mode: str = "perspective",
    cylinder_curve: float = 0.40,
    cylinder_axis: str = "vertical",
    cylinder_bow: float = 0.08,
    displace: float = 0.5,
    softness: float = 0.30,
    supersample: int = 4,
) -> tuple[np.ndarray, list[int]]:
    """
    将透明 LOGO 高精度超采样透视（可选圆柱弯曲 + 表面肌理置换）映射到原图局部 ROI。
    返回 (warped_rgba_uint8_in_roi, [rx1, ry1, rx2, ry2])。
    """
    H, W = bg_rgb_full.shape[:2]
    # Compute tight ROI around dst_quad with comfortable padding
    pad = 24
    rx1 = _clamp_int(int(math.floor(float(dst_quad[:, 0].min()))) - pad, 0, W)
    ry1 = _clamp_int(int(math.floor(float(dst_quad[:, 1].min()))) - pad, 0, H)
    rx2 = _clamp_int(int(math.ceil(float(dst_quad[:, 0].max()))) + pad, 0, W)
    ry2 = _clamp_int(int(math.ceil(float(dst_quad[:, 1].max()))) + pad, 0, H)
    rw, rh = rx2 - rx1, ry2 - ry1
    if rw <= 0 or rh <= 0:
        raise ValueError(f"四角坐标完全超出画布范围: {dst_quad.tolist()}")

    # Prepare high-res source RGBA (upscale small logos first for crisp strokes)
    src_arr = np.array(logo_rgba_img.convert("RGBA"), dtype=np.uint8)
    min_dim = min(src_arr.shape[0], src_arr.shape[1])
    if min_dim < 240:
        up = max(2, int(math.ceil(240.0 / max(1, min_dim))))
        src_arr = cv2.resize(src_arr, (src_arr.shape[1] * up, src_arr.shape[0] * up), interpolation=cv2.INTER_LANCZOS4)

    if mode == "cylinder":
        src_arr = apply_cylindrical_bend(src_arr, curve=cylinder_curve, axis=cylinder_axis, bow=cylinder_bow)

    sh, sw = src_arr.shape[:2]
    src_pts = np.array([[0, 0], [sw - 1, 0], [sw - 1, sh - 1], [0, sh - 1]], dtype=np.float32)

    ss = max(1, min(4, int(supersample)))
    local_dst_hi = (dst_quad - np.array([rx1, ry1], dtype=np.float32)) * float(ss)
    M = cv2.getPerspectiveTransform(src_pts, local_dst_hi)

    # Premultiply RGB by alpha before perspective warp to prevent dark/white fringe halos
    src_f = src_arr.astype(np.float32)
    a_f = src_f[..., 3:4] / 255.0
    src_premult = np.concatenate([src_f[..., :3] * a_f, src_f[..., 3:4]], axis=-1)

    warped_hi = cv2.warpPerspective(
        src_premult,
        M,
        (rw * ss, rh * ss),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    warped_premult = cv2.resize(warped_hi, (rw, rh), interpolation=cv2.INTER_AREA)

    # Un-premultiply cleanly
    wa = np.clip(warped_premult[..., 3:4], 0.0, 255.0)
    safe_a = np.where(wa > 1.0, wa / 255.0, 1.0)
    wrgb = np.where(wa > 1.0, np.clip(warped_premult[..., :3] / safe_a, 0.0, 255.0), 0.0)
    warped_rgba = np.concatenate([wrgb, wa], axis=-1).astype(np.uint8)

    # Surface texture displacement (uses background micro-texture in ROI; auto-damped on narrow <28px strips to prevent smearing thin strokes)
    bg_roi = bg_rgb_full[ry1:ry2, rx1:rx2]
    edge_lens = [
        float(np.linalg.norm(dst_quad[1] - dst_quad[0])),
        float(np.linalg.norm(dst_quad[2] - dst_quad[1])),
        float(np.linalg.norm(dst_quad[3] - dst_quad[2])),
        float(np.linalg.norm(dst_quad[0] - dst_quad[3])),
    ]
    min_edge = min(edge_lens)
    eff_displace = float(displace) * min(1.0, max(0.0, (min_edge - 16.0) / 20.0)) if min_edge < 36.0 else float(displace)
    if eff_displace > 1e-4:
        warped_rgba = apply_surface_displacement(warped_rgba, bg_roi, strength=eff_displace)

    # Subtle optical lens softness matching real camera MTF on product surfaces
    if softness > 1e-4:
        k_sigma = float(softness)
        a_blur = cv2.GaussianBlur(warped_rgba[..., 3].astype(np.float32), (0, 0), sigmaX=k_sigma)
        warped_rgba = warped_rgba.copy()
        warped_rgba[..., 3] = np.clip(a_blur, 0, 255).astype(np.uint8)

    return warped_rgba, [rx1, ry1, rx2, ry2]


def apply_ps_blend(
    bg_rgb: np.ndarray,
    fg_rgba: np.ndarray,
    blend: str = "multiply",
    opacity: float = 0.88,
) -> np.ndarray:
    """
    标准 Adobe Photoshop 混合模式（向量化 float32 实现，100% 兼容 NumPy 2.x）：
    bg_rgb: HxWx3 uint8/float32 [0..255]
    fg_rgba: HxWx4 uint8/float32 [0..255]
    """
    b_key = blend.strip().lower()
    if b_key not in PS_BLEND_KEYS:
        raise ValueError(f"不支持的混合模式: {blend}（支持: {', '.join(PS_BLEND_KEYS.keys())}）")

    B = bg_rgb.astype(np.float32) / 255.0
    S = fg_rgba[..., :3].astype(np.float32) / 255.0
    A = (fg_rgba[..., 3:4].astype(np.float32) / 255.0) * float(np.clip(opacity, 0.0, 1.0))

    if b_key == "normal":
        blended = S
    elif b_key == "multiply":
        blended = B * S
    elif b_key == "screen":
        blended = 1.0 - (1.0 - B) * (1.0 - S)
    elif b_key == "overlay":
        blended = np.where(B <= 0.5, 2.0 * B * S, 1.0 - 2.0 * (1.0 - B) * (1.0 - S))
    elif b_key == "soft_light":
        # W3C / Adobe PDF Soft Light specification
        d = np.where(B <= 0.25, ((16.0 * B - 12.0) * B + 4.0) * B, np.sqrt(np.clip(B, 0.0, 1.0)))
        blended = np.where(
            S <= 0.5,
            B - (1.0 - 2.0 * S) * B * (1.0 - B),
            B + (2.0 * S - 1.0) * (d - B),
        )
    elif b_key == "darken":
        blended = np.minimum(B, S)
    elif b_key == "lighten":
        blended = np.maximum(B, S)
    elif b_key == "linear_burn":
        blended = np.clip(B + S - 1.0, 0.0, 1.0)
    else:
        blended = S

    out = B * (1.0 - A) + np.clip(blended, 0.0, 1.0) * A
    return np.clip(out * 255.0, 0.0, 255.0).astype(np.uint8)


def _find_iopaint_cmd() -> list[str] | None:
    exe = shutil.which("iopaint")
    if exe:
        return [exe]
    try:
        import importlib.util

        if importlib.util.find_spec("iopaint") is not None:
            return [sys.executable, "-m", "iopaint"]
    except Exception:
        pass
    return None


def erase_regions(
    img_rgb: np.ndarray,
    boxes: list[list[int]] | None = None,
    polygons: list[np.ndarray] | None = None,
    engine: str = "auto",
    inpaint_radius: int = 5,
    iopaint_device: str = "cpu",
) -> tuple[np.ndarray, np.ndarray, str]:
    """
    无痕擦除指定矩形/多边形区域（旧乱码 LOGO、按钮假字等）。
    返回 (cleaned_rgb, erase_mask_u8, actual_engine_used)。
    - engine='iopaint': 调用本机 `iopaint run --model=lama`
    - engine='opencv': 调用 OpenCV `INPAINT_TELEA` 并保留平滑过渡
    - engine='auto': 本机有 iopaint 优先用 LaMa，否则无缝降级 opencv
    """
    H, W = img_rgb.shape[:2]
    mask = np.zeros((H, W), dtype=np.uint8)
    for bx1, by1, bx2, by2 in boxes or []:
        cv2.rectangle(mask, (bx1, by1), (bx2, by2), 255, thickness=-1)
    for poly in polygons or []:
        pts_i = np.round(poly).astype(np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts_i], 255)

    if int(mask.max()) == 0 or engine == "none":
        return img_rgb.copy(), mask, "none"

    iopaint_cmd = _find_iopaint_cmd() if engine in ("auto", "iopaint") else None
    if engine == "iopaint" and iopaint_cmd is None:
        raise RuntimeError("未检测到本机安装的 iopaint，请先运行 `pip install iopaint` 或改传 `--erase-engine opencv`。")

    if iopaint_cmd is not None:
        with tempfile.TemporaryDirectory(prefix="dumik-iopaint-") as td:
            td_p = Path(td)
            in_dir = td_p / "in"
            mk_dir = td_p / "mask"
            out_dir = td_p / "out"
            in_dir.mkdir()
            mk_dir.mkdir()
            out_dir.mkdir()
            img_file = in_dir / "target.png"
            mask_file = mk_dir / "target.png"
            Image.fromarray(img_rgb, mode="RGB").save(img_file)
            Image.fromarray(mask, mode="L").save(mask_file)
            cmd = [
                *iopaint_cmd,
                "run",
                "--model=lama",
                f"--device={iopaint_device}",
                f"--image={in_dir}",
                f"--mask={mk_dir}",
                f"--output={out_dir}",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out_file = out_dir / "target.png"
            if proc.returncode == 0 and out_file.is_file():
                cleaned = np.array(Image.open(out_file).convert("RGB"), dtype=np.uint8)
                return cleaned, mask, "iopaint-lama"
            if engine == "iopaint":
                raise RuntimeError(f"IOPaint 执行失败: {proc.stderr[-400:]}")

    # OpenCV local fast inpainting fallback (runs strictly on padded local bbox for speed & crispness)
    ys, xs = np.where(mask > 0)
    pad = max(24, inpaint_radius * 4)
    rx1 = _clamp_int(int(xs.min()) - pad, 0, W)
    ry1 = _clamp_int(int(ys.min()) - pad, 0, H)
    rx2 = _clamp_int(int(xs.max()) + pad + 1, 0, W)
    ry2 = _clamp_int(int(ys.max()) + pad + 1, 0, H)

    roi_bgr = cv2.cvtColor(img_rgb[ry1:ry2, rx1:rx2], cv2.COLOR_RGB2BGR)
    roi_mask = cv2.dilate(mask[ry1:ry2, rx1:rx2], np.ones((3, 3), np.uint8), iterations=1)
    inpainted_bgr = cv2.inpaint(roi_bgr, roi_mask, inpaintRadius=max(2, int(inpaint_radius)), flags=cv2.INPAINT_TELEA)
    inpainted_rgb = cv2.cvtColor(inpainted_bgr, cv2.COLOR_BGR2RGB)

    # Transfer real high-frequency micro-texture from surrounding clean border onto inpainted interior
    roi_orig = img_rgb[ry1:ry2, rx1:rx2].astype(np.float32)
    roi_smooth = cv2.GaussianBlur(roi_orig, (0, 0), sigmaX=3.0)
    high_freq = roi_orig - roi_smooth
    rh_i, rw_i = roi_mask.shape
    ring = cv2.dilate(roi_mask, np.ones((15, 15), np.uint8), iterations=1) - roi_mask
    if int((ring > 0).sum()) > 40:
        # Mirror-shift high-frequency texture from nearby clean pixels (preserves crystal/brushed grain)
        ys_r, xs_r = np.where(ring > 0)
        ys_m, xs_m = np.where(roi_mask > 0)
        if len(ys_m) > 0:
            # Estimate dominant offset from mask center to cleanest neighboring strip
            mw = int(xs_m.max() - xs_m.min()) + 4
            mh = int(ys_m.max() - ys_m.min()) + 4
            if mw <= mh and (xs_m.max() + mw < rw_i or xs_m.min() - mw >= 0):
                shift_x = mw if (xs_m.max() + mw < rw_i) else -mw
                shift_y = 0
            else:
                shift_x = 0
                shift_y = mh if (ys_m.max() + mh < rh_i) else -mh
            src_y = np.clip(ys_m + shift_y, 0, rh_i - 1)
            src_x = np.clip(xs_m + shift_x, 0, rw_i - 1)
            patched = inpainted_rgb.astype(np.float32)
            patched[ys_m, xs_m] = np.clip(patched[ys_m, xs_m] + high_freq[src_y, src_x] * 0.85, 0, 255)
            inpainted_rgb = patched.astype(np.uint8)

    feather = cv2.GaussianBlur(roi_mask.astype(np.float32) / 255.0, (0, 0), sigmaX=1.2)[..., None]
    out_full = img_rgb.copy()
    blended_roi = img_rgb[ry1:ry2, rx1:rx2].astype(np.float32) * (1.0 - feather) + inpainted_rgb.astype(np.float32) * feather
    out_full[ry1:ry2, rx1:rx2] = np.clip(blended_roi, 0, 255).astype(np.uint8)
    return out_full, mask, "opencv-telea"


def recolor_led_screens(
    img_rgb: np.ndarray,
    screen_boxes: list[list[int]],
    color_hex: str = "#FF5E00",
    glow_strength: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """
    将电子秤/家电黑屏数码管发光字无损改色（带物理多层外发光，严格限制在黑屏玻璃内零溢色）。
    返回 (merged_rgb, overlay_rgba_in_union_roi, union_roi_box)。
    """
    tr, tg, tb = parse_hex_rgb(color_hex)
    tr_f, tg_f, tb_f = float(tr), float(tg), float(tb)
    # Slight bright core lift along target hue (keeps orange vivid orange, not yellow)
    core_r = min(255.0, tr_f * 1.0 + 25.0)
    core_g = min(255.0, tg_f * 1.32 + 12.0)
    core_b = min(255.0, tb_f * 1.25 + 22.0)

    H, W = img_rgb.shape[:2]
    out = img_rgb.astype(np.float32).copy()
    full_overlay = np.zeros((H, W, 4), dtype=np.uint8)

    ux1, uy1, ux2, uy2 = W, H, 0, 0
    for bx1, by1, bx2, by2 in screen_boxes:
        ux1, uy1 = min(ux1, bx1), min(uy1, by1)
        ux2, uy2 = max(ux2, bx2), max(uy2, by2)
        roi = out[by1:by2, bx1:bx2].copy()
        lum = 0.299 * roi[..., 0] + 0.587 * roi[..., 1] + 0.114 * roi[..., 2]
        dark = (lum < 85.0).astype(np.uint8)
        n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
        if n_lbl <= 1:
            continue
        screen_lbl = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        screen_mask = (labels == screen_lbl).astype(np.uint8)
        # Fill holes inside black screen (digits sit inside screen)
        contours, _ = cv2.findContours(screen_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(screen_mask)
        cv2.drawContours(filled, contours, -1, 1, thickness=-1)
        inner = cv2.erode(filled, np.ones((3, 3), np.uint8), iterations=1)

        digit_raw = np.clip((lum - 58.0) / (235.0 - 58.0), 0.0, 1.0) * inner.astype(np.float32)
        d_bin = (digit_raw > 0.15).astype(np.uint8)
        dn, dlbl, dstats, _ = cv2.connectedComponentsWithStats(d_bin, connectivity=8)
        valid = np.zeros_like(d_bin)
        for i in range(1, dn):
            if int(dstats[i, cv2.CC_STAT_AREA]) >= 20:
                valid[dlbl == i] = 1
        valid_aa = cv2.dilate(valid, np.ones((7, 7), np.uint8), iterations=1)
        digit_alpha = digit_raw * valid_aa.astype(np.float32)

        dark_bg = np.array([14.0, 13.0, 12.0], dtype=np.float32)
        base = roi * (1.0 - digit_alpha[..., None]) + dark_bg * digit_alpha[..., None]

        core = np.clip((digit_alpha - 0.65) / 0.35, 0.0, 1.0) ** 1.5
        led_r = np.clip(tr_f * digit_alpha + (core_r - tr_f) * core, 0, 255)
        led_g = np.clip(tg_f * digit_alpha + (core_g - tg_f) * core, 0, 255)
        led_b = np.clip(tb_f * digit_alpha + (core_b - tb_f) * core, 0, 255)
        led_rgb = np.stack([led_r, led_g, led_b], axis=-1)

        mask_f = filled.astype(np.float32)[..., None]
        g_tight = cv2.GaussianBlur(digit_alpha, (0, 0), sigmaX=2.8)
        g_mid = cv2.GaussianBlur(digit_alpha, (0, 0), sigmaX=9.0)
        g_wide = cv2.GaussianBlur(digit_alpha, (0, 0), sigmaX=22.0)

        halo_only = np.clip(1.0 - digit_alpha, 0.0, 1.0)
        gs = float(glow_strength)
        # Keep bloom deeply saturated in target color without overshooting core
        b_r = (g_tight * (tr_f * 0.68) + g_mid * (tr_f * 0.41) + g_wide * (tr_f * 0.19)) * gs
        b_g = (g_tight * (tg_f * 0.40) + g_mid * (tg_f * 0.22) + g_wide * (tg_f * 0.09)) * halo_only * gs
        b_b = (g_tight * (tb_f * 0.35) + g_mid * (tb_f * 0.18)) * halo_only * gs
        bloom = np.stack([b_r, b_g, b_b], axis=-1) * mask_f

        out_roi = np.clip(base + led_rgb + bloom, 0.0, 255.0)
        out_roi = np.where(mask_f > 0.5, out_roi, roi)
        out[by1:by2, bx1:bx2] = out_roi

        # Store screen-masked edited layer for PSD editability
        ov = np.zeros((by2 - by1, bx2 - bx1, 4), dtype=np.uint8)
        ov[..., :3] = out_roi.astype(np.uint8)
        ov[..., 3] = (filled * 255).astype(np.uint8)
        full_overlay[by1:by2, bx1:bx2] = ov

    merged_u8 = np.clip(out, 0, 255).astype(np.uint8)
    if ux2 <= ux1 or uy2 <= uy1:
        return merged_u8, np.zeros((1, 1, 4), dtype=np.uint8), [0, 0, 1, 1]
    return merged_u8, full_overlay[uy1:uy2, ux1:ux2], [ux1, uy1, ux2, uy2]


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


def save_multilayer_psd(
    base_rgb: np.ndarray,
    merged_rgb: np.ndarray,
    layers: list[dict[str, Any]],
    out_path: Path,
) -> None:
    """
    零外部依赖写出标准 Adobe Photoshop 8-bit RGB 多图层 PSD：
    - 底层「原图」：完整原始底图（RGB，正常 100%）
    - 额外每个图层支持：
        - `name_ascii` / `name_unicode`: 中英文图层名
        - `box`: [x1, y1, x2, y2] 图层在整图中的精确坐标
        - `rgba`: HxWx4 uint8（写入真实 Alpha 透明通道 channel_id=-1 + R/G/B）
        - `blend`: 'normal' | 'multiply' | 'soft_light' | 'overlay' | 'screen' | ...（真实 PS 混合模式键）
        - `opacity`: 0.0~1.0（真实 PS 不透明度字节 0~255）
        - `visible`: bool
    - 末尾写入 `merged_rgb` 合成预览，Windows / Eagle / 飞书 / PS 均可秒开预览。
    """
    H, W = base_rgb.shape[:2]

    def _build_layer(
        top: int,
        left: int,
        bottom: int,
        right: int,
        ascii_name: str,
        unicode_name: str,
        rgb_or_rgba: np.ndarray,
        blend: str = "normal",
        opacity: float = 1.0,
        visible: bool = True,
    ) -> tuple[bytes, bytes]:
        has_alpha = rgb_or_rgba.ndim == 3 and rgb_or_rgba.shape[2] == 4
        ch_pairs: list[tuple[int, bytes]] = []
        if has_alpha:
            ch_pairs.append((-1, np.ascontiguousarray(rgb_or_rgba[..., 3]).tobytes()))
        ch_pairs.append((0, np.ascontiguousarray(rgb_or_rgba[..., 0]).tobytes()))
        ch_pairs.append((1, np.ascontiguousarray(rgb_or_rgba[..., 1]).tobytes()))
        ch_pairs.append((2, np.ascontiguousarray(rgb_or_rgba[..., 2]).tobytes()))

        rec = bytearray()
        rec += struct.pack(">iiii", top, left, bottom, right)
        rec += struct.pack(">H", len(ch_pairs))
        ch_blobs = bytearray()
        for cid, raw_bytes in ch_pairs:
            ch_len = 2 + len(raw_bytes)
            rec += struct.pack(">hI", cid, ch_len)
            ch_blobs += struct.pack(">H", 0) + raw_bytes  # compression=0 (raw)

        blend_key = PS_BLEND_KEYS.get(blend.lower(), b"norm")
        op_byte = _clamp_int(int(round(float(opacity) * 255.0)), 0, 255)
        flags = 0 if visible else 2
        rec += b"8BIM" + blend_key
        rec += struct.pack(">BBBB", op_byte, 0, flags, 0)

        extra = bytearray()
        extra += struct.pack(">I", 0)  # Layer mask data length = 0
        extra += struct.pack(">I", 0)  # Layer blending ranges length = 0
        extra += _pack_pascal_string(ascii_name, 4)
        extra += _pack_unicode_layer_name(unicode_name)
        rec += struct.pack(">I", len(extra)) + extra
        return bytes(rec), bytes(ch_blobs)

    records: list[bytes] = []
    channels: list[bytes] = []

    r0, c0 = _build_layer(0, 0, H, W, "Base", "原图", base_rgb, blend="normal", opacity=1.0, visible=True)
    records.append(r0)
    channels.append(c0)

    for layer in layers:
        x1, y1, x2, y2 = [int(v) for v in layer["box"]]
        ri, ci = _build_layer(
            top=y1,
            left=x1,
            bottom=y2,
            right=x2,
            ascii_name=str(layer["name_ascii"]),
            unicode_name=str(layer["name_unicode"]),
            rgb_or_rgba=layer["rgba"],
            blend=str(layer.get("blend", "normal")),
            opacity=float(layer.get("opacity", 1.0)),
            visible=bool(layer.get("visible", True)),
        )
        records.append(ri)
        channels.append(ci)

    layer_info = struct.pack(">h", len(records)) + b"".join(records) + b"".join(channels)
    if len(layer_info) % 2:
        layer_info += b"\x00"
    layer_and_mask = struct.pack(">I", len(layer_info)) + layer_info + struct.pack(">I", 0)

    mr = np.ascontiguousarray(merged_rgb[..., 0]).tobytes()
    mg = np.ascontiguousarray(merged_rgb[..., 1]).tobytes()
    mb = np.ascontiguousarray(merged_rgb[..., 2]).tobytes()
    merged_data = struct.pack(">H", 0) + mr + mg + mb

    header = b"8BPS" + struct.pack(">H6sHIIHH", 1, b"\x00" * 6, 3, H, W, 8, 3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header)
        f.write(struct.pack(">I", 0))  # color mode data
        f.write(struct.pack(">I", 0))  # image resources
        f.write(struct.pack(">I", len(layer_and_mask)))
        f.write(layer_and_mask)
        f.write(merged_data)


def _save_flat_image(rgb: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(rgb, mode="RGB")
    ext = out_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        im.save(out_path, quality=96)
    elif ext in (".tif", ".tiff"):
        im.save(out_path, format="TIFF", compression="tiff_lzw")
    else:
        im.save(out_path, format="PNG")


def cmd_patch_logo(args: argparse.Namespace) -> int:
    img_path = Path(args.image).resolve()
    logo_path = Path(args.logo).resolve()
    out_path = Path(args.out).resolve()

    base_rgb = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)
    H, W = base_rgb.shape[:2]

    dst_quad = resolve_quad(args.quad, (W, H))

    # Optional erase of existing garbled logo / text before placing real logo
    erase_boxes = [resolve_box(b, (W, H)) for b in (args.erase_box or [])]
    erase_polys = [dst_quad] if args.erase_quad else []
    working_rgb = base_rgb.copy()
    erase_engine_used = "none"
    psd_layers: list[dict[str, Any]] = []

    if erase_boxes or erase_polys:
        cleaned_rgb, erase_mask, erase_engine_used = erase_regions(
            working_rgb,
            boxes=erase_boxes,
            polygons=erase_polys,
            engine=args.erase_engine,
            inpaint_radius=args.inpaint_radius,
            iopaint_device=args.iopaint_device,
        )
        if erase_engine_used != "none":
            ys, xs = np.where(erase_mask > 0)
            if len(ys) > 0:
                ex1 = _clamp_int(int(xs.min()) - 8, 0, W)
                ey1 = _clamp_int(int(ys.min()) - 8, 0, H)
                ex2 = _clamp_int(int(xs.max()) + 9, 0, W)
                ey2 = _clamp_int(int(ys.max()) + 9, 0, H)
                e_alpha = cv2.GaussianBlur(erase_mask[ey1:ey2, ex1:ex2].astype(np.float32), (0, 0), sigmaX=1.2)
                e_rgba = np.concatenate(
                    [cleaned_rgb[ey1:ey2, ex1:ex2], np.clip(e_alpha, 0, 255).astype(np.uint8)[..., None]],
                    axis=-1,
                )
                psd_layers.append(
                    {
                        "name_ascii": "Erased_Base",
                        "name_unicode": "擦除旧字层",
                        "box": [ex1, ey1, ex2, ey2],
                        "rgba": e_rgba,
                        "blend": "normal",
                        "opacity": 1.0,
                        "visible": True,
                    }
                )
            working_rgb = cleaned_rgb

    with Image.open(logo_path) as lim:
        logo_prepared = prepare_logo_rgba(
            lim,
            crop_box=args.logo_crop,
            trim=not args.no_trim_logo,
            rotate_deg=args.rotate,
            tint_hex=args.tint,
            drop_reg_mark=bool(args.drop_reg),
        )

    warped_rgba, roi_box = warp_logo_onto_roi(
        logo_prepared,
        working_rgb,
        dst_quad,
        mode=args.mode,
        cylinder_curve=args.cylinder_curve,
        cylinder_axis=args.cylinder_axis,
        cylinder_bow=args.cylinder_bow,
        displace=args.displace,
        softness=args.softness,
    )
    rx1, ry1, rx2, ry2 = roi_box

    merged_rgb = working_rgb.copy()
    merged_rgb[ry1:ry2, rx1:rx2] = apply_ps_blend(
        working_rgb[ry1:ry2, rx1:rx2],
        warped_rgba,
        blend=args.blend,
        opacity=args.opacity,
    )

    psd_layers.append(
        {
            "name_ascii": "Logo_Patch",
            "name_unicode": args.layer_name or "LOGO精修层",
            "box": roi_box,
            "rgba": warped_rgba,
            "blend": args.blend,
            "opacity": args.opacity,
            "visible": True,
        }
    )

    if out_path.suffix.lower() == ".psd":
        save_multilayer_psd(base_rgb, merged_rgb, psd_layers, out_path)
    else:
        _save_flat_image(merged_rgb, out_path)

    preview_path_str = ""
    if args.preview_png:
        prev_p = Path(args.preview_png).resolve()
        _save_flat_image(merged_rgb, prev_p)
        preview_path_str = str(prev_p)

    print(
        json.dumps(
            {
                "status": "patched",
                "mode": args.mode,
                "blend": args.blend,
                "opacity": args.opacity,
                "displace": args.displace,
                "erase_engine": erase_engine_used,
                "roi_box": roi_box,
                "out": str(out_path),
                "preview_png": preview_path_str,
                "layers": ["原图", *[l["name_unicode"] for l in psd_layers]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_erase(args: argparse.Namespace) -> int:
    img_path = Path(args.image).resolve()
    out_path = Path(args.out).resolve()
    base_rgb = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)
    H, W = base_rgb.shape[:2]

    boxes = [resolve_box(b, (W, H)) for b in (args.box or [])]
    polys = [resolve_quad(q, (W, H)) for q in (args.quad or [])]
    cleaned_rgb, mask, engine_used = erase_regions(
        base_rgb,
        boxes=boxes,
        polygons=polys,
        engine=args.engine,
        inpaint_radius=args.inpaint_radius,
        iopaint_device=args.iopaint_device,
    )

    psd_layers: list[dict[str, Any]] = []
    ys, xs = np.where(mask > 0)
    if len(ys) > 0:
        ex1 = _clamp_int(int(xs.min()) - 8, 0, W)
        ey1 = _clamp_int(int(ys.min()) - 8, 0, H)
        ex2 = _clamp_int(int(xs.max()) + 9, 0, W)
        ey2 = _clamp_int(int(ys.max()) + 9, 0, H)
        e_alpha = cv2.GaussianBlur(mask[ey1:ey2, ex1:ex2].astype(np.float32), (0, 0), sigmaX=1.2)
        e_rgba = np.concatenate(
            [cleaned_rgb[ey1:ey2, ex1:ex2], np.clip(e_alpha, 0, 255).astype(np.uint8)[..., None]],
            axis=-1,
        )
        psd_layers.append(
            {
                "name_ascii": "Erased",
                "name_unicode": "局部去字擦除层",
                "box": [ex1, ey1, ex2, ey2],
                "rgba": e_rgba,
                "blend": "normal",
                "opacity": 1.0,
                "visible": True,
            }
        )

    if out_path.suffix.lower() == ".psd":
        save_multilayer_psd(base_rgb, cleaned_rgb, psd_layers, out_path)
    else:
        _save_flat_image(cleaned_rgb, out_path)

    preview_path_str = ""
    if args.preview_png:
        prev_p = Path(args.preview_png).resolve()
        _save_flat_image(cleaned_rgb, prev_p)
        preview_path_str = str(prev_p)

    print(
        json.dumps(
            {
                "status": "erased",
                "erase_engine": engine_used,
                "out": str(out_path),
                "preview_png": preview_path_str,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_recolor_led(args: argparse.Namespace) -> int:
    img_path = Path(args.image).resolve()
    out_path = Path(args.out).resolve()
    base_rgb = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)
    H, W = base_rgb.shape[:2]

    screen_boxes = [resolve_box(b, (W, H)) for b in args.screen_box]
    merged_rgb, overlay_rgba, union_box = recolor_led_screens(
        base_rgb,
        screen_boxes=screen_boxes,
        color_hex=args.color,
        glow_strength=args.glow,
    )
    psd_layers = [
        {
            "name_ascii": "LED_Recolor",
            "name_unicode": "数码屏改色层",
            "box": union_box,
            "rgba": overlay_rgba,
            "blend": "normal",
            "opacity": 1.0,
            "visible": True,
        }
    ]
    if out_path.suffix.lower() == ".psd":
        save_multilayer_psd(base_rgb, merged_rgb, psd_layers, out_path)
    else:
        _save_flat_image(merged_rgb, out_path)

    preview_path_str = ""
    if args.preview_png:
        prev_p = Path(args.preview_png).resolve()
        _save_flat_image(merged_rgb, prev_p)
        preview_path_str = str(prev_p)

    print(
        json.dumps(
            {
                "status": "recolored",
                "color": args.color.upper(),
                "screens": len(screen_boxes),
                "out": str(out_path),
                "preview_png": preview_path_str,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DUMIK 代码精准修标 / 圆柱透视贴标 / 擦字 / 数码屏改色工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("patch-logo", help="四角透视或圆柱曲面精准贴入透明 LOGO 并输出分层 PSD/PNG")
    pl.add_argument("--image", required=True, help="目标底图路径")
    pl.add_argument("--logo", required=True, help="透明底 LOGO PNG 路径")
    pl.add_argument("--quad", nargs=8, type=float, required=True, help="目标贴合四角 (TL TR BR BL 顺时针 8 数值，支持 0~1 或像素)")
    pl.add_argument("--mode", choices=["perspective", "cylinder"], default="perspective", help="形变模式：perspective 平面透视 / cylinder 圆柱弯曲")
    pl.add_argument("--cylinder-curve", type=float, default=0.40, help="圆柱模式弯曲强度 (0.1~0.8)")
    pl.add_argument("--cylinder-axis", choices=["vertical", "horizontal"], default="vertical", help="圆柱轴向")
    pl.add_argument("--cylinder-bow", type=float, default=0.06, help="圆柱上下弧度弯曲量 (-0.25~0.25)")
    pl.add_argument("--displace", type=float, default=0.5, help="底图表面肌理置换强度 (0 关闭，推荐 0.4~1.0)")
    pl.add_argument("--softness", type=float, default=0.30, help="边缘光学微柔化半径 (0~1.5)")
    pl.add_argument("--blend", choices=list(PS_BLEND_KEYS.keys()), default="multiply", help="PS 混合模式")
    pl.add_argument("--opacity", type=float, default=0.88, help="图层不透明度 (0~1)")
    pl.add_argument("--tint", default=None, help="可选重新着色 #RRGGBB（如 #7E8288 浅冷灰丝印）")
    pl.add_argument("--rotate", type=float, default=0.0, help="LOGO 旋转角度（如 -90 顺时针 90° 竖排）")
    pl.add_argument("--logo-crop", nargs=4, type=float, default=None, help="先裁取 LOGO 的子框 x1 y1 x2 y2（支持 0~1 或像素）")
    pl.add_argument("--drop-reg", action="store_true", help="自动移除右上角独立小 ®/™ 标")
    pl.add_argument("--no-trim-logo", action="store_true", help="不自动紧裁 LOGO 透明边")
    pl.add_argument("--erase-quad", action="store_true", help="贴标前先自动擦除 quad 区域内的旧乱码")
    pl.add_argument("--erase-box", nargs=4, type=float, action="append", default=[], help="额外擦除指定框（可多次传）")
    pl.add_argument("--erase-engine", choices=["auto", "iopaint", "opencv", "none"], default="auto", help="擦除引擎")
    pl.add_argument("--inpaint-radius", type=int, default=5, help="OpenCV 擦除修补半径")
    pl.add_argument("--iopaint-device", default="cpu", help="IOPaint 设备 (cpu/cuda)")
    pl.add_argument("--layer-name", default="LOGO精修层", help="PSD 内 LOGO 图层中文名")
    pl.add_argument("--out", required=True, help="输出文件路径（.psd 输出多图层可编辑源档，.png/.jpg 输出成图）")
    pl.add_argument("--preview-png", default=None, help="可选同时输出一张直看融合预览 PNG")
    pl.set_defaults(func=cmd_patch_logo)

    er = sub.add_parser("erase", help="仅擦除画面中的乱码小字/按钮假字/水印")
    er.add_argument("--image", required=True, help="目标底图路径")
    er.add_argument("--box", nargs=4, type=float, action="append", default=[], help="待擦除矩形框 x1 y1 x2 y2（支持 0~1 或像素）")
    er.add_argument("--quad", nargs=8, type=float, action="append", default=[], help="待擦除四边形 8 数值")
    er.add_argument("--engine", choices=["auto", "iopaint", "opencv"], default="auto", help="擦除引擎")
    er.add_argument("--inpaint-radius", type=int, default=5, help="OpenCV 修补半径")
    er.add_argument("--iopaint-device", default="cpu", help="IOPaint 设备")
    er.add_argument("--out", required=True, help="输出路径（.psd / .png / .jpg）")
    er.add_argument("--preview-png", default=None, help="可选同步输出融合预览 PNG")
    er.set_defaults(func=cmd_erase)

    led = sub.add_parser("recolor-led", help="电子秤/家电黑屏数码管发光字无损改色")
    led.add_argument("--image", required=True, help="目标底图路径")
    led.add_argument("--screen-box", nargs=4, type=float, action="append", required=True, help="黑屏区域框 x1 y1 x2 y2（可多次传）")
    led.add_argument("--color", default="#FF5E00", help="目标荧光色 #RRGGBB（默认荧光橙 #FF5E00）")
    led.add_argument("--glow", type=float, default=1.0, help="光学外发光强度 (0~2)")
    led.add_argument("--out", required=True, help="输出路径（.psd / .png / .jpg）")
    led.add_argument("--preview-png", default=None, help="可选同步输出融合预览 PNG")
    led.set_defaults(func=cmd_recolor_led)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
