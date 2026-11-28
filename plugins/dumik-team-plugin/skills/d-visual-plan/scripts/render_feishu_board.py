#!/usr/bin/env python3
"""
Pure-Python Pillow reconstructor & cropper for Feishu whiteboards.

Reconstructs each logical Feishu board zone (主图区 / 入口区 / 详情区) directly onto
unified local canvases using raw node coordinates, z-index layering, sections,
images, shapes, tables, connectors, and sticky notes, then crops out individual
cards (<ID>_画布原图.png), horizontal row strips (<ID>_整行.png), and zone overviews
(*区总览.png) without browser overhead or temporary exhaust in the project dir.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]
    PIL_AVAILABLE = False


SCRIPT_DIR = Path(__file__).resolve().parent


def _overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def _rect_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(0.0, max(ax - (bx + bw), bx - (ax + aw)))
    dy = max(0.0, max(ay - (by + bh), by - (ay + ah)))
    return math.hypot(dx, dy)


def _find_cjk_font_path() -> str | None:
    local_fonts = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    candidates = [
        r"C:\Windows\Fonts\MiSansVF.ttf",
        os.path.join(local_fonts, "MiSansVF.ttf"),
        r"C:\Windows\Fonts\MiSans-Regular.ttf",
        os.path.join(local_fonts, "MiSans-Regular.ttf"),
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _parse_hex_rgba(raw: Any, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if not isinstance(raw, str):
        return default
    s = raw.strip().lstrip("#")
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), default[3])
        except ValueError:
            return default
    return default


def _text_width(draw: Any, txt: str, font: Any) -> int:
    if not txt:
        return 0
    box = draw.textbbox((0, 0), txt, font=font)
    return max(0, box[2] - box[0])


def _wrap_text_to_width(draw: Any, text: str, font: Any, max_w: int) -> list[str]:
    lines: list[str] = []
    safe_w = max(20, max_w)
    for para in text.splitlines():
        para = para.strip()
        if not para:
            continue
        cur = ""
        for ch in para:
            test = cur + ch
            if cur and _text_width(draw, test, font) > safe_w:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines or ([text.strip()] if text.strip() else [])


def _get_font(font_path: str | None, font_cache: dict[int, Any], size_px: int) -> Any:
    s = max(9, size_px)
    if s in font_cache:
        return font_cache[s]
    if font_path and PIL_AVAILABLE:
        f = ImageFont.truetype(font_path, s)
    elif PIL_AVAILABLE:
        f = ImageFont.load_default()
    else:
        f = None
    font_cache[s] = f
    return f


def _fit_text_lines(
    draw: Any,
    text: str,
    max_w: int,
    max_h: int,
    font_path: str | None,
    font_cache: dict[int, Any],
    pref_px: int,
) -> tuple[Any, list[str], int]:
    start = max(10, min(pref_px, max_h - 4 if max_h > 14 else 14))
    for fs in range(start, 9, -2):
        font = _get_font(font_path, font_cache, fs)
        lines = _wrap_text_to_width(draw, text, font, max_w)
        line_h = int(fs * 1.28)
        if len(lines) * line_h <= max_h:
            return font, lines, line_h
    font = _get_font(font_path, font_cache, 10)
    lines = _wrap_text_to_width(draw, text, font, max_w)
    line_h = 13
    max_lines = max(1, max_h // line_h)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1]:
            lines[-1] = lines[-1][:-1] + "…"
    return font, lines, line_h


def _draw_fitted_text(
    draw: Any,
    text: str,
    box: tuple[int, int, int, int],
    *,
    font_path: str | None,
    font_cache: dict[int, Any],
    pref_px: int,
    fill_rgba: tuple[int, int, int, int],
    h_align: str = "center",
    v_align: str = "mid",
    shadow_rgba: tuple[int, int, int, int] | None = None,
) -> None:
    if not text or not text.strip():
        return
    x1, y1, x2, y2 = box
    pad_x = max(4, min(14, int((x2 - x1) * 0.04)))
    pad_y = max(3, min(10, int((y2 - y1) * 0.04)))
    avail_w = max(12, (x2 - x1) - 2 * pad_x)
    avail_h = max(12, (y2 - y1) - 2 * pad_y)
    chosen_font, lines, chosen_lh = _fit_text_lines(draw, text, avail_w, avail_h, font_path, font_cache, pref_px)
    if not lines:
        return
    total_h = len(lines) * chosen_lh
    if v_align == "top":
        cur_y = y1 + pad_y
    elif v_align == "bottom":
        cur_y = max(y1 + pad_y, y2 - pad_y - total_h)
    else:
        cur_y = max(y1 + pad_y, y1 + ((y2 - y1) - total_h) // 2)
    for ln in lines:
        lw = _text_width(draw, ln, chosen_font)
        if h_align == "left":
            tx = x1 + pad_x
        elif h_align == "right":
            tx = max(x1 + pad_x, x2 - pad_x - lw)
        else:
            tx = max(x1 + pad_x, x1 + ((x2 - x1) - lw) // 2)
        if shadow_rgba:
            draw.text((tx + 1, cur_y + 1), ln, font=chosen_font, fill=shadow_rgba)
        draw.text((tx, cur_y), ln, font=chosen_font, fill=fill_rgba)
        cur_y += chosen_lh


def _region_avg_luma(canvas: Any, box: tuple[int, int, int, int]) -> float:
    x1 = max(0, min(canvas.width - 1, box[0]))
    y1 = max(0, min(canvas.height - 1, box[1]))
    x2 = max(x1 + 1, min(canvas.width, box[2]))
    y2 = max(y1 + 1, min(canvas.height, box[3]))
    crop = canvas.crop((x1, y1, x2, y2)).resize((8, 8)).convert("L")
    px = list(getattr(crop, "get_flattened_data", crop.getdata)())
    return sum(px) / max(len(px), 1)


def _open_token_rgba(
    token: str,
    raw_token_files: dict[str, Path],
    image_cache: dict[str, Any] | None = None,
) -> Any | None:
    if not PIL_AVAILABLE or not token:
        return None
    if image_cache is not None and token in image_cache:
        return image_cache[token]
    src_p = raw_token_files.get(token)
    if not src_p or not src_p.is_file():
        return None
    try:
        with Image.open(src_p) as opened:
            pil_im = opened.convert("RGBA")
        if image_cache is not None:
            image_cache[token] = pil_im
        return pil_im
    except Exception:
        return None


def _draw_arrowhead(
    draw: Any,
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: tuple[int, int, int, int],
    size: float = 9.0,
) -> None:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist < 2.0:
        return
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    base_x = p2[0] - ux * size
    base_y = p2[1] - uy * size
    hw = size * 0.48
    pts = [
        (p2[0], p2[1]),
        (base_x + px * hw, base_y + py * hw),
        (base_x - px * hw, base_y - py * hw),
    ]
    draw.polygon(pts, fill=color)


def _safe_clip_line_points(node: dict[str, Any]) -> tuple[list[tuple[float, float]], str, str]:
    conn = node.get("connector") or {}
    start_meta = conn.get("start") or {}
    end_meta = conn.get("end") or {}
    sp = start_meta.get("position") or {}
    ep = end_meta.get("position") or {}
    pts: list[tuple[float, float]] = []
    if sp and ep and ("x" in sp or "y" in sp):
        pts.append((float(sp.get("x") or 0.0), float(sp.get("y") or 0.0)))
        for tp in conn.get("turning_points") or []:
            if isinstance(tp, dict) and ("x" in tp or "y" in tp):
                pts.append((float(tp.get("x") or 0.0), float(tp.get("y") or 0.0)))
        pts.append((float(ep.get("x") or 0.0), float(ep.get("y") or 0.0)))
    elif node.get("w", 0) > 0 or node.get("h", 0) > 0:
        x, y, w, h = float(node.get("x") or 0.0), float(node.get("y") or 0.0), float(node.get("w") or 0.0), float(node.get("h") or 0.0)
        pts = [(x, y), (x + w, y + h)]
    return pts, str(start_meta.get("arrow_style") or "none"), str(end_meta.get("arrow_style") or "none")


def _intersects_rect(
    item: dict[str, Any],
    bounds: tuple[float, float, float, float],
    *,
    margin: float = 0.0,
) -> bool:
    bx1, by1, bx2, by2 = bounds
    ix1 = float(item.get("x") or 0.0)
    iy1 = float(item.get("y") or 0.0)
    ix2 = ix1 + float(item.get("w") or 0.0)
    iy2 = iy1 + float(item.get("h") or 0.0)
    return _overlap_1d(bx1 - margin, bx2 + margin, ix1, ix2) > 0 and _overlap_1d(by1 - margin, by2 + margin, iy1, iy2) > 0


def render_region_canvas(
    bounds: tuple[float, float, float, float],
    parsed: dict[str, list[dict[str, Any]]],
    raw_token_files: dict[str, Path],
    *,
    scale: float = 0.55,
    bg_rgba: tuple[int, int, int, int] = (247, 248, 250, 255),
    draw_grid: bool = True,
    exclude_node_ids: set[str] | None = None,
    image_cache: dict[str, Any] | None = None,
) -> Any | None:
    """Reconstruct a region `(x1, y1, x2, y2)` of the Feishu board in true spatial coordinates."""
    if not PIL_AVAILABLE:
        return None
    bx1, by1, bx2, by2 = bounds
    bw = max(1.0, bx2 - bx1)
    bh = max(1.0, by2 - by1)
    target_w = max(32, int(round(bw * scale)))
    target_h = max(32, int(round(bh * scale)))

    canvas = Image.new("RGBA", (target_w, target_h), bg_rgba)
    draw = ImageDraw.Draw(canvas, "RGBA")
    font_path = _find_cjk_font_path()
    font_cache: dict[int, Any] = {}
    excluded = exclude_node_ids or set()

    def to_px(x: float, y: float, w: float, h: float) -> tuple[int, int, int, int]:
        px1 = int(round((x - bx1) * scale))
        py1 = int(round((y - by1) * scale))
        px2 = max(px1 + 1, int(round((x + w - bx1) * scale)))
        py2 = max(py1 + 1, int(round((y + h - by1) * scale)))
        return px1, py1, px2, py2

    def pt_to_px(x: float, y: float) -> tuple[float, float]:
        return ((x - bx1) * scale, (y - by1) * scale)

    if draw_grid:
        step = max(24, int(round(80 * scale)))
        dot_c = (224, 228, 236, 255)
        for gx in range(step // 2, target_w, step):
            for gy in range(step // 2, target_h, step):
                draw.point((gx, gy), fill=dot_c)

    # Layer 0: Section containers (background zones like 主图 / 入口图)
    for sec in sorted(parsed.get("sections", []), key=lambda s: int(s.get("z_index") or 0)):
        if sec.get("id") in excluded or not _intersects_rect(sec, bounds, margin=20):
            continue
        px1, py1, px2, py2 = to_px(sec["x"], sec["y"], sec["w"], sec["h"])
        st = sec.get("style") or {}
        fill_op = int(st.get("fill_opacity", 35) or 0)
        fill_c = _parse_hex_rgba(st.get("fill_color"), (238, 241, 246, 255))
        bdr_c = _parse_hex_rgba(st.get("border_color"), (188, 196, 208, 255))
        if fill_op > 0:
            alpha = max(18, min(200, int(round(255 * fill_op / 100.0))))
            draw.rounded_rectangle(
                [px1, py1, px2, py2],
                radius=10,
                fill=(fill_c[0], fill_c[1], fill_c[2], alpha),
                outline=(bdr_c[0], bdr_c[1], bdr_c[2], 210),
                width=2,
            )
        else:
            draw.rounded_rectangle([px1, py1, px2, py2], radius=10, outline=(bdr_c[0], bdr_c[1], bdr_c[2], 210), width=2)
        title = (sec.get("section_title") or sec.get("text") or "").strip()
        if title:
            badge_w = min(max(64, len(title) * 16 + 22), max(64, px2 - px1 - 12))
            badge_h = 26
            bx_t1, by_t1 = max(2, px1 + 8), max(2, py1 + 8)
            draw.rounded_rectangle(
                [bx_t1, by_t1, bx_t1 + badge_w, by_t1 + badge_h],
                radius=6,
                fill=(255, 255, 255, 235),
                outline=(176, 184, 196, 255),
                width=1,
            )
            _draw_fitted_text(
                draw,
                title,
                (bx_t1, by_t1, bx_t1 + badge_w, by_t1 + badge_h),
                font_path=font_path,
                font_cache=font_cache,
                pref_px=13,
                fill_rgba=(78, 89, 105, 255),
            )

    # Layer 1: Z-ordered images, shapes, tables, connectors, text_shapes
    z_items: list[tuple[int, int, float, str, dict[str, Any]]] = []
    for im in parsed.get("images", []):
        if im.get("id") not in excluded and im.get("w", 0) > 0 and im.get("h", 0) > 0 and _intersects_rect(im, bounds, margin=20):
            z_items.append((int(im.get("z_index") or 0), 0, -float(im.get("area") or 0.0), "image", im))
    for shp in parsed.get("shapes", []):
        if shp.get("id") not in excluded and shp.get("w", 0) > 0 and shp.get("h", 0) > 0 and _intersects_rect(shp, bounds, margin=20):
            prio = 4 if shp.get("type") == "text_shape" else 1
            z_items.append((int(shp.get("z_index") or 0), prio, -float(shp.get("area") or 0.0), "shape", shp))
    for tbl in parsed.get("tables", []):
        if tbl.get("id") not in excluded and tbl.get("rows") and _intersects_rect(tbl, bounds, margin=20):
            z_items.append((int(tbl.get("z_index") or 0), 2, -float(tbl.get("area") or 0.0), "table", tbl))
    for conn in parsed.get("connectors", []):
        if conn.get("id") not in excluded:
            pts, _, _ = _safe_clip_line_points(conn)
            if pts and any((bx1 - 150) <= px <= (bx2 + 150) and (by1 - 150) <= py <= (by2 + 150) for px, py in pts):
                z_items.append((int(conn.get("z_index") or 0), 3, 0.0, "connector", conn))
            elif pts and min(px for px, _ in pts) <= bx2 and max(px for px, _ in pts) >= bx1 and min(py for _, py in pts) <= by2 and max(py for _, py in pts) >= by1:
                z_items.append((int(conn.get("z_index") or 0), 3, 0.0, "connector", conn))

    z_items.sort(key=lambda t: (t[0], t[1], t[2]))

    for _, _, _, kind, node in z_items:
        if kind == "image":
            pil_im = _open_token_rgba(node.get("token") or "", raw_token_files, image_cache)
            if pil_im is None:
                continue
            nat_w, nat_h = pil_im.size
            if nat_w > 0 and node["w"] > 0 and node["h"] > 0:
                nat_ratio = nat_h / nat_w
                node_ratio = node["h"] / node["w"]
                if nat_ratio > node_ratio * 1.15:
                    crop_h = max(1, min(nat_h, int(round(nat_w * node_ratio))))
                    pil_im = pil_im.crop((0, 0, nat_w, crop_h))
            px1, py1, px2, py2 = to_px(node["x"], node["y"], node["w"], node["h"])
            pw, ph = max(1, px2 - px1), max(1, py2 - py1)
            resized = pil_im.resize((pw, ph), Image.Resampling.LANCZOS)
            # Clip alpha_composite safely when extending beyond bounds
            cx1, cy1 = max(0, px1), max(0, py1)
            cx2, cy2 = min(target_w, px1 + pw), min(target_h, py1 + ph)
            if cx2 > cx1 and cy2 > cy1:
                sub = resized.crop((cx1 - px1, cy1 - py1, cx2 - px1, cy2 - py1))
                canvas.alpha_composite(sub, (cx1, cy1))

        elif kind == "shape":
            st = node.get("style") or {}
            tm = node.get("text_meta") or {}
            px1, py1, px2, py2 = to_px(node["x"], node["y"], node["w"], node["h"])
            is_text_only = node.get("type") == "text_shape"
            shape_kind = str((node.get("shape_kind") or "round_rect")).lower()
            if not is_text_only:
                fill_op = int(st.get("fill_opacity", 100) or 0)
                bdr_op = int(st.get("border_opacity", 100) or 0)
                fill_c = _parse_hex_rgba(st.get("fill_color"), (240, 244, 252, 255))
                bdr_c = _parse_hex_rgba(st.get("border_color"), (78, 89, 105, 255))
                fill_val = (fill_c[0], fill_c[1], fill_c[2], max(25, min(255, int(round(255 * fill_op / 100.0))))) if fill_op > 0 else None
                outline_val = (bdr_c[0], bdr_c[1], bdr_c[2], max(40, min(255, int(round(255 * bdr_op / 100.0))))) if (bdr_op > 0 and st.get("border_style", "solid") != "none") else None
                bdr_w_name = str(st.get("border_width") or "narrow").lower()
                bdr_w = 2 if bdr_w_name in ("medium", "bold", "wide") else 1
                min_dim = min(max(1, px2 - px1), max(1, py2 - py1))
                if "ellipse" in shape_kind or "circle" in shape_kind:
                    draw.ellipse([px1, py1, px2, py2], fill=fill_val, outline=outline_val, width=bdr_w)
                elif "round" in shape_kind and min_dim >= 14:
                    rad = max(3, min(12, min_dim // 5))
                    draw.rounded_rectangle([px1, py1, px2, py2], radius=rad, fill=fill_val, outline=outline_val, width=bdr_w)
                else:
                    draw.rectangle([px1, py1, px2, py2], fill=fill_val, outline=outline_val, width=bdr_w)

            txt = (node.get("text") or "").strip()
            if not txt:
                continue
            pref_fs = int(round(float(tm.get("font_size") or 32) * scale * 0.92))
            txt_c = _parse_hex_rgba(tm.get("text_color"), (31, 35, 41, 255))
            shadow = None
            if is_text_only and not tm.get("text_color"):
                bg_luma = _region_avg_luma(canvas, (px1, py1, px2, py2))
                if bg_luma < 110:
                    txt_c = (255, 255, 255, 255)
                    shadow = (0, 0, 0, 180)
            is_large_container = node["w"] >= 580 and node["h"] >= 700
            v_align = "top" if is_large_container else str(tm.get("vertical_align") or "mid")
            h_align = str(tm.get("horizontal_align") or "center")
            _draw_fitted_text(
                draw,
                txt,
                (px1, py1, px2, py2),
                font_path=font_path,
                font_cache=font_cache,
                pref_px=max(12, pref_fs),
                fill_rgba=txt_c,
                h_align=h_align,
                v_align=v_align,
                shadow_rgba=shadow,
            )

        elif kind == "table":
            rows_data = node.get("rows") or []
            px1, py1, px2, py2 = to_px(node["x"], node["y"], node["w"], node["h"])
            n_rows = len(rows_data)
            n_cols = max(len(r) for r in rows_data)
            if n_cols <= 0:
                continue
            draw.rectangle([px1, py1, px2, py2], fill=(255, 255, 255, 248), outline=(78, 89, 105, 255), width=1)
            col_w = (px2 - px1) / n_cols
            row_h = (py2 - py1) / n_rows
            for r_i, row_cells in enumerate(rows_data):
                cy1 = int(round(py1 + r_i * row_h))
                cy2 = int(round(py1 + (r_i + 1) * row_h))
                if r_i == 0:
                    draw.rectangle([px1, cy1, px2, cy2], fill=(238, 242, 248, 255))
                draw.line([(px1, cy1), (px2, cy1)], fill=(154, 163, 178, 255), width=1)
                for c_i in range(n_cols):
                    cx1 = int(round(px1 + c_i * col_w))
                    cx2 = int(round(px1 + (c_i + 1) * col_w))
                    if r_i == 0:
                        draw.line([(cx1, py1), (cx1, py2)], fill=(154, 163, 178, 255), width=1)
                    cell_txt = row_cells[c_i] if c_i < len(row_cells) else ""
                    if cell_txt:
                        _draw_fitted_text(
                            draw,
                            cell_txt,
                            (cx1, cy1, cx2, cy2),
                            font_path=font_path,
                            font_cache=font_cache,
                            pref_px=max(10, int(round(row_h * 0.28))),
                            fill_rgba=(31, 35, 41, 255),
                        )

        elif kind == "connector":
            pts, start_arrow, end_arrow = _safe_clip_line_points(node)
            if len(pts) < 2:
                continue
            st = node.get("style") or {}
            line_c = _parse_hex_rgba(st.get("border_color"), (96, 106, 122, 220))
            px_pts = [pt_to_px(px, py) for px, py in pts]
            draw.line(px_pts, fill=(line_c[0], line_c[1], line_c[2], 220), width=2)
            if end_arrow and end_arrow != "none":
                _draw_arrowhead(draw, px_pts[-2], px_pts[-1], (line_c[0], line_c[1], line_c[2], 235))
            if start_arrow and start_arrow != "none":
                _draw_arrowhead(draw, px_pts[1], px_pts[0], (line_c[0], line_c[1], line_c[2], 235))

    # Layer 2: Sticky notes in exact board coordinates
    for stk in sorted(parsed.get("stickies", []), key=lambda s: int(s.get("z_index") or 0)):
        if stk.get("id") in excluded or not _intersects_rect(stk, bounds, margin=20):
            continue
        txt = (stk.get("text") or "").strip()
        if not txt:
            continue
        px1, py1, px2, py2 = to_px(stk["x"], stk["y"], stk["w"], stk["h"])
        fill_c = _parse_hex_rgba((stk.get("style") or {}).get("fill_color"), (254, 241, 206, 248))
        draw.rounded_rectangle([px1 + 2, py1 + 3, px2 + 2, py2 + 3], radius=6, fill=(0, 0, 0, 28))
        draw.rounded_rectangle(
            [px1, py1, px2, py2],
            radius=6,
            fill=(fill_c[0], fill_c[1], fill_c[2], 248),
            outline=(212, 167, 44, 255),
            width=1,
        )
        _draw_fitted_text(
            draw,
            txt,
            (px1, py1, px2, py2),
            font_path=font_path,
            font_cache=font_cache,
            pref_px=max(12, min(18, int(round(30 * scale)))),
            fill_rgba=(31, 35, 41, 255),
        )

    return canvas


def _is_effectively_blank(img: Any, bg_rgb: tuple[int, int, int] = (247, 248, 250)) -> bool:
    """Return True if a rendered crop has virtually zero non-background content."""
    if not PIL_AVAILABLE or img is None:
        return True
    thumb = img.convert("RGB").resize((48, 48))
    pixels = list(getattr(thumb, "get_flattened_data", thumb.getdata)())
    if not pixels:
        return True
    bg_r, bg_g, bg_b = bg_rgb
    non_bg = sum(1 for r, g, b in pixels if abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b) > 18)
    return (non_bg / len(pixels)) < 0.015


def _save_png_atomic(img: Any, dest_path: Path, *, check_blank: bool = False) -> Path:
    if check_blank and _is_effectively_blank(img):
        raise ValueError(f"Refusing to save blank crop: {dest_path.name}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_p = dest_path.with_suffix(".tmp.png")
    img.convert("RGB").save(tmp_p, format="PNG")
    os.replace(tmp_p, dest_path)
    return dest_path


def _crop_world_rect_from_canvas(
    zone_img: Any,
    zone_bounds: tuple[float, float, float, float],
    scale: float,
    world_rect: tuple[float, float, float, float],
    *,
    max_width: int = 1280,
    max_height: int = 3400,
) -> Any:
    zx1, zy1, _, _ = zone_bounds
    wx1, wy1, wx2, wy2 = world_rect
    px1 = max(0, min(zone_img.width - 1, int(round((wx1 - zx1) * scale))))
    py1 = max(0, min(zone_img.height - 1, int(round((wy1 - zy1) * scale))))
    px2 = max(px1 + 1, min(zone_img.width, int(round((wx2 - zx1) * scale))))
    py2 = max(py1 + 1, min(zone_img.height, int(round((wy2 - zy1) * scale))))
    cropped = zone_img.crop((px1, py1, px2, py2))
    cw, ch = cropped.size
    downscale = min(1.0, max_width / cw if cw > max_width else 1.0, max_height / ch if ch > max_height else 1.0)
    if downscale < 0.999:
        cropped = cropped.resize((max(1, int(round(cw * downscale))), max(1, int(round(ch * downscale)))), Image.Resampling.LANCZOS)
    return cropped


def _compute_card_crop_bounds(
    card_item: dict[str, Any],
    parsed: dict[str, list[dict[str, Any]]],
    *,
    vertical_neighbors: list[tuple[float, float]] | None = None,
    horizontal_neighbors: list[tuple[float, float]] | None = None,
    pad_x: float = 32.0,
    pad_y: float = 22.0,
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float] | None]:
    """Compute tight-context card rect + optional horizontal row-strip rect (with side refs)."""
    rect = card_item.get("rect") or {}
    bx = float(rect.get("x") or 0.0)
    by = float(rect.get("y") or 0.0)
    bw = float(rect.get("w") or 0.0)
    bh = float(rect.get("h") or 0.0)
    cx1, cy1, cx2, cy2 = bx - pad_x, by - pad_y, bx + bw + pad_x, by + bh + pad_y

    # Clamp vertical expansion strictly away from vertical neighbor cards (including slight <=60u overlaps)
    upper_ceil = -1e12
    lower_floor = 1e12
    for ny1, ny2 in vertical_neighbors or []:
        if ny2 <= by + 60.0 and ny1 < by:
            upper_ceil = max(upper_ceil, min(ny2 + 4.0, by + 2.0))
        elif ny1 >= by + bh - 60.0 and ny2 > by + bh:
            lower_floor = min(lower_floor, max(ny1 - 2.0, by + bh - 60.0))

    # Clamp horizontal expansion away from side-by-side neighbor cards in horizontal rows (e.g. main/SKU rows)
    left_wall = -1e12
    right_wall = 1e12
    for nx1, nx2 in horizontal_neighbors or []:
        if nx2 <= bx + 40.0 and nx1 < bx:
            left_wall = max(left_wall, min((nx2 + bx) / 2.0, bx - 4.0))
        elif nx1 >= bx + bw - 40.0 and nx2 > bx + bw:
            right_wall = min(right_wall, max((bx + bw + nx1) / 2.0, bx + bw + 4.0))

    # Expand to keep shapes/badges straddling card border (skip detached zone headers like 'sku'/'主图')
    zone_header_words = {"sku", "SKU", "主图", "750主图", "入口", "入口图", "车图", "详情"}
    for node in [*parsed.get("shapes", []), *parsed.get("tables", [])]:
        ntxt = (node.get("text") or "").strip()
        if ntxt in zone_header_words and (node["y"] + node["h"] <= by + 4.0 or node["x"] + node["w"] <= bx + 4.0):
            continue
        if _overlap_1d(bx - 120, bx + bw + 120, node["x"], node["x"] + node["w"]) > 0 and _overlap_1d(by - 120, by + bh + 120, node["y"], node["y"] + node["h"]) > 0:
            if node["w"] < bw * 1.4 and node["h"] < bh * 1.4:
                nx1, ny1, nx2, ny2 = node["x"], node["y"], node["x"] + node["w"], node["y"] + node["h"]
                if ny1 >= upper_ceil and ny2 <= lower_floor and nx1 >= left_wall - 20.0 and nx2 <= right_wall + 20.0:
                    cx1 = min(cx1, nx1 - 16.0)
                    cx2 = max(cx2, nx2 + 16.0)
                    cy1 = min(cy1, ny1 - 12.0)
                    cy2 = max(cy2, ny2 + 12.0)

    # Expand for foreground cutout images straddling card border (e.g. overlaid product cutouts on SKU cards)
    card_node_id = (card_item.get("rect") or {}).get("node_id") or ""
    for im in parsed.get("images", []):
        if im.get("id") == card_node_id:
            continue
        if im["w"] <= bw * 0.95 and im["h"] <= bh * 0.95:
            if _overlap_1d(bx, bx + bw, im["x"], im["x"] + im["w"]) > 0 and _overlap_1d(by, by + bh, im["y"], im["y"] + im["h"]) > 0:
                ix1, iy1, ix2, iy2 = im["x"], im["y"], im["x"] + im["w"], im["y"] + im["h"]
                if iy1 >= upper_ceil and iy2 <= lower_floor and ix1 >= left_wall - 12.0 and ix2 <= right_wall + 12.0:
                    cx1 = min(cx1, max(left_wall, ix1 - 10.0))
                    cx2 = max(cx2, min(right_wall, ix2 + 10.0))
                    cy1 = min(cy1, max(upper_ceil, iy1 - 10.0))
                    cy2 = max(cy2, min(lower_floor, iy2 + 10.0))

    # Expand for adjacent sticky notes belonging to this card (keeps real relative position!)
    attached = set(card_item.get("sticky_notes") or [])
    for stk in parsed.get("stickies", []):
        txt = (stk.get("text") or "").strip()
        if not txt:
            continue
        dist = _rect_distance((bx, by, bw, bh), (stk["x"], stk["y"], stk["w"], stk["h"]))
        vert_overlap = _overlap_1d(by - 120, by + bh + 120, stk["y"], stk["y"] + stk["h"]) > 0
        if (txt in attached and dist <= 950.0) or (dist <= 420.0 and vert_overlap):
            sx1, sy1, sx2, sy2 = stk["x"], stk["y"], stk["x"] + stk["w"], stk["y"] + stk["h"]
            if sy1 >= upper_ceil - 40 and sy2 <= lower_floor + 40:
                cx1 = min(cx1, max(left_wall, sx1 - 18.0))
                cx2 = max(cx2, min(right_wall, sx2 + 18.0))
                cy1 = min(cy1, max(upper_ceil, sy1 - 14.0))
                cy2 = max(cy2, min(lower_floor, sy2 + 14.0))

    cx1 = max(cx1, left_wall)
    cx2 = min(cx2, right_wall)
    cy1 = max(cy1, upper_ceil)
    cy2 = min(cy2, lower_floor)
    if cx2 <= bx:
        cx1, cx2 = bx, bx + bw
    if cy2 <= by:
        cy1, cy2 = by, by + bh
    card_crop = (cx1, cy1, cx2, cy2)

    # Horizontal strip rect spanning card + right-side reference images
    side_refs = card_item.get("side_reference_images") or []
    if not side_refs:
        return card_crop, None

    rx1, ry1, rx2, ry2 = card_crop
    side_tokens = {sr.get("token") for sr in side_refs if sr.get("token")}
    matched_ref_boxes = 0
    for im in parsed.get("images", []):
        if im.get("token") in side_tokens and abs(im["cy"] - (by + bh / 2.0)) <= max(bh * 1.4, 2400.0):
            rx1 = min(rx1, im["x"] - 24.0)
            rx2 = max(rx2, im["x"] + im["w"] + 28.0)
            ry1 = min(ry1, im["y"] - 20.0)
            ry2 = max(ry2, im["y"] + im["h"] + 20.0)
            matched_ref_boxes += 1
    if not matched_ref_boxes:
        return card_crop, None
    ry1 = max(ry1, upper_ceil - 40.0)
    ry2 = min(ry2, lower_floor + 40.0)
    return card_crop, (rx1, ry1, rx2, ry2)


def _refine_flush_detail_crops(
    chunk: list[dict[str, Any]],
    zone_img: Any,
    zone_bounds: tuple[float, float, float, float],
    scale: float,
    parsed: dict[str, list[dict[str, Any]]],
) -> None:
    """
    Prevent Feishu image slice lines from cutting straight through a single continuous scene/object.
    Inspects flush/overlapping transitions on the rendered zone image: if horizontal edge energy
    across the raw seam is high (>=26), searches nearby rows (avoiding overlay text shapes)
    for the cleanest quiet horizontal divider valley and snaps the crop boundary there.
    """
    if len(chunk) < 2 or not PIL_AVAILABLE:
        return
    zx1, zy1, _, _ = zone_bounds
    rgb = zone_img.convert("RGB")
    px = rgb.load()
    img_w, img_h = rgb.size

    # Collect overlay text/table boxes so snapped split never cuts through a text overlay
    avoid_y_intervals: list[tuple[float, float]] = []
    for node in [*parsed.get("shapes", []), *parsed.get("tables", [])]:
        if node.get("w", 0) > 0 and node.get("h", 0) > 0 and node["h"] < 650 and (node.get("text") or node.get("rows")):
            avoid_y_intervals.append((float(node["y"]), float(node["y"]) + float(node["h"])))

    def _row_stats(py: int, x1_px: int, x2_px: int) -> tuple[float, float, float]:
        """Return (avg_energy, p90_block_energy, max_block_energy) across horizontal ~68px blocks."""
        span = x2_px - x1_px
        if py < 0 or py >= img_h or span < 24:
            return 999.0, 999.0, 999.0
        n_blocks = max(4, min(12, span // 64))
        blk_w = span / n_blocks
        blocks: list[float] = []
        for bi in range(n_blocks):
            bx1 = int(x1_px + bi * blk_w)
            bx2 = min(x2_px - 2, int(x1_px + (bi + 1) * blk_w))
            hd = 0
            cnt = 0
            for x in range(bx1, bx2, 2):
                r0, g0, b0 = px[x, py]
                r1, g1, b1 = px[x + 2, py]
                hd += abs(r0 - r1) + abs(g0 - g1) + abs(b0 - b1)
                cnt += 1
            blocks.append(hd / max(cnt, 1))
        blocks.sort()
        avg_e = sum(blocks) / len(blocks)
        p90_e = blocks[-2] if len(blocks) >= 4 else blocks[-1]
        max_e = blocks[-1]
        return avg_e, p90_e, max_e

    for i in range(len(chunk) - 1):
        sp_a = chunk[i]
        sp_b = chunk[i + 1]
        ra = sp_a["card"]["rect"]
        rb = sp_b["card"]["rect"]
        a_y1, a_y2 = float(ra["y"]), float(ra["y"]) + float(ra["h"])
        b_y1, b_y2 = float(rb["y"]), float(rb["y"]) + float(rb["h"])
        gap = b_y1 - a_y2
        if gap > 22.0 or gap < -80.0:
            continue

        # Clamp overlapping pill boundaries cleanly (e.g. next card's top pill overlapping prev card bottom)
        if gap < -4.0:
            cut_w = b_y1 - 2.0
            if sp_a["crop_b"][3] > cut_w > a_y1 + 120.0:
                sp_a["crop_b"] = (sp_a["crop_b"][0], sp_a["crop_b"][1], sp_a["crop_b"][2], cut_w)
            continue

        # Column interior bounds in pixel space (94% width so arm/mug edges on left/right margins are guarded)
        w_min = min(float(ra["w"]), float(rb["w"]))
        col_x1_w = max(float(ra["x"]), float(rb["x"])) + 0.03 * w_min
        col_x2_w = min(float(ra["x"]) + float(ra["w"]), float(rb["x"]) + float(rb["w"])) - 0.03 * w_min
        x1_px = max(4, min(img_w - 8, int(round((col_x1_w - zx1) * scale))))
        x2_px = max(x1_px + 24, min(img_w - 4, int(round((col_x2_w - zx1) * scale))))

        y_seam_w = (a_y2 + b_y1) / 2.0
        py_seam = int(round((y_seam_w - zy1) * scale))
        # A genuine clean margin around the raw slice line must span >= 10 contiguous full-width quiet rows
        # (a thin 4-6px hairline beneath a dangling headline/badge must NOT block snapping to a wide divider band)
        seam_band = [_row_stats(py, x1_px, x2_px) for py in range(max(0, py_seam - 7), min(img_h, py_seam + 8))]
        has_clean_seam_band = False
        q_streak = 0
        for avg_v, p90_v, _ in seam_band:
            q_streak = (q_streak + 1) if (avg_v <= 20.0 and p90_v <= 26.0) else 0
            if q_streak >= 10:
                has_clean_seam_band = True
                break
        if has_clean_seam_band:
            continue

        # Raw slice cut directly through high-detail graphics — find the nearest clean full-width divider:
        # (1) uniform quiet horizontal margin band, OR (2) sharp full-width horizontal color-step banner seam.
        lo_w = max(a_y1 + 0.25 * float(ra["h"]), y_seam_w - 0.65 * float(ra["h"]))
        hi_w = min(b_y2 - 0.25 * float(rb["h"]), y_seam_w + 0.65 * float(rb["h"]))
        py_lo = max(4, int(round((lo_w - zy1) * scale)))
        py_hi = min(img_h - 4, int(round((hi_w - zy1) * scale)))
        if py_hi - py_lo < 20:
            continue

        def _row_step_score(py: int) -> tuple[float, float]:
            """Return (fraction_of_cols_with_vertical_step, mean_vertical_delta) across row py -> py+1."""
            if py < 1 or py >= img_h - 2:
                return 0.0, 0.0
            step_hits = 0
            total_s = 0
            v_sum = 0
            for x in range(x1_px, x2_px, 4):
                r0, g0, b0 = px[x, py - 1]
                r1, g1, b1 = px[x, py + 1]
                vd = abs(r0 - r1) + abs(g0 - g1) + abs(b0 - b1)
                v_sum += vd
                if vd >= 42:
                    step_hits += 1
                total_s += 1
            return (step_hits / max(total_s, 1)), (v_sum / max(total_s, 1))

        stats_map = {py: _row_stats(py, x1_px, x2_px) for py in range(py_lo, py_hi + 1)}
        # Build contiguous full-width quiet runs (zero arm/handle/box crossing any horizontal block)
        runs: list[list[int]] = []
        cur_run: list[int] = []
        for py in range(py_lo, py_hi + 1):
            wy = zy1 + py / scale
            hits_overlay = any((oy1 + 6.0) < wy < (oy2 - 6.0) for oy1, oy2 in avoid_y_intervals)
            avg_v, p90_v, max_v = stats_map[py]
            if avg_v <= 15.0 and p90_v <= 22.0 and max_v <= 36.0 and not hits_overlay:
                cur_run.append(py)
            else:
                if len(cur_run) >= 6:
                    runs.append(cur_run)
                cur_run = []
        if len(cur_run) >= 6:
            runs.append(cur_run)

        best_py = py_seam
        best_score = float("inf")
        for run in runs:
            mid_py = run[len(run) // 2]
            if abs(mid_py - py_seam) < 8:
                continue
            mean_e = sum(stats_map[y][0] + 0.4 * stats_map[y][1] for y in run) / len(run)
            score = mean_e + 0.03 * abs(mid_py - py_seam)
            if score < best_score:
                best_score = score
                best_py = mid_py

        # Fallback: detect sharp full-width horizontal banner/section step (e.g. beige card -> dark section banner)
        if best_py == py_seam:
            for py in range(py_lo + 4, py_hi - 4):
                if abs(py - py_seam) < 10:
                    continue
                wy = zy1 + py / scale
                if any((oy1 + 6.0) < wy < (oy2 - 6.0) for oy1, oy2 in avoid_y_intervals):
                    continue
                frac, v_mean = _row_step_score(py)
                if frac < 0.72 or v_mean < 48.0:
                    continue
                # At least one side (above or below the horizontal seam) must be a clean low-texture margin/frame
                above_avg = sum(stats_map[y][0] for y in range(py - 4, py)) / 4.0
                below_avg = sum(stats_map[y][0] for y in range(py + 1, py + 5)) / 4.0
                if min(above_avg, below_avg) > 22.0:
                    continue
                score = min(above_avg, below_avg) - 0.15 * v_mean + 0.035 * abs(py - py_seam)
                if score < best_score:
                    best_score = score
                    best_py = py

        if best_py == py_seam:
            continue
        wy_cut = zy1 + best_py / scale
        sp_a["crop_b"] = (sp_a["crop_b"][0], sp_a["crop_b"][1], sp_a["crop_b"][2], wy_cut + 2.0)
        sp_b["crop_b"] = (sp_b["crop_b"][0], wy_cut, sp_b["crop_b"][2], sp_b["crop_b"][3])
        if sp_a.get("strip_b") is not None:
            sb = sp_a["strip_b"]
            sp_a["strip_b"] = (sb[0], sb[1], sb[2], max(sb[3], wy_cut + 2.0))
        if sp_b.get("strip_b") is not None:
            sb = sp_b["strip_b"]
            sp_b["strip_b"] = (sb[0], max(sb[1], wy_cut) if wy_cut < sb[3] else sb[1], sb[2], sb[3])


def _export_zone_group(
    *,
    zone_label: str,
    cards: list[dict[str, Any]],
    parsed: dict[str, list[dict[str, Any]]],
    raw_token_files: dict[str, Path],
    dest_dir: Path,
    image_cache: dict[str, Any],
    default_pad_x: float = 34.0,
    default_pad_y: float = 24.0,
    max_chunk_world_h: float = 11000.0,
    overview_max_w: int = 1500,
    write_row_strips: bool = True,
    write_overview: bool = True,
    refine_flush_seams: bool = False,
) -> dict[str, Any]:
    """Reconstruct one logical zone on local canvas(es), export overview + crop every card/strip."""
    result: dict[str, Any] = {"overviews": [], "snapshots": {}, "row_strips": {}}
    valid_cards = [c for c in cards if (c.get("rect") or {}).get("w", 0) > 0 and (c.get("rect") or {}).get("h", 0) > 0]
    if not valid_cards:
        return result

    all_rects = [
        (
            float(c["rect"]["x"]),
            float(c["rect"]["y"]),
            float(c["rect"]["x"]) + float(c["rect"]["w"]),
            float(c["rect"]["y"]) + float(c["rect"]["h"]),
        )
        for c in valid_cards
    ]
    # Prepare crop rectangles for each card & row strip
    card_specs: list[dict[str, Any]] = []
    for idx, card in enumerate(valid_cards):
        cx1, cy1, cx2, cy2 = all_rects[idx]
        other_y = [(ry1, ry2) for i, (rx1, ry1, rx2, ry2) in enumerate(all_rects) if i != idx and _overlap_1d(cx1, cx2, rx1, rx2) > 40.0]
        other_x = [(rx1, rx2) for i, (rx1, ry1, rx2, ry2) in enumerate(all_rects) if i != idx and _overlap_1d(cy1, cy2, ry1, ry2) > 40.0]
        crop_b, strip_b = _compute_card_crop_bounds(
            card,
            parsed,
            vertical_neighbors=other_y,
            horizontal_neighbors=other_x,
            pad_x=default_pad_x,
            pad_y=default_pad_y,
        )
        union_b = strip_b or crop_b
        card_specs.append({"card": card, "crop_b": crop_b, "strip_b": strip_b, "union_b": union_b})

    # Include enclosing section bounds when compact (e.g. 主图 / 入口图)
    sec_boxes: list[tuple[float, float, float, float]] = []
    sec_ids = {(c.get("rect") or {}).get("node_id") for c in valid_cards}
    for sec in parsed.get("sections", []):
        sbox = (sec["x"], sec["y"], sec["x"] + sec["w"], sec["y"] + sec["h"])
        for sp in card_specs:
            ub = sp["union_b"]
            if _overlap_1d(sbox[0], sbox[2], ub[0], ub[2]) > 0 and _overlap_1d(sbox[1], sbox[3], ub[1], ub[3]) > 0:
                sec_boxes.append(sbox)
                break
        if sec["id"] in sec_ids:
            sec_boxes.append(sbox)

    # Group card_specs into vertical chunks <= max_chunk_world_h (never splitting inside any card/row)
    sorted_specs = sorted(card_specs, key=lambda sp: sp["union_b"][1])
    chunks: list[list[dict[str, Any]]] = []
    cur_chunk: list[dict[str, Any]] = []
    cur_y1 = sorted_specs[0]["union_b"][1]
    for sp in sorted_specs:
        uy1, uy2 = sp["union_b"][1], sp["union_b"][3]
        gap_prev = (uy1 - cur_chunk[-1]["union_b"][3]) if cur_chunk else 999.0
        if cur_chunk and (uy2 - cur_y1) > max_chunk_world_h and gap_prev > 25.0:
            chunks.append(cur_chunk)
            cur_chunk = [sp]
            cur_y1 = uy1
        else:
            cur_chunk.append(sp)
    if cur_chunk:
        chunks.append(cur_chunk)

    overview_parts: list[Any] = []
    for c_idx, chunk in enumerate(chunks, start=1):
        zx1 = min(sp["union_b"][0] for sp in chunk) - 48.0
        zy1 = min(sp["union_b"][1] for sp in chunk) - 48.0
        zx2 = max(sp["union_b"][2] for sp in chunk) + 48.0
        zy2 = max(sp["union_b"][3] for sp in chunk) + 48.0
        if len(chunks) == 1 and sec_boxes:
            zx1 = min(zx1, *(b[0] - 32.0 for b in sec_boxes))
            zy1 = min(zy1, *(b[1] - 32.0 for b in sec_boxes))
            zx2 = max(zx2, *(b[2] + 32.0 for b in sec_boxes))
            zy2 = max(zy2, *(b[3] + 32.0 for b in sec_boxes))

        zone_w_units = max(100.0, zx2 - zx1)
        # Render crisp resolution so each 800-1100u card crop comes out ~480-680px wide
        scale = min(0.75, max(0.36, 1850.0 / zone_w_units))
        if zone_w_units < 1400.0:
            scale = min(0.68, max(0.45, 900.0 / zone_w_units))
        zone_bounds = (zx1, zy1, zx2, zy2)
        zone_img = render_region_canvas(
            zone_bounds,
            parsed,
            raw_token_files,
            scale=scale,
            image_cache=image_cache,
        )
        if zone_img is None:
            continue

        if refine_flush_seams:
            _refine_flush_detail_crops(chunk, zone_img, zone_bounds, scale, parsed)

        # Direct crops from reconstructed zone canvas (guarding against neighbor-tail duplicate bleed)
        for sp_idx, sp in enumerate(chunk):
            cid = sp["card"]["id"]
            cb = sp["crop_b"]
            bleeding_ids: set[str] = set()
            if sp_idx > 0:
                prev_rect = chunk[sp_idx - 1]["card"]["rect"]
                py1_p = float(prev_rect["y"])
                py2_p = py1_p + float(prev_rect["h"])
                for im in parsed.get("images", []):
                    im_id = im.get("id") or ""
                    if not im_id or im_id == (sp["card"].get("rect") or {}).get("node_id"):
                        continue
                    im_y1, im_y2 = float(im["y"]), float(im["y"]) + float(im["h"])
                    im_x1, im_x2 = float(im["x"]), float(im["x"]) + float(im["w"])
                    if _overlap_1d(cb[0], cb[2], im_x1, im_x2) < (cb[2] - cb[0]) * 0.45:
                        continue
                    # Image mainly belongs to previous card but its tail pokes over the top of this card
                    if im_y1 < cb[1] - 120.0 and im_y2 > cb[1] + 25.0 and im_y2 < cb[3] - 120.0:
                        ov_prev = _overlap_1d(py1_p, py2_p, im_y1, im_y2)
                        if ov_prev > float(im["h"]) * 0.55:
                            bleeding_ids.add(im_id)
            if bleeding_ids:
                clean_canvas = render_region_canvas(
                    cb,
                    parsed,
                    raw_token_files,
                    scale=scale,
                    draw_grid=False,
                    exclude_node_ids=bleeding_ids,
                    image_cache=image_cache,
                )
                card_crop_img = _crop_world_rect_from_canvas(clean_canvas, cb, scale, cb, max_width=760, max_height=3200) if clean_canvas is not None else _crop_world_rect_from_canvas(zone_img, zone_bounds, scale, cb, max_width=760, max_height=3200)
            else:
                card_crop_img = _crop_world_rect_from_canvas(zone_img, zone_bounds, scale, cb, max_width=760, max_height=3200)
            snap_path = _save_png_atomic(card_crop_img, dest_dir / f"{cid}_画布原图.png", check_blank=True)
            result["snapshots"][cid] = snap_path

            if write_row_strips and sp["strip_b"] is not None:
                strip_img = _crop_world_rect_from_canvas(zone_img, zone_bounds, scale, sp["strip_b"], max_width=1500, max_height=2400)
                strip_path = _save_png_atomic(strip_img, dest_dir / f"{cid}_整行.png")
                result["row_strips"][cid] = strip_path

        if write_overview:
            ow, oh = zone_img.size
            if ow > overview_max_w:
                r = overview_max_w / ow
                ov_img = zone_img.resize((overview_max_w, max(1, int(round(oh * r)))), Image.Resampling.LANCZOS)
            else:
                ov_img = zone_img
            overview_parts.append(ov_img)

    if write_overview and overview_parts:
        # Merge overview parts vertically unless huge (>16000px)
        total_h = sum(im.height for im in overview_parts)
        max_w = max(im.width for im in overview_parts)
        if total_h <= 16500:
            merged = Image.new("RGB", (max_w, total_h), (247, 248, 250))
            cy = 0
            for im in overview_parts:
                merged.paste(im.convert("RGB"), (0, cy))
                cy += im.height
            ov_path = _save_png_atomic(merged, dest_dir / f"{zone_label}总览.png")
            result["overviews"].append(ov_path)
        else:
            for p_i, im in enumerate(overview_parts, start=1):
                ov_path = _save_png_atomic(im, dest_dir / f"{zone_label}总览_{p_i}.png")
                result["overviews"].append(ov_path)

    return result


def reconstruct_and_crop_board(
    *,
    analyzed_board: dict[str, Any],
    parsed: dict[str, list[dict[str, Any]]],
    raw_token_files: dict[str, Path],
    dest_dir: Path,
    zones: set[str] | None = None,
    write_row_strips: bool = True,
    write_overviews: bool = True,
) -> dict[str, Any]:
    """
    Reconstruct local zones (main/entry/detail) of a Feishu board in Pillow and crop
    <ID>_画布原图.png, optional <ID>_整行.png, and *区总览.png.
    """
    if not PIL_AVAILABLE:
        return {"overviews": [], "snapshots": {}, "row_strips": {}}
    dest_dir.mkdir(parents=True, exist_ok=True)
    active_zones = zones or {"main", "entry", "detail"}
    image_cache: dict[str, Any] = {}
    out: dict[str, Any] = {"overviews": [], "snapshots": {}, "row_strips": {}}

    try:
        if "main" in active_zones and analyzed_board.get("main_cards"):
            r = _export_zone_group(
                zone_label="主图区",
                cards=analyzed_board["main_cards"],
                parsed=parsed,
                raw_token_files=raw_token_files,
                dest_dir=dest_dir,
                image_cache=image_cache,
                default_pad_x=34.0,
                default_pad_y=24.0,
                write_row_strips=write_row_strips,
                write_overview=write_overviews,
            )
            out["overviews"].extend(r["overviews"])
            out["snapshots"].update(r["snapshots"])
            out["row_strips"].update(r["row_strips"])

        if "entry" in active_zones and analyzed_board.get("entry_cards"):
            r = _export_zone_group(
                zone_label="入口区",
                cards=analyzed_board["entry_cards"],
                parsed=parsed,
                raw_token_files=raw_token_files,
                dest_dir=dest_dir,
                image_cache=image_cache,
                default_pad_x=36.0,
                default_pad_y=28.0,
                write_row_strips=write_row_strips,
                write_overview=write_overviews,
            )
            out["overviews"].extend(r["overviews"])
            out["snapshots"].update(r["snapshots"])
            out["row_strips"].update(r["row_strips"])

        if "detail" in active_zones and analyzed_board.get("detail_screens"):
            r = _export_zone_group(
                zone_label="详情区",
                cards=analyzed_board["detail_screens"],
                parsed=parsed,
                raw_token_files=raw_token_files,
                dest_dir=dest_dir,
                image_cache=image_cache,
                default_pad_x=28.0,
                default_pad_y=12.0,
                write_row_strips=write_row_strips,
                write_overview=write_overviews,
                refine_flush_seams=True,
            )
            out["overviews"].extend(r["overviews"])
            out["snapshots"].update(r["snapshots"])
            out["row_strips"].update(r["row_strips"])
    finally:
        for im in image_cache.values():
            try:
                im.close()
            except Exception:
                pass
        image_cache.clear()

    return out


def render_single_card_crop(
    *,
    card_item: dict[str, Any],
    parsed: dict[str, list[dict[str, Any]]],
    raw_token_files: dict[str, Path],
    dest_path: Path,
) -> Path | None:
    """Backward-compatible single-card local board render & crop."""
    if not PIL_AVAILABLE:
        return None
    rect = card_item.get("rect") or {}
    bw = float(rect.get("w") or 0.0)
    bh = float(rect.get("h") or 0.0)
    if bw <= 0 or bh <= 0:
        return None
    crop_b, _ = _compute_card_crop_bounds(card_item, parsed, pad_x=24.0, pad_y=18.0)
    cw = max(1.0, crop_b[2] - crop_b[0])
    ch = max(1.0, crop_b[3] - crop_b[1])
    scale = min(560.0 / cw, 3200.0 / ch)
    canvas = render_region_canvas(crop_b, parsed, raw_token_files, scale=scale, draw_grid=False)
    if canvas is None:
        return None
    return _save_png_atomic(canvas, dest_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="纯 Python 本地还原飞书画布排布并按分区/卡片/整行自动裁切。")
    parser.add_argument("--url", help="飞书 Wiki / Docx / 画板链接")
    parser.add_argument("--whiteboard-token", action="append", default=[], help="直接指定画板 token")
    parser.add_argument("--nodes-json", type=Path, help="离线调试：传入 raw nodes JSON 文件路径")
    parser.add_argument("--media-dir", type=Path, help="离线调试：传入已下载的 raw image token 文件目录 (<token>.png/jpg)")
    parser.add_argument("--out-dir", type=Path, required=True, help="输出裁切图的目录")
    parser.add_argument("--zones", default="main,entry,detail", help="要还原裁切的区：main,entry,detail")
    parser.add_argument("--no-overviews", action="store_true", help="只裁单卡和整行，不输出*区总览图")
    parser.add_argument("--no-row-strips", action="store_true", help="不额外输出*_整行.png")
    args = parser.parse_args()

    if not PIL_AVAILABLE:
        print(json.dumps({"ok": False, "error": "缺少 Pillow 依赖 (pip install pillow)"}, ensure_ascii=False))
        return 2

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import parse_feishu_canvas as pfc  # noqa: E402

    selected_zones = {z.strip().lower() for z in args.zones.split(",") if z.strip()}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.nodes_json:
        raw_obj = json.loads(args.nodes_json.read_text(encoding="utf-8"))
        raw_nodes = raw_obj if isinstance(raw_obj, list) else ((raw_obj.get("data") or {}).get("nodes") or raw_obj.get("nodes") or [])
        analyzed = pfc.analyze_whiteboard_nodes(raw_nodes, board_token="OfflineBoard")
        parsed = analyzed.pop("_parsed_nodes", None) or pfc._normalize_nodes(raw_nodes)
        raw_token_files: dict[str, Path] = {}
        if args.media_dir and args.media_dir.is_dir():
            for f in args.media_dir.iterdir():
                if f.is_file():
                    raw_token_files[f.stem] = f
        out = reconstruct_and_crop_board(
            analyzed_board=analyzed,
            parsed=parsed,
            raw_token_files=raw_token_files,
            dest_dir=args.out_dir,
            zones=selected_zones,
            write_row_strips=not args.no_row_strips,
            write_overviews=not args.no_overviews,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "overviews": [str(p) for p in out["overviews"]],
                    "snapshots": len(out["snapshots"]),
                    "rowStrips": len(out["row_strips"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    identities = pfc.detect_lark_identities()
    wb_tokens = list(args.whiteboard_token)
    if args.url and not wb_tokens:
        uinfo = pfc.parse_feishu_url(args.url)
        if uinfo.get("block_token"):
            wb_tokens.append(uinfo["block_token"])
        elif uinfo.get("resource_type") == "wiki":
            wresp, _ = pfc.call_with_identity_fallback(["wiki", "+node-get", "--node-token", uinfo["resource_token"]], identities)
            doc_tok = (wresp.get("data") or {}).get("obj_token") or ""
            if doc_tok:
                dresp, _ = pfc.call_with_identity_fallback(["docs", "+fetch", "--api-version", "v2", "--doc", doc_tok], identities)
                content = ((dresp.get("data") or {}).get("document") or {}).get("content") or ""
                parsed_doc = pfc.parse_doc_markup(content)
                wb_tokens.extend(w["token"] for w in parsed_doc.get("whiteboards", []))

    if not wb_tokens:
        print(json.dumps({"ok": False, "error": "请传入 --url、--whiteboard-token 或 --nodes-json"}, ensure_ascii=False))
        return 1

    raw_tmp = args.out_dir / "_tmp"
    summary: dict[str, Any] = {"ok": True, "overviews": [], "snapshots": 0, "rowStrips": 0}
    blocked: set[str] = set()
    try:
        raw_token_files = {}
        for tok in wb_tokens:
            raw_resp, _ = pfc.call_with_identity_fallback(
                ["whiteboard", "+export", "--whiteboard-token", tok, "--output-type", "raw"],
                identities,
            )
            raw_nodes = (raw_resp.get("data") or {}).get("nodes") or []
            analyzed = pfc.analyze_whiteboard_nodes(raw_nodes, board_token=tok)
            parsed = analyzed.pop("_parsed_nodes", None) or pfc._normalize_nodes(raw_nodes)
            needed = {im["token"] for im in parsed.get("images", []) if im.get("token")}
            for img_tok in sorted(needed):
                if img_tok in raw_token_files:
                    continue
                saved, _ = pfc.download_whiteboard_media(
                    img_tok, raw_tmp, img_tok, identities, blocked_download_identities=blocked
                )
                if saved and Path(saved).is_file():
                    raw_token_files[img_tok] = Path(saved)
            res = reconstruct_and_crop_board(
                analyzed_board=analyzed,
                parsed=parsed,
                raw_token_files=raw_token_files,
                dest_dir=args.out_dir,
                zones=selected_zones,
                write_row_strips=not args.no_row_strips,
                write_overviews=not args.no_overviews,
            )
            summary["overviews"].extend(str(p) for p in res["overviews"])
            summary["snapshots"] += len(res["snapshots"])
            summary["rowStrips"] += len(res["row_strips"])
    finally:
        shutil.rmtree(raw_tmp, ignore_errors=True)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
