#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse a Feishu wiki/docx document and its embedded whiteboards into:
1. canvas-manifest.json (structured product facts, revision patches, must-render list,
   milestone slots, detail screens, 3:4 main cards, 1:1 entry/SKU cards, main-vs-detail
   shared priority waves)
2. 拆解清单.md (concise Chinese operational checklist)
3. Optional downloaded reference assets via lark-cli docs +media-download / +media-preview
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


DEFAULT_GENERATION_RATIO = "9:16"
IMAGE_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{15,40}$")
MUST_RENDER_RE = re.compile(r"((?:必渲|必拍)\s*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳0-9]+)([^\n|；;]*)")
SELLING_KEYWORDS = (
    "纯钛",
    "100%",
    "ta1",
    "抗菌",
    "99.9%",
    "0涂层",
    "不粘",
    "加大",
    "加深",
    "加宽",
    "加长",
    "圆润",
    "不伤嘴",
    "不伤口",
    "毛刺",
    "抛光",
    "一体成型",
    "无接缝",
    "无焊接",
    "耐腐蚀",
    "抗酸碱",
    "不变色",
    "重金属",
    "304",
    "316",
    "木勺",
    "喝汤",
    "舀粥",
    "拌饭",
    "西瓜",
    "蛋羹",
    "手柄",
    "实木柄",
    "沙比利",
    "烫手",
    "轻量",
    "轻盈",
    "洗碗机",
    "消毒柜",
    "检测报告",
    "食卫",
    "金黄色葡萄球菌",
    "金色葡萄球菌",
    "打滑",
    "防烫",
    "耐高温",
    "不掉色",
    "0喷漆",
    "专人专用",
    "钛铝钢",
    "三层截面",
    "截面",
    "微孔",
    "疏油",
    "导磁",
    "锅底",
    "钢铲",
    "耐磨",
    "大肚",
    "宽底",
    "颠锅",
    "单手",
    "49mm",
    "4.9cm",
    "43mm",
    "4.3cm",
    "6mm",
    "0.6cm",
    "22%",
    "33%",
    "18cm",
    "18.7cm",
    "18.8cm",
    "187mm",
    "180mm",
    "19.3g",
    "21.3g",
    "结晶",
    "钛结晶",
    "茶渍",
    "茶垢",
    "一冲即净",
    "锁温",
    "保温",
    "保冷",
    "真空",
    "双层",
    "150g",
    "178g",
    "250g",
    "400ml",
    "防漏",
    "防尘",
    "密封",
    "滑动",
    "倒置",
    "硅胶",
    "杯口",
    "假一罚万",
    "不锈钢",
    "陶瓷",
    "不松动",
    "抗氧化",
    "抑菌",
    "保鲜",
)
NOISE_TEXTS = {"1", "2", "3", "m", "勺", "勺子", "根", "*****", "看右侧", "见右侧", "同上"}
SIGNPOST_RE = re.compile(r"^[→←↓↑▶▷►•·.\-\s]+$")
VIDEO_FRAME_KEYWORDS = ("卖点合集视频", "主图视频", "视频脚本", "视频")
GENERIC_PRODUCT_TOKENS = {
    "纯钛",
    "100%",
    "ta1",
    "抗菌",
    "99.9%",
    "0重金属",
    "0异味",
    "重金属",
    "健康",
    "安心",
    "马克杯",
    "水杯",
    "杯子",
    "勺子",
    "汤勺",
    "煎锅",
    "炒锅",
    "锅具",
    "一体成型",
}
ENTRY_NOTE_KEYWORDS = ("车图", "入口", "sku", "SKU", "800主图", "白底")
MAIN_MARKER_KEYWORDS = ("750主图", "主图")
DETAIL_MARKER_KEYWORDS = ("详情",)
MILESTONE_KEYWORDS = ("里程碑", "产品身份卡", "首屏KV", "超级符号", "概念1", "概念2")
FACT_BLOCK_KEYWORDS = (
    "卖点",
    "我们是一个",
    "卖点合集",
    "可视化卖点",
    "材质/工艺卖点",
    "市场需求",
    "小卖点",
    "痛点",
)
CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class FeishuCanvasError(RuntimeError):
    """Raised when Feishu API access or whiteboard parsing fails."""


@dataclass
class DocBlockParser(HTMLParser):
    """Lightweight parser for Feishu docs +fetch v2 markup."""

    title: str = ""
    headings: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    whiteboards: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._in_heading = False
        self._in_p = False
        self._in_td = False
        self._in_li = False
        self._in_a = False
        self._cur_href = ""
        self._a_buf: list[str] = []
        self._buf: list[str] = []
        self._cell_parts: list[str] = []
        self._cur_row: list[str] = []
        self._cur_table: list[list[str]] = []
        self._last_heading = ""
        self._last_h1 = ""
        self._cur_heading_tag = ""
        self._context_lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
            self._buf = []
        elif tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = True
            self._cur_heading_tag = tag
            self._buf = []
        elif tag == "table":
            self._cur_table = []
        elif tag == "tr":
            self._cur_row = []
        elif tag in ("td", "th"):
            self._in_td = True
            self._cell_parts = []
        elif tag == "li":
            self._in_li = True
            self._buf = []
        elif tag == "p":
            self._in_p = True
            self._buf = []
        elif tag == "a":
            self._in_a = True
            self._cur_href = attr_map.get("href", "").strip()
            self._a_buf = []
        elif tag == "whiteboard":
            token = attr_map.get("token", "").strip()
            if token:
                ctx_lines = [x for x in [self._last_h1, self._last_heading, *self._context_lines[-4:]] if x]
                ctx_joined = " | ".join(dict.fromkeys(ctx_lines))
                is_ms = any(k in ctx_joined for k in ("里程碑", "KV", "超级符号"))
                has_video = "视频" in ctx_joined
                has_detail = ("详情" in ctx_joined) or ("主图详情" in ctx_joined)
                is_video_only = has_video and not has_detail and not is_ms
                is_main_detail = ("主图详情" in ctx_joined) or ("详情策划" in ctx_joined)
                is_revision = (
                    any(k in ctx_joined for k in ("修改", "返修", "调整", "补丁"))
                    and not is_main_detail
                    and not is_ms
                )
                self.whiteboards.append(
                    {
                        "token": token,
                        "heading": self._last_h1 or self._last_heading,
                        "context": ctx_joined,
                        "is_milestone_heading": is_ms,
                        "is_video_only": is_video_only,
                        "is_main_detail_heading": is_main_detail,
                        "is_revision_heading": is_revision,
                    }
                )
                self._context_lines = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self.title = "".join(self._buf).strip()
            self._in_title = False
        elif tag == "a" and self._in_a:
            atext = " ".join("".join(self._a_buf).split())
            if self._cur_href and not self._in_td:
                self.links.append({"text": atext or self._cur_href, "href": self._cur_href})
            self._in_a = False
        elif tag in ("h1", "h2", "h3", "h4") and self._in_heading:
            text = " ".join("".join(self._buf).split())
            if text:
                if self._in_td:
                    self._cell_parts.append(text)
                else:
                    self.headings.append(text)
                    self._last_heading = text
                    if self._cur_heading_tag == "h1":
                        self._last_h1 = text
                        self._context_lines = [text]
                    else:
                        self._context_lines.append(text)
            self._in_heading = False
        elif tag == "li" and self._in_li:
            text = " ".join("".join(self._buf).split())
            if text:
                if self._in_td:
                    self._cell_parts.append(text)
                else:
                    self.paragraphs.append(text)
                    self._context_lines.append(text)
            self._in_li = False
        elif tag == "p" and self._in_p:
            text = " ".join("".join(self._buf).split())
            if text:
                if self._in_td:
                    self._cell_parts.append(text)
                else:
                    self.paragraphs.append(text)
                    self._context_lines.append(text)
            self._in_p = False
        elif tag in ("td", "th") and self._in_td:
            cell_text = "\n".join(part for part in self._cell_parts if part).strip()
            self._cur_row.append(cell_text)
            self._in_td = False
        elif tag == "tr":
            if any(c for c in self._cur_row):
                self._cur_table.append(self._cur_row)
            self._cur_row = []
        elif tag == "table":
            if self._cur_table:
                self.tables.append(self._cur_table)
            self._cur_table = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._a_buf.append(data)
        if self._in_title or self._in_heading or self._in_li or self._in_p:
            self._buf.append(data)
        elif self._in_td:
            text = data.strip()
            if text:
                self._cell_parts.append(text)


def parse_feishu_url(url: str) -> dict[str, str]:
    """Extract wiki/docx/whiteboard tokens from a Feishu URL."""
    parsed = urlparse(url.strip())
    qs = parse_qs(parsed.query)
    path_parts = [p for p in parsed.path.split("/") if p]
    info: dict[str, str] = {"url": url.strip()}
    for kind in ("wiki", "docx", "docs", "board", "whiteboard"):
        if kind in path_parts:
            idx = path_parts.index(kind)
            if idx + 1 < len(path_parts):
                info["resource_type"] = kind
                info["resource_token"] = path_parts[idx + 1]
                break
    for key in ("blockToken", "block_token", "whiteboard_token"):
        vals = qs.get(key)
        if vals and vals[0]:
            info["block_token"] = vals[0].strip()
            break
    if not info.get("block_token") and info.get("resource_type") in ("board", "whiteboard"):
        info["block_token"] = info.get("resource_token", "")
    return info


def parse_doc_markup(content: str) -> dict[str, Any]:
    """Parse Feishu docx v2 content into title, headings, tables, links, and whiteboards."""
    parser = DocBlockParser()
    parser.feed(content)
    parser.close()
    return {
        "title": parser.title,
        "headings": parser.headings,
        "tables": parser.tables,
        "whiteboards": parser.whiteboards,
        "paragraphs": parser.paragraphs,
        "links": parser.links,
    }


def resolve_lark_cli() -> str:
    exe = shutil.which("lark-cli.cmd") or shutil.which("lark-cli")
    if not exe:
        raise FeishuCanvasError("未找到 lark-cli，请确认已安装并加入 PATH。")
    return exe


