#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build minimalist floating-canvas visual final-review deliverables for DUMIK:
1. Full-height annotated images (<stem>_审稿标注.jpg) with crisp numbered colored
   boxes rendered using Google Sans (Latin/digits) + MiSans (Chinese).
2. A minimalist, self-contained offline HTML review canvas (终稿审查报告_<项目名>.html):
   - No top header bar, no sidebar: one smooth scrollable infinite vertical canvas.
   - Center: seamless continuous detail page flow (0px gap) with clickable colored
     bounding boxes.
   - Left & Right margins: floating comment cards connected by thin curved SVG
     leader lines with anchor dots, scrolling naturally with the canvas.
   - Top-right fixed floating Info Navigation Card with progress bar, severity
     filters, collapsible body, and per-issue mini thumbnail items with modern
     CSS Scrollspy (scroll-target-group + IntersectionObserver fallback) &
     standardized custom scrollbars.
   - Copyable text uses user-select: text (supports partial drag selection) plus
     one-click full-block Copy buttons.
   - Large (+50% bigger) Feishu planning reference previews inside each card,
     clicking opens a native <dialog closedby="any"> lightbox with scroll-chain
     containment (overscroll-behavior: contain) and safe ref ID lookup (never breaks
     on Windows backslash paths).
   - Efficiency boosters: shorthand JSON support (images as paths, auto plan_ref
     resolution by screen ID like S03/M01, copy shorthand string/list, automatic
     compliance-to-red escalation, and multi-threaded image/thumbnail encoding).
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import html
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

SEVERITY_META = {
    "error": {
        "label": "必改",
        "color": (229, 46, 46),
        "fill": (229, 46, 46, 28),
        "hex": "#E52E2E",
    },
    "missing": {
        "label": "漏填",
        "color": (235, 118, 12),
        "fill": (235, 118, 12, 26),
        "hex": "#EB760C",
    },
    "warn": {
        "label": "优化",
        "color": (30, 122, 232),
        "fill": (30, 122, 232, 24),
        "hex": "#1E7AE8",
    },
}

COMPLIANCE_RED_KEYWORDS = (
    "违禁",
    "极限词",
    "行业领先",
    "无菌空间",
    "国家权威",
    "国家级",
    "免责声明",
    "来源注",
    "合规红线",
    "广告法",
)
SCREEN_ID_RE = re.compile(r"\b((?:S|M|E)\d{1,2})\b", re.IGNORECASE)


def _load_var_font(candidates: list[str], size: int, variation: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in candidates:
        if os.path.isfile(fp):
            try:
                f = ImageFont.truetype(fp, size)
                if variation:
                    try:
                        f.set_variation_by_name(variation)
                    except Exception:
                        pass
                return f
            except Exception:
                continue
    return ImageFont.load_default()


def get_mixed_fonts(size: int, bold: bool = True) -> tuple[Any, Any]:
    local_fonts = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    latin_candidates = [
        os.path.join(local_fonts, "GoogleSansFlex-VariableFont_ROND,opsz,slnt,wdth,wght.ttf"),
        r"C:\Windows\Fonts\GoogleSansFlex-VariableFont_ROND,opsz,slnt,wdth,wght.ttf",
        os.path.join(local_fonts, "GoogleSans-Bold.ttf" if bold else "GoogleSans-Regular.ttf"),
        r"C:\Windows\Fonts\GoogleSans-Bold.ttf" if bold else r"C:\Windows\Fonts\GoogleSans-Regular.ttf",
        r"C:\Windows\Fonts\MiSansVF.ttf",
        os.path.join(local_fonts, "MiSansVF.ttf"),
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    cn_candidates = [
        r"C:\Windows\Fonts\MiSansVF.ttf",
        os.path.join(local_fonts, "MiSansVF.ttf"),
        r"C:\Windows\Fonts\MiSans-Semibold.ttf" if bold else r"C:\Windows\Fonts\MiSans-Regular.ttf",
        os.path.join(local_fonts, "MiSans-Semibold.ttf" if bold else "MiSans-Regular.ttf"),
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    latin_font = _load_var_font(latin_candidates, size, "SemiBold" if bold else "Regular")
    cn_font = _load_var_font(cn_candidates, size, "Semibold" if bold else "Regular")
    return latin_font, cn_font


def _split_runs(text: str) -> list[tuple[bool, str]]:
    if not text:
        return []
    runs: list[tuple[bool, str]] = []
    cur_latin = ord(text[0]) < 128
    buf = [text[0]]
    for ch in text[1:]:
        is_lat = ord(ch) < 128
        if is_lat == cur_latin:
            buf.append(ch)
        else:
            runs.append((cur_latin, "".join(buf)))
            cur_latin = is_lat
            buf = [ch]
    runs.append((cur_latin, "".join(buf)))
    return runs


def measure_mixed_text(draw: ImageDraw.ImageDraw, text: str, latin_font: Any, cn_font: Any) -> tuple[int, int]:
    total_w = 0.0
    max_h = 0
    for is_lat, seg in _split_runs(text):
        f = latin_font if is_lat else cn_font
        total_w += draw.textlength(seg, font=f)
        tb = draw.textbbox((0, 0), seg, font=f)
        max_h = max(max_h, tb[3] - tb[1])
    return int(round(total_w)), max_h


def draw_mixed_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[float, float],
    text: str,
    latin_font: Any,
    cn_font: Any,
    fill: tuple[int, int, int, int],
) -> None:
    x, y = pos
    try:
        lat_asc, _ = latin_font.getmetrics()
        cn_asc, _ = cn_font.getmetrics()
    except Exception:
        lat_asc, cn_asc = 0, 0
    base_asc = max(lat_asc, cn_asc)
    for is_lat, seg in _split_runs(text):
        f = latin_font if is_lat else cn_font
        asc = lat_asc if is_lat else cn_asc
        dy = (base_asc - asc) if base_asc else 0
        draw.text((x, y + dy), seg, fill=fill, font=f)
        x += draw.textlength(seg, font=f)


def clamp_bbox(bbox: list[int | float], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    x1 = max(2, min(w - 6, x1))
    y1 = max(2, min(h - 6, y1))
    x2 = max(x1 + 12, min(w - 2, x2))
    y2 = max(y1 + 12, min(h - 2, y2))
    return x1, y1, x2, y2


def draw_issue_box(
    overlay: Image.Image,
    issue_id: str,
    short_tag: str,
    severity: str,
    bbox: tuple[int, int, int, int],
    scale_ref_w: int = 790,
) -> None:
    meta = SEVERITY_META.get(severity, SEVERITY_META["error"])
    color = meta["color"]
    fill_rgba = meta["fill"]

    draw = ImageDraw.Draw(overlay, "RGBA")
    x1, y1, x2, y2 = bbox
    scale = max(0.85, min(2.2, scale_ref_w / 790.0))
    stroke = max(3, int(round(4 * scale)))
    radius = max(7, int(round(9 * scale)))

    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill_rgba)
    draw.rounded_rectangle(
        [x1 - 2, y1 - 2, x2 + 2, y2 + 2],
        radius=radius + 2,
        outline=(255, 255, 255, 235),
        width=stroke + 3,
    )
    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=radius,
        outline=(*color, 255),
        width=stroke,
    )

    font_sz = max(17, int(round(19 * scale)))
    lat_f, cn_f = get_mixed_fonts(font_sz, bold=True)
    badge_text = f"#{issue_id} {short_tag}" if short_tag else f"#{issue_id}"
    tw, th = measure_mixed_text(draw, badge_text, lat_f, cn_f)
    pad_x = int(round(10 * scale))
    pad_y = int(round(6 * scale))
    bw = tw + pad_x * 2
    bh = max(th + pad_y * 2, int(round(font_sz * 1.48)))

    bx1 = x1
    by1 = y1 - bh - 4
    if by1 < 4:
        by1 = y1 + 4
    if bx1 + bw > overlay.width - 4:
        bx1 = max(4, overlay.width - bw - 4)
    bx2 = bx1 + bw
    by2 = by1 + bh

    draw.rounded_rectangle([bx1 - 2, by1 - 2, bx2 + 2, by2 + 2], radius=8, fill=(255, 255, 255, 240))
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=6, fill=(*color, 255))
    draw_mixed_text(draw, (bx1 + pad_x, by1 + pad_y - 2), badge_text, lat_f, cn_f, fill=(255, 255, 255, 255))


