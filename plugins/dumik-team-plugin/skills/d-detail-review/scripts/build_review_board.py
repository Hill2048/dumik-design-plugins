#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build minimalist floating-canvas visual final-review deliverables for DUMIK:
1. Full-height annotated images (<stem>_审稿标注.jpg) with crisp numbered colored
   boxes rendered using Google Sans (Latin/digits) + MiSans (Chinese).
2. A minimalist, self-contained, multi-version offline HTML review canvas
   (终稿审查报告_<项目名>.html):
   - Iterative versioning (一审 / 二审 / 三审 ...): automatically merges new
     review rounds into the existing HTML report, deduplicates shared Feishu
     planning reference images across versions, and supports incremental issue
     inheritance (`carry`, `inherit_unresolved_from` + `resolved_ids`) so
     second/third reviews never need to re-author unchanged defects.
   - Top-right fixed floating Info Navigation Card with an accessible single-row
     version switcher tablist (focusgroup="tablist nomemory" + aria-selected +
     View Transitions), progress bar per version, severity filters, collapsible
     body, and per-issue mini thumbnail items with modern CSS Scrollspy.
   - Center: seamless continuous detail page flow (0px gap) with clickable colored
     bounding boxes.
   - Left & Right margins: floating comment cards connected by thin curved SVG
     leader lines with anchor dots, scrolling naturally with the canvas.
   - Copyable text uses user-select: text (supports partial drag selection) plus
     one-click full-block Copy buttons.
   - Large (+50% bigger) Feishu planning reference previews inside each card,
     clicking opens a native <dialog closedby="any"> lightbox with scroll-chain
     containment (overscroll-behavior: contain) and safe ref ID lookup.
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
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

DATA_START_MARKER = "/*DUMIK_REVIEW_DATA_START*/"
DATA_END_MARKER = "/*DUMIK_REVIEW_DATA_END*/"

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
    "星号悬空",
)
SCREEN_ID_RE = re.compile(r"\b((?:S|M|E)\d{1,2})\b", re.IGNORECASE)
CN_ROUND_LABELS = ("一审", "二审", "三审", "四审", "五审", "六审", "七审", "八审", "九审", "十审")


def default_version_label(num: int) -> str:
    if 1 <= num <= len(CN_ROUND_LABELS):
        return CN_ROUND_LABELS[num - 1]
    return f"第{num}审"


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


def _data_uri_digest(uri: str) -> str:
    return hashlib.sha1(uri.encode("ascii", errors="ignore")).hexdigest()[:16]