def extract_json_payload(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise FeishuCanvasError(f"lark-cli 返回非 JSON 输出: {stdout[:300]}")
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        raise FeishuCanvasError(f"解析 lark-cli JSON 失败: {exc}") from exc


def run_lark_cli(args: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    exe = resolve_lark_cli()
    proc = subprocess.run(
        [exe, *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return extract_json_payload(combined)


def detect_lark_identities() -> list[str]:
    """Return ordered identity list, preferring user when valid, then bot."""
    try:
        status = run_lark_cli(["auth", "status"])
    except FeishuCanvasError:
        return ["bot"]
    identities = status.get("identities", {})
    order: list[str] = []
    if identities.get("user", {}).get("available"):
        order.append("user")
    if identities.get("bot", {}).get("available"):
        order.append("bot")
    return order or ["bot"]


def call_with_identity_fallback(
    base_args: list[str],
    identities: list[str],
    *,
    cwd: Path | None = None,
) -> tuple[dict[str, Any], str]:
    last_err: dict[str, Any] | None = None
    for identity in identities:
        resp = run_lark_cli([base_args[0], *base_args[1:], "--as", identity], cwd=cwd)
        if resp.get("ok"):
            return resp, identity
        last_err = resp
        subtype = ((resp.get("error") or {}).get("subtype") or "").lower()
        code = (resp.get("error") or {}).get("code")
        if subtype == "permission_denied" or code in (131006, 99991663, 99991672):
            continue
        break
    msg = ((last_err or {}).get("error") or {}).get("message") or "未知接口错误"
    hint = ((last_err or {}).get("error") or {}).get("hint") or ""
    raise FeishuCanvasError(f"调用 {' '.join(base_args[:2])} 失败: {msg} {hint}".strip())


def _ensure_image_extension(saved_path: Path, content_type: str) -> Path:
    if saved_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return saved_path
    ext = CONTENT_TYPE_EXT.get((content_type or "").split(";", 1)[0].strip().lower(), ".png")
    target = Path(str(saved_path) + ext)
    if target.exists():
        target.unlink()
    saved_path.rename(target)
    return target


def download_whiteboard_media(
    token: str,
    dest_dir: Path,
    stem: str,
    identities: list[str],
    *,
    blocked_download_identities: set[str] | None = None,
) -> tuple[str | None, str | None]:
    """Download whiteboard image via +media-download, falling back to +media-preview."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", stem).strip("_")[:36] or token
    rel_out = f"./{safe_stem}"
    blocked = blocked_download_identities if blocked_download_identities is not None else set()

    for cmd_name in ("+media-download", "+media-preview"):
        for identity in identities:
            if cmd_name == "+media-download" and identity in blocked:
                continue
            resp = run_lark_cli(
                [
                    "docs",
                    cmd_name,
                    "--as",
                    identity,
                    "--token",
                    token,
                    "--output",
                    rel_out,
                    "--overwrite",
                ],
                cwd=dest_dir,
            )
            if resp.get("ok"):
                data = resp.get("data") or {}
                saved = data.get("saved_path")
                ctype = str(data.get("content_type") or "")
                if saved and Path(saved).exists():
                    return str(_ensure_image_extension(Path(saved).resolve(), ctype)), None
                matches = list(dest_dir.glob(f"{safe_stem}*"))
                if matches:
                    return str(_ensure_image_extension(matches[0].resolve(), ctype)), None
            elif cmd_name == "+media-download":
                subtype = ((resp.get("error") or {}).get("subtype") or "").lower()
                if subtype == "permission_denied":
                    blocked.add(identity)
    return None, f"无法下载或预览图片 {token}（身份：{','.join(identities)}）"


def node_text(node: dict[str, Any]) -> str:
    txt = node.get("text")
    if isinstance(txt, dict):
        raw = txt.get("text") or ""
        return "\n".join(line.strip() for line in raw.splitlines() if line.strip())
    return ""


def parse_table_node(node: dict[str, Any]) -> list[list[str]]:
    cells = ((node.get("table") or {}).get("cells")) or []
    by_row: dict[int, list[tuple[int, str]]] = {}
    for cell in cells:
        r = int(cell.get("row_index") or 0)
        c = int(cell.get("col_index") or 0)
        txt = ""
        if isinstance(cell.get("text"), dict):
            txt = (cell["text"].get("text") or "").strip()
        by_row.setdefault(r, []).append((c, txt))
    rows: list[list[str]] = []
    for r in sorted(by_row):
        row = [t for _, t in sorted(by_row[r], key=lambda item: item[0])]
        if any(row):
            rows.append(row)
    return rows


def rect_of(node: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(node.get("x") or 0.0)
    y = float(node.get("y") or 0.0)
    w = float(node.get("width") or 0.0)
    h = float(node.get("height") or 0.0)
    return x, y, w, h


def center_of(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = rect
    return x + w / 2.0, y + h / 2.0


def overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def rect_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    dx = max(0.0, max(bx1 - ax2, ax1 - bx2))
    dy = max(0.0, max(by1 - ay2, ay1 - by2))
    return (dx * dx + dy * dy) ** 0.5


def sanitize_filename(name: str, fallback: str = "task") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\r\n]+', "-", name).strip(" .-")
    return cleaned[:80] or fallback


def extract_semantic_tokens(texts: list[str]) -> set[str]:
    joined = " ".join(texts)
    tokens: set[str] = set()
    for kw in SELLING_KEYWORDS:
        if kw.lower() in joined.lower():
            tokens.add(kw.lower())
    for phrase in re.findall(r"[\u4e00-\u9fff]{3,10}", joined):
        if phrase not in NOISE_TEXTS:
            tokens.add(phrase)
    for num_unit in re.findall(r"\d+(?:\.\d+)?\s*(?:mm|cm|g|%|倍)", joined, flags=re.IGNORECASE):
        tokens.add(re.sub(r"\s+", "", num_unit.lower()))
    return tokens


def extract_must_render_codes(texts: list[str]) -> set[str]:
    joined = "\n".join(texts)
    return {re.sub(r"\s+", "", m.group(1)) for m in MUST_RENDER_RE.finditer(joined)}


def _extract_must_render_items(
    shapes: list[dict[str, Any]],
    stickies: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_code: dict[str, list[str]] = {}
    for node in shapes + stickies:
        txt = node.get("text", "")
        if not txt or "必渲" not in txt and "必拍" not in txt:
            continue
        for line in txt.splitlines():
            for match in MUST_RENDER_RE.finditer(line):
                code = re.sub(r"\s+", "", match.group(1))
                rest = match.group(2).strip(" ：:|/-")
                full_line = (code + (" " + rest if rest else "")).strip()
                by_code.setdefault(code, []).append(full_line)

    result: list[dict[str, str]] = []
    for code, entries in by_code.items():
        # Prefer the most informative description
        best = max(dict.fromkeys(entries), key=len)
        result.append({"code": code, "title": best})
    return result


def _normalize_nodes(raw_nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    images: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []
    stickies: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    connectors: list[dict[str, Any]] = []

    raw_by_id = {n.get("id", ""): n for n in raw_nodes if n.get("id")}

    def _resolve_abs_pos_and_section(node: dict[str, Any]) -> tuple[float, float, str, str]:
        ax = float(node.get("x") or 0.0)
        ay = float(node.get("y") or 0.0)
        sec_id = ""
        sec_title = ""
        seen = {node.get("id", "")}
        pid = node.get("parent_id")
        while pid and pid in raw_by_id and pid not in seen:
            seen.add(pid)
            par = raw_by_id[pid]
            if par.get("type") == "section":
                ax += float(par.get("x") or 0.0)
                ay += float(par.get("y") or 0.0)
                if not sec_id:
                    sec_id = par.get("id", "")
                    sec_title = (((par.get("section") or {}).get("title")) or node_text(par)).strip()
            pid = par.get("parent_id")
        return ax, ay, sec_id, sec_title

    for node in raw_nodes:
        ntype = node.get("type")
        _, _, w, h = rect_of(node)
        x, y, parent_sec_id, parent_sec_title = _resolve_abs_pos_and_section(node)
        cx, cy = center_of((x, y, w, h))
        item = {
            "id": node.get("id", ""),
            "type": ntype,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cx": cx,
            "cy": cy,
            "area": w * h,
            "ratio": round(w / h, 3) if h > 0 else 0.0,
            "z_index": int(node.get("z_index") or 0),
            "parent_id": node.get("parent_id") or "",
            "parent_section_id": parent_sec_id,
            "parent_section_title": parent_sec_title,
            "style": node.get("style") or {},
            "text_meta": node.get("text") or {},
        }
        if ntype == "image":
            tok = ((node.get("image") or {}).get("token")) or ""
            item["token"] = tok
            images.append(item)
        elif ntype in ("composite_shape", "text_shape"):
            item["text"] = node_text(node)
            item["shape_kind"] = ((node.get("composite_shape") or {}).get("type")) or ""
            shapes.append(item)
        elif ntype == "sticky_note":
            item["text"] = node_text(node)
            stickies.append(item)
        elif ntype == "table":
            item["rows"] = parse_table_node(node)
            tables.append(item)
        elif ntype == "section":
            sec_title = (((node.get("section") or {}).get("title")) or node_text(node)).strip()
            item["section_title"] = sec_title
            item["text"] = sec_title or node_text(node)
            sections.append(item)
        elif ntype == "connector":
            item["connector"] = node.get("connector") or {}
            connectors.append(item)

    return {
        "images": images,
        "shapes": shapes,
        "stickies": stickies,
        "tables": tables,
        "sections": sections,
        "connectors": connectors,
    }


def _detect_horizontal_main_row_ids(
    images: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> set[str]:
    """Protect >=3-card horizontal 3:4 main-image rows from being swallowed by vertical detail stacks."""
    cands: list[dict[str, Any]] = []
    for img in images:
        if img["w"] >= 600 and img["h"] >= 800 and 0.66 <= img["ratio"] <= 0.86:
            cands.append(img)
    for shp in shapes:
        if shp["w"] >= 600 and shp["h"] >= 800 and 0.66 <= shp["ratio"] <= 0.86 and not shp["text"]:
            cands.append(shp)
    for sec in sections:
        if 600 <= sec["w"] <= 1800 and 800 <= sec["h"] <= 2400 and 0.66 <= sec["ratio"] <= 0.86:
            cands.append(sec)

    rows: list[list[dict[str, Any]]] = []
    for cand in sorted(cands, key=lambda c: (c["y"], c["x"])):
        placed = False
        for row in rows:
            anchor_y = statistics.median(c["y"] for c in row)
            if abs(cand["y"] - anchor_y) <= 350:
                row.append(cand)
                placed = True
                break
        if not placed:
            rows.append([cand])

    protected: set[str] = set()
    for row in rows:
        # Count distinct horizontal positions (dedup overlapping image + frame)
        xs: list[float] = []
        for item in sorted(row, key=lambda k: k["x"]):
            if not any(abs(item["x"] - px) < 250 for px in xs):
                xs.append(item["x"])
        if len(xs) >= 3:
            row_y1 = min(c["y"] for c in row) - 500
            row_y2 = max(c["y"] + c["h"] for c in row) + 500
            row_x1 = min(c["x"] for c in row) - 2200
            row_x2 = max(c["x"] + c["w"] for c in row) + 1200
            has_text = any(
                s["text"] and row_x1 <= s["cx"] <= row_x2 and row_y1 <= s["cy"] <= row_y2 for s in shapes
            )
            if has_text or any(c["type"] in ("composite_shape", "section") for c in row):
                for item in row:
                    protected.add(item["id"])
    return protected


def _is_signpost_text(text: str) -> bool:
    clean = (text or "").strip()
    if not clean or clean in NOISE_TEXTS:
        return True
    return bool(SIGNPOST_RE.fullmatch(clean))


def _has_overhead_video_marker(
    node: dict[str, Any],
    video_markers: list[dict[str, Any]],
) -> bool:
    for vm in video_markers:
        horizontally_close = (node["x"] - 160) <= vm["cx"] <= (node["x"] + node["w"] + 160)
        just_above_or_top = (node["y"] - 420) <= vm["y"] <= (node["y"] + 180)
        if horizontally_close and just_above_or_top:
            return True
    return False


def _is_non_detail_section(node: dict[str, Any]) -> bool:
    p_sec = node.get("parent_section_title") or ""
    if not p_sec:
        return False
    return ("主图" in p_sec or "入口" in p_sec or "车图" in p_sec) and "详情" not in p_sec


def _find_detail_stack(
    images: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    stickies: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    *,
    protected_main_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
    """Detect dominant vertical detail stack (container-first) and isolate parallel stacks."""
    protected = protected_main_ids or set()
    candidates: list[dict[str, Any]] = []

    container_nodes = [
        *( (s, "layout_frame") for s in sorted(shapes, key=lambda n: -n["area"]) ),
        *( (sec, "section_frame") for sec in sorted(sections, key=lambda n: -n["area"]) ),
    ]
    # Keep larger outer containers (chapters/screens) ahead of smaller nested frames or sub-images
    container_nodes.sort(key=lambda pair: -pair[0]["area"])
    for node, kind in container_nodes:
        if node["id"] in protected or _is_non_detail_section(node):
            continue
        if not (650 <= node["w"] <= 1900 and 420 <= node["h"] <= 4500):
            continue
        overlaps_existing = any(
            overlap_1d(node["x"], node["x"] + node["w"], c["x"], c["x"] + c["w"]) > min(node["w"], c["w"]) * 0.5
            and overlap_1d(node["y"], node["y"] + node["h"], c["y"], c["y"] + c["h"]) > min(node["h"], c["h"]) * 0.5
            for c in candidates
        )
        if overlaps_existing:
            continue
        card = dict(node, token="", source_kind=kind)
        if node.get("text") and not _is_signpost_text(node["text"]):
            card["initial_text"] = node["text"]
        candidates.append(card)

    for img in images:
        if img["id"] in protected or _is_non_detail_section(img):
            continue
        if not (650 <= img["w"] <= 1900 and 320 <= img["h"] <= 4500):
            continue
        inside_container = any(
            c["area"] > 0
            and img["area"] <= c["area"] * 0.96
            and (
                (
                    (c["x"] - 30) <= img["cx"] <= (c["x"] + c["w"] + 30)
                    and (c["y"] - 30) <= img["cy"] <= (c["y"] + c["h"] + 30)
                )
                or (
                    overlap_1d(img["x"], img["x"] + img["w"], c["x"], c["x"] + c["w"]) > min(img["w"], c["w"]) * 0.5
                    and overlap_1d(img["y"], img["y"] + img["h"], c["y"], c["y"] + c["h"]) > min(img["h"], c["h"]) * 0.5
                )
            )
            for c in candidates
        )
        if not inside_container:
            candidates.append(dict(img, source_kind="image"))

    if len(candidates) < 4:
        return [], set(), []

    clusters: list[list[dict[str, Any]]] = []
    for cand in sorted(candidates, key=lambda c: c["x"]):
        placed = False
        for cluster in clusters:
            anchor_x = statistics.median(c["x"] for c in cluster)
            if abs(cand["x"] - anchor_x) <= 220:
                cluster.append(cand)
                placed = True
                break
        if not placed:
            clusters.append([cand])

    scored_stacks: list[tuple[float, float, list[dict[str, Any]]]] = []
    for cluster in clusters:
        if len(cluster) < 4:
            continue
        med_w = statistics.median(c["w"] for c in cluster)
        aligned = [c for c in cluster if 0.72 * med_w <= c["w"] <= 1.32 * med_w]
        if len(aligned) < 4:
            continue
        aligned.sort(key=lambda c: (c["y"], c["x"]))

        contiguous_runs: list[list[dict[str, Any]]] = [[aligned[0]]]
        for item in aligned[1:]:
            prev = contiguous_runs[-1][-1]
            gap = item["y"] - (prev["y"] + prev["h"])
            if -350 <= gap <= 8000:
                contiguous_runs[-1].append(item)
            else:
                contiguous_runs.append([item])
        longest = max(contiguous_runs, key=len)
        if len(longest) < 4:
            continue

        x_min = min(c["x"] for c in longest) - 550
        x_max = max(c["x"] + c["w"] for c in longest) + 550
        y_min = min(c["y"] for c in longest) - 250
        y_max = max(c["y"] + c["h"] for c in longest) + 250
        text_hits = sum(
            1 for s in shapes if s["text"] and not _is_signpost_text(s["text"]) and x_min <= s["cx"] <= x_max and y_min <= s["cy"] <= y_max
        )
        sticky_hits = sum(
            1 for s in stickies if s["text"] and x_min <= s["cx"] <= x_max and y_min <= s["cy"] <= y_max
        )
        if text_hits + sticky_hits == 0:
            continue
        width_bonus = 6.0 if 720 <= med_w <= 1120 else 0.0
        score = len(longest) * 6.0 + text_hits * 1.2 + sticky_hits * 2.5 + width_bonus
        x_med = statistics.median(c["x"] for c in longest)
        scored_stacks.append((score, x_med, longest))

    if not scored_stacks:
        return [], set(), []

    scored_stacks.sort(key=lambda item: item[0], reverse=True)
    _, best_x, best_stack = scored_stacks[0]

    # Absorb thin horizontal continuation image strips sitting flush right below a detail card (e.g. 201 bottom pyramid)
    best_ids = {c["id"] for c in best_stack}
    for card in best_stack:
        for img in images:
            if img["id"] in best_ids or img["id"] in protected or _is_non_detail_section(img):
                continue
            if 650 <= img["w"] <= 1900 and 100 <= img["h"] < 340 and abs(img["x"] - card["x"]) <= 120:
                gap_y = img["y"] - (card["y"] + card["h"])
                if -40 <= gap_y <= 45:
                    card["h"] = max(card["h"], (img["y"] + img["h"]) - card["y"])
                    card["cy"] = card["y"] + card["h"] / 2.0
                    card["area"] = card["w"] * card["h"]
                    best_ids.add(img["id"])

    alt_stacks: list[dict[str, Any]] = []
    alt_consumed_ids: set[str] = set()
    for _, x_med, stk in scored_stacks[1:]:
        if abs(x_med - best_x) >= 1500:
            alt_stacks.append({"x": round(x_med), "screen_count": len(stk)})
            for item in stk:
                alt_consumed_ids.add(item["id"])
    consumed_ids = {item["id"] for item in best_stack} | alt_consumed_ids
    return best_stack, consumed_ids, alt_stacks


def _assign_annotations_to_cards(
    cards: list[dict[str, Any]],
    images: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    stickies: list[dict[str, Any]],
    consumed_image_ids: set[str],
    consumed_shape_ids: set[str],
    consumed_sticky_ids: set[str],
    *,
    x_pad: float,
    y_pad: float,
    sticky_pad: float,
) -> None:
    """Attach embedded sub-images, editable texts, and sticky notes to cards without duplicating."""
    for card in cards:
        card["embedded_images"] = []
        card.setdefault("side_reference_images", [])
        init_txt = card.get("initial_text") or ""
        card["texts"] = [(card["y"], card["x"], init_txt)] if init_txt else []
        card["sticky_notes"] = []

    if not cards:
        return

    for img in images:
        if img["id"] in consumed_image_ids:
            continue
        best_card = None
        best_dist = float("inf")
        for card in cards:
            cr = (card["x"] - 40, card["y"] - 40, card["w"] + 80, card["h"] + 80)
            if cr[0] <= img["cx"] <= cr[0] + cr[2] and cr[1] <= img["cy"] <= cr[1] + cr[3]:
                area_limit = 1.02 if card.get("source_kind") != "image" else 0.90
                if img["area"] < card["area"] * area_limit:
                    d = rect_distance((card["x"], card["y"], card["w"], card["h"]), (img["x"], img["y"], img["w"], img["h"]))
                    if d < best_dist:
                        best_dist = d
                        best_card = card
        if best_card is not None:
            best_card["embedded_images"].append(
                {
                    "id": img["id"],
                    "token": img["token"],
                    "width": round(img["w"]),
                    "height": round(img["h"]),
                    "area": round(img["area"]),
                }
            )
            consumed_image_ids.add(img["id"])

    for shp in shapes:
        if shp["id"] in consumed_shape_ids or not shp["text"] or _is_signpost_text(shp["text"]):
            continue
        best_card = None
        best_score = -1e18
        for card in cards:
            cx1, cy1 = card["x"] - x_pad, card["y"] - y_pad
            cx2, cy2 = card["x"] + card["w"] + x_pad, card["y"] + card["h"] + y_pad
            if not (cx1 <= shp["cx"] <= cx2 and cy1 <= shp["cy"] <= cy2):
                continue
            ov_y = overlap_1d(card["y"], card["y"] + card["h"], shp["y"], shp["y"] + shp["h"])
            ov_x = overlap_1d(card["x"], card["x"] + card["w"], shp["x"], shp["x"] + shp["w"])
            inside = (
                card["x"] <= shp["cx"] <= card["x"] + card["w"]
                and card["y"] <= shp["cy"] <= card["y"] + card["h"]
            )
            dist = rect_distance((card["x"], card["y"], card["w"], card["h"]), (shp["x"], shp["y"], shp["w"], shp["h"]))
            score = (10000.0 if inside else 0.0) + ov_y * 2.0 + ov_x - dist
            if score > best_score:
                best_score = score
                best_card = card
        if best_card is not None:
            best_card["texts"].append((shp["y"], shp["x"], shp["text"]))
            consumed_shape_ids.add(shp["id"])

    for stk in stickies:
        if stk["id"] in consumed_sticky_ids or not stk["text"]:
            continue
        if stk["w"] >= 1400 and stk["h"] >= 1400 and "卖点" in stk["text"]:
            continue
        best_card = None
        best_dist = float("inf")
        for card in cards:
            cx1, cy1 = card["x"] - sticky_pad, card["y"] - sticky_pad
            cx2, cy2 = card["x"] + card["w"] + sticky_pad, card["y"] + card["h"] + sticky_pad
            if not (cx1 <= stk["cx"] <= cx2 and cy1 <= stk["cy"] <= cy2):
                continue
            d = rect_distance((card["x"], card["y"], card["w"], card["h"]), (stk["x"], stk["y"], stk["w"], stk["h"]))
            if d < best_dist:
                best_dist = d
                best_card = card
        if best_card is not None:
            best_card["sticky_notes"].append(stk["text"])
            consumed_sticky_ids.add(stk["id"])

    for card in cards:
        ordered = [t for _, _, t in sorted(card["texts"], key=lambda item: (item[0], item[1]))]
        deduped: list[str] = []
        for t in ordered:
            if t not in deduped and not _is_signpost_text(t):
                deduped.append(t)
        card["texts"] = deduped


def _attach_side_references(
    cards: list[dict[str, Any]],
    images: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    consumed_image_ids: set[str],
    consumed_shape_ids: set[str],
    *,
    max_x_gap: float = 2800.0,
) -> list[dict[str, Any]]:
    """Attach unconsumed plain competitor/reference images aligned to the right of wireframe cards."""
    attached_refs: list[dict[str, Any]] = []
    if not cards:
        return attached_refs

    for img in sorted(images, key=lambda n: (n["y"], n["x"])):
        if img["id"] in consumed_image_ids:
            continue
        if img["w"] < 300 or img["h"] < 300:
            continue
        # Only swallow bare reference screenshots (do not swallow images that contain copywriting boxes)
        has_overlay_text = any(
            s["id"] not in consumed_shape_ids
            and s.get("text")
            and not _is_signpost_text(s["text"])
            and (img["x"] - 20) <= s["cx"] <= (img["x"] + img["w"] + 20)
            and (img["y"] - 20) <= s["cy"] <= (img["y"] + img["h"] + 20)
            for s in shapes
        )
        if has_overlay_text:
            continue

        best_card = None
        best_gap = float("inf")
        for card in cards:
            # Stay inside same section when card belongs to an explicit section (don't swallow adjacent car-angle section)
            c_sec = card.get("parent_section_id") or ""
            i_sec = img.get("parent_section_id") or ""
            if c_sec and i_sec and c_sec != i_sec:
                continue
            gap_x = img["x"] - (card["x"] + card["w"])
            if not (-10 <= gap_x <= max_x_gap):
                continue
            ov_y = overlap_1d(card["y"], card["y"] + card["h"], img["y"], img["y"] + img["h"])
            if ov_y < min(card["h"], img["h"]) * 0.20:
                continue
            if gap_x < best_gap:
                best_gap = gap_x
                best_card = card

        if best_card is not None:
            best_card.setdefault("side_reference_images", []).append(
                {
                    "id": img["id"],
                    "token": img["token"],
                    "width": round(img["w"]),
                    "height": round(img["h"]),
                    "area": round(img["area"]),
                    "x": round(img["x"]),
                    "y": round(img["y"]),
                }
            )
            consumed_image_ids.add(img["id"])
            attached_refs.append(img)
    for card in cards:
        refs = card.get("side_reference_images") or []
        refs.sort(key=lambda r: (round(r.get("x", 0) / 450), r.get("y", 0)))
    return attached_refs


def _find_main_and_entry_cards(
    images: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    stickies: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    consumed_image_ids: set[str],
    consumed_shape_ids: set[str],
    consumed_section_ids: set[str],
    consumed_sticky_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Identify 3:4 main-image wireframes (excluding video frames), 1:1 entry/SKU cards, and right-side refs."""
    entry_markers = [
        n
        for n in (stickies + shapes)
        if n["id"] not in consumed_sticky_ids
        and n["id"] not in consumed_shape_ids
        and n.get("text")
        and len(n["text"]) <= 24
        and any(k in n["text"] for k in ENTRY_NOTE_KEYWORDS)
    ]
    main_markers = [
        n
        for n in (stickies + shapes)
        if n["id"] not in consumed_sticky_ids
        and n["id"] not in consumed_shape_ids
        and n.get("text")
        and len(n["text"]) <= 24
        and any(k in n["text"] for k in MAIN_MARKER_KEYWORDS)
    ]
    video_markers = [
        n
        for n in (shapes + stickies)
        if n["id"] not in consumed_shape_ids
        and n["id"] not in consumed_sticky_ids
        and n.get("text")
        and len(n["text"]) <= 24
        and any(k in n["text"] for k in VIDEO_FRAME_KEYWORDS)
    ]

    main_candidates: list[dict[str, Any]] = []
    square_candidates: list[dict[str, Any]] = []

    for img in images:
        if img["id"] in consumed_image_ids:
            continue
        if _has_overhead_video_marker(img, video_markers):
            consumed_image_ids.add(img["id"])
            continue
        if img["w"] >= 600 and img["h"] >= 800 and 0.66 <= img["ratio"] <= 0.86:
            main_candidates.append(dict(img, source_kind="image"))
        elif img["w"] >= 580 and img["h"] >= 580 and 0.88 <= img["ratio"] <= 1.12:
            square_candidates.append(dict(img, source_kind="image"))

    for node, kind in [*( (s, "layout_frame") for s in shapes ), *( (sec, "section_frame") for sec in sections )]:
        if kind == "layout_frame" and (node["id"] in consumed_shape_ids or node.get("text")):
            continue
        if kind == "section_frame" and node["id"] in consumed_section_ids:
            continue
        if _has_overhead_video_marker(node, video_markers):
            if kind == "section_frame":
                consumed_section_ids.add(node["id"])
            else:
                consumed_shape_ids.add(node["id"])
            for shp in shapes:
                if (node["x"] - 20) <= shp["cx"] <= (node["x"] + node["w"] + 20) and (node["y"] - 20) <= shp["cy"] <= (node["y"] + node["h"] + 20):
                    consumed_shape_ids.add(shp["id"])
            continue
        if 600 <= node["w"] <= 1800 and 800 <= node["h"] <= 2400 and 0.66 <= node["ratio"] <= 0.86:
            overlaps = any(
                overlap_1d(node["x"], node["x"] + node["w"], c["x"], c["x"] + c["w"]) > min(node["w"], c["w"]) * 0.5
                and overlap_1d(node["y"], node["y"] + node["h"], c["y"], c["y"] + c["h"]) > min(node["h"], c["h"]) * 0.5
                for c in main_candidates
            )
            if not overlaps:
                main_candidates.append(dict(node, token="", source_kind=kind))
        elif kind == "layout_frame" and 580 <= node["w"] <= 1800 and 580 <= node["h"] <= 1800 and 0.88 <= node["ratio"] <= 1.12:
            overlaps = any(
                overlap_1d(node["x"], node["x"] + node["w"], c["x"], c["x"] + c["w"]) > min(node["w"], c["w"]) * 0.5
                and overlap_1d(node["y"], node["y"] + node["h"], c["y"], c["y"] + c["h"]) > min(node["h"], c["h"]) * 0.5
                for c in square_candidates
            )
            if not overlaps:
                square_candidates.append(dict(node, token="", source_kind=kind))

    rows: list[list[dict[str, Any]]] = []
    for cand in sorted(main_candidates, key=lambda c: (c["y"], c["x"])):
        placed = False
        for row in rows:
            anchor_y = statistics.median(c["y"] for c in row)
            if abs(cand["y"] - anchor_y) <= 350:
                row.append(cand)
                placed = True
                break
        if not placed:
            rows.append([cand])

    active_main_cards: list[dict[str, Any]] = []
    car_angle_cards: list[dict[str, Any]] = []
    competitor_refs: list[dict[str, Any]] = []

    for row in rows:
        row.sort(key=lambda c: c["x"])
        row_y1 = min(c["y"] for c in row) - 500
        row_y2 = max(c["y"] + c["h"] for c in row) + 500
        row_x1 = min(c["x"] for c in row) - 2200
        row_x2 = max(c["x"] + c["w"] for c in row) + 1200

        nearby_texts = [
            s
            for s in shapes
            if s["id"] not in consumed_shape_ids
            and s["text"]
            and not _is_signpost_text(s["text"])
            and row_x1 <= s["cx"] <= row_x2
            and row_y1 <= s["cy"] <= row_y2
        ]
        nearby_entry_marker = any(
            abs(s["cy"] - statistics.median(c["cy"] for c in row)) <= 1200
            and row_x1 - 2500 <= s["cx"] <= row_x2
            and ("车图" in s["text"] or "入口" in s["text"])
            for s in entry_markers
        )
        nearby_main_marker = any(
            abs(s["cy"] - statistics.median(c["cy"] for c in row)) <= 1200
            and row_x1 - 2500 <= s["cx"] <= row_x2
            for s in main_markers
        )
        has_selling_text = any(len(s["text"]) >= 3 for s in nearby_texts)

        wireframes_in_row = [c for c in row if c["source_kind"] in ("layout_frame", "section_frame")]
        if nearby_entry_marker and not nearby_main_marker and len(nearby_texts) <= 2:
            car_angle_cards.extend(row)
        elif wireframes_in_row:
            # Bare images sitting to the right of active wireframes are competitor/inspiration screenshots
            active_main_cards.extend(wireframes_in_row)
            max_wf_right = max(w["x"] + w["w"] for w in wireframes_in_row)
            for c in row:
                if c["source_kind"] == "image":
                    has_inside_txt = any(
                        s["id"] not in consumed_shape_ids
                        and s.get("text")
                        and not _is_signpost_text(s["text"])
                        and (c["x"] - 20) <= s["cx"] <= (c["x"] + c["w"] + 20)
                        and (c["y"] - 20) <= s["cy"] <= (c["y"] + c["h"] + 20)
                        for s in shapes
                    )
                    if not has_inside_txt and c["x"] >= max_wf_right - 100:
                        continue
                    active_main_cards.append(c)
        elif has_selling_text or nearby_main_marker:
            active_main_cards.extend(row)
        else:
            competitor_refs.extend(row)

    for card in active_main_cards + car_angle_cards:
        if card["source_kind"] == "image":
            consumed_image_ids.add(card["id"])
        elif card["source_kind"] == "section_frame":
            consumed_section_ids.add(card["id"])
        else:
            consumed_shape_ids.add(card["id"])

    _assign_annotations_to_cards(
        active_main_cards,
        images,
        shapes,
        stickies,
        consumed_image_ids,
        consumed_shape_ids,
        consumed_sticky_ids,
        x_pad=450,
        y_pad=350,
        sticky_pad=650,
    )
    competitor_refs.extend(
        _attach_side_references(
            active_main_cards,
            images,
            shapes,
            consumed_image_ids,
            consumed_shape_ids,
            max_x_gap=2800.0,
        )
    )

    active_entry_cards: list[dict[str, Any]] = []
    has_entry_section = any("入口" in (sec.get("section_title") or "") for sec in sections)
    sorted_squares = sorted(
        square_candidates,
        key=lambda c: (0 if c["source_kind"] == "layout_frame" else 1, c["y"], c["x"]),
    )
    for sq in sorted_squares:
        p_sec = sq.get("parent_section_title") or ""
        if "车图" in p_sec and "入口" not in p_sec:
            competitor_refs.append(sq)
            if sq["source_kind"] == "image":
                consumed_image_ids.add(sq["id"])
            continue
        if sq["source_kind"] == "image" and sq["id"] in consumed_image_ids:
            continue
        sx1, sy1, sx2, sy2 = sq["x"] - 320, sq["y"] - 220, sq["x"] + sq["w"] + 500, sq["y"] + sq["h"] + 280
        has_overlay_shape = any(
            s["id"] not in consumed_shape_ids
            and s["type"] == "composite_shape"
            and s["text"]
            and not _is_signpost_text(s["text"])
            and sx1 <= s["cx"] <= sx2
            and sy1 <= s["cy"] <= sy2
            for s in shapes
        )
        has_entry_note = any(
            abs(s["cy"] - sq["cy"]) <= 1500 and abs(s["cx"] - sq["cx"]) <= 2200 for s in entry_markers
        )
        in_entry_section = "入口" in p_sec
        explicit_sku = any(
            k in s["text"] for s in shapes if sx1 <= s["cx"] <= sx2 and sy1 <= s["cy"] <= sy2 for k in ("sku", "SKU", "入口", "800主图")
        )
        keep_sq = in_entry_section or sq["source_kind"] == "layout_frame" or (
            not has_entry_section and (has_overlay_shape or has_entry_note)
        ) or explicit_sku
        if keep_sq:
            active_entry_cards.append(sq)
            if sq["source_kind"] == "image":
                consumed_image_ids.add(sq["id"])
            else:
                consumed_shape_ids.add(sq["id"])
            competitor_refs.extend(
                _attach_side_references(
                    [sq],
                    images,
                    shapes,
                    consumed_image_ids,
                    consumed_shape_ids,
                    max_x_gap=1800.0,
                )
            )
        else:
            competitor_refs.append(sq)

    active_entry_cards.sort(key=lambda c: (c["y"], c["x"]))
    _assign_annotations_to_cards(
        active_entry_cards,
        images,
        shapes,
        stickies,
        consumed_image_ids,
        consumed_shape_ids,
        consumed_sticky_ids,
        x_pad=550,
        y_pad=220,
        sticky_pad=1400,
    )
    competitor_refs.extend(
        _attach_side_references(
            active_entry_cards,
            images,
            shapes,
            consumed_image_ids,
            consumed_shape_ids,
            max_x_gap=1800.0,
        )
    )

    return active_main_cards, active_entry_cards, competitor_refs


def _extract_milestone_slots(
    board_meta: dict[str, Any],
    parsed: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    images = parsed["images"]
    shapes = parsed["shapes"]
    sections = parsed["sections"]

    has_milestone_signals = board_meta.get("is_milestone_heading") or any(
        any(k in s["text"] for k in MILESTONE_KEYWORDS) for s in shapes + sections
    )
    if not has_milestone_signals:
        return []

    slot_shapes = [
        s
        for s in sorted(shapes, key=lambda k: (k["y"], k["x"]))
        if s["text"] and "里程碑" not in s["text"]
    ]
    slots: list[dict[str, Any]] = []
    for idx, shp in enumerate(slot_shapes, start=1):
        matched_imgs = [
            {
                "id": img["id"],
                "token": img["token"],
                "width": round(img["w"]),
                "height": round(img["h"]),
            }
            for img in images
            if overlap_1d(img["x"], img["x"] + img["w"], shp["x"], shp["x"] + shp["w"]) > 0
            and img["y"] <= shp["y"] + shp["h"] + 150
        ]
        slots.append(
            {
                "id": f"MS{idx:02d}",
                "slot_name": shp["text"],
                "status": "已有参考图" if matched_imgs else "待生成定调",
                "target_gen_ratio": DEFAULT_GENERATION_RATIO,
                "reference_images": matched_imgs,
            }
        )
    return slots


def _extract_revision_patch(
    raw_nodes: list[dict[str, Any]],
    *,
    board_token: str,
    board_heading: str,
    board_context: str = "",
) -> dict[str, Any]:
    parsed = _normalize_nodes(raw_nodes)
    texts = [
        s["text"]
        for s in sorted(parsed["shapes"] + parsed["stickies"], key=lambda k: (k["y"], k["x"]))
        if s.get("text") and s["text"] not in NOISE_TEXTS
    ]
    img_count = len(parsed["images"])
    return {
        "board_token": board_token,
        "heading": board_heading or "最新修改轮",
        "context": board_context,
        "node_count": len(raw_nodes),
        "image_count": img_count,
        "texts": list(dict.fromkeys(texts)),
    }


def _detect_fact_conflicts(raw_texts: list[str]) -> list[str]:
    notes: list[str] = []
    joined = "\n".join(raw_texts)
    if re.search(r"勺深\s*6\s*cm", joined) and re.search(r"勺深[：:]\s*(?:6|5\.8)\s*mm", joined):
        notes.append("画布标注存在单位笔误：底部尺寸图写「勺深6cm」，规格文本写「勺深6mm（0.6cm）」，出图排版前按 6mm/0.6cm 核实。")
    if ("18.7cm" in joined or "187mm" in joined) and "18.8cm" in joined:
        notes.append("大号勺长同时出现「187mm(18.7cm)」与「18.8cm」，生图标注前需确认以哪个实测尺寸为准。")
    return notes


def analyze_whiteboard_nodes(
    raw_nodes: list[dict[str, Any]],
    *,
    board_token: str,
    board_heading: str = "",
    is_milestone_heading: bool = False,
    default_ratio: str = DEFAULT_GENERATION_RATIO,
) -> dict[str, Any]:
    """Spatially cluster a Feishu whiteboard's nodes into structured planning items."""
    parsed = _normalize_nodes(raw_nodes)
    images = parsed["images"]
    shapes = parsed["shapes"]
    stickies = parsed["stickies"]
    tables = parsed["tables"]
    sections = parsed["sections"]

    milestone_slots = _extract_milestone_slots(
        {"token": board_token, "heading": board_heading, "is_milestone_heading": is_milestone_heading},
        parsed,
    )
    if milestone_slots and is_milestone_heading:
        return {
            "board_token": board_token,
            "board_kind": "milestone",
            "milestone_slots": milestone_slots,
            "detail_screens": [],
            "main_cards": [],
            "entry_cards": [],
            "must_render_assets": [],
            "alt_detail_stacks": [],
            "competitor_reference_count": 0,
            "board_facts": {"tables": [], "selling_notes": [], "spec_texts": [], "positioning_formulas": []},
            "fact_conflicts": [],
        }

    protected_main_ids = _detect_horizontal_main_row_ids(images, shapes, sections)
    detail_cards_raw, all_detail_consumed_ids, alt_detail_stacks = _find_detail_stack(
        images,
        shapes,
        stickies,
        sections,
        protected_main_ids=protected_main_ids,
    )
    consumed_image_ids = {c["id"] for c in detail_cards_raw if c["source_kind"] == "image"} | {
        img["id"] for img in images if img["id"] in all_detail_consumed_ids
    }
    consumed_shape_ids = {c["id"] for c in detail_cards_raw if c["source_kind"] == "layout_frame"} | {
        shp["id"] for shp in shapes if shp["id"] in all_detail_consumed_ids
    }
    consumed_section_ids = {c["id"] for c in detail_cards_raw if c["source_kind"] == "section_frame"} | {
        sec["id"] for sec in sections if sec["id"] in all_detail_consumed_ids
    }
    consumed_sticky_ids: set[str] = set()

    _assign_annotations_to_cards(
        detail_cards_raw,
        images,
        shapes,
        stickies,
        consumed_image_ids,
        consumed_shape_ids,
        consumed_sticky_ids,
        x_pad=550,
        y_pad=60,
        sticky_pad=650,
    )
    detail_side_refs = _attach_side_references(
        detail_cards_raw,
        images,
        shapes,
        consumed_image_ids,
        consumed_shape_ids,
        max_x_gap=1800.0,
    )

    main_cards_raw, entry_cards_raw, competitor_refs = _find_main_and_entry_cards(
        images,
        shapes,
        stickies,
        sections,
        consumed_image_ids,
        consumed_shape_ids,
        consumed_section_ids,
        consumed_sticky_ids,
    )
    competitor_refs = [*detail_side_refs, *competitor_refs]

    # Identify repeating tiny brand logo icons (<=360x260 used >=3 times) so they never mask real refs
    token_areas: dict[str, list[int]] = {}
    for raw_card in [*detail_cards_raw, *main_cards_raw, *entry_cards_raw]:
        for emb in raw_card.get("embedded_images", []):
            tok = emb.get("token", "")
            if tok:
                token_areas.setdefault(tok, []).append(int(emb.get("area") or (emb.get("width", 0) * emb.get("height", 0))))
    small_logo_tokens = {
        tok
        for tok, areas in token_areas.items()
        if len(areas) >= 3 and max(areas) <= 360 * 260
    }

    def _pick_primary_ref_token(raw_card: dict[str, Any]) -> str:
        if raw_card.get("token"):
            return str(raw_card["token"])
        embs = [e for e in raw_card.get("embedded_images", []) if e.get("token")]
        non_logo_embs = [e for e in embs if e["token"] not in small_logo_tokens]
        if non_logo_embs:
            best_emb = max(non_logo_embs, key=lambda e: int(e.get("area") or (e.get("width", 0) * e.get("height", 0))))
            return str(best_emb["token"])
        side_refs = [s for s in raw_card.get("side_reference_images", []) if s.get("token")]
        if side_refs:
            best_side = min(side_refs, key=lambda s: int(s.get("x") or 0))
            return str(best_side["token"])
        if embs:
            best_emb = max(embs, key=lambda e: int(e.get("area") or (e.get("width", 0) * e.get("height", 0))))
            return str(best_emb["token"])
        return ""

    main_cards: list[dict[str, Any]] = []
    for idx, c in enumerate(main_cards_raw, start=1):
        texts = [t for t in c["texts"] if not _is_signpost_text(t)]
        title = texts[0].splitlines()[0] if texts else f"主图槽位 {idx}"
        must_codes = sorted(extract_must_render_codes(texts + c["sticky_notes"]))
        main_cards.append(
            {
                "id": f"M{idx:02d}",
                "title": title,
                "source_kind": c["source_kind"],
                "image_token": c.get("token", ""),
                "primary_ref_token": _pick_primary_ref_token(c),
                "rect": {
                    "x": c["x"],
                    "y": c["y"],
                    "w": c["w"],
                    "h": c["h"],
                    "node_id": c["id"],
                    "z_index": c.get("z_index", 0),
                    "style": c.get("style") or {},
                },
                "board_size": f"{round(c['w'])}x{round(c['h'])}",
                "deliverable_spec": "主图 3:4",
                "target_gen_ratio": default_ratio,
                "texts": texts,
                "sticky_notes": c["sticky_notes"],
                "embedded_images": c["embedded_images"],
                "side_reference_images": c.get("side_reference_images", []),
                "must_render_codes": must_codes,
                "semantic_tokens": sorted(extract_semantic_tokens(texts + c["sticky_notes"])),
            }
        )

    detail_screens: list[dict[str, Any]] = []
    for idx, c in enumerate(detail_cards_raw, start=1):
        texts = [t for t in c["texts"] if not _is_signpost_text(t)]
        title = texts[0].splitlines()[0] if texts else f"详情分屏 {idx}"
        all_tokens = ([c["token"]] if c.get("token") else []) + [
            e["token"] for e in c["embedded_images"] if e.get("token")
        ]
        must_codes = sorted(extract_must_render_codes(texts + c["sticky_notes"]))
        detail_screens.append(
            {
                "id": f"S{idx:02d}",
                "title": title,
                "source_kind": c["source_kind"],
                "image_token": c.get("token", ""),
                "primary_ref_token": _pick_primary_ref_token(c),
                "rect": {
                    "x": c["x"],
                    "y": c["y"],
                    "w": c["w"],
                    "h": c["h"],
                    "node_id": c["id"],
                    "z_index": c.get("z_index", 0),
                    "style": c.get("style") or {},
                },
                "all_image_tokens": all_tokens,
                "board_size": f"{round(c['w'])}x{round(c['h'])}",
                "deliverable_spec": f"详情页 790x{round(c['h'] * 790 / c['w'])}" if c["w"] > 0 else "详情页 790xn",
                "target_gen_ratio": default_ratio,
                "texts": texts,
                "sticky_notes": c["sticky_notes"],
                "embedded_images": c["embedded_images"],
                "side_reference_images": c.get("side_reference_images", []),
                "must_render_codes": must_codes,
                "semantic_tokens": sorted(extract_semantic_tokens(texts + c["sticky_notes"])),
                "is_main_shared": False,
                "linked_main_ids": [],
                "match_reasons": [],
                "conflict_notes": [],
                "priority_wave": 2,
            }
        )

    entry_cards: list[dict[str, Any]] = []
    for idx, c in enumerate(entry_cards_raw, start=1):
        texts = [t for t in c.get("texts", []) if not _is_signpost_text(t)]
        title = texts[0].splitlines()[0] if texts else c.get("role_hint", f"入口/SKU图 {idx}")
        entry_cards.append(
            {
                "id": f"E{idx:02d}",
                "title": title,
                "role_hint": c.get("role_hint", "1:1 入口/SKU图"),
                "image_token": c.get("token", ""),
                "primary_ref_token": _pick_primary_ref_token(c),
                "rect": {
                    "x": c["x"],
                    "y": c["y"],
                    "w": c["w"],
                    "h": c["h"],
                    "node_id": c["id"],
                    "z_index": c.get("z_index", 0),
                    "style": c.get("style") or {},
                },
                "board_size": f"{round(c['w'])}x{round(c['h'])}",
                "deliverable_spec": "入口图/SKU 1:1" if 0.88 <= c["ratio"] <= 1.12 else "车图/入口参考",
                "target_gen_ratio": default_ratio,
                "texts": texts,
                "sticky_notes": c.get("sticky_notes", []),
                "embedded_images": c.get("embedded_images", []),
                "side_reference_images": c.get("side_reference_images", []),
                "priority_wave": 3,
            }
        )

    # Cross-deliverable priority matching: 1-to-1 primary theme match (ignoring generic product words & tiny logos)
    scored_matches: dict[str, list[tuple[int, dict[str, Any], list[str]]]] = {}
    for mc in main_cards:
        m_sem = set(mc["semantic_tokens"])
        m_specific = (m_sem - GENERIC_PRODUCT_TOKENS) or m_sem
        m_imgs = ({mc["image_token"]} | {e["token"] for e in mc["embedded_images"] if e.get("token")}) - small_logo_tokens
        m_imgs.discard("")
        m_must = set(mc["must_render_codes"])
        m_all_txt = " ".join(mc["texts"] + mc["sticky_notes"])

        candidates_for_mc: list[tuple[int, dict[str, Any], list[str]]] = []
        for scr in detail_screens:
            if classify_screen_visual_mode(scr, is_main_shared=False).get("visual_mode") == "layout_only":
                continue
            s_sem = set(scr["semantic_tokens"])
            s_specific = (s_sem - GENERIC_PRODUCT_TOKENS) or s_sem
            s_imgs = set(scr["all_image_tokens"]) - small_logo_tokens
            s_must = set(scr["must_render_codes"])
            s_all_txt = " ".join(scr["texts"] + scr["sticky_notes"])

            shared_must = sorted(s_must & m_must)
            shared_imgs = sorted(s_imgs & m_imgs)
            shared_specific = sorted(m_specific & s_specific)

            score = len(shared_must) * 25 + len(shared_imgs) * 20
            score += sum(9 if len(tok) >= 4 else 6 for tok in shared_specific)
            reasons: list[str] = []
            if shared_must:
                reasons.append("共用必渲(" + "、".join(shared_must) + ")")
            if shared_imgs:
                reasons.append(f"共用底图/局部素材({len(shared_imgs)}个)")
            if shared_specific:
                reasons.append("卖点重合: " + "、".join(shared_specific[:6]))

            # Head-card (M01) -> Hero KV (Sxx with 首屏/KV/主KV文案)
            if mc["id"] == "M01" and (
                "首屏" in scr["title"]
                or "kv" in scr["title"].lower()
                or ("100%纯钛" in s_all_txt and ("保温马克杯" in s_all_txt or "0重金属" in s_all_txt))
            ):
                score += 12
                reasons.append("首屏KV与首图同源")

            if score >= 10:
                candidates_for_mc.append((score, scr, reasons))

        candidates_for_mc.sort(key=lambda item: item[0], reverse=True)
        # Keep all screens sharing explicit must-render badges; otherwise pick top 1 primary core screen
        chosen_matches: list[tuple[int, dict[str, Any], list[str]]] = []
        for sc_tuple in candidates_for_mc:
            if any("共用必渲" in r for r in sc_tuple[2]):
                chosen_matches.append(sc_tuple)
        if not chosen_matches and candidates_for_mc:
            chosen_matches = [candidates_for_mc[0]]
        scored_matches[mc["id"]] = chosen_matches

    for mc in main_cards:
        for _, scr, reasons in scored_matches.get(mc["id"], []):
            scr["is_main_shared"] = True
            scr["priority_wave"] = 1
            if mc["id"] not in scr["linked_main_ids"]:
                scr["linked_main_ids"].append(mc["id"])
            scr["match_reasons"].append(f"{mc['id']}({mc['title']}): " + "; ".join(reasons))
            for note in scr["sticky_notes"]:
                scr["conflict_notes"].append(f"详情批注「{note}」需同步核对是否影响 {mc['id']}")
            for note in mc["sticky_notes"]:
                scr["conflict_notes"].append(f"主图 {mc['id']} 批注「{note}」需一并落实到 {scr['id']}")
            scr["conflict_notes"] = list(dict.fromkeys(scr["conflict_notes"]))

    selling_notes = [
        n["text"]
        for n in (stickies + shapes)
        if n.get("text") and (any(k in n["text"] for k in FACT_BLOCK_KEYWORDS) or len(n["text"]) >= 45)
    ]
    positioning_formulas = [
        n["text"]
        for n in shapes
        if n.get("text") and ("我们是一个" in n["text"] or "一锅两用" in n["text"])
    ]
    spec_texts = [
        s["text"]
        for s in shapes
        if s["type"] == "text_shape"
        and s["text"]
        and s["text"] not in NOISE_TEXTS
        and (re.search(r"\d+(?:\.\d+)?\s*(?:mm|cm|g)\b", s["text"], re.I) or "大号" in s["text"] or "中号" in s["text"])
    ]
    must_render_assets = _extract_must_render_items(shapes, stickies)
    all_raw_texts = [s["text"] for s in shapes + stickies if s["text"]]
    fact_conflicts = _detect_fact_conflicts(all_raw_texts)

    if alt_detail_stacks:
        alt_desc = "、".join(f"x≈{a['x']}({a['screen_count']}屏)" for a in alt_detail_stacks)
        fact_conflicts.append(
            f"检测到画布内并排存在多套详情列（已按主列拆解，备选列：{alt_desc}），如需切换请明确指定。"
        )

    return {
        "board_token": board_token,
        "board_kind": "planning",
        "milestone_slots": milestone_slots,
        "detail_screens": detail_screens,
        "main_cards": main_cards,
        "entry_cards": entry_cards,
        "must_render_assets": must_render_assets,
        "alt_detail_stacks": alt_detail_stacks,
        "competitor_reference_count": len(competitor_refs),
        "board_facts": {
            "tables": [t["rows"] for t in tables],
            "selling_notes": list(dict.fromkeys(selling_notes)),
            "spec_texts": list(dict.fromkeys(spec_texts)),
            "positioning_formulas": list(dict.fromkeys(positioning_formulas)),
        },
        "fact_conflicts": fact_conflicts,
        "_parsed_nodes": parsed,
    }


LAYOUT_ONLY_KEYWORDS = (
    "检测报告",
    "质检报告",
    "认证报告",
    "检验报告",
    "权威检测",
    "食卫报告",
    "纯钛报告",
    "抗菌报告",
    "产品参数",
    "规格参数",
    "基本参数",
    "尺寸参数",
    "商品标题仅为搜索关键词",
    "售后保障",
    "温馨提示",
    "使用说明表",
    "销售排行",
    "是指:",
)
VISUAL_ACTION_KEYWORDS = (
    "舀",
    "煎",
    "炒",
    "煮",
    "炖",
    "切",
    "握",
    "洗碗机",
    "灶",
    "汤",
    "蛋",
    "肉",
    "倒置",
    "单手",
    "端杯",
    "冲泡",
)
CONTRAST_PROOF_KEYWORDS = ("对比", "普通", "传统", "升级", "老款", "vs", "VS", "不锈钢", "陶瓷", "木勺", "涂层")
MACRO_PROOF_KEYWORDS = (
    "纯钛",
    "涂层",
    "材质",
    "抛光",
    "打磨",
    "圆润",
    "无毛刺",
    "截面",
    "三层",
    "微孔",
    "拉丝",
    "一体成型",
    "无焊接",
    "无接缝",
)
SCENE_ACTION_KEYWORDS = (
    "一锅",
    "容量",
    "加深",
    "加宽",
    "大底",
    "大肚",
    "装",
    "盛",
    "舀",
    "煎",
    "炒",
    "煮",
    "洗碗机",
    "颠锅",
    "单手",
    "明火",
    "电磁炉",
)
PRESERVED_STATUS_PREFIXES = (
    "已锁定",
    "已定稿",
    "候选已出",
    "提示词就绪",
    "返修中",
    "无需生图",
)


def classify_screen_visual_mode(
    entry: dict[str, Any],
    *,
    is_main_shared: bool = False,
) -> dict[str, str]:
    """Classify a screen into pure_visual or layout_only and translate copy into physical evidence."""
    parts = [str(entry.get("title") or "")]
    parts.extend(str(t) for t in (entry.get("texts") or []))
    parts.extend(str(n) for n in (entry.get("sticky_notes") or []))
    combined = " ".join(parts)

    has_layout_kw = any(kw in combined for kw in LAYOUT_ONLY_KEYWORDS)
    has_action_kw = any(kw in combined for kw in VISUAL_ACTION_KEYWORDS)
    has_contrast_proof_kw = any(
        kw in combined for kw in ("对比", "vs", "VS", "不锈钢", "陶瓷", "木勺")
    )
    if has_layout_kw and not has_action_kw and not has_contrast_proof_kw:
        return {
            "visual_mode": "layout_only",
            "evidence_family": "纯后期排版",
            "visual_plan_hint": "纯后期排版屏（不生图，直接复用白底正侧视图或报告排版）",
            "default_status": "无需生图（后期排版）",
        }

    if any(kw in combined for kw in CONTRAST_PROOF_KEYWORDS):
        hint = "同机位同光物理状态直观对比纯画面，不画生硬分割线与文字，预留顶部或侧边 25% 净底供 PS 压对比标题。"
        if is_main_shared:
            hint = f"{hint} 9:16三段式同源母版，中段55%核心对比兼顾790xn/3:4/1:1。"
        return {
            "visual_mode": "pure_visual",
            "evidence_family": "对比证明",
            "visual_plan_hint": hint,
            "default_status": "待写词",
        }

    if any(kw in combined for kw in MACRO_PROOF_KEYWORDS):
        hint = "光学微距特写（打出真实金属漫反射/宽倒角高光/无焊缝过渡），不画放大镜圆框与指示引线，预留约 30% 低反差干净虚化区供 PS 拉引线排字。"
        if is_main_shared:
            hint = f"{hint} 9:16三段式同源母版，中段55%细节区兼顾790xn/3:4/1:1。"
        return {
            "visual_mode": "pure_visual",
            "evidence_family": "材质与结构微距",
            "visual_plan_hint": hint,
            "default_status": "待写词",
        }

    if any(kw in combined for kw in SCENE_ACTION_KEYWORDS):
        tail = (
            "9:16三段式同源母版：主体与动作稳居画幅中段55%，顶部预留25%干净低反差负空间，一图通吃790xn/3:4/1:1。"
            if is_main_shared
            else "主体聚焦动作瞬态，预留 25%~30% 干净低反差负空间供 PS 排版，全画面禁一切文字与角标。"
        )
        return {
            "visual_mode": "pure_visual",
            "evidence_family": "场景与动作证明",
            "visual_plan_hint": f"用熟悉食物/动作瞬态作物理参照证卖点；{tail}",
            "default_status": "待写词",
        }

    hint = (
        "9:16三段式同源母版：主体稳居画幅中段55%，顶部预留25%~30%平整负空间供 PS 压主图与详情大字，全画面禁一切文字与角标。"
        if is_main_shared
        else "主体聚焦、光影克制，预留 25%~35% 平整负空间供 PS 排版，全画面禁一切文字与角标。"
    )
    return {
        "visual_mode": "pure_visual",
        "evidence_family": "核心利益主视觉",
        "visual_plan_hint": hint,
        "default_status": "待写词",
    }


CAMERA_SHOT_POOLS: dict[str, list[str]] = {
    "材质与结构微距": ["掠射平视·微距特写", "微俯45°·局部近景", "正侧工程·近景特写"],
    "对比证明": ["同机位微俯·双态中景", "正俯90°·并置对比", "平视对等·双态对比"],
    "场景与动作证明": ["微俯3/4·中景瞬态", "生活视角·近景交互", "正俯桌面·满载中景"],
    "核心利益主视觉": ["标准中长焦·主视觉中景", "低机位平视·主体特写", "微俯3/4·空间中全景"],
    "纯后期排版": ["—"],
}


def assign_alternating_camera_shots(screens: list[dict[str, Any]]) -> None:
    """Assign camera shot & framing scale per screen so consecutive screens alternate cleanly."""
    prev_shot: str | None = None
    family_cursors: dict[str, int] = {}

    for item in screens:
        if item.get("visual_mode") == "layout_only" or item.get("evidence_family") == "纯后期排版":
            item["camera_shot"] = "—"
            continue

        family = item.get("evidence_family") or "核心利益主视觉"
        pool = CAMERA_SHOT_POOLS.get(family) or CAMERA_SHOT_POOLS["核心利益主视觉"]
        start_idx = family_cursors.get(family, 0)

        chosen = pool[start_idx % len(pool)]
        picked_offset = 0
        for offset in range(len(pool)):
            cand = pool[(start_idx + offset) % len(pool)]
            if cand != prev_shot:
                chosen = cand
                picked_offset = offset
                break

        family_cursors[family] = (start_idx + picked_offset + 1) % len(pool)
        item["camera_shot"] = chosen
        prev_shot = chosen


def build_manifest(
    *,
    doc_info: dict[str, Any],
    boards: list[dict[str, Any]],
    source_url: str,
    identities_used: list[str],
    default_ratio: str = DEFAULT_GENERATION_RATIO,
    downloaded_assets: dict[str, str] | None = None,
    download_warnings: list[str] | None = None,
    revision_patches: list[dict[str, Any]] | None = None,
    skipped_video_boards: list[dict[str, Any]] | None = None,
    other_doc_boards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Combine document tables/facts with analyzed whiteboards into a unified manifest."""
    downloaded_assets = downloaded_assets or {}
    download_warnings = download_warnings or []
    revision_patches = revision_patches or []
    skipped_video_boards = skipped_video_boards or []
    other_doc_boards = other_doc_boards or []

    milestone_items: list[dict[str, Any]] = []
    detail_screens: list[dict[str, Any]] = []
    main_cards: list[dict[str, Any]] = []
    entry_cards: list[dict[str, Any]] = []
    must_render_assets: list[dict[str, str]] = []
    board_tables: list[list[list[str]]] = []
    selling_notes: list[str] = []
    spec_texts: list[str] = []
    positioning_formulas: list[str] = []
    fact_conflicts: list[str] = []
    competitor_ref_count = 0

    for b in boards:
        milestone_items.extend(b.get("milestone_slots", []))
        detail_screens.extend(b.get("detail_screens", []))
        main_cards.extend(b.get("main_cards", []))
        entry_cards.extend(b.get("entry_cards", []))
        must_render_assets.extend(b.get("must_render_assets", []))
        competitor_ref_count += int(b.get("competitor_reference_count", 0))
        bf = b.get("board_facts", {})
        board_tables.extend(bf.get("tables", []))
        selling_notes.extend(bf.get("selling_notes", []))
        spec_texts.extend(bf.get("spec_texts", []))
        positioning_formulas.extend(bf.get("positioning_formulas", []))
        fact_conflicts.extend(b.get("fact_conflicts", []))

    # Dedupe must_render_assets by code
    dedup_must: dict[str, dict[str, str]] = {}
    for m in must_render_assets:
        code = m.get("code", "")
        if code and (code not in dedup_must or len(m.get("title", "")) > len(dedup_must[code].get("title", ""))):
            dedup_must[code] = m
    must_render_list = list(dedup_must.values())

    if not milestone_items:
        milestone_items = [
            {
                "id": "MS01",
                "slot_name": "产品白底身份卡（结构与材质锁）",
                "status": "待补齐白底参考",
                "target_gen_ratio": default_ratio,
                "reference_images": [],
            },
            {
                "id": "MS02",
                "slot_name": "首屏 KV 视觉定调",
                "status": "待生成定调",
                "target_gen_ratio": default_ratio,
                "reference_images": [],
            },
            {
                "id": "MS03",
                "slot_name": "超级符号 / 核心视觉锤",
                "status": "待生成定调",
                "target_gen_ratio": default_ratio,
                "reference_images": [],
            },
            {
                "id": "MS04",
                "slot_name": "核心使用场景母版",
                "status": "待生成定调",
                "target_gen_ratio": default_ratio,
                "reference_images": [],
            },
        ]

    for group in (detail_screens, main_cards, entry_cards):
        for item in group:
            tok = item.get("image_token")
            if tok and tok in downloaded_assets:
                item["local_asset_path"] = downloaded_assets[tok]
            ptok = item.get("primary_ref_token") or tok or ""
            if ptok and ptok in downloaded_assets:
                item["primary_ref_path"] = downloaded_assets[ptok]
            for emb in item.get("embedded_images", []):
                etok = emb.get("token")
                if etok and etok in downloaded_assets:
                    emb["local_asset_path"] = downloaded_assets[etok]
            side_paths: list[str] = list(item.get("side_ref_paths") or [])
            for sref in item.get("side_reference_images", []):
                stok = sref.get("token")
                if stok and stok in downloaded_assets:
                    sref["local_asset_path"] = downloaded_assets[stok]
                    if downloaded_assets[stok] not in side_paths:
                        side_paths.append(downloaded_assets[stok])
            if side_paths:
                item["side_ref_paths"] = side_paths
    for ms in milestone_items:
        for ref in ms.get("reference_images", []):
            rtok = ref.get("token")
            if rtok and rtok in downloaded_assets:
                ref["local_asset_path"] = downloaded_assets[rtok]
                if not ms.get("primary_ref_path"):
                    ms["primary_ref_path"] = downloaded_assets[rtok]

    for item in detail_screens:
        item.update(classify_screen_visual_mode(item, is_main_shared=(item.get("priority_wave") == 1)))
    assign_alternating_camera_shots(detail_screens)

    wave1_shared = [s for s in detail_screens if s.get("priority_wave") == 1]
    wave2_rest = [s for s in detail_screens if s.get("priority_wave") != 1]

    for item in entry_cards:
        item.update(classify_screen_visual_mode(item, is_main_shared=False))

    for mc in main_cards:
        mc["linked_detail_ids"] = [s["id"] for s in wave1_shared if mc["id"] in s.get("linked_main_ids", [])]

    layout_only_count = sum(
        1 for item in (wave1_shared + wave2_rest + entry_cards) if item.get("visual_mode") == "layout_only"
    )

    linked_main_ids = {mid for s in wave1_shared for mid in s.get("linked_main_ids", [])}
    unmatched_main_cards = [m for m in main_cards if m["id"] not in linked_main_ids]

    pending = list(dict.fromkeys(fact_conflicts)) + download_warnings
    for rp in revision_patches:
        summary_txt = " / ".join(rp.get("texts", [])[:5]) or f"{rp.get('image_count', 0)} 张参考图"
        pending.insert(0, f"文档内含最新修改补丁画布「{rp.get('heading')}」({rp.get('board_token')}): {summary_txt}")
    if other_doc_boards:
        names = "、".join(f"{b.get('heading') or '策划画布'}({b['token']})" for b in other_doc_boards)
        pending.append(f"文档内还有其他同级/备用画布未混入当前清单：{names}（需要全部拆解可加 --all-doc-boards）。")

    return {
        "schemaVersion": 2,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sourceUrl": source_url,
        "title": doc_info.get("title") or "未命名飞书画布任务",
        "identitiesUsed": identities_used,
        "defaultGenRatio": default_ratio,
        "deliverableSpecs": {
            "main": "3:4（含画布 750主图，从 9:16 核心画面优先规划与复用）",
            "detail": "790 x n（按 9:16 竖版纯无字底图生成）",
            "entry": "1:1（含 800主图 / 车图 / SKU，能复用则裁切，无法复用排最后独立生成）",
        },
        "productFacts": {
            "links": doc_info.get("links", []),
            "docTables": doc_info.get("tables", []),
            "boardTables": board_tables,
            "positioningFormulas": list(dict.fromkeys(positioning_formulas)),
            "sellingNotes": list(dict.fromkeys(selling_notes)),
            "specTexts": list(dict.fromkeys(spec_texts)),
        },
        "mustRenderAssets": must_render_list,
        "revisionPatches": revision_patches,
        "skippedVideoBoards": skipped_video_boards,
        "otherDocBoards": other_doc_boards,
        "summaryCounts": {
            "milestoneSlots": len(milestone_items),
            "mainCards3x4": len(main_cards),
            "detailScreensTotal": len(detail_screens),
            "wave1MainSharedDetailScreens": len(wave1_shared),
            "wave2DetailOnlyScreens": len(wave2_rest),
            "wave3EntrySkuCards": len(entry_cards),
            "layoutOnlyScreens": layout_only_count,
            "mustRenderCount": len(must_render_list),
            "revisionPatches": len(revision_patches),
            "unmatchedMainCards": len(unmatched_main_cards),
            "filteredCompetitorRefs": competitor_ref_count,
            "downloadedAssets": len(downloaded_assets),
        },
        "waves": {
            "wave0_milestone": milestone_items,
            "wave1_detail_main_shared": wave1_shared,
            "wave2_detail_rest": wave2_rest,
            "wave3_entry_sku": entry_cards,
            "detailScreensOrdered": detail_screens,
        },
        "mainCards3x4": main_cards,
        "unmatchedMainCards": unmatched_main_cards,
        "zoneOverviews": [ov for b in boards for ov in b.get("zone_overviews", [])],
        "pendingConfirmations": pending,
    }


def _md_cell(value: str) -> str:
    return " / ".join(line.strip() for line in (value or "").splitlines() if line.strip()).replace("|", "｜")


def render_checklist_markdown(manifest: dict[str, Any]) -> str:
    """Render concise Chinese operational checklist without any tier jargon."""
    lines: list[str] = []
    title = manifest.get("title", "飞书画布拆解清单")
    counts = manifest.get("summaryCounts", {})
    ratio = manifest.get("defaultGenRatio", DEFAULT_GENERATION_RATIO)
    waves = manifest.get("waves", {})
    facts = manifest.get("productFacts", {})
    patches = manifest.get("revisionPatches", [])
    must_renders = manifest.get("mustRenderAssets", [])

    lines.append(f"# {title} — 画布自动拆解清单")
    lines.append("")
    lines.append(f"- 来源链接：{manifest.get('sourceUrl', '')}")
    for lk in facts.get("links", [])[:3]:
        lines.append(f"- 商品参考链接：[{lk.get('text', '商品链接')}]({lk.get('href', '')})")
    lines.append(f"- 默认生图画幅：**{ratio} 竖版**（详情页 790xn 直用，可同步裁切/延展给 3:4 主图与 1:1 入口图）")
    lines.append(
        f"- 清单统计：视觉里程碑 {counts.get('milestoneSlots', 0)} 项 ｜ "
        f"第一批（详情页×主图共用优先）{counts.get('wave1MainSharedDetailScreens', 0)} 屏 ｜ "
        f"第二批（详情其余分屏）{counts.get('wave2DetailOnlyScreens', 0)} 屏 ｜ "
        f"第三批（独立 1:1 入口/SKU）{counts.get('wave3EntrySkuCards', 0)} 张 ｜ "
        f"核心必渲特写 {counts.get('mustRenderCount', 0)} 项 ｜ "
        f"已自动过滤纯竞品参考图 {counts.get('filteredCompetitorRefs', 0)} 张"
    )
    lines.append("")

    if patches:
        lines.append("## 最新修改轮补丁（优先对齐）")
        lines.append("")
        for rp in patches:
            summary_txt = " / ".join(rp.get("texts", [])) or f"含 {rp.get('image_count', 0)} 张参考图"
            lines.append(f"- **{rp.get('heading', '修改轮')}**（`{rp.get('board_token', '')}`，含图 {rp.get('image_count', 0)} 张）：{summary_txt}")
        lines.append("")

    lines.append("## 一、产品事实与核心卖点")
    lines.append("")
    for table in facts.get("docTables", []):
        for row in table:
            if len(row) >= 2 and any(k in row[0] for k in ("这是什么", "绰号", "对我有什么用", "有何不同", "何以见得")):
                val = " / ".join(line.strip() for line in row[-1].splitlines() if line.strip())
                if val:
                    lines.append(f"- **{row[0]}**：{val}")
    for formula in facts.get("positioningFormulas", []):
        lines.append(f"- **产品定位**：{_md_cell(formula)}")
    for note in facts.get("sellingNotes", []):
        lines.append(f"- **卖点笔记**：{_md_cell(note)[:320]}")
    for spec in facts.get("specTexts", []):
        lines.append(f"- **实测尺寸规格**：{_md_cell(spec)}")
    lines.append("")

    if must_renders:
        lines.append("## 必渲核心特写清单（与主图/详情共用优先定调）")
        lines.append("")
        for mr in must_renders:
            lines.append(f"- **{mr['code']}**：{mr['title']}")
        lines.append("")

    lines.append("## 二、先出：视觉里程碑设定（定调后锁入 design.md，默认 9:16）")
    lines.append("")
    lines.append("| 编号 | 里程碑设定项 | 默认画幅 | 当前状态 | 已有画布参考 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for ms in waves.get("wave0_milestone", []):
        refs = ms.get("reference_images", [])
        ref_str = _md_cell("、".join(r.get("local_asset_path") or r.get("token", "") for r in refs) or "无")
        lines.append(
            f"| {_md_cell(ms['id'])} | {_md_cell(ms['slot_name'])} | {_md_cell(ms.get('target_gen_ratio', ratio))} | {_md_cell(ms['status'])} | {ref_str} |"
        )
    lines.append("")

    lines.append("## 三、第一批优先（主图出现过的核心画面，详情优先规划并默认按 9:16 出图）")
    lines.append("")
    lines.append("| 详情屏 | 关联主图 | 核心卖点与文案 | 画布批注 / 需注意 | 目标画幅 & 交付规格 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in waves.get("wave1_detail_main_shared", []):
        linked = _md_cell("、".join(item.get("linked_main_ids", [])))
        copy_text = _md_cell(" / ".join(item.get("texts", [])))[:120] or _md_cell(item.get("title", ""))
        notes = _md_cell("；".join(item.get("sticky_notes", []) + item.get("conflict_notes", [])) or "无")
        spec = _md_cell(f"{item.get('target_gen_ratio', ratio)} -> {item.get('deliverable_spec', '')}")
        lines.append(
            f"| {_md_cell(item['id'])}（{_md_cell(item['title'])}） | {linked} | {copy_text} | {notes} | {spec} |"
        )
    if not waves.get("wave1_detail_main_shared"):
        lines.append("| — | — | 未检出主图直接重合屏，请人工核对主图清单 | — | — |")
    lines.append("")

    lines.append("## 四、第二批（详情页其余分屏，默认 9:16）")
    lines.append("")
    lines.append("| 详情屏 | 画面主题与文案 | 画布批注 | 目标画幅 & 交付规格 |")
    lines.append("| --- | --- | --- | --- |")
    for item in waves.get("wave2_detail_rest", []):
        copy_text = _md_cell(" / ".join(item.get("texts", [])))[:120] or _md_cell(item.get("title", ""))
        notes = _md_cell("；".join(item.get("sticky_notes", [])) or "无")
        spec = _md_cell(f"{item.get('target_gen_ratio', ratio)} -> {item.get('deliverable_spec', '')}")
        lines.append(
            f"| {_md_cell(item['id'])}（{_md_cell(item['title'])}） | {copy_text} | {notes} | {spec} |"
        )
    lines.append("")

    lines.append("## 五、第三批与主图对照（1:1 入口图 / SKU 与 3:4 主图总览）")
    lines.append("")
    for mc in manifest.get("mainCards3x4", []):
        copy_text = _md_cell(" / ".join(mc.get("texts", [])))[:100] or _md_cell(mc.get("title", ""))
        notes = _md_cell("；".join(mc.get("sticky_notes", [])))
        suffix = f"（批注：{notes}）" if notes else ""
        lines.append(f"- **主图 {mc['id']}**：{copy_text}{suffix}")
    for ec in waves.get("wave3_entry_sku", []):
        copy_text = _md_cell(" / ".join(ec.get("texts", [])))[:100] or _md_cell(ec.get("title", ""))
        lines.append(f"- **入口/SKU {ec['id']}**（{ec.get('deliverable_spec', '1:1')}）：{copy_text}")
    lines.append("")

    pending = manifest.get("pendingConfirmations", [])
    lines.append("## 六、待拍板 / 差异提醒")
    if pending:
        lines.append("")
        for p in pending:
            lines.append(f"- {p}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


PROJECT_SOURCE_LINE_RE = re.compile(r"^-\s*飞书源：(.+?)\s*$", re.MULTILINE)
PROJECT_ROW_ID_RE = re.compile(r"^(MS\d+|S\d+|M\d+|E\d+)(?:\b|（|$)")


def extract_feishu_url_from_project_md(project_md_text: str) -> str:
    """Extract the stored Feishu source URL/spec from project.md header."""
    m = PROJECT_SOURCE_LINE_RE.search(project_md_text or "")
    if not m:
        return ""
    raw = m.group(1).strip()
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("whiteboard:"):
        return raw
    return ""


def _img_cell(rel_path: str | None) -> str:
    if not rel_path:
        return "—"
    clean = str(rel_path).replace("\\", "/").strip()
    if not clean or clean in ("—", "无"):
        return "—"
    if "<img" in clean:
        return clean
    return f'<img src="{clean}" width="110">'


def _imgs_cell(item: dict[str, Any]) -> str:
    row_strip = (item.get("row_strip_path") or "").strip()
    if row_strip:
        clean_rs = row_strip.replace("\\", "/")
        return clean_rs if "<img" in clean_rs else f'<img src="{clean_rs}" width="220">'
    paths: list[str] = []
    snap = item.get("snapshot_path") or ""
    if snap:
        paths.append(snap)
    elif item.get("primary_ref_path"):
        paths.append(item["primary_ref_path"])
    for sp in item.get("side_ref_paths") or []:
        if sp and sp not in paths:
            paths.append(sp)
    if not paths:
        return "—"
    tags: list[str] = []
    for idx, p in enumerate(paths):
        clean = str(p).replace("\\", "/").strip()
        if "<img" in clean:
            tags.append(clean)
        else:
            w = 110 if idx == 0 else 95
            tags.append(f'<img src="{clean}" width="{w}">')
    return " ".join(tags)


def parse_existing_project_statuses(project_md_text: str) -> dict[str, dict[str, str]]:
    """Read confirmed status, asset path, and preview columns from an existing project.md."""
    statuses: dict[str, dict[str, str]] = {}
    current_headers: list[str] = []

    for raw_line in (project_md_text or "").splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            if not line.startswith("|"):
                current_headers = []
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            continue
        if cells[0] in ("编号", "详情屏"):
            current_headers = cells
            continue

        row_id = cells[0].strip("` ")
        m = PROJECT_ROW_ID_RE.match(row_id)
        if not m:
            continue
        norm_id = m.group(1)

        status_idx = -1
        path_idx = -1
        out_idx = -1
        for idx, h in enumerate(current_headers):
            if "状态" in h:
                status_idx = idx
            elif "路径" in h:
                path_idx = idx
            elif "当前出图" in h:
                out_idx = idx

        status_val = cells[status_idx] if 0 <= status_idx < len(cells) else cells[-1]
        path_val = cells[path_idx] if 0 <= path_idx < len(cells) else ""
        out_val = cells[out_idx] if 0 <= out_idx < len(cells) else ""
        statuses[norm_id] = {
            "status": status_val.strip(),
            "asset_path": "" if path_val.strip() in ("", "无", "—") else path_val.strip("` "),
            "current_output": "—" if out_val.strip() in ("", "无", "—") else out_val.strip(),
        }
    return statuses


def _pick_preserved_status(prev_info: dict[str, str] | None, default_status: str) -> str:
    if not prev_info:
        return default_status
    prev = (prev_info.get("status") or "").strip()
    if any(prev.startswith(prefix) for prefix in PRESERVED_STATUS_PREFIXES):
        return prev
    return default_status


def _compact_fact_lines(facts: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for table in facts.get("docTables", []):
        for row in table:
            if len(row) >= 2 and any(k in row[0] for k in ("这是什么", "绰号", "对我有什么用", "有何不同", "何以见得")):
                val = _md_cell(row[-1])[:160]
                if val:
                    out.append(f"- **{row[0]}**：{val}")
    for formula in facts.get("positioningFormulas", [])[:3]:
        out.append(f"- **产品定位**：{_md_cell(formula)[:180]}")
    for note in facts.get("sellingNotes", [])[:5]:
        out.append(f"- **卖点要点**：{_md_cell(note)[:180]}")
    for spec in facts.get("specTexts", [])[:4]:
        out.append(f"- **实测规格**：{_md_cell(spec)[:140]}")
    return out


def render_project_markdown(
    manifest: dict[str, Any],
    existing_statuses: dict[str, dict[str, str]] | None = None,
) -> str:
    """Render concise 5-section image-embedded project.md (zero tier jargon, strict ref isolation)."""
    existing_statuses = existing_statuses or {}
    lines: list[str] = []
    title = manifest.get("title", "未命名项目")
    counts = manifest.get("summaryCounts", {})
    ratio = manifest.get("defaultGenRatio", DEFAULT_GENERATION_RATIO)
    waves = manifest.get("waves", {})
    facts = manifest.get("productFacts", {})
    patches = manifest.get("revisionPatches", [])
    must_renders = manifest.get("mustRenderAssets", [])

    lines.append(f"# {title} — 项目总账本")
    lines.append("")
    lines.append(f"- 飞书源：{manifest.get('sourceUrl', '未绑定')}")
    for lk in facts.get("links", [])[:2]:
        lines.append(f"- 商品参考链接：[{lk.get('text', '商品链接')}]({lk.get('href', '')})")
    lines.append(f"- 默认生图画幅：**{ratio} 竖版**（纯无字底图，人工后期 PS 排版）")
    lines.append("- 参考图隔离铁律：表中「画布原参考」仅作写词前视觉读图参考，严禁作为生图 API 垫图（`@图N` 仅用 `设定集/白底图/` 与 `设定集/里程碑/`）")
    lines.append(
        f"- 批次统计：第 0 批里程碑 {counts.get('milestoneSlots', 0)} 项 ｜ "
        f"3:4 主图 {counts.get('mainCards3x4', 0)} 张 ｜ "
        f"详情共计 {counts.get('detailScreensTotal', 0)} 屏（第 1 批主图共用 {counts.get('wave1MainSharedDetailScreens', 0)} 屏，含纯后期排版 {counts.get('layoutOnlyScreens', 0)} 屏） ｜ "
        f"第 3 批独立 1:1 入口/SKU {counts.get('wave3EntrySkuCards', 0)} 张 ｜ "
        f"已吸收/过滤参考图 {counts.get('filteredCompetitorRefs', 0)} 张"
    )
    lines.append("")

    if patches:
        lines.append("## 最新修改轮补丁（最优先对齐）")
        lines.append("")
        for rp in patches:
            summary_txt = _md_cell(" / ".join(rp.get("texts", [])))[:200] or f"含 {rp.get('image_count', 0)} 张参考图"
            lines.append(f"- **{rp.get('heading', '修改轮')}**（`{rp.get('board_token', '')}`，含图 {rp.get('image_count', 0)} 张）：{summary_txt}")
        lines.append("")

    lines.append("## 一、核心策划分析（卖点提纯与唯一规格真源）")
    lines.append("")
    fact_lines = _compact_fact_lines(facts)
    if fact_lines:
        lines.extend(fact_lines)
    else:
        lines.append("- 待补充核心卖点与实测规格。")
    if must_renders:
        lines.append("- **必渲核心特写**：" + "；".join(f"{m['code']}（{_md_cell(m['title'])[:40]}）" for m in must_renders[:10]))
    lines.append("")

    lines.append("## 二、第 0 批：视觉里程碑设定（定调后锁入 design.md）")
    lines.append("")
    lines.append("| 编号 | 里程碑项 | 画幅 | 状态 | 定稿/参考路径 | 定调重点 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for ms in waves.get("wave0_milestone", []):
        ms_id = ms["id"]
        prev = existing_statuses.get(ms_id)
        refs = ms.get("reference_images", [])
        ref_str = _md_cell("、".join(r.get("local_asset_path") or r.get("token", "") for r in refs))
        asset_path = (prev or {}).get("asset_path") or ref_str or "无"
        status = _pick_preserved_status(prev, ms.get("status", "待生成定调"))
        slot_name = _md_cell(ms.get("slot_name", ms_id))
        focus = "锁产品真实结构、固有色与材质光学反射" if ms_id == "MS01" else "定光影、背景基调、负空间比例与纯无字画面"
        lines.append(f"| {ms_id} | {slot_name} | {ms.get('target_gen_ratio', ratio)} | {status} | {asset_path} | {focus} |")
    lines.append("")

    zone_overviews = manifest.get("zoneOverviews") or []
    main_ovs = [o for o in zone_overviews if "主图区总览" in o]
    detail_ovs = [o for o in zone_overviews if "详情区总览" in o]
    entry_ovs = [o for o in zone_overviews if "入口区总览" in o]

    lines.append("## 三、3:4 主图转化序列（门面点击逻辑与同源裁切对照）")
    lines.append("")
    if main_ovs:
        links_md = " · ".join(f"[{Path(o).name}]({o})" for o in main_ovs)
        lines.append(f"> 主图区完整排布还原总览：{links_md}（含侧边参考 Row 可另看 `<编号>_整行.png`）")
        lines.append("")
    lines.append("| 编号 | 画布原图与参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字画面与来源方式 | 当前出图 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for mc in manifest.get("mainCards3x4", []):
        mid = mc["id"]
        prev = existing_statuses.get(mid)
        ref_img = _imgs_cell(mc)
        copy_txt = _md_cell(" / ".join(mc.get("texts", [])))[:110] or _md_cell(mc.get("title", mid))
        notes = _md_cell("；".join(mc.get("sticky_notes", [])))[:60]
        copy_col = f"{copy_txt}（批注：{notes}）" if notes else copy_txt
        linked_det = mc.get("linked_detail_ids") or [
            s["id"] for s in waves.get("wave1_detail_main_shared", []) if mid in s.get("linked_main_ids", [])
        ]
        source_mode = f"★由第1批 9:16 母片裁切派生（关联 {'、'.join(linked_det)}）" if linked_det else "独立 3:4 无字底图（预留上方净底压主副标题）"
        default_st = "待派生" if linked_det else "待写词"
        out_img = (prev or {}).get("current_output") or "—"
        status = _pick_preserved_status(prev, default_st)
        lines.append(f"| {mid} | {ref_img} | {copy_col} | {source_mode} | {out_img} | {status} |")
    if not manifest.get("mainCards3x4"):
        lines.append("| — | — | 暂无 3:4 主图卡片 | — | — | — |")
    lines.append("")

    lines.append("## 四、详情页纵向叙事全表（第 1 批（最优先）★主图同源屏 + 第 2 批其余分屏，按阅读顺序顺排）")
    lines.append("")
    if detail_ovs:
        links_md = " · ".join(f"[第{i}段]({o})" for i, o in enumerate(detail_ovs, start=1)) if len(detail_ovs) > 1 else f"[{Path(detail_ovs[0]).name}]({detail_ovs[0]})"
        lines.append(f"> 详情区完整排布还原总览：{links_md}（跨切片无缝画面已自动重定位分界线）")
        lines.append("")
    lines.append("| 编号 | 批次与关联 | 画布原图与参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字底图拍法 & PS留白 | 机位景别 | 当前出图 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    detail_ordered = waves.get("detailScreensOrdered")
    if not detail_ordered:
        combined_det = [*waves.get("wave1_detail_main_shared", []), *waves.get("wave2_detail_rest", [])]
        detail_ordered = sorted(
            combined_det,
            key=lambda x: (int(m.group(1)) if (m := re.search(r"(\d+)", str(x.get("id", "")))) else 9999),
        )
    for item in detail_ordered:
        sid = item["id"]
        prev = existing_statuses.get(sid)
        is_w1 = item.get("priority_wave") == 1
        cls_info = classify_screen_visual_mode(item, is_main_shared=is_w1) if "visual_mode" not in item else item
        is_layout = cls_info.get("visual_mode") == "layout_only"
        linked = _md_cell("、".join(item.get("linked_main_ids", [])))
        if is_layout:
            batch_col = "后期排版"
        elif is_w1:
            batch_col = f"**★第1批**（同源 {linked}）" if linked else "**★第1批**"
        else:
            batch_col = "第2批"

        ref_img = _imgs_cell(item)
        title_txt = _md_cell(item.get("title", sid))[:36]
        copy_txt = _md_cell(" / ".join(item.get("texts", [])))[:95]
        notes_list = list(item.get("sticky_notes", []))
        copy_col = copy_txt or f"**{title_txt}**"
        if notes_list:
            copy_col = f"{copy_col}（批注：{_md_cell('；'.join(notes_list))[:60]}）"

        conflicts = list(item.get("conflict_notes", []))
        conflict_str = f"（对齐：{_md_cell('；'.join(conflicts))[:70]}）" if conflicts else ""
        hint = _md_cell(cls_info.get("visual_plan_hint", "")) + conflict_str
        fam = _md_cell(cls_info.get("evidence_family", "核心利益主视觉"))
        shot = _md_cell(item.get("camera_shot") or CAMERA_SHOT_POOLS.get(fam, ["微俯3/4·中景瞬态"])[0])
        out_img = (prev or {}).get("current_output") or "—"
        status = _pick_preserved_status(prev, cls_info.get("default_status", "待写词"))
        lines.append(f"| {sid} | {batch_col} | {ref_img} | {copy_col} | {hint} | {shot} | {out_img} | {status} |")
    if not detail_ordered:
        lines.append("| — | — | — | 未检出详情分屏 | — | — | — | — |")
    lines.append("")

    lines.append("## 五、第 3 批：独立 1:1 入口车图与 SKU 底图")
    lines.append("")
    if entry_ovs:
        links_md = " · ".join(f"[{Path(o).name}]({o})" for o in entry_ovs)
        lines.append(f"> 入口区完整排布还原总览：{links_md}")
        lines.append("")
    lines.append("| 编号 | 画布原图与参考 | 交付规格 & 运营原主副标题/批注 | 纯无字底图拍法 & 来源方式 | 当前出图 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for ec in waves.get("wave3_entry_sku", []):
        eid = ec["id"]
        prev = existing_statuses.get(eid)
        cls_info = classify_screen_visual_mode(ec, is_main_shared=False) if "visual_mode" not in ec else ec
        ref_img = _imgs_cell(ec)
        spec = _md_cell(ec.get("deliverable_spec", "1:1 入口/SKU"))
        copy_txt = _md_cell(" / ".join(ec.get("texts", [])))[:80] or _md_cell(ec.get("title", eid))
        notes = _md_cell("；".join(ec.get("sticky_notes", [])))[:50]
        title_col = f"**{spec}**：{copy_txt}" + (f"（批注：{notes}）" if notes else "")
        hint = _md_cell(cls_info.get("visual_plan_hint", "")) + "；独立无字底图"
        out_img = (prev or {}).get("current_output") or "—"
        status = _pick_preserved_status(prev, cls_info.get("default_status", "待写词"))
        lines.append(f"| {eid} | {ref_img} | {title_col} | {hint} | {out_img} | {status} |")
    if not waves.get("wave3_entry_sku"):
        lines.append("| — | — | 暂无独立 1:1 入口或 SKU 图（可从主图/详情底图派生） | — | — | — |")
    lines.append("")

    pending = manifest.get("pendingConfirmations", [])
    if pending:
        lines.append("## 六、待拍板提醒")
        lines.append("")
        for p in pending:
            lines.append(f"- {p}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _import_board_renderer():
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import render_feishu_board  # noqa: E402

    return render_feishu_board


def _render_card_snapshot_png(
    *,
    card_item: dict[str, Any],
    parsed: dict[str, list[dict[str, Any]]],
    raw_token_files: dict[str, Path],
    dest_path: Path,
) -> Path | None:
    """Delegate single-card snapshot rendering to render_feishu_board (reconstructed crop)."""
    rfb = _import_board_renderer()
    return rfb.render_single_card_crop(
        card_item=card_item,
        parsed=parsed,
        raw_token_files=raw_token_files,
        dest_path=dest_path,
    )


def fetch_and_parse(
    *,
    url: str | None,
    whiteboard_tokens: list[str],
    project_root: Path,
    task_name: str | None = None,
    output_dir: Path | None = None,
    assets_dir: Path | None = None,
    default_ratio: str = DEFAULT_GENERATION_RATIO,
    download_assets: bool = False,
    all_doc_boards: bool = False,
    write_project_md: bool = True,
    sync_existing: bool = False,
    manifest_out: Path | None = None,
    checklist_out: Path | None = None,
) -> tuple[dict[str, Any], Path | None, Path | None, Path | None]:
    project_md_path = project_root / "project.md"
    existing_statuses: dict[str, dict[str, str]] = {}
    if project_md_path.exists():
        prev_md = project_md_path.read_text(encoding="utf-8")
        if sync_existing:
            existing_statuses = parse_existing_project_statuses(prev_md)
        if not url and not whiteboard_tokens:
            extracted_src = extract_feishu_url_from_project_md(prev_md)
            if extracted_src.startswith("whiteboard:"):
                whiteboard_tokens = [t.strip() for t in extracted_src.split(":", 1)[1].split(",") if t.strip()]
            elif extracted_src:
                url = extracted_src
    identities = detect_lark_identities()
    used_identities: set[str] = set()
    doc_info: dict[str, Any] = {
        "title": "",
        "headings": [],
        "tables": [],
        "whiteboards": [],
        "paragraphs": [],
        "links": [],
    }
    target_boards: list[dict[str, Any]] = []
    revision_patches: list[dict[str, Any]] = []
    skipped_video_boards: list[dict[str, Any]] = []
    other_doc_boards: list[dict[str, Any]] = []
    primary_block_token = ""

    if url:
        uinfo = parse_feishu_url(url)
        primary_block_token = uinfo.get("block_token", "")
        rtype = uinfo.get("resource_type", "")
        rtoken = uinfo.get("resource_token", "")

        doc_token = ""
        if rtype == "wiki" and rtoken:
            wresp, wid = call_with_identity_fallback(
                ["wiki", "+node-get", "--node-token", rtoken],
                identities,
            )
            used_identities.add(wid)
            wdata = wresp.get("data") or {}
            doc_info["title"] = wdata.get("title") or ""
            if wdata.get("obj_type") in ("docx", "doc"):
                doc_token = wdata.get("obj_token") or ""
        elif rtype in ("docx", "docs") and rtoken:
            doc_token = rtoken

        if doc_token:
            dresp, did = call_with_identity_fallback(
                ["docs", "+fetch", "--api-version", "v2", "--doc", doc_token],
                identities,
            )
            used_identities.add(did)
            content = ((dresp.get("data") or {}).get("document") or {}).get("content") or ""
            parsed_doc = parse_doc_markup(content)
            if not doc_info["title"]:
                doc_info["title"] = parsed_doc.get("title") or ""
            doc_info["headings"] = parsed_doc.get("headings", [])
            doc_info["tables"] = parsed_doc.get("tables", [])
            doc_info["whiteboards"] = parsed_doc.get("whiteboards", [])
            doc_info["paragraphs"] = parsed_doc.get("paragraphs", [])
            doc_info["links"] = parsed_doc.get("links", [])

    def export_raw(token: str) -> list[dict[str, Any]]:
        raw_resp, wid = call_with_identity_fallback(
            ["whiteboard", "+export", "--whiteboard-token", token, "--output-type", "raw"],
            identities,
        )
        used_identities.add(wid)
        return (raw_resp.get("data") or {}).get("nodes") or []

    # Decide board roles intelligently
    selected_queue: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    seen_wb: set[str] = set()

    if whiteboard_tokens:
        for tok in whiteboard_tokens:
            if tok and tok not in seen_wb:
                seen_wb.add(tok)
                selected_queue.append(({"token": tok, "heading": "手动指定画布", "is_milestone_heading": False}, export_raw(tok)))
    elif primary_block_token:
        matched_doc_wb = next((w for w in doc_info["whiteboards"] if w["token"] == primary_block_token), None)
        meta = matched_doc_wb or {"token": primary_block_token, "heading": "链接主策划画布", "is_milestone_heading": False}
        seen_wb.add(primary_block_token)
        selected_queue.append((meta, export_raw(primary_block_token)))
        for w in doc_info["whiteboards"]:
            if w["token"] in seen_wb:
                continue
            if w.get("is_milestone_heading") or all_doc_boards:
                seen_wb.add(w["token"])
                selected_queue.append((w, export_raw(w["token"])))
    else:
        # Bare wiki/docx URL: classify embedded boards so we never grab a small revision patch as the whole plan
        planning_candidates: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
        for idx, w in enumerate(doc_info["whiteboards"]):
            tok = w["token"]
            if tok in seen_wb:
                continue
            seen_wb.add(tok)
            if w.get("is_video_only") and not all_doc_boards:
                skipped_video_boards.append({"token": tok, "heading": w.get("heading", ""), "context": w.get("context", "")})
                continue
            nodes = export_raw(tok)
            if w.get("is_milestone_heading"):
                selected_queue.append((w, nodes))
            else:
                planning_candidates.append((idx, w, nodes))

        if planning_candidates:
            if all_doc_boards:
                for _, w, nodes in planning_candidates:
                    selected_queue.append((w, nodes))
            else:
                # Base board = prefer main_detail heading, then largest node count
                def board_rank(item: tuple[int, dict[str, Any], list[dict[str, Any]]]) -> tuple[int, int]:
                    _, wmeta, nds = item
                    return (1 if wmeta.get("is_main_detail_heading") else 0, len(nds))

                base_idx, base_w, base_nodes = max(planning_candidates, key=board_rank)
                selected_queue.append((base_w, base_nodes))

                for idx, w, nodes in planning_candidates:
                    if w["token"] == base_w["token"]:
                        continue
                    # Boards appearing above the base board with few nodes or marked 修改/返修/调整 are revision patches
                    if w.get("is_revision_heading") or (idx < base_idx and len(nodes) < 80):
                        revision_patches.append(
                            _extract_revision_patch(
                                nodes,
                                board_token=w["token"],
                                board_heading=w.get("heading", ""),
                                board_context=w.get("context", ""),
                            )
                        )
                    else:
                        other_doc_boards.append(
                            {
                                "token": w["token"],
                                "heading": w.get("heading", ""),
                                "node_count": len(nodes),
                            }
                        )

    if not selected_queue:
        raise FeishuCanvasError("未解析出任何飞书画板 token，请检查链接或传入 --whiteboard-token。")

    parsed_by_board: list[dict[str, list[dict[str, Any]]]] = []
    for wb_meta, raw_nodes in selected_queue:
        analyzed = analyze_whiteboard_nodes(
            raw_nodes,
            board_token=wb_meta["token"],
            board_heading=wb_meta.get("heading", ""),
            is_milestone_heading=bool(wb_meta.get("is_milestone_heading")),
            default_ratio=default_ratio,
        )
        parsed_by_board.append(analyzed.pop("_parsed_nodes", None) or _normalize_nodes(raw_nodes))
        target_boards.append(analyzed)

    resolved_assets_dir = assets_dir or (project_root / "素材" / "飞书画布")

    def _to_rel_posix(p: Path) -> str:
        try:
            return p.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return str(p)

    downloaded_assets: dict[str, str] = {}
    download_warnings: list[str] = []
    if download_assets:
        resolved_assets_dir.mkdir(parents=True, exist_ok=True)
        # Clear previously auto-generated board snapshots/overviews/refs so stale files never linger
        for old_f in resolved_assets_dir.iterdir():
            if old_f.is_file() and re.match(
                r"^(?:(?:MS|M|S|E)\d+_(?:画布原图|整行|参考\d*)|(?:主图区|入口区|详情区)总览(?:_\d+)?)$",
                old_f.stem,
            ):
                old_f.unlink(missing_ok=True)

        # 1. Gather all unique raw image tokens needed for zone reconstruction, side refs, and milestones
        raw_tokens_needed: list[str] = []
        seen_raw: set[str] = set()

        def _add_raw(tok: str) -> None:
            if tok and tok not in seen_raw:
                seen_raw.add(tok)
                raw_tokens_needed.append(tok)

        for b, p_nodes in zip(target_boards, parsed_by_board):
            for ms in b.get("milestone_slots", []):
                for r in ms.get("reference_images", []):
                    _add_raw(r.get("token", ""))
            for card in [*b.get("main_cards", []), *b.get("detail_screens", []), *b.get("entry_cards", [])]:
                _add_raw(card.get("image_token", ""))
                for emb in card.get("embedded_images", []):
                    _add_raw(emb.get("token", ""))
                for sr in card.get("side_reference_images", []):
                    _add_raw(sr.get("token", ""))
                # Catch any image overlapping the card or straddling its borders (badges, bottom strips)
                rect = card.get("rect") or {}
                rx, ry, rw, rh = float(rect.get("x") or 0), float(rect.get("y") or 0), float(rect.get("w") or 0), float(rect.get("h") or 0)
                if rw > 0 and rh > 0:
                    for im in p_nodes.get("images", []):
                        if (
                            overlap_1d(rx - 80, rx + rw + 80, im["x"], im["x"] + im["w"]) > 0
                            and overlap_1d(ry - 80, ry + rh + 80, im["y"], im["y"] + im["h"]) > 0
                        ):
                            _add_raw(im.get("token", ""))

        raw_tmp_dir = resolved_assets_dir / "_tmp"
        raw_token_files: dict[str, Path] = {}
        blocked_dl: set[str] = set()
        try:
            for tok in raw_tokens_needed:
                saved_path, warn = download_whiteboard_media(
                    tok,
                    raw_tmp_dir,
                    tok,
                    identities,
                    blocked_download_identities=blocked_dl,
                )
                if saved_path and Path(saved_path).is_file():
                    raw_token_files[tok] = Path(saved_path)
                elif warn:
                    download_warnings.append(warn)

            # 2. Export milestone reference images cleanly
            for b in target_boards:
                for ms in b.get("milestone_slots", []):
                    for idx_r, r in enumerate(ms.get("reference_images", []), start=1):
                        tok = r.get("token", "")
                        src_p = raw_token_files.get(tok)
                        if src_p and src_p.is_file():
                            stem = f"{ms['id']}_参考" if idx_r == 1 else f"{ms['id']}_参考{idx_r}"
                            dst_p = resolved_assets_dir / f"{stem}{src_p.suffix or '.png'}"
                            shutil.copy2(src_p, dst_p)
                            downloaded_assets[tok] = _to_rel_posix(dst_p)

            # 3. Reconstruct zones cleanly onto local canvases and crop cards/strips, plus copy full-res refs
            rfb = _import_board_renderer()
            for b, p_nodes in zip(target_boards, parsed_by_board):
                zone_out = rfb.reconstruct_and_crop_board(
                    analyzed_board=b,
                    parsed=p_nodes,
                    raw_token_files=raw_token_files,
                    dest_dir=resolved_assets_dir,
                    write_row_strips=True,
                    write_overviews=True,
                )
                if zone_out.get("overviews"):
                    b["zone_overviews"] = [_to_rel_posix(Path(p)) for p in zone_out["overviews"]]
                snaps = zone_out.get("snapshots") or {}
                strips = zone_out.get("row_strips") or {}

                for card in [*b.get("main_cards", []), *b.get("detail_screens", []), *b.get("entry_cards", [])]:
                    side_paths: list[str] = []
                    for idx_sr, sr in enumerate(card.get("side_reference_images", []), start=1):
                        tok = sr.get("token", "")
                        src_p = raw_token_files.get(tok)
                        if src_p and src_p.is_file():
                            dst_p = resolved_assets_dir / f"{card['id']}_参考{idx_sr}{src_p.suffix or '.png'}"
                            shutil.copy2(src_p, dst_p)
                            rel = _to_rel_posix(dst_p)
                            side_paths.append(rel)
                            downloaded_assets.setdefault(tok, rel)
                    if side_paths:
                        card["side_ref_paths"] = side_paths

                    cid = card["id"]
                    if cid in strips and Path(strips[cid]).is_file():
                        card["row_strip_path"] = _to_rel_posix(Path(strips[cid]))

                    if cid in snaps and Path(snaps[cid]).is_file():
                        card["snapshot_path"] = _to_rel_posix(Path(snaps[cid]))
                    elif (card.get("primary_ref_token") or card.get("image_token")) in raw_token_files:
                        tok = card.get("primary_ref_token") or card.get("image_token")
                        src_p = raw_token_files[tok]
                        dst_p = resolved_assets_dir / f"{card['id']}_画布原图{src_p.suffix or '.png'}"
                        shutil.copy2(src_p, dst_p)
                        rel = _to_rel_posix(dst_p)
                        card["snapshot_path"] = rel
                        downloaded_assets.setdefault(tok, rel)
        finally:
            shutil.rmtree(raw_tmp_dir, ignore_errors=True)

    manifest = build_manifest(
        doc_info=doc_info,
        boards=target_boards,
        source_url=url or f"whiteboard:{','.join(m['token'] for m, _ in selected_queue)}",
        identities_used=sorted(used_identities),
        default_ratio=default_ratio,
        downloaded_assets=downloaded_assets,
        download_warnings=download_warnings,
        revision_patches=revision_patches,
        skipped_video_boards=skipped_video_boards,
        other_doc_boards=other_doc_boards,
    )

    written_project_md: Path | None = None
    if write_project_md:
        project_root.mkdir(parents=True, exist_ok=True)
        pm_tmp = project_root / "project.md.tmp"
        pm_tmp.write_text(
            render_project_markdown(manifest, existing_statuses=existing_statuses),
            encoding="utf-8",
        )
        os.replace(pm_tmp, project_md_path)
        written_project_md = project_md_path

    if output_dir and not manifest_out and not checklist_out:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_out = output_dir / "canvas-manifest.json"
        checklist_out = output_dir / "拆解清单.md"

    if manifest_out:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_tmp = manifest_out.parent / f"{manifest_out.name}.tmp"
        manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(manifest_tmp, manifest_out)

    if checklist_out:
        checklist_out.parent.mkdir(parents=True, exist_ok=True)
        checklist_out.write_text(render_checklist_markdown(manifest), encoding="utf-8")

    return manifest, written_project_md, manifest_out, checklist_out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拆解飞书文档与画布，直接写入精炼 project.md（零本地 JSON 冗余）。")
    parser.add_argument("--url", help="飞书 wiki / docx / whiteboard 链接")
    parser.add_argument("--whiteboard-token", action="append", default=[], help="直接指定飞书画板 token，可传多个")
    parser.add_argument("--project-root", default=".", help="DUMIK 项目根目录，默认当前工作目录")
    parser.add_argument("--task-name", default=None, help="保留兼容参数（默认不再建 制作/图片/<task-name>）")
    parser.add_argument("--output-dir", default=None, help="显式调试目录（仅用于额外输出清单或临时目录）")
    parser.add_argument("--assets-dir", default=None, help="覆盖下载画布图片存储目录，默认 <project-root>/素材/飞书画布")
    parser.add_argument("--default-ratio", default=DEFAULT_GENERATION_RATIO, help="默认生图比例，默认 9:16")
    parser.add_argument("--download-assets", action="store_true", help="下载画布内有效参考图到本地 素材/飞书画布/")
    parser.add_argument("--all-doc-boards", action="store_true", help="导出文档内全部画布（默认只取主画布与里程碑画布）")
    parser.add_argument("--sync", action="store_true", help="增量同步已有 project.md（保留已锁定/已定稿状态，不冲掉进度）")
    parser.add_argument("--no-project-md", action="store_true", help="仅内存解析或配合 --manifest-out 调试，不写 project.md")
    parser.add_argument("--manifest-out", default=None, help="显式写出 JSON 清单的路径（如系统临时目录）")
    parser.add_argument("--checklist-out", default=None, help="显式写出旧版 拆解清单.md 的路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        manifest, project_md_path, manifest_out, checklist_out = fetch_and_parse(
            url=args.url,
            whiteboard_tokens=args.whiteboard_token,
            project_root=Path(args.project_root).resolve(),
            task_name=args.task_name,
            output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
            assets_dir=Path(args.assets_dir).resolve() if args.assets_dir else None,
            default_ratio=args.default_ratio,
            download_assets=bool(args.download_assets),
            all_doc_boards=bool(args.all_doc_boards),
            write_project_md=not bool(args.no_project_md),
            sync_existing=bool(args.sync),
            manifest_out=Path(args.manifest_out).resolve() if args.manifest_out else None,
            checklist_out=Path(args.checklist_out).resolve() if args.checklist_out else None,
        )
    except FeishuCanvasError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "title": manifest.get("title"),
                "identitiesUsed": manifest.get("identitiesUsed"),
                "defaultGenRatio": manifest.get("defaultGenRatio"),
                "summaryCounts": manifest.get("summaryCounts"),
                "projectMdPath": str(project_md_path) if project_md_path else None,
                "manifestPath": str(manifest_out) if manifest_out else None,
                "checklistPath": str(checklist_out) if checklist_out else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
