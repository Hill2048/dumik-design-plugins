#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK Eagle 本地灵感库检索 + 项目防撞车助手（纯只读）。

通过本机 Eagle HTTP API (http://localhost:41595) 检索当前打开库中的干净真机实拍参考图：
1. 支持按 `--folder`（如 "纯钛杯子"）和 `--query`（如 "晨间餐桌"）筛选。
2. 自动扫描项目根目录的 `design.md` 与 `制作/*/prompt.md`，提取已用过的 Eagle ID 并自动剔除（防道具与构图撞车）。
3. 返回前 `--top N`（默认 3）张未用过的本地图片绝对路径，并在系统 `%TEMP%\\dumik-runs\\` 拼一张 3 格备选预览图供秒选直垫。
4. 若本机未打开 Eagle，优雅返回 `status: "eagle_offline"`，绝不阻塞主流程。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw


EAGLE_API_BASE = "http://localhost:41595/api"
# Eagle item IDs are 13-char uppercase alphanumeric tokens (e.g. MWKGD3MFY8Q3B)
EAGLE_ID_RE = re.compile(r"\b([A-Z0-9]{13})\b")
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}


def _http_get_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def collect_used_eagle_ids(project_root: Path | None) -> set[str]:
    """扫描项目 design.md 与 制作/*/prompt.md 中已引用过的 Eagle ID，防止跨屏重复垫同一张参考图。"""
    used: set[str] = set()
    if not project_root or not project_root.is_dir():
        return used

    scan_files: list[Path] = []
    design_md = project_root / "design.md"
    if design_md.is_file():
        scan_files.append(design_md)
    make_dir = project_root / "制作"
    if make_dir.is_dir():
        scan_files.extend(make_dir.rglob("prompt.md"))

    for f in scan_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in EAGLE_ID_RE.finditer(text):
            token = m.group(1)
            # Filter out pure digits or pure letters that might be hex/words
            if any(c.isdigit() for c in token) and any(c.isalpha() for c in token):
                used.add(token)
    return used


def _find_folder_ids(folders: list[dict[str, Any]], keyword: str) -> list[str]:
    kw = keyword.strip().lower()
    matched: list[str] = []

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            name = str(node.get("name") or "")
            if kw in name.lower():
                fid = str(node.get("id") or "")
                if fid:
                    matched.append(fid)
            children = node.get("children") or []
            if isinstance(children, list):
                _walk(children)

    _walk(folders)
    return matched


def _resolve_item_file(library_path: Path, item: dict[str, Any]) -> Path | None:
    item_id = str(item.get("id") or "")
    name = str(item.get("name") or "")
    ext = str(item.get("ext") or "").lower().lstrip(".")
    if not item_id or ext not in IMAGE_EXTS:
        return None
    info_dir = library_path / "images" / f"{item_id}.info"
    if not info_dir.is_dir():
        return None
    direct = info_dir / f"{name}.{ext}"
    if direct.is_file():
        return direct
    for cand in info_dir.iterdir():
        if cand.is_file() and cand.suffix.lower().lstrip(".") in IMAGE_EXTS and not cand.name.endswith("_thumbnail.png"):
            return cand
    return None


def make_candidate_strip(items: list[dict[str, Any]], out_path: Path) -> Path | None:
    if not items:
        return None
    thumb = 320
    pad = 14
    bar_h = 28
    w = len(items) * thumb + (len(items) + 1) * pad
    h = thumb + bar_h + pad * 2
    canvas = Image.new("RGB", (w, h), (26, 26, 30))
    draw = ImageDraw.Draw(canvas)
    for idx, it in enumerate(items):
        x0 = pad + idx * (thumb + pad)
        y0 = pad
        label = f"[{idx + 1}] {it['id']} {it['name'][:18]}"
        draw.rectangle([x0, y0, x0 + thumb, y0 + bar_h], fill=(45, 48, 56))
        draw.text((x0 + 6, y0 + 7), label, fill=(240, 240, 245))
        with Image.open(it["file_path"]) as im:
            cp = im.convert("RGB")
            cp.thumbnail((thumb, thumb), Image.LANCZOS)
            ix = x0 + (thumb - cp.width) // 2
            iy = y0 + bar_h + (thumb - cp.height) // 2
            canvas.paste(cp, (ix, iy))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, quality=90)
    return out_path


