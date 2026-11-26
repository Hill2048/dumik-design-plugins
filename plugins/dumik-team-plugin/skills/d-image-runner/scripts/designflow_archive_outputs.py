#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archive DesignFlow MCP generated images cleanly into a project work directory.

Replaces repetitive ad-hoc `python -c` snippets that parse tool output logs:
- Accepts one or more JSON files (e.g. saved DesignFlow tool outputs or asset lists)
  or direct local image paths.
- Extracts unique existing image file paths, copies them losslessly into `--out-dir`
  with clean deterministic names (`<prefix>_01.png`, etc.), verifies dimensions via PIL,
  and prints a compact JSON summary (including aspect ratio check against `--expect-ratio`).
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

from PIL import Image, ImageDraw


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PATH_KEYS = {"filePath", "localPath", "path", "outputPath", "imagePath", "file"}


def _collect_paths_from_obj(obj: Any, found: list[Path]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PATH_KEYS and isinstance(v, str):
                p = Path(v)
                if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                    found.append(p)
            else:
                _collect_paths_from_obj(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_paths_from_obj(item, found)
    elif isinstance(obj, str):
        stripped = obj.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                _collect_paths_from_obj(json.loads(stripped), found)
                return
            except Exception:
                pass
        if len(stripped) < 400 and any(stripped.lower().endswith(ext) for ext in IMAGE_EXTS):
            p = Path(stripped)
            if p.is_file():
                found.append(p)


def extract_image_paths(inputs: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if not p.exists():
            continue
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            found.append(p)
            continue
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            try:
                _collect_paths_from_obj(json.loads(text), found)
            except Exception:
                for m in re.finditer(r'([A-Za-z]:[\\/][^"\r\n<>|]+?\.(?:png|jpg|jpeg|webp))', text, re.IGNORECASE):
                    cand = Path(m.group(1).replace("\\\\", "\\"))
                    if cand.is_file():
                        found.append(cand)
    # Deduplicate preserving order
    unique: list[Path] = []
    seen: set[str] = set()
    for p in found:
        key = str(p.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p.resolve())
    return unique


def parse_ratio(ratio_text: str) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)\s*", ratio_text or "")
    if not m:
        return None
    w, h = float(m.group(1)), float(m.group(2))
    return (w / h) if h > 0 else None


def build_pick_contact_sheet(
    records: list[dict[str, Any]],
    out_path: Path,
    cols: int = 3,
    thumb_size: int = 340,
) -> Path | None:
    """生成带编号、尺寸与异常红框警示的选片联系表（默认落 %TEMP%）。"""
    if not records:
        return None
    n = len(records)
    cols = max(1, min(cols, n))
    rows = (n + cols - 1) // cols
    pad = 16
    bar_h = 30
    cell_w = thumb_size
    cell_h = thumb_size + bar_h
    sheet_w = cols * cell_w + (cols + 1) * pad
    sheet_h = rows * cell_h + (rows + 1) * pad

    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)

    for idx, rec in enumerate(records):
        r, c = divmod(idx, cols)
        x0 = pad + c * (cell_w + pad)
        y0 = pad + r * (cell_h + pad)

        warn_flags: list[str] = []
        if not rec.get("ratio_ok", True):
            warn_flags.append("RATIO!")
        if not rec.get("res_ok", True):
            warn_flags.append("LOWRES!")
        is_warn = bool(warn_flags)

        title = f"[{idx + 1}] {Path(rec['saved']).stem}  {rec['width']}x{rec['height']}"
        if warn_flags:
            title += "  [" + "/".join(warn_flags) + "]"
        bar_bg = (165, 32, 32) if is_warn else (42, 44, 52)
        draw.rectangle([x0, y0, x0 + cell_w, y0 + bar_h], fill=bar_bg)
        draw.text((x0 + 8, y0 + 8), title[:48], fill=(255, 255, 255))

        with Image.open(rec["saved"]) as im:
            cp = im.convert("RGB")
            cp.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            ix = x0 + (thumb_size - cp.width) // 2
            iy = y0 + bar_h + (thumb_size - cp.height) // 2
            sheet.paste(cp, (ix, iy))

        if is_warn:
            draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(235, 50, 50), width=4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=90)
    return out_path


def archive_images(
    sources: list[Path],
    out_dir: Path,
    prefix: str = "候选",
    expect_ratio: str = "",
    min_long_edge: int = 1024,
    contact_sheet_path: Path | None = None,
    skip_contact_sheet: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = parse_ratio(expect_ratio)
    results: list[dict[str, Any]] = []
    ratio_warnings: list[str] = []
    res_warnings: list[str] = []

    for idx, src in enumerate(sources, start=1):
        ext = src.suffix.lower() or ".png"
        dst = out_dir / f"{prefix}_{idx:02d}{ext}"
        shutil.copy2(src, dst)
        with Image.open(dst) as img:
            w, h = img.size
        actual_ratio = round(w / h, 4) if h else 0.0
        ratio_ok = True
        if expected is not None and h > 0:
            diff = abs(actual_ratio - expected) / expected
            if diff > 0.12:
                ratio_ok = False
                ratio_warnings.append(f"{dst.name}: {w}x{h} (actual={actual_ratio}, expect={expect_ratio})")
        res_ok = max(w, h) >= min_long_edge if min_long_edge > 0 else True
        if not res_ok:
            res_warnings.append(f"{dst.name}: {w}x{h} (< {min_long_edge}px)")
        results.append(
            {
                "source": str(src),
                "saved": str(dst),
                "width": w,
                "height": h,
                "ratio_ok": ratio_ok,
                "res_ok": res_ok,
            }
        )

    sheet_saved: str | None = None
    if results and not skip_contact_sheet:
        if contact_sheet_path is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            contact_sheet_path = Path(tempfile.gettempdir()) / "dumik-runs" / f"选片联系表_{prefix}_{stamp}.jpg"
        saved_p = build_pick_contact_sheet(results, contact_sheet_path)
        sheet_saved = str(saved_p) if saved_p else None

    return {
        "status": "ok" if results else "empty",
        "count": len(results),
        "out_dir": str(out_dir),
        "contact_sheet": sheet_saved,
        "ratio_warnings": ratio_warnings,
        "res_warnings": res_warnings,
        "files": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive DesignFlow generated images with PIL verification and pick contact sheet.")
    parser.add_argument("--out-dir", required=True, help="Target work directory (e.g. 制作/S01_健康材料对比).")
    parser.add_argument("--prefix", default="候选", help="Filename prefix (default: 候选).")
    parser.add_argument("--expect-ratio", default="", help="Optional expected aspect ratio like 9:16 or 1:1.")
    parser.add_argument("--min-long-edge", type=int, default=1024, help="Minimum long-edge pixel threshold for health check (default: 1024).")
    parser.add_argument("--contact-sheet", default="", help="Optional custom path for the pick contact sheet (default: %%TEMP%%\\dumik-runs\\pick-sheet-*.jpg).")
    parser.add_argument("--no-contact-sheet", action="store_true", help="Disable generating the pick contact sheet.")
    parser.add_argument("inputs", nargs="+", help="Image paths or DesignFlow JSON/output files.")
    args = parser.parse_args(argv)

    sources = extract_image_paths(args.inputs)
    summary = archive_images(
        sources=sources,
        out_dir=Path(args.out_dir),
        prefix=args.prefix,
        expect_ratio=args.expect_ratio,
        min_long_edge=args.min_long_edge,
        contact_sheet_path=Path(args.contact_sheet) if args.contact_sheet else None,
        skip_contact_sheet=args.no_contact_sheet,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