def img_to_data_uri(img: Image.Image, max_width: int = 790, quality: int = 86) -> str:
    work = img.convert("RGB")
    if max_width and work.width > max_width:
        nh = int(round(work.height * (max_width / work.width)))
        work = work.resize((max_width, max(1, nh)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    work.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def make_nav_thumb_uri(base_img: Image.Image, bbox: tuple[int, int, int, int], severity: str) -> str:
    """Create a crisp 116x84 mini preview thumbnail showing context + tiny colored marker."""
    w, h = base_img.size
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    bw = max(x2 - x1, 220)
    bh = max(y2 - y1, 160)
    target_ratio = 116.0 / 84.0
    crop_w = min(w, max(bw * 1.45, bh * target_ratio * 1.25))
    crop_h = min(h, crop_w / target_ratio)
    if crop_h < bh * 1.2:
        crop_h = min(h, bh * 1.25)
        crop_w = min(w, crop_h * target_ratio)

    lx1 = int(round(max(0, min(w - crop_w, cx - crop_w / 2))))
    ly1 = int(round(max(0, min(h - crop_h, cy - crop_h / 2))))
    lx2 = int(round(min(w, lx1 + crop_w)))
    ly2 = int(round(min(h, ly1 + crop_h)))

    sub = base_img.crop((lx1, ly1, lx2, ly2)).convert("RGB")
    sw, sh = sub.size
    tw, th = 116, 84
    sub = sub.resize((tw, th), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(sub)
    sx = tw / max(1, sw)
    sy = th / max(1, sh)
    rx1 = max(1, int(round((x1 - lx1) * sx)))
    ry1 = max(1, int(round((y1 - ly1) * sy)))
    rx2 = min(tw - 2, max(rx1 + 6, int(round((x2 - lx1) * sx))))
    ry2 = min(th - 2, max(ry1 + 6, int(round((y2 - ly1) * sy))))
    col = SEVERITY_META.get(severity, SEVERITY_META["error"])["color"]
    draw.rectangle([rx1, ry1, rx2, ry2], outline=col, width=2)
    return img_to_data_uri(sub, max_width=116, quality=80)


def resolve_ref_path(raw: str, screen: str, project_root: Path | None) -> Path | None:
    """Resolve explicit plan_ref OR auto-discover Feishu canvas ref by screen ID (e.g. S03 -> 素材/飞书画布/S03_画布原图.png)."""
    if raw and raw.strip():
        p = Path(raw)
        if p.is_file():
            return p.resolve()
        if project_root:
            cand = project_root / raw
            if cand.is_file():
                return cand.resolve()
    if project_root and screen:
        m = SCREEN_ID_RE.search(screen)
        if m:
            sid = m.group(1).upper()
            board_dir = project_root / "素材" / "飞书画布"
            for suffix in ("_画布原图.png", "_整行.png", "_画布原图.jpg"):
                cand = board_dir / f"{sid}{suffix}"
                if cand.is_file():
                    return cand.resolve()
    return None


def normalize_copy_blocks(raw_issue: dict[str, Any]) -> list[dict[str, str]]:
    """Support full copy_blocks OR concise shorthand 'copy': str | list[str | dict]."""
    blocks: list[dict[str, str]] = []
    raw_list = raw_issue.get("copy_blocks")
    if raw_list is None and "copy" in raw_issue:
        cval = raw_issue["copy"]
        raw_list = [cval] if isinstance(cval, str) else list(cval or [])
    for idx, item in enumerate(raw_list or [], start=1):
        if isinstance(item, str):
            if item.strip():
                blocks.append({"label": "修改文案" if len(raw_list) == 1 else f"修改文案 {idx}", "text": item})
        elif isinstance(item, dict) and str(item.get("text") or "").strip():
            blocks.append({"label": str(item.get("label") or f"修改文案 {idx}"), "text": str(item["text"])})
    return blocks


def normalize_severity(raw_issue: dict[str, Any]) -> str:
    sev = str(raw_issue.get("severity") or "error").lower()
    if sev not in SEVERITY_META:
        sev = "error"
    # Guardrail: compliance / prohibited-word findings are ALWAYS red ("error")
    haystack = " ".join(
        str(raw_issue.get(k) or "") for k in ("short_tag", "title", "issue")
    )
    if any(kw in haystack for kw in COMPLIANCE_RED_KEYWORDS):
        return "error"
    return sev


def trim_trailing_solid(img: Image.Image, min_keep_y: int) -> Image.Image:
    w, h = img.size
    if h <= 3000:
        return img
    rgb = img.convert("RGB")
    probe_h = 80
    cut_y = h
    while cut_y - probe_h > max(min_keep_y + 180, 1200):
        band = rgb.crop((0, cut_y - probe_h, w, cut_y)).resize((48, 16))
        ext = band.getextrema()
        if all((hi - lo) <= 6 for lo, hi in ext):
            cut_y -= probe_h
        else:
            break
    if cut_y < h - 160:
        return img.crop((0, 0, w, min(h, cut_y + 40)))
    return img


def build_html_report(
    project_name: str,
    pages_data: list[dict[str, Any]],
    cards_data: list[dict[str, Any]],
    plan_ref_pool: dict[str, str],
) -> str:
    cnt_error = sum(1 for c in cards_data if c["severity"] == "error")
    cnt_missing = sum(1 for c in cards_data if c["severity"] == "missing")
    cnt_warn = sum(1 for c in cards_data if c["severity"] == "warn")
    total = len(cards_data)

    payload_json = json.dumps(
        {
            "projectName": project_name,
            "planRefs": plan_ref_pool,
            "pages": pages_data,
            "cards": cards_data,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    title_esc = html.escape(f"{project_name} · 终稿审查")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title_esc}</title>
<style>
  :root {{
    --font-stack: "Google Sans Flex", "Google Sans", "Google Sans Text", "MiSans VF", "MiSans", "PingFang SC", "Microsoft YaHei", sans-serif;
    --bg: #ECEBE7;
    --surface: #FFFFFF;
    --ink: #191918;
    --muted: #76746E;
    --line: #E2E0D9;
    --err: #E52E2E;
    --miss: #EB760C;
    --warn: #1E7AE8;
    --ok: #1F9D55;
    --nav-w: 258px;
    --detail-w: 610px;
    --card-w: 420px;
    --gap-x: 46px;
    --scrollbar-thumb: #9C988F;
    --scrollbar-track: #F2F0EA;
  }}
  @media (max-width: 1840px) {{
    :root {{ --detail-w: 560px; --card-w: 380px; --gap-x: 38px; --nav-w: 244px; }}
  }}
  @media (max-width: 1620px) {{
    :root {{ --detail-w: 520px; --card-w: 340px; --gap-x: 30px; --nav-w: 232px; }}
  }}

  * {{ box-sizing: border-box; }}
  html {{
    scroll-behavior: smooth;
  }}
  html, body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--font-stack);
    -webkit-font-smoothing: antialiased;
  }}

  /* Right-top floating Info & Navigation Card (replaces full-width top bar) */
  .nav-card {{
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 80;
    width: var(--nav-w);
    max-height: calc(100vh - 32px);
    display: flex;
    flex-direction: column;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(25, 25, 24, 0.11);
    border-radius: 14px;
    box-shadow: 0 10px 34px rgba(25, 25, 24, 0.12);
    overflow: hidden;
    transition: width 0.18s ease;
  }}
  .nav-card.collapsed {{
    width: auto;
  }}
  .nav-card.collapsed .nav-collapsible {{
    display: none;
  }}

  .nav-head {{
    padding: 11px 13px 9px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }}
  .nav-title-wrap {{
    min-width: 0;
  }}
  .nav-title {{
    font-size: 13.5px;
    font-weight: 700;
    letter-spacing: -0.01em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .nav-prog-row {{
    margin-top: 5px;
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
  }}
  .prog-track {{
    flex: 1;
    min-width: 68px;
    height: 4px;
    background: #E4E2DB;
    border-radius: 99px;
    overflow: hidden;
  }}
  .prog-fill {{
    height: 100%;
    width: 0%;
    background: var(--ok);
    transition: width 0.2s;
  }}
  .nav-head-btns {{
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
  }}
  .icon-btn {{
    font-family: var(--font-stack);
    border: 1px solid var(--line);
    background: #FAF9F6;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 3px 7px;
    border-radius: 6px;
    cursor: pointer;
  }}
  .icon-btn:hover {{ color: var(--ink); border-color: #C7C4BA; }}

  .nav-filters {{
    padding: 8px 10px;
    border-bottom: 1px solid var(--line);
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    background: #FAF9F6;
  }}
  .f-btn {{
    font-family: var(--font-stack);
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 3px 7px;
    border-radius: 6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: background 0.12s, color 0.12s;
  }}
  .f-btn:hover {{ background: #ECEAE3; color: var(--ink); }}
  .f-btn.active {{ background: #191918; color: #FFF; }}
  .dot {{ width: 6px; height: 6px; border-radius: 50%; display: inline-block; }}
  .dot-err {{ background: var(--err); }}
  .dot-miss {{ background: var(--miss); }}
  .dot-warn {{ background: var(--warn); }}

  /* Scrollspy navigation list with thumbnails & modern scrollbar styling */
  .nav-list {{
    scroll-target-group: auto;
    overflow-y: auto;
    padding: 7px 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    scrollbar-width: thin;
    scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
  }}
  @supports not (scrollbar-color: auto) {{
    .nav-list {{ scrollbar-width: auto; }}
    .nav-list::-webkit-scrollbar {{ width: 7px; }}
    .nav-list::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 99px; }}
    .nav-list::-webkit-scrollbar-track {{ background: var(--scrollbar-track); }}
  }}
  .nav-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 6px;
    border-radius: 8px;
    text-decoration: none;
    color: var(--ink);
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    transition: background 0.12s, border-color 0.12s, opacity 0.15s;
  }}
  .nav-item:hover {{
    background: #F4F2EC;
  }}
  .nav-item:is(:target-current, .target-current) {{
    background: #F3F1EA;
    border-color: #DCD9CF;
    border-left-color: #191918;
    font-weight: 700;
  }}
  .nav-item.done {{
    opacity: 0.42;
  }}
  .nav-item.hidden {{
    display: none;
  }}
  .nav-thumb {{
    width: 52px;
    height: 38px;
    border-radius: 5px;
    object-fit: cover;
    border: 1px solid var(--line);
    background: #EFECE5;
    flex-shrink: 0;
  }}
  .nav-item-info {{
    min-width: 0;
    flex: 1;
  }}
  .nav-item-top {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
  }}
  .nav-num {{
    font-weight: 700;
    color: #FFF;
    padding: 0.5px 5px;
    border-radius: 4px;
    font-size: 10px;
    flex-shrink: 0;
  }}
  .sev-error .nav-num {{ background: var(--err); }}
  .sev-missing .nav-num {{ background: var(--miss); }}
  .sev-warn .nav-num {{ background: var(--warn); }}
  .nav-scr {{
    color: var(--muted);
    font-size: 10.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .nav-tag {{
    margin-top: 2px;
    font-size: 11.5px;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Full-width infinite scrollable canvas (reserves space on right for fixed nav card) */
  .canvas-shell {{
    width: 100%;
    overflow-x: auto;
    padding: 22px calc(var(--nav-w) + 34px) 120px 22px;
    transition: padding-right 0.18s ease;
  }}
  body.nav-collapsed .canvas-shell {{
    padding-right: 22px;
  }}
  .stage {{
    position: relative;
    width: calc(var(--card-w) * 2 + var(--gap-x) * 2 + var(--detail-w));
    margin: 0 auto;
    min-height: 800px;
  }}

  /* SVG thin leader-line layer */
  .wires-svg {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 10;
    overflow: visible;
  }}
  .wire-path {{
    fill: none;
    stroke-width: 1.4;
    stroke-linecap: round;
    opacity: 0.62;
    transition: opacity 0.15s, stroke-width 0.15s;
  }}
  .wire-path.active {{ stroke-width: 2.4; opacity: 1; }}
  .wire-path.done {{ opacity: 0.22; stroke-dasharray: 4 4; }}
  .wire-dot {{ opacity: 0.85; transition: opacity 0.15s; }}
  .wire-dot.active {{ opacity: 1; }}
  .wire-dot.done {{ opacity: 0.28; }}

  /* Centered seamless continuous detail page */
  .detail-col {{
    position: relative;
    width: var(--detail-w);
    margin: 0 auto;
    background: #FFF;
    box-shadow: 0 6px 32px rgba(25, 25, 24, 0.1);
    border-radius: 4px;
    overflow: hidden;
    font-size: 0;
    z-index: 5;
  }}
  .page-seg {{
    position: relative;
    width: 100%;
    display: block;
    line-height: 0;
  }}
  .page-seg img {{
    display: block;
    width: 100%;
    height: auto;
  }}
  .hotspot {{
    position: absolute;
    cursor: pointer;
    border-radius: 6px;
    scroll-margin-top: 28vh;
    outline: none;
    transition: box-shadow 0.15s, background 0.15s;
  }}
  .hotspot:hover, .hotspot.active {{
    background: rgba(255, 255, 255, 0.14);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.95), 0 0 0 5px rgba(25, 25, 24, 0.72);
    z-index: 6;
  }}
  .hotspot.is-done {{
    background: rgba(31, 157, 85, 0.16);
  }}

  /* Floating cards layer (left & right wings) */
  .float-layer {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 20;
  }}
  .f-card {{
    position: absolute;
    width: var(--card-w);
    pointer-events: auto;
    background: rgba(255, 255, 255, 0.97);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(25, 25, 24, 0.09);
    border-radius: 12px;
    padding: 13px 14px;
    box-shadow: 0 4px 20px rgba(25, 25, 24, 0.06);
    transition: box-shadow 0.15s, border-color 0.15s, opacity 0.18s;
  }}
  .f-card:hover, .f-card.active {{
    border-color: rgba(25, 25, 24, 0.36);
    box-shadow: 0 10px 30px rgba(25, 25, 24, 0.14);
    z-index: 35;
  }}
  .f-card.done {{ opacity: 0.48; }}
  .f-card.done .card-body {{ display: none; }}
  .f-card.hidden {{ display: none; }}

  .c-head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }}
  .c-meta {{
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }}
  .badge {{
    font-size: 11px;
    font-weight: 700;
    color: #FFF;
    padding: 2px 7px;
    border-radius: 5px;
    flex-shrink: 0;
  }}
  .sev-error .badge {{ background: var(--err); }}
  .sev-missing .badge {{ background: var(--miss); }}
  .sev-warn .badge {{ background: var(--warn); }}
  .screen {{
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .done-chk {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11.5px;
    font-weight: 500;
    color: var(--muted);
    cursor: pointer;
    flex-shrink: 0;
    user-select: none;
  }}
  .done-chk input {{
    accent-color: var(--ok);
    width: 14px;
    height: 14px;
    margin: 0;
    cursor: pointer;
  }}

  .card-body {{ margin-top: 8px; }}
  .c-title {{
    font-size: 14px;
    font-weight: 700;
    line-height: 1.4;
    margin: 0 0 3px;
  }}
  .c-desc {{
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.5;
    margin: 0 0 8px;
  }}

  .copy-row {{
    border: 1px solid #E7E5DE;
    background: #F8F7F4;
    border-radius: 8px;
    margin-top: 6px;
    overflow: hidden;
  }}
  .copy-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 9px;
    border-bottom: 1px solid #ECEAE3;
    background: #F2F0EA;
  }}
  .copy-lbl {{
    font-size: 11px;
    font-weight: 600;
    color: #5E5B54;
  }}
  .copy-btn {{
    font-family: var(--font-stack);
    border: none;
    background: #191918;
    color: #FFF;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 5px;
    cursor: pointer;
    transition: background 0.12s;
  }}
  .copy-btn:hover {{ background: #3A3936; }}
  .copy-btn.copied {{ background: var(--ok); }}
  /* Support free partial drag-selection (never user-select: all) */
  .copy-txt {{
    margin: 0;
    padding: 8px 10px;
    font-family: var(--font-stack);
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    white-space: pre-wrap;
    word-break: break-word;
    user-select: text;
    -webkit-user-select: text;
    cursor: text;
  }}

  .action-tip {{
    margin-top: 6px;
    font-size: 12px;
    color: #6B573A;
    background: #FFFBF2;
    border: 1px solid #EFE2C4;
    border-radius: 6px;
    padding: 6px 9px;
  }}

  /* +50% enlarged Feishu planning reference preview */
  .plan-box {{
    margin-top: 10px;
    border: 1px solid var(--line);
    border-radius: 9px;
    overflow: hidden;
    background: #F6F5F1;
    cursor: zoom-in;
  }}
  .plan-box-head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 5px 10px;
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    background: #F1EFE9;
    border-bottom: 1px solid var(--line);
  }}
  .plan-box img {{
    display: block;
    width: 100%;
    max-height: 410px;
    object-fit: contain;
    background: #FAF9F6;
  }}

  /* Native modal <dialog> lightbox with light-dismiss & scroll-chain containment */
  dialog.lightbox {{
    padding: 0;
    border: none;
    background: transparent;
    max-width: 94vw;
    max-height: 92vh;
    overflow: auto;
    overscroll-behavior: contain;
  }}
  dialog.lightbox::backdrop {{
    background: rgba(15, 15, 14, 0.84);
    backdrop-filter: blur(4px);
    overflow: hidden;
    overscroll-behavior: contain;
  }}
  .lb-inner {{
    position: relative;
    background: #1C1B19;
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 20px 56px rgba(0, 0, 0, 0.52);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }}
  .lb-bar {{
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    color: #F4F3EE;
    font-size: 13px;
    font-weight: 600;
    padding: 2px 4px;
  }}
  .lb-close {{
    font-family: var(--font-stack);
    border: 1px solid rgba(255, 255, 255, 0.24);
    background: rgba(255, 255, 255, 0.12);
    color: #FFF;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 7px;
    cursor: pointer;
  }}
  .lb-close:hover {{ background: rgba(255, 255, 255, 0.24); }}
  .lb-inner img {{
    display: block;
    max-width: 88vw;
    max-height: 82vh;
    object-fit: contain;
    border-radius: 6px;
    background: #FFF;
  }}
</style>
</head>
<body>

<aside class="nav-card" id="nav-card" aria-label="审稿信息导航卡">
  <div class="nav-head">
    <div class="nav-title-wrap">
      <div class="nav-title">{title_esc}</div>
      <div class="nav-prog-row">
        <div class="prog-track"><div class="prog-fill" id="prog-fill"></div></div>
        <span id="prog-txt">0 / {total}</span>
      </div>
    </div>
    <div class="nav-head-btns">
      <button class="icon-btn nav-collapsible" type="button" onclick="resetDone()" title="重置勾选">重置</button>
      <button class="icon-btn" type="button" id="collapse-btn" onclick="toggleNav()" title="收起/展开导航">收起</button>
    </div>
  </div>
  <div class="nav-filters nav-collapsible">
    <button class="f-btn active" type="button" data-f="all" onclick="setFilter('all', this)">全部 {total}</button>
    <button class="f-btn" type="button" data-f="error" onclick="setFilter('error', this)"><span class="dot dot-err"></span>必改 {cnt_error}</button>
    <button class="f-btn" type="button" data-f="missing" onclick="setFilter('missing', this)"><span class="dot dot-miss"></span>漏填 {cnt_missing}</button>
    <button class="f-btn" type="button" data-f="warn" onclick="setFilter('warn', this)"><span class="dot dot-warn"></span>优化 {cnt_warn}</button>
    <button class="f-btn" type="button" data-f="todo" onclick="setFilter('todo', this)">未改</button>
  </div>
  <nav class="nav-list nav-collapsible" id="nav-list" aria-label="问题快速定位"></nav>
</aside>

<main class="canvas-shell">
  <div class="stage" id="stage">
    <svg class="wires-svg" id="wires-svg"></svg>
    <div class="detail-col" id="detail-col"></div>
    <div class="float-layer" id="float-layer"></div>
  </div>
</main>

<dialog class="lightbox" id="lightbox" closedby="any" aria-labelledby="lb-cap">
  <div class="lb-inner">
    <div class="lb-bar">
      <span id="lb-cap">策划原图放大</span>
      <form method="dialog" style="margin:0;">
        <button class="lb-close" type="submit">关闭 (Esc)</button>
      </form>
    </div>
    <img id="lb-img" src="" alt="策划原图放大预览" />
  </div>
</dialog>

<script>
const DATA = {payload_json};
const SEV_COLOR = {{ error: "#E52E2E", missing: "#EB760C", warn: "#1E7AE8" }};
const STORE_KEY = "dumik_review_done_v4_" + DATA.projectName;
let currentFilter = "all";
let hoverId = null;
let doneMap = {{}};
try {{ doneMap = JSON.parse(localStorage.getItem(STORE_KEY) || "{{}}"); }} catch (e) {{ doneMap = {{}}; }}

function saveDone() {{
  try {{ localStorage.setItem(STORE_KEY, JSON.stringify(doneMap)); }} catch (e) {{}}
}}

function esc(s) {{
  return String(s || "").replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

function copyText(btn, text, ev) {{
  if (ev) ev.stopPropagation();
  const ok = () => {{
    btn.textContent = "已复制";
    btn.classList.add("copied");
    setTimeout(() => {{
      btn.textContent = "复制";
      btn.classList.remove("copied");
    }}, 1200);
  }};
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(text).then(ok).catch(() => fallbackCopy(text, ok));
  }} else {{
    fallbackCopy(text, ok);
  }}
}}

function fallbackCopy(text, cb) {{
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  try {{ document.execCommand("copy"); }} catch (e) {{}}
  document.body.removeChild(ta);
  cb();
}}

// Native <dialog> lightbox with safe refId lookup + fallback light-dismiss
const lbDialog = document.getElementById("lightbox");
const lbImg = document.getElementById("lb-img");
const lbCap = document.getElementById("lb-cap");

function openLightboxByRef(refId, caption) {{
  const src = DATA.planRefs[refId];
  if (!src) return;
  lbImg.src = src;
  lbCap.textContent = caption || "策划原图放大预览";
  if (typeof lbDialog.showModal === "function") {{
    if (!lbDialog.open) lbDialog.showModal();
  }} else {{
    lbDialog.setAttribute("open", "");
  }}
}}

if (!("closedBy" in HTMLDialogElement.prototype)) {{
  lbDialog.addEventListener("click", (event) => {{
    if (event.target !== lbDialog) return;
    const rect = lbDialog.getBoundingClientRect();
    const inside = (
      rect.top <= event.clientY && event.clientY <= rect.top + rect.height &&
      rect.left <= event.clientX && event.clientX <= rect.left + rect.width
    );
    if (!inside) lbDialog.close();
  }});
}}

function toggleNav() {{
  const card = document.getElementById("nav-card");
  const btn = document.getElementById("collapse-btn");
  const collapsed = card.classList.toggle("collapsed");
  document.body.classList.toggle("nav-collapsed", collapsed);
  btn.textContent = collapsed ? "展开" : "收起";
  scheduleLayout();
}}

function updateProgress() {{
  const total = DATA.cards.length;
  const done = DATA.cards.filter(c => doneMap[c.id]).length;
  document.getElementById("prog-fill").style.width = (total ? Math.round(done / total * 100) : 0) + "%";
  document.getElementById("prog-txt").textContent = `${{done}} / ${{total}}`;
}}

function isCardVisible(c) {{
  if (currentFilter === "all") return true;
  if (currentFilter === "todo") return !doneMap[c.id];
  return c.severity === currentFilter;
}}

function highlightPair(id) {{
  hoverId = id;
  document.querySelectorAll(".hotspot.active, .f-card.active, .wire-path.active, .wire-dot.active")
    .forEach(el => el.classList.remove("active"));
  if (!id) return;
  ["hs-", "fcard-", "wire-", "dot1-", "dot2-"].forEach(pre => {{
    const el = document.getElementById(pre + id);
    if (el) el.classList.add("active");
  }});
}}

function focusIssue(id) {{
  highlightPair(id);
  const hs = document.getElementById("hs-" + id);
  if (hs) hs.scrollIntoView({{ behavior: "smooth", block: "center" }});
}}

function toggleDone(id, chk, ev) {{
  if (ev) ev.stopPropagation();
  doneMap[id] = chk.checked;
  saveDone();
  updateProgress();
  const fc = document.getElementById("fcard-" + id);
  if (fc) fc.classList.toggle("done", chk.checked);
  const hs = document.getElementById("hs-" + id);
  if (hs) hs.classList.toggle("is-done", chk.checked);
  const ni = document.getElementById("nav-" + id);
  if (ni) ni.classList.toggle("done", chk.checked);
  applyVisibilityAndLayout();
}}

function resetDone() {{
  doneMap = {{}};
  saveDone();
  document.querySelectorAll(".f-card").forEach(el => {{
    el.classList.remove("done");
    const inp = el.querySelector('input[type="checkbox"]');
    if (inp) inp.checked = false;
  }});
  document.querySelectorAll(".hotspot").forEach(el => el.classList.remove("is-done"));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("done"));
  updateProgress();
  applyVisibilityAndLayout();
}}

function setFilter(f, btn) {{
  currentFilter = f;
  document.querySelectorAll(".f-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  applyVisibilityAndLayout();
}}

function renderStream() {{
  const col = document.getElementById("detail-col");
  col.innerHTML = "";
  for (const pg of DATA.pages) {{
    const seg = document.createElement("div");
    seg.className = "page-seg";
    seg.dataset.key = pg.key;
    const spots = pg.hotspots.map(h => `
      <div class="hotspot ${{doneMap[h.id] ? 'is-done' : ''}}"
           id="hs-${{esc(h.id)}}"
           tabindex="-1"
           data-id="${{esc(h.id)}}"
           style="left:${{h.left}}%;top:${{h.top}}%;width:${{h.width}}%;height:${{h.height}}%;"></div>
    `).join("");
    seg.innerHTML = `<img src="${{pg.uri}}" alt="${{esc(pg.label)}}" onload="scheduleLayout()" />${{spots}}`;
    col.appendChild(seg);
  }}
}}

function renderNavList() {{
  const list = document.getElementById("nav-list");
  list.innerHTML = "";
  for (const c of DATA.cards) {{
    const a = document.createElement("a");
    a.id = "nav-" + c.id;
    a.href = "#hs-" + c.id;
    a.className = `nav-item sev-${{c.severity}}` + (doneMap[c.id] ? " done" : "");
    a.dataset.id = c.id;
    a.innerHTML = `
      <img class="nav-thumb" src="${{c.nav_thumb_uri}}" alt="#${{esc(c.id)}}" />
      <div class="nav-item-info">
        <div class="nav-item-top">
          <span class="nav-num">#${{esc(c.id)}}</span>
          <span class="nav-scr">${{esc(c.screen)}}</span>
        </div>
        <div class="nav-tag">${{esc(c.short_tag || c.title)}}</div>
      </div>
    `;
    list.appendChild(a);
  }}
}}

function renderFloatingCards() {{
  const layer = document.getElementById("float-layer");
  layer.innerHTML = "";
  for (const c of DATA.cards) {{
    const isDone = !!doneMap[c.id];
    const planSrc = c.plan_ref_id ? DATA.planRefs[c.plan_ref_id] : "";
    const el = document.createElement("div");
    el.id = "fcard-" + c.id;
    el.className = `f-card sev-${{c.severity}}` + (isDone ? " done" : "");
    el.dataset.id = c.id;

    const copyHtml = (c.copy_blocks || []).map((b, idx) => `
      <div class="copy-row">
        <div class="copy-bar">
          <span class="copy-lbl">${{esc(b.label || "修改文案")}}</span>
          <button class="copy-btn" type="button" data-cid="${{esc(c.id)}}" data-idx="${{idx}}">复制</button>
        </div>
        <pre class="copy-txt">${{esc(b.text)}}</pre>
      </div>
    `).join("");

    const actionHtml = c.action_note ? `<div class="action-tip">${{esc(c.action_note)}}</div>` : "";

    const planHtml = planSrc ? `
      <div class="plan-box" data-ref-id="${{esc(c.plan_ref_id)}}" data-cap="${{esc(c.screen)}} · 策划原图">
        <div class="plan-box-head">
          <span>策划原图对照</span>
          <span>点击全屏放大</span>
        </div>
        <img src="${{planSrc}}" alt="策划原图" onload="scheduleLayout()" />
      </div>
    ` : "";

    el.innerHTML = `
      <div class="c-head">
        <div class="c-meta">
          <span class="badge">#${{esc(c.id)}} ${{esc(c.severity_label)}}</span>
          <span class="screen">${{esc(c.screen)}}</span>
        </div>
        <label class="done-chk">
          <input type="checkbox" data-done-id="${{esc(c.id)}}" ${{isDone ? "checked" : ""}} />
          <span>已改</span>
        </label>
      </div>
      <div class="card-body">
        <div class="c-title">${{esc(c.title)}}</div>
        <div class="c-desc">${{esc(c.issue)}}</div>
        ${{copyHtml}}
        ${{actionHtml}}
        ${{planHtml}}
      </div>
    `;
    layer.appendChild(el);
  }}
}}

// Clean event delegation (no inline string escaping pitfalls!)
document.addEventListener("click", (ev) => {{
  const copyBtn = ev.target.closest(".copy-btn");
  if (copyBtn) {{
    const cid = copyBtn.getAttribute("data-cid");
    const idx = Number(copyBtn.getAttribute("data-idx"));
    const item = DATA.cards.find(x => x.id === cid);
    if (item && item.copy_blocks && item.copy_blocks[idx]) {{
      copyText(copyBtn, item.copy_blocks[idx].text, ev);
    }}
    return;
  }}
  const planBox = ev.target.closest(".plan-box");
  if (planBox) {{
    openLightboxByRef(planBox.getAttribute("data-ref-id"), planBox.getAttribute("data-cap"));
    return;
  }}
  const hs = ev.target.closest(".hotspot");
  if (hs) {{
    const id = hs.getAttribute("data-id");
    highlightPair(id);
    const fc = document.getElementById("fcard-" + id);
    if (fc && !fc.classList.contains("hidden")) fc.scrollIntoView({{ behavior: "smooth", block: "center" }});
    return;
  }}
  const navA = ev.target.closest(".nav-item");
  if (navA) {{
    ev.preventDefault();
    focusIssue(navA.getAttribute("data-id"));
  }}
}});

document.addEventListener("change", (ev) => {{
  const inp = ev.target.closest('input[data-done-id]');
  if (inp) toggleDone(inp.getAttribute("data-done-id"), inp, ev);
}});

document.addEventListener("mouseover", (ev) => {{
  const target = ev.target.closest(".f-card, .hotspot, .nav-item");
  const nextId = target ? target.getAttribute("data-id") : null;
  if (nextId !== hoverId) highlightPair(nextId);
}});

function applyVisibilityAndLayout() {{
  for (const c of DATA.cards) {{
    const vis = isCardVisible(c);
    const fc = document.getElementById("fcard-" + c.id);
    if (fc) fc.classList.toggle("hidden", !vis);
    const hs = document.getElementById("hs-" + c.id);
    if (hs) hs.style.display = vis ? "" : "none";
    const ni = document.getElementById("nav-" + c.id);
    if (ni) ni.classList.toggle("hidden", !vis);
  }}
  scheduleLayout();
}}

let layoutTimer = null;
function scheduleLayout() {{
  if (layoutTimer) cancelAnimationFrame(layoutTimer);
  layoutTimer = requestAnimationFrame(layoutFloatingNotes);
}}

function layoutFloatingNotes() {{
  const stage = document.getElementById("stage");
  const detailCol = document.getElementById("detail-col");
  const svg = document.getElementById("wires-svg");
  const stageRect = stage.getBoundingClientRect();
  const detailRect = detailCol.getBoundingClientRect();
  const stageLeft = stageRect.left;
  const stageTop = stageRect.top;
  const detailLeft = detailRect.left - stageLeft;
  const detailRight = detailRect.right - stageLeft;
  const detailCenterX = (detailLeft + detailRight) / 2;

  const entries = [];
  for (const c of DATA.cards) {{
    if (!isCardVisible(c)) continue;
    const hs = document.getElementById("hs-" + c.id);
    const fc = document.getElementById("fcard-" + c.id);
    if (!hs || !fc) continue;
    const hr = hs.getBoundingClientRect();
    if (hr.height < 2) continue;
    const boxLeft = hr.left - stageLeft;
    const boxRight = hr.right - stageLeft;
    const boxCenterX = (boxLeft + boxRight) / 2;
    const boxCenterY = (hr.top + hr.bottom) / 2 - stageTop;
    const cardH = fc.offsetHeight || 180;
    entries.push({{ c, fc, boxLeft, boxRight, boxCenterX, boxCenterY, cardH }});
  }}

  entries.sort((a, b) => a.boxCenterY - b.boxCenterY);

  const GAP_Y = 18;
  let bottomLeft = 0;
  let bottomRight = 0;
  const placed = [];

  for (const item of entries) {{
    const idealY = Math.max(0, item.boxCenterY - Math.min(item.cardH * 0.3, 95));
    const yIfLeft = Math.max(idealY, bottomLeft);
    const yIfRight = Math.max(idealY, bottomRight);
    const driftLeft = yIfLeft - idealY;
    const driftRight = yIfRight - idealY;

    const prefersLeft = item.boxCenterX < detailCenterX - 35;
    const prefersRight = item.boxCenterX > detailCenterX + 35;
    let side = "right";
    if (prefersLeft && driftLeft <= driftRight + 120) {{
      side = "left";
    }} else if (prefersRight && driftRight <= driftLeft + 120) {{
      side = "right";
    }} else {{
      side = driftLeft <= driftRight ? "left" : "right";
    }}

    const cardY = side === "left" ? yIfLeft : yIfRight;
    if (side === "left") {{
      bottomLeft = cardY + item.cardH + GAP_Y;
      item.fc.style.left = "0px";
      item.fc.style.right = "auto";
    }} else {{
      bottomRight = cardY + item.cardH + GAP_Y;
      item.fc.style.left = "auto";
      item.fc.style.right = "0px";
    }}
    item.fc.style.top = `${{Math.round(cardY)}}px`;
    placed.push({{ ...item, side, cardY }});
  }}

  const totalH = Math.max(detailCol.offsetHeight + 40, bottomLeft + 40, bottomRight + 40);
  stage.style.minHeight = `${{Math.ceil(totalH)}}px`;
  svg.setAttribute("viewBox", `0 0 ${{stage.offsetWidth}} ${{Math.ceil(totalH)}}`);

  let svgHtml = "";
  const stageW = stage.offsetWidth;
  for (const p of placed) {{
    const col = SEV_COLOR[p.c.severity] || "#E52E2E";
    const isDone = !!doneMap[p.c.id];
    const isAct = hoverId === p.c.id;
    const cls = (isAct ? " active" : "") + (isDone ? " done" : "");

    const cardW = p.fc.offsetWidth;
    const anchorY = Math.round(p.cardY + Math.min(26, p.cardH / 2));
    const boxY = Math.round(p.boxCenterY);

    let x1, x2, mid;
    if (p.side === "left") {{
      x1 = Math.round(p.boxLeft);
      x2 = Math.round(cardW);
      mid = Math.round((x1 + x2) / 2);
    }} else {{
      x1 = Math.round(p.boxRight);
      x2 = Math.round(stageW - cardW);
      mid = Math.round((x1 + x2) / 2);
    }}

    const d = `M ${{x1}} ${{boxY}} C ${{mid}} ${{boxY}}, ${{mid}} ${{anchorY}}, ${{x2}} ${{anchorY}}`;
    svgHtml += `<path id="wire-${{esc(p.c.id)}}" class="wire-path${{cls}}" d="${{d}}" stroke="${{col}}" />`;
    svgHtml += `<circle id="dot1-${{esc(p.c.id)}}" class="wire-dot${{cls}}" cx="${{x1}}" cy="${{boxY}}" r="${{isAct ? 4.5 : 3.5}}" fill="${{col}}" />`;
    svgHtml += `<circle id="dot2-${{esc(p.c.id)}}" class="wire-dot${{cls}}" cx="${{x2}}" cy="${{anchorY}}" r="${{isAct ? 3.5 : 2.8}}" fill="${{col}}" />`;
  }}
  svg.innerHTML = svgHtml;
}}

// Modern Scrollspy: native scroll-target-group + aria-current sync, with IntersectionObserver fallback
function initScrollspy() {{
  const navLinks = () => Array.from(document.querySelectorAll("#nav-list a.nav-item"));
  if (CSS.supports("scroll-target-group: auto")) {{
    const syncAria = () => {{
      const cur = document.querySelector("#nav-list a.nav-item:target-current");
      navLinks().forEach(a => a.setAttribute("aria-current", a === cur ? "true" : "false"));
    }};
    syncAria();
    document.addEventListener("scrollend", syncAria);
  }} else {{
    const obs = new IntersectionObserver((entries) => {{
      for (const e of entries) {{
        if (!e.isIntersecting) continue;
        const id = e.target.getAttribute("data-id");
        navLinks().forEach(a => {{
          const active = a.getAttribute("data-id") === id;
          a.classList.toggle("target-current", active);
          a.setAttribute("aria-current", active ? "true" : "false");
        }});
      }}
    }}, {{ rootMargin: "-35% 0px -45% 0px", threshold: 0 }});
    document.querySelectorAll(".hotspot").forEach(hs => obs.observe(hs));
  }}
}}

window.addEventListener("resize", scheduleLayout);
renderStream();
renderNavList();
renderFloatingCards();
updateProgress();
applyVisibilityAndLayout();
initScrollspy();
setTimeout(scheduleLayout, 250);
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render annotated review images and minimalist floating-canvas HTML review board.")
    parser.add_argument("--spec", required=True, help="Path to temporary review_input.json.")
    parser.add_argument("--project-root", default="", help="Optional project root for auto plan_ref matching and default 成品/审稿报告/ output.")
    parser.add_argument("--out-dir", default="", help="Output directory (defaults to <project-root>/成品/审稿报告 when --project-root is set).")
    parser.add_argument("--workers", type=int, default=6, help="Parallel threads for thumbnails & base64 encoding.")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project_root = Path(args.project_root).resolve() if args.project_root else None
    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif project_root:
        out_dir = project_root / "成品" / "审稿报告"
    else:
        raise ValueError("必须指定 --out-dir 或 --project-root。")
    out_dir.mkdir(parents=True, exist_ok=True)

    project_name = str(spec.get("project_name") or (project_root.name if project_root else "详情页终稿")).strip()

    # Load source images (supports dict entries OR concise raw path strings)
    img_map: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(spec.get("images") or [], start=1):
        if isinstance(item, str):
            p = Path(item)
            key = str(idx)
            label = p.name
        else:
            p = Path(item["path"])
            key = str(item.get("key") or idx)
            label = str(item.get("label") or p.name)
        if not p.is_file():
            raise FileNotFoundError(f"Source image not found: {p}")
        im = Image.open(p).convert("RGB")
        img_map[key] = {
            "key": key,
            "label": label,
            "path": p,
            "image": im,
            "overlay": Image.new("RGBA", im.size, (0, 0, 0, 0)),
            "issues": [],
        }

    issues_raw = list(spec.get("issues") or [])
    path_to_ref_id: dict[Path, str] = {}
    unique_ref_paths: list[tuple[str, Path]] = []
    normalized_issues: list[tuple[dict[str, Any], dict[str, Any], tuple[int, int, int, int], str]] = []

    for idx, raw in enumerate(issues_raw, start=1):
        issue = dict(raw)
        issue["id"] = str(issue.get("id") or f"{idx:02d}").zfill(2)
        sev = normalize_severity(issue)
        issue["severity"] = sev

        img_key = str(issue.get("image_key") or "1")
        if img_key not in img_map:
            raise KeyError(f"Issue #{issue['id']} references unknown image_key={img_key}")
        entry = img_map[img_key]
        base_img: Image.Image = entry["image"]
        bbox = clamp_bbox(issue["bbox"], base_img.width, base_img.height)

        draw_issue_box(
            entry["overlay"],
            issue_id=issue["id"],
            short_tag=str(issue.get("short_tag") or ""),
            severity=sev,
            bbox=bbox,
            scale_ref_w=base_img.width,
        )
        entry["issues"].append((issue, bbox))

        plan_ref_path = resolve_ref_path(str(issue.get("plan_ref") or ""), str(issue.get("screen") or ""), project_root)
        ref_id = ""
        if plan_ref_path:
            if plan_ref_path not in path_to_ref_id:
                ref_id = f"ref_{len(unique_ref_paths) + 1:02d}"
                path_to_ref_id[plan_ref_path] = ref_id
                unique_ref_paths.append((ref_id, plan_ref_path))
            else:
                ref_id = path_to_ref_id[plan_ref_path]

        normalized_issues.append((issue, entry, bbox, ref_id))

    # Parallel encoding for Feishu planning references (+50% sharper) and mini nav thumbnails
    plan_ref_pool: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        ref_futs = {
            rid: pool.submit(lambda rp=rp: img_to_data_uri(Image.open(rp).convert("RGB"), max_width=1100, quality=88))
            for rid, rp in unique_ref_paths
        }
        thumb_futs = [
            pool.submit(make_nav_thumb_uri, entry["image"], bbox, issue["severity"])
            for issue, entry, bbox, _ in normalized_issues
        ]
        for rid, fut in ref_futs.items():
            plan_ref_pool[rid] = fut.result()
        nav_thumbs = [f.result() for f in thumb_futs]

    cards_data: list[dict[str, Any]] = []
    for (issue, _, bbox, ref_id), thumb_uri in zip(normalized_issues, nav_thumbs):
        cards_data.append(
            {
                "id": issue["id"],
                "severity": issue["severity"],
                "severity_label": SEVERITY_META[issue["severity"]]["label"],
                "screen": str(issue.get("screen") or ""),
                "bbox": list(bbox),
                "short_tag": str(issue.get("short_tag") or ""),
                "title": str(issue.get("title") or issue.get("short_tag") or ""),
                "issue": str(issue.get("issue") or ""),
                "copy_blocks": normalize_copy_blocks(issue),
                "action_note": str(issue.get("action_note") or ""),
                "plan_ref_id": ref_id,
                "nav_thumb_uri": thumb_uri,
            }
        )

    pages_data: list[dict[str, Any]] = []
    saved_annotated: list[Path] = []
    for key, entry in img_map.items():
        base_rgba = entry["image"].convert("RGBA")
        merged = Image.alpha_composite(base_rgba, entry["overlay"]).convert("RGB")
        max_issue_y = max((b[3] for _, b in entry["issues"]), default=1200)
        trimmed = trim_trailing_solid(merged, min_keep_y=max_issue_y)

        stem = entry["path"].stem
        out_img = out_dir / f"{stem}_审稿标注.jpg"
        trimmed.save(out_img, quality=92, optimize=True)
        saved_annotated.append(out_img)

        tw, th = trimmed.size
        hotspots = [
            {
                "id": iss["id"],
                "title": iss.get("title") or iss.get("short_tag") or "",
                "left": round((b[0] / tw) * 100, 3),
                "top": round((b[1] / th) * 100, 3),
                "width": round(((b[2] - b[0]) / tw) * 100, 3),
                "height": round(((b[3] - b[1]) / th) * 100, 3),
            }
            for iss, b in entry["issues"]
        ]
        pages_data.append(
            {
                "key": key,
                "label": entry["label"],
                "uri": img_to_data_uri(trimmed, max_width=790, quality=86),
                "hotspots": hotspots,
            }
        )

    html_content = build_html_report(
        project_name=project_name,
        pages_data=pages_data,
        cards_data=cards_data,
        plan_ref_pool=plan_ref_pool,
    )
    html_path = out_dir / f"终稿审查报告_{project_name}.html"
    html_path.write_text(html_content, encoding="utf-8")

    print(f"HTML_REPORT={html_path}")
    for p in saved_annotated:
        print(f"ANNOTATED_IMAGE={p}")
    print(f"ISSUES_TOTAL={len(cards_data)}")
    try:
        scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import dumik_telemetry

        dumik_telemetry.report_event_async(event="invoke", skill="d-detail-review", mode="review")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