def query_eagle_candidates(
    *,
    folder: str = "",
    query: str = "",
    project_root: Path | None = None,
    top: int = 3,
    api_base: str = EAGLE_API_BASE,
    skip_preview: bool = False,
) -> dict[str, Any]:
    used_ids = collect_used_eagle_ids(project_root)

    try:
        lib_info = _http_get_json(f"{api_base}/library/info")
    except Exception as exc:
        return {
            "status": "eagle_offline",
            "message": f"本机 Eagle 未打开或本地 API 不可达，已跳过自动选图（{exc}）",
            "used_ids_count": len(used_ids),
            "candidates": [],
        }

    data = lib_info.get("data") or {}
    lib_path_raw = data.get("library", {}).get("path") or data.get("path") or ""
    if not lib_path_raw:
        # Fallback: query application/info or library path
        try:
            app_info = _http_get_json(f"{api_base}/library/info")
            lib_path_raw = (app_info.get("data") or {}).get("library", {}).get("path") or ""
        except Exception:
            pass

    params: dict[str, str] = {"limit": "200"}
    if folder:
        fids = _find_folder_ids(data.get("folders") or [], folder)
        if fids:
            params["folders"] = ",".join(fids)
    if query:
        params["keyword"] = query

    url = f"{api_base}/item/list?{urllib.parse.urlencode(params)}"
    try:
        items_resp = _http_get_json(url, timeout=5.0)
    except Exception as exc:
        return {"status": "eagle_error", "message": str(exc), "candidates": []}

    raw_items = items_resp.get("data") or []
    lib_path = Path(lib_path_raw) if lib_path_raw else None

    picked: list[dict[str, Any]] = []
    skipped_used = 0
    for it in raw_items:
        iid = str(it.get("id") or "")
        if not iid:
            continue
        if iid in used_ids:
            skipped_used += 1
            continue
        ext = str(it.get("ext") or "").lower().lstrip(".")
        if ext not in IMAGE_EXTS:
            continue

        file_path: Path | None = None
        if lib_path and lib_path.is_dir():
            file_path = _resolve_item_file(lib_path, it)
        if file_path is None and isinstance(it.get("filePath"), str):
            cand = Path(it["filePath"])
            if cand.is_file():
                file_path = cand

        picked.append(
            {
                "id": iid,
                "name": str(it.get("name") or ""),
                "ext": ext,
                "width": it.get("width"),
                "height": it.get("height"),
                "tags": it.get("tags") or [],
                "file_path": str(file_path) if file_path else "",
            }
        )
        if len(picked) >= top:
            break

    preview_path: str | None = None
    valid_for_preview = [p for p in picked if p["file_path"] and Path(p["file_path"]).is_file()]
    if valid_for_preview and not skip_preview:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_p = Path(tempfile.gettempdir()) / "dumik-runs" / f"参考备选_{stamp}.jpg"
        saved = make_candidate_strip(valid_for_preview, out_p)
        preview_path = str(saved) if saved else None

    return {
        "status": "ok",
        "folder": folder,
        "query": query,
        "skipped_used_count": skipped_used,
        "preview_sheet": preview_path,
        "candidates": picked,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从本机 Eagle 灵感库按场景检索干净真机实拍参考图（自动去重防撞车）")
    ap.add_argument("--folder", default="", help="Eagle 库内文件夹名称关键词（如 纯钛杯子）")
    ap.add_argument("--query", default="", help="场景检索关键词（如 晨间餐桌、办公桌）")
    ap.add_argument("--project-root", default="", help="DUMIK 项目根目录（自动剔除 design.md 与 prompt.md 中已用 ID）")
    ap.add_argument("--top", type=int, default=3, help="返回备选数量（默认 3）")
    ap.add_argument("--no-preview", action="store_true", help="不生成备选拼图预览")
    args = ap.parse_args(argv)

    res = query_eagle_candidates(
        folder=args.folder,
        query=args.query,
        project_root=Path(args.project_root).resolve() if args.project_root else None,
        top=args.top,
        skip_preview=args.no_preview,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