def extract_existing_board_data(html_path: Path) -> dict[str, Any] | None:
    """Parse embedded review DATA JSON from an existing HTML board (supports both v1 single-version and v2 multi-version)."""
    if not html_path.is_file():
        return None
    text = html_path.read_text(encoding="utf-8", errors="replace")
    raw_json = ""
    s_idx = text.find(DATA_START_MARKER)
    e_idx = text.find(DATA_END_MARKER)
    if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
        raw_json = text[s_idx + len(DATA_START_MARKER) : e_idx].strip()
    else:
        m = re.search(r"const\s+DATA\s*=\s*(\{.*?\});\s*\n\s*const\s+SEV_COLOR", text, re.S)
        if m:
            raw_json = m.group(1).strip()
    if not raw_json:
        return None
    # Unescape </ safely if present (standard json.loads handles \/)
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        return None
    # Auto-upgrade legacy single-version HTML to schemaVersion 2
    if "versions" not in data:
        mtime = datetime.fromtimestamp(html_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        pages = list(data.get("pages") or [])
        id_to_page_key: dict[str, str] = {}
        for pg in pages:
            pkey = str(pg.get("key") or "1")
            for hs in pg.get("hotspots") or []:
                id_to_page_key[str(hs.get("id") or "")] = pkey
        cards = []
        for c in data.get("cards") or []:
            cc = dict(c)
            if not cc.get("image_key"):
                cc["image_key"] = id_to_page_key.get(str(cc.get("id") or ""), "1")
            cards.append(cc)
        return {
            "schemaVersion": 2,
            "projectName": str(data.get("projectName") or html_path.stem),
            "planRefs": dict(data.get("planRefs") or {}),
            "latestVersionId": "v1",
            "versions": [
                {
                    "id": "v1",
                    "label": "一审",
                    "createdAt": mtime,
                    "summary": "",
                    "resolvedCount": 0,
                    "resolvedNotes": [],
                    "pages": pages,
                    "cards": cards,
                }
            ],
        }
    return data


def export_version_as_spec(board_data: dict[str, Any], version_id: str | None = None) -> dict[str, Any]:
    """Export a lightweight, no-base64 JSON spec of the latest (or given) version for fast next-round authoring."""
    versions = board_data.get("versions") or []
    if not versions:
        return {"project_name": board_data.get("projectName", ""), "images": [], "issues": []}
    target = versions[-1]
    if version_id:
        for v in versions:
            if v.get("id") == version_id:
                target = v
                break
    light_issues = []
    for c in target.get("cards") or []:
        light_issues.append(
            {
                "id": c.get("id", ""),
                "severity": c.get("severity", "error"),
                "screen": c.get("screen", ""),
                "image_key": c.get("image_key", "1"),
                "bbox": c.get("bbox", [0, 0, 100, 100]),
                "short_tag": c.get("short_tag", ""),
                "title": c.get("title", ""),
                "issue": c.get("issue", ""),
                "copy_blocks": c.get("copy_blocks", []),
                "action_note": c.get("action_note", ""),
                "plan_ref_id": c.get("plan_ref_id", ""),
            }
        )
    return {
        "project_name": board_data.get("projectName", ""),
        "source_version": {"id": target.get("id"), "label": target.get("label")},
        "images": [{"key": p.get("key", ""), "label": p.get("label", "")} for p in (target.get("pages") or [])],
        "issues": light_issues,
    }


def resolve_issues_with_inheritance(
    spec: dict[str, Any],
    prev_version: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Support three authoring speeds:
    1. Full `issues: [...]` (classic mode)
    2. Per-item `{"carry": "02", ...overrides}` inside `issues` to inherit unchanged text/copy/plan_ref from previous round
    3. Incremental mode: `inherit_unresolved_from: "prev"` + `resolved_ids: ["04", "06"]` + optional `updates: {"03": {...}}` + `new_issues: [...]`
    Returns (resolved_raw_issues, resolved_summary_notes).
    """
    prev_by_id: dict[str, dict[str, Any]] = {}
    prev_ordered: list[dict[str, Any]] = []
    if prev_version:
        for c in prev_version.get("cards") or []:
            cid = str(c.get("id") or "").zfill(2)
            prev_by_id[cid] = c
            prev_ordered.append(c)

    def _merge_from_prev(base_card: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "severity": base_card.get("severity", "error"),
            "screen": base_card.get("screen", ""),
            "image_key": base_card.get("image_key", "1"),
            "bbox": list(base_card.get("bbox") or [20, 20, 200, 120]),
            "short_tag": base_card.get("short_tag", ""),
            "title": base_card.get("title", ""),
            "issue": base_card.get("issue", ""),
            "copy_blocks": list(base_card.get("copy_blocks") or []),
            "action_note": base_card.get("action_note", ""),
            "_inherited_plan_ref_id": base_card.get("plan_ref_id", ""),
            "_carried_from": str(base_card.get("id") or ""),
        }
        for k, v in override.items():
            if k in ("carry", "inherit_id"):
                continue
            if k == "copy":
                merged.pop("copy_blocks", None)
                merged["copy"] = v
            else:
                merged[k] = v
        return merged

    resolved_notes: list[str] = list(spec.get("resolved_notes") or [])

    if spec.get("inherit_unresolved_from") and prev_ordered:
        resolved_set = {str(x).zfill(2) for x in (spec.get("resolved_ids") or [])}
        updates_raw = spec.get("updates") or {}
        updates = {str(k).zfill(2): v for k, v in updates_raw.items() if isinstance(v, dict)}
        out: list[dict[str, Any]] = []
        for pc in prev_ordered:
            pid = str(pc.get("id") or "").zfill(2)
            if pid in resolved_set:
                if not spec.get("resolved_notes"):
                    tag = pc.get("short_tag") or pc.get("title") or ""
                    scr = pc.get("screen") or ""
                    resolved_notes.append(f"#{pid} {scr} {tag}".strip())
                continue
            ov = updates.get(pid, {})
            item = _merge_from_prev(pc, ov)
            if "id" not in ov:
                item.pop("id", None)
            out.append(item)
        for ni in spec.get("new_issues") or []:
            item = dict(ni)
            item["_is_new"] = True
            out.append(item)
        return out, resolved_notes

    out_issues: list[dict[str, Any]] = []
    for raw in spec.get("issues") or []:
        carry_id = raw.get("carry") or raw.get("inherit_id")
        if carry_id is not None and prev_by_id:
            key = str(carry_id).zfill(2)
            if key not in prev_by_id:
                raise KeyError(f"carry/inherit_id #{key} not found in previous version.")
            out_issues.append(_merge_from_prev(prev_by_id[key], raw))
        else:
            out_issues.append(dict(raw))

    if not resolved_notes and spec.get("resolved_ids") and prev_by_id:
        for rid in spec.get("resolved_ids") or []:
            key = str(rid).zfill(2)
            pc = prev_by_id.get(key)
            if pc:
                resolved_notes.append(f"#{key} {pc.get('screen', '')} {pc.get('short_tag', '')}".strip())

    return out_issues, resolved_notes


def build_html_report(board_data: dict[str, Any]) -> str:
    project_name = str(board_data.get("projectName") or "详情页终稿")
    versions = board_data.get("versions") or []
    latest_id = str(board_data.get("latestVersionId") or (versions[-1]["id"] if versions else "v1"))
    latest_ver = next((v for v in versions if v.get("id") == latest_id), versions[-1])
    latest_cards = latest_ver.get("cards") or []
    cnt_error = sum(1 for c in latest_cards if c.get("severity") == "error")
    cnt_missing = sum(1 for c in latest_cards if c.get("severity") == "missing")
    cnt_warn = sum(1 for c in latest_cards if c.get("severity") == "warn")
    total = len(latest_cards)

    payload_json = json.dumps(board_data, ensure_ascii=False).replace("</", "<\\/")
    title_esc = html.escape(f"{project_name} · 终稿审查")

    # Initial SSR version tabs markup (WCAG + tabs guide: initial aria-selected rendered in HTML)
    ver_tabs_html_parts = []
    for v in versions:
        vid = str(v.get("id") or "v1")
        vlabel = html.escape(str(v.get("label") or vid))
        vcnt = len(v.get("cards") or [])
        is_sel = vid == latest_id
        sel_attr = "true" if is_sel else "false"
        fg_start = " focusgroupstart" if is_sel else ""
        ver_tabs_html_parts.append(
            f'<button type="button" role="tab" class="v-tab" id="vtab-{html.escape(vid)}" '
            f'data-vid="{html.escape(vid)}" aria-selected="{sel_attr}"{fg_start}>'
            f'<span class="v-tab-lbl">{vlabel}</span><span class="v-tab-cnt">{vcnt}</span></button>'
        )
    ver_tabs_html = "".join(ver_tabs_html_parts)
    ver_bar_class = "nav-versions nav-collapsible" + ("" if len(versions) >= 1 else " hidden")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title_esc}</title>
<style>
  @property --fade-start {{
    syntax: "<length>";
    inherits: false;
    initial-value: 0px;
  }}
  @property --fade-end {{
    syntax: "<length>";
    inherits: false;
    initial-value: 0px;
  }}

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
    --nav-w: 266px;
    --detail-w: 610px;
    --card-w: 420px;
    --gap-x: 46px;
    --scrollbar-thumb: #9C988F;
    --scrollbar-track: #F2F0EA;
  }}
  @media (max-width: 1840px) {{
    :root {{ --detail-w: 560px; --card-w: 380px; --gap-x: 38px; --nav-w: 252px; }}
  }}
  @media (max-width: 1620px) {{
    :root {{ --detail-w: 520px; --card-w: 340px; --gap-x: 30px; --nav-w: 238px; }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    ::view-transition-group(*),
    ::view-transition-old(*),
    ::view-transition-new(*) {{
      animation: none !important;
    }}
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

  /* Right-top floating Info & Navigation Card */
  .nav-card {{
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 80;
    width: var(--nav-w);
    max-height: calc(100vh - 32px);
    display: flex;
    flex-direction: column;
    background: rgba(255, 255, 255, 0.95);
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
    flex: 1;
  }}
  .nav-title {{
    font-size: 13.5px;
    font-weight: 700;
    letter-spacing: -0.01em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    outline: none;
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
    min-width: 64px;
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

  /* Single-row horizontal scrollable version switcher tablist */
  .nav-versions {{
    border-bottom: 1px solid var(--line);
    background: #F6F5F0;
    padding: 4px 10px 0;
  }}
  .nav-versions.hidden {{
    display: none;
  }}
  .v-tablist {{
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 2px;
    overflow-x: auto;
    scroll-snap-type: inline proximity;
    scroll-padding-inline: 18px;
    scrollbar-width: none;
    --fade-size: 18px;
    mask:
      linear-gradient(black, black) no-clip subtract,
      linear-gradient(to right, black, transparent) 0 0 / var(--fade-start) 100% no-repeat no-clip,
      linear-gradient(to right, transparent, black) 100% 0 / var(--fade-end) 100% no-repeat no-clip;
    animation: reveal-fade-start linear both, hide-fade-end linear both;
    animation-timeline: scroll(self inline);
    animation-range: 0 var(--fade-size), calc(100% - var(--fade-size)) 100%;
  }}
  .v-tablist::-webkit-scrollbar {{ display: none; }}
  @keyframes reveal-fade-start {{
    to {{ --fade-start: var(--fade-size); }}
  }}
  @keyframes hide-fade-end {{
    from {{ --fade-end: var(--fade-size); }}
  }}
  .v-tablist.more-start {{ --fade-start: var(--fade-size); }}
  .v-tablist.more-end {{ --fade-end: var(--fade-size); }}

  .v-tab {{
    position: relative;
    flex: none;
    scroll-snap-align: start;
    font-family: var(--font-stack);
    font-size: 11.5px;
    font-weight: 600;
    border: none;
    background: transparent;
    color: var(--muted);
    padding: 6px 8px 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
    transition: color 0.12s;
  }}
  .v-tab:hover {{
    color: var(--ink);
  }}
  .v-tab[aria-selected="true"] {{
    color: var(--ink);
  }}
  .v-tab[aria-selected="true"]::after {{
    content: "";
    position: absolute;
    inset: auto 4px 0;
    border-block-end: 2.5px solid var(--ink);
  }}
  .v-tab-cnt {{
    font-size: 10px;
    font-weight: 700;
    padding: 0 5px;
    line-height: 16px;
    border-radius: 99px;
    background: #E6E4DC;
    color: #5E5C55;
  }}
  .v-tab[aria-selected="true"] .v-tab-cnt {{
    background: #191918;
    color: #FFF;
  }}

  .nav-ver-meta {{
    padding: 5px 11px;
    font-size: 10.5px;
    color: var(--muted);
    background: #FAF9F6;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }}
  .nav-ver-meta.is-history {{
    background: #FFF6E8;
    color: #8A4F07;
  }}
  .ver-pill-ok {{
    color: var(--ok);
    font-weight: 700;
  }}
  .ver-jump-latest {{
    font-family: var(--font-stack);
    border: none;
    background: #191918;
    color: #FFF;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 5px;
    cursor: pointer;
    flex-shrink: 0;
  }}
  .ver-jump-latest:hover {{ background: #3A3936; }}

  .nav-filters {{
    padding: 7px 10px;
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

  /* Full-width infinite scrollable canvas */
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
    view-transition-name: review-stage;
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
      <div class="nav-title" id="nav-title" tabindex="-1">{title_esc}</div>
      <div class="nav-prog-row">
        <div class="prog-track"><div class="prog-fill" id="prog-fill"></div></div>
        <span id="prog-txt">0 / {total}</span>
      </div>
    </div>
    <div class="nav-head-btns">
      <button class="icon-btn nav-collapsible" type="button" onclick="resetDone()" title="重置当前版本勾选">重置</button>
      <button class="icon-btn" type="button" id="collapse-btn" onclick="toggleNav()" title="收起/展开导航">收起</button>
    </div>
  </div>
  <div class="{ver_bar_class}" id="nav-versions">
    <div class="v-tablist" id="v-tablist" role="tablist" focusgroup="tablist nomemory" aria-label="审稿版本切换">{ver_tabs_html}</div>
  </div>
  <div class="nav-ver-meta nav-collapsible" id="nav-ver-meta"></div>
  <div class="nav-filters nav-collapsible" id="nav-filters">
    <button class="f-btn active" type="button" data-f="all" onclick="setFilter('all', this)">全部 <span id="fc-all">{total}</span></button>
    <button class="f-btn" type="button" data-f="error" onclick="setFilter('error', this)"><span class="dot dot-err"></span>必改 <span id="fc-error">{cnt_error}</span></button>
    <button class="f-btn" type="button" data-f="missing" onclick="setFilter('missing', this)"><span class="dot dot-miss"></span>漏填 <span id="fc-missing">{cnt_missing}</span></button>
    <button class="f-btn" type="button" data-f="warn" onclick="setFilter('warn', this)"><span class="dot dot-warn"></span>优化 <span id="fc-warn">{cnt_warn}</span></button>
    <button class="f-btn" type="button" data-f="todo" onclick="setFilter('todo', this)">未改</button>
  </div>
  <nav class="nav-list nav-collapsible" id="nav-list" aria-label="问题快速定位"></nav>
</aside>

<main class="canvas-shell">
  <div class="stage" id="stage" role="tabpanel" aria-labelledby="vtab-{html.escape(latest_id)}">
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
const DATA = {DATA_START_MARKER}{payload_json}{DATA_END_MARKER};
const SEV_COLOR = {{ error: "#E52E2E", missing: "#EB760C", warn: "#1E7AE8" }};
let currentVersionId = DATA.latestVersionId || (DATA.versions[DATA.versions.length - 1] && DATA.versions[DATA.versions.length - 1].id);
let currentFilter = "all";
let hoverId = null;
let doneMap = {{}};
let activeObserver = null;

function getCurrentVersion() {{
  return DATA.versions.find(v => v.id === currentVersionId) || DATA.versions[DATA.versions.length - 1];
}}

function storeKeyFor(vid) {{
  return `dumik_review_done_v5_${{DATA.projectName}}_${{vid}}`;
}}

function loadDone(vid) {{
  try {{
    doneMap = JSON.parse(localStorage.getItem(storeKeyFor(vid)) || "{{}}");
  }} catch (e) {{
    doneMap = {{}};
  }}
}}

function saveDone() {{
  try {{ localStorage.setItem(storeKeyFor(currentVersionId), JSON.stringify(doneMap)); }} catch (e) {{}}
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
  const ver = getCurrentVersion();
  const total = ver.cards.length;
  const done = ver.cards.filter(c => doneMap[c.id]).length;
  document.getElementById("prog-fill").style.width = (total ? Math.round(done / total * 100) : 0) + "%";
  document.getElementById("prog-txt").textContent = `${{done}} / ${{total}}`;
}}

function updateFilterCounts() {{
  const cards = getCurrentVersion().cards;
  const err = cards.filter(c => c.severity === "error").length;
  const miss = cards.filter(c => c.severity === "missing").length;
  const warn = cards.filter(c => c.severity === "warn").length;
  document.getElementById("fc-all").textContent = cards.length;
  document.getElementById("fc-error").textContent = err;
  document.getElementById("fc-missing").textContent = miss;
  document.getElementById("fc-warn").textContent = warn;
}}

function updateVersionUI() {{
  const ver = getCurrentVersion();
  const latest = DATA.versions[DATA.versions.length - 1];
  const isLatest = ver.id === latest.id;

  const tabs = Array.from(document.querySelectorAll("#v-tablist .v-tab"));
  for (const tab of tabs) {{
    const selected = tab.getAttribute("data-vid") === ver.id;
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    tab.toggleAttribute("focusgroupstart", selected);
    if (selected) {{
      try {{
        tab.scrollIntoView({{ block: "nearest", inline: "nearest", container: "nearest" }});
      }} catch (e) {{
        tab.scrollIntoView({{ block: "nearest", inline: "nearest" }});
      }}
    }}
  }}

  const stage = document.getElementById("stage");
  stage.setAttribute("aria-labelledby", "vtab-" + ver.id);

  const metaEl = document.getElementById("nav-ver-meta");
  const timeTxt = ver.createdAt ? esc(ver.createdAt) : "";
  const resolvedCount = Number(ver.resolvedCount || (ver.resolvedNotes ? ver.resolvedNotes.length : 0));
  if (!isLatest) {{
    metaEl.classList.add("is-history");
    metaEl.innerHTML = `<span>正在看历史版本 · ${{esc(ver.label)}}</span><button class="ver-jump-latest" type="button" data-jump-latest="1">回最新 ${{esc(latest.label)}}</button>`;
  }} else {{
    metaEl.classList.remove("is-history");
    const deltaHtml = resolvedCount > 0 ? `<span class="ver-pill-ok">较上轮已消 ${{resolvedCount}} 项</span>` : `<span>${{esc(ver.label)}} · 最新</span>`;
    metaEl.innerHTML = `${{deltaHtml}}<span>${{timeTxt}}</span>`;
  }}
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
  for (const pg of getCurrentVersion().pages) {{
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
  const cards = getCurrentVersion().cards;
  if (!cards.length) {{
    list.innerHTML = '<div style="padding:18px 10px;text-align:center;font-size:12px;font-weight:600;color:var(--ok);">本轮审查通过 · 0 处待改</div>';
    return;
  }}
  for (const c of cards) {{
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
  for (const c of getCurrentVersion().cards) {{
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

function applyVersionDOM(vid, resetScroll) {{
  currentVersionId = vid;
  hoverId = null;
  currentFilter = "all";
  document.querySelectorAll(".f-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-f") === "all"));
  loadDone(vid);
  updateVersionUI();
  updateFilterCounts();
  renderStream();
  renderNavList();
  renderFloatingCards();
  updateProgress();
  applyVisibilityAndLayout();
  initScrollspy();
  if (resetScroll) window.scrollTo({{ top: 0, behavior: "instant" }});
  setTimeout(scheduleLayout, 180);
}}

function switchVersion(vid) {{
  if (vid === currentVersionId) return;
  if (!DATA.versions.some(v => v.id === vid)) return;
  if (!document.startViewTransition) {{
    applyVersionDOM(vid, true);
    document.getElementById("nav-title")?.focus({{ preventScroll: true }});
    return;
  }}
  const transition = document.startViewTransition(() => {{
    applyVersionDOM(vid, true);
  }});
  transition.finished.finally(() => {{
    scheduleLayout();
    const activeTab = document.getElementById("vtab-" + vid);
    if (activeTab && (!document.activeElement || !document.body.contains(document.activeElement))) {{
      activeTab.focus({{ preventScroll: true }});
    }}
  }});
}}

// Clean event delegation
document.addEventListener("click", (ev) => {{
  const vtab = ev.target.closest(".v-tab");
  if (vtab) {{
    switchVersion(vtab.getAttribute("data-vid"));
    return;
  }}
  const jumpLatest = ev.target.closest("[data-jump-latest]");
  if (jumpLatest) {{
    const latest = DATA.versions[DATA.versions.length - 1];
    if (latest) switchVersion(latest.id);
    return;
  }}
  const copyBtn = ev.target.closest(".copy-btn");
  if (copyBtn) {{
    const cid = copyBtn.getAttribute("data-cid");
    const idx = Number(copyBtn.getAttribute("data-idx"));
    const item = getCurrentVersion().cards.find(x => x.id === cid);
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

// Keyboard fallback for version tablist when focusgroup is not yet supported natively
const vTablist = document.getElementById("v-tablist");
vTablist.addEventListener("keydown", (ev) => {{
  const tabs = Array.from(vTablist.querySelectorAll(".v-tab"));
  const idx = tabs.indexOf(document.activeElement);
  if (idx === -1 || tabs.length <= 1) return;
  let next = -1;
  if (ev.key === "ArrowRight") next = (idx + 1) % tabs.length;
  else if (ev.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
  else if (ev.key === "Home") next = 0;
  else if (ev.key === "End") next = tabs.length - 1;
  if (next !== -1) {{
    ev.preventDefault();
    tabs[next].focus();
    // Selection by activation is safer for heavy full-canvas swaps; Enter/Space activates, or click
  }}
}});

// Edge fade fallback when CSS scroll-driven animations are not supported
if (!CSS.supports("animation-timeline", "scroll()")) {{
  const first = vTablist.firstElementChild;
  const last = vTablist.lastElementChild;
  if (first && last && first !== last) {{
    const edgeObs = new IntersectionObserver((entries) => {{
      for (const {{ target, intersectionRatio }} of entries) {{
        vTablist.classList.toggle(target === first ? "more-start" : "more-end", intersectionRatio < 1);
      }}
    }}, {{ root: vTablist, threshold: 1, rootMargin: "1px" }});
    edgeObs.observe(first);
    edgeObs.observe(last);
  }}
}}

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
  for (const c of getCurrentVersion().cards) {{
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
  for (const c of getCurrentVersion().cards) {{
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

// Modern Scrollspy: native scroll-target-group + aria-current sync, with cleanable IntersectionObserver fallback
let scrollendBound = false;
function initScrollspy() {{
  if (activeObserver) {{
    activeObserver.disconnect();
    activeObserver = null;
  }}
  const navLinks = () => Array.from(document.querySelectorAll("#nav-list a.nav-item"));
  if (CSS.supports("scroll-target-group: auto")) {{
    const syncAria = () => {{
      const cur = document.querySelector("#nav-list a.nav-item:target-current");
      navLinks().forEach(a => a.setAttribute("aria-current", a === cur ? "true" : "false"));
    }};
    syncAria();
    if (!scrollendBound) {{
      document.addEventListener("scrollend", syncAria);
      scrollendBound = true;
    }}
  }} else {{
    activeObserver = new IntersectionObserver((entries) => {{
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
    document.querySelectorAll(".hotspot").forEach(hs => activeObserver.observe(hs));
  }}
}}

window.addEventListener("resize", scheduleLayout);
applyVersionDOM(currentVersionId, false);
setTimeout(scheduleLayout, 250);
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render annotated review images and multi-version minimalist floating-canvas HTML review board."
    )
    parser.add_argument("--spec", default="", help="Path to temporary review_input.json.")
    parser.add_argument("--project-root", default="", help="Optional project root for auto plan_ref matching and default 成品/审稿报告/ output.")
    parser.add_argument("--out-dir", default="", help="Output directory (defaults to <project-root>/成品/审稿报告 when --project-root is set).")
    parser.add_argument("--append-to", default="", help="Explicit existing HTML report to merge into (by default auto-merges if target HTML already exists).")
    parser.add_argument("--fresh", action="store_true", help="Ignore existing HTML history and start fresh from v1.")
    parser.add_argument("--version-id", default="", help="Optional explicit version id (e.g. v2). Passing an existing id updates that version in place.")
    parser.add_argument("--version-label", default="", help="Optional explicit version label (e.g. 二审 / 三审).")
    parser.add_argument("--export-prev-spec", default="", help="Export latest version issues from --append-to (or default report) as lightweight JSON for fast editing, then exit.")
    parser.add_argument("--workers", type=int, default=6, help="Parallel threads for thumbnails & base64 encoding.")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve() if args.project_root else None

    if args.export_prev_spec:
        src_html = Path(args.append_to) if args.append_to else None
        if not src_html and project_root:
            report_dir = project_root / "成品" / "审稿报告"
            cands = sorted(report_dir.glob("终稿审查报告_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
            if cands:
                src_html = cands[0]
        if not src_html or not src_html.is_file():
            raise FileNotFoundError("未找到可导出的历史审稿台 HTML，请用 --append-to 指定路径。")
        existing = extract_existing_board_data(src_html)
        if not existing:
            raise ValueError(f"无法解析历史审稿台数据: {src_html}")
        exported = export_version_as_spec(existing)
        out_p = Path(args.export_prev_spec)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EXPORTED_PREV_SPEC={out_p}")
        return 0

    if not args.spec:
        raise ValueError("必须指定 --spec <review_input.json>。")

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif project_root:
        out_dir = project_root / "成品" / "审稿报告"
    else:
        raise ValueError("必须指定 --out-dir 或 --project-root。")
    out_dir.mkdir(parents=True, exist_ok=True)

    project_name = str(spec.get("project_name") or (project_root.name if project_root else "详情页终稿")).strip()
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", project_name)
    out_html = out_dir / f"终稿审查报告_{safe_name}.html"

    # Load existing multi-version history unless --fresh is requested
    existing_board: dict[str, Any] | None = None
    if not args.fresh:
        candidate_html = Path(args.append_to) if args.append_to else out_html
        if candidate_html.is_file():
            existing_board = extract_existing_board_data(candidate_html)

    versions_list: list[dict[str, Any]] = list(existing_board.get("versions") or []) if existing_board else []
    plan_ref_pool: dict[str, str] = dict(existing_board.get("planRefs") or {}) if existing_board else {}
    digest_to_ref_id: dict[str, str] = {_data_uri_digest(uri): rid for rid, uri in plan_ref_pool.items()}

    # Determine version_id and version_label
    explicit_vid = str(args.version_id or spec.get("version_id") or "").strip()
    existing_idx = next((i for i, v in enumerate(versions_list) if v.get("id") == explicit_vid), -1) if explicit_vid else -1

    if existing_idx != -1:
        version_id = explicit_vid
        round_num = existing_idx + 1
        prev_version = versions_list[existing_idx - 1] if existing_idx > 0 else None
    else:
        round_num = len(versions_list) + 1
        version_id = explicit_vid or f"v{round_num}"
        prev_version = versions_list[-1] if versions_list else None

    version_label = str(
        args.version_label
        or spec.get("version_label")
        or (versions_list[existing_idx].get("label") if existing_idx != -1 else "")
        or default_version_label(round_num)
    ).strip()

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

    issues_raw, resolved_notes = resolve_issues_with_inheritance(spec, prev_version)
    path_to_ref_id: dict[Path, str] = {}
    new_ref_paths: list[tuple[Path, list[int]]] = []
    normalized_issues: list[tuple[dict[str, Any], dict[str, Any], tuple[int, int, int, int], str, Path | None]] = []

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

        inherited_rid = str(issue.get("_inherited_plan_ref_id") or "")
        explicit_ref_raw = str(issue.get("plan_ref") or "")
        plan_ref_path: Path | None = None
        preset_rid = ""
        if inherited_rid and not explicit_ref_raw and inherited_rid in plan_ref_pool:
            preset_rid = inherited_rid
        else:
            plan_ref_path = resolve_ref_path(explicit_ref_raw, str(issue.get("screen") or ""), project_root)
            if plan_ref_path and plan_ref_path not in path_to_ref_id:
                path_to_ref_id[plan_ref_path] = ""
                new_ref_paths.append((plan_ref_path, []))

        normalized_issues.append((issue, entry, bbox, preset_rid, plan_ref_path))

    # Parallel encoding for Feishu planning references (deduped against existing pool) & mini nav thumbnails
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        ref_futs = {
            rp: pool.submit(lambda p=rp: img_to_data_uri(Image.open(p).convert("RGB"), max_width=1100, quality=88))
            for rp, _ in new_ref_paths
        }
        thumb_futs = [
            pool.submit(make_nav_thumb_uri, entry["image"], bbox, issue["severity"])
            for issue, entry, bbox, _, _ in normalized_issues
        ]
        next_ref_num = len(plan_ref_pool) + 1
        for rp, fut in ref_futs.items():
            uri = fut.result()
            dg = _data_uri_digest(uri)
            if dg in digest_to_ref_id:
                path_to_ref_id[rp] = digest_to_ref_id[dg]
            else:
                while f"ref_{next_ref_num:02d}" in plan_ref_pool:
                    next_ref_num += 1
                rid = f"ref_{next_ref_num:02d}"
                next_ref_num += 1
                plan_ref_pool[rid] = uri
                digest_to_ref_id[dg] = rid
                path_to_ref_id[rp] = rid
        nav_thumbs = [f.result() for f in thumb_futs]

    cards_data: list[dict[str, Any]] = []
    for (issue, entry, bbox, preset_rid, plan_ref_path), thumb_uri in zip(normalized_issues, nav_thumbs):
        ref_id = preset_rid or (path_to_ref_id.get(plan_ref_path, "") if plan_ref_path else "")
        cards_data.append(
            {
                "id": issue["id"],
                "severity": issue["severity"],
                "severity_label": SEVERITY_META[issue["severity"]]["label"],
                "screen": str(issue.get("screen") or ""),
                "image_key": entry["key"],
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

    resolved_count = int(spec.get("resolved_count") or len(resolved_notes))
    if not resolved_count and prev_version and len(prev_version.get("cards") or []) > len(cards_data):
        resolved_count = max(0, len(prev_version.get("cards") or []) - len(cards_data))

    new_version_obj = {
        "id": version_id,
        "label": version_label,
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": str(spec.get("reviewer_summary") or ""),
        "resolvedCount": resolved_count,
        "resolvedNotes": resolved_notes,
        "pages": pages_data,
        "cards": cards_data,
    }

    if existing_idx != -1:
        versions_list[existing_idx] = new_version_obj
    else:
        versions_list.append(new_version_obj)

    board_data = {
        "schemaVersion": 2,
        "projectName": project_name,
        "planRefs": plan_ref_pool,
        "latestVersionId": versions_list[-1]["id"],
        "versions": versions_list,
    }

    html_content = build_html_report(board_data)
    written_html = out_html
    try:
        tmp_html = out_dir / f".{out_html.stem}.tmp"
        tmp_html.write_text(html_content, encoding="utf-8")
        try:
            os.replace(tmp_html, out_html)
        except PermissionError:
            tmp_html.unlink(missing_ok=True)
            out_html.write_text(html_content, encoding="utf-8")
    except PermissionError:
        written_html = out_dir / f"{out_html.stem}_{version_id}.html"
        written_html.write_text(html_content, encoding="utf-8")
        print(f"WARN_LOCKED_TARGET={out_html} -> FALLBACK={written_html}", file=sys.stderr)

    print(f"HTML_REPORT={written_html}")
    for p in saved_annotated:
        print(f"ANNOTATED_IMAGE={p}")
    print(f"VERSION={version_id} ({version_label}) | TOTAL_VERSIONS={len(versions_list)} | ISSUES_TOTAL={len(cards_data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
