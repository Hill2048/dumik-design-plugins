#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stateless DUMIK project pipeline coordinator.

Reads root project.md and per-screen 制作/<ID>_*/prompt.md directly:
- Zero JSON queues or run logs inside the project directory.
- Temporary batch JSON is created only in OS %TEMP%/dumik-runs and removed immediately.
- Real files on disk (prompt.md, candidates, 设定集/里程碑/, 成品/) are the single source of truth.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import uuid


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
IMAGE_RUNNER_SCRIPT = PLUGIN_ROOT / "skills" / "d-image-runner" / "scripts" / "generate_batch_images.py"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
ROW_ID_RE = re.compile(r"^(MS\d+|S\d+|M\d+|E\d+)\b")
RATIO_LINE_RE = re.compile(r"比例\s*[:：]\s*([0-9]+:[0-9]+|[0-9]+x[0-9]+|source-[0-9a-z-]+)", re.IGNORECASE)
AT_IMAGE_PATH_RE = re.compile(
    r"`?@图(\d+)`?\s*[:：]\s*(?:`([^`]+)`|\"([^\"]+)\"|'([^']+)'|([^\r\n（(]+?))(?=\s*[（(]|\s*$)",
    re.MULTILINE,
)
TARGET_FILE_RE = re.compile(
    r"(?:^|[-*\s])`?目标图`?\s*[:：]\s*(?:`([^`]+)`|\"([^\"]+)\"|([^\r\n（(]+?))(?=\s*[（(]|\s*$)",
    re.MULTILINE,
)
PERSON_SIGNAL_RE = re.compile(r"(手腕|手指|四指|两指|单手|双手|手掌|手背|拎着|穿握|端握|握把|真丝袖|袖口|小臂|肩背|侧颜|半身|女主|模特)")
PERSON_EXCLUSION_RE = re.compile(r"(无人物|无人·|无人|不出现人物|绝不露脸|不露正脸|严禁露脸)")
CANDIDATE_NUM_RE = re.compile(r"候选[_-](\d+)")
FENCE_RE = re.compile(r"```(?:[^\n`]*)\n(.*?)```", re.DOTALL)


class PipelineError(Exception):
    pass


@dataclass
class ProjectRow:
    id: str
    wave: int
    title: str
    linked_main: list[str]
    source_mode: str
    status: str
    asset_path: str
    line_index: int
    headers: list[str]
    cells: list[str]


def sanitize_slug(text: str, fallback: str = "item") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\s\r\n]+', "-", text).strip("-")
    return cleaned[:32] or fallback


def resolve_output_size(ratio: str, quality: str) -> str:
    clean_ratio = (ratio or "9:16").strip().lower()
    clean_q = (quality or "2k").strip().lower()
    supported = ("9:16", "16:9", "3:4", "4:3", "1:1", "2:3", "3:2")
    if clean_ratio in supported:
        return f"{clean_ratio}-{clean_q}"
    if any(clean_ratio.startswith(f"{r}-") for r in supported):
        return clean_ratio
    if re.fullmatch(r"\d+x\d+", clean_ratio):
        return clean_ratio
    return "9:16-2k"


def _extract_title_from_cells(row_id: str, cells: list[str], headers: list[str]) -> str:
    for idx, h in enumerate(headers):
        if (
            any(k in h for k in ("里程碑项", "画面主题", "核心卖点意图", "画面意图", "运营原主副标题", "交付规格"))
            and idx < len(cells)
        ):
            raw = cells[idx]
            bold_m = re.search(r"\*\*([^*]+)\*\*", raw)
            if bold_m:
                candidate = bold_m.group(1).strip()
                if not candidate.startswith(("入口图/SKU", "车图/入口")):
                    return candidate
            clean = re.split(r"[:：/（(]", raw, 1)[0].strip("* ")
            if clean and clean not in ("—", "无"):
                return clean
    return row_id


def parse_project_md(project_md_path: Path) -> tuple[list[str], list[ProjectRow]]:
    if not project_md_path.is_file():
        raise PipelineError(f"找不到项目总账本：{project_md_path}（请先运行 d-init 初始化）。")
    lines = project_md_path.read_text(encoding="utf-8").splitlines()
    rows: list[ProjectRow] = []
    current_wave = 2
    current_headers: list[str] = []

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            if "第 0 批" in stripped or "里程碑" in stripped:
                current_wave = 0
            elif "3:4 主图" in stripped or "第 3 批" in stripped or "主图派生对照" in stripped:
                current_wave = 3
            elif "详情页纵向叙事全表" in stripped or "第 2 批" in stripped:
                current_wave = 2
            elif "第 1 批" in stripped:
                current_wave = 1
            current_headers = []
            continue

        if not (stripped.startswith("|") and stripped.endswith("|")):
            if not stripped.startswith("|"):
                current_headers = []
            continue

        cells = [c.strip() for c in stripped[1:-1].split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
            continue
        if cells[0] in ("编号", "详情屏"):
            current_headers = cells
            continue

        m = ROW_ID_RE.match(cells[0].strip("` "))
        if not m:
            continue
        row_id = m.group(1)

        status_idx = -1
        path_idx = -1
        linked_idx = -1
        batch_idx = -1
        mode_idx = -1
        for c_idx, h in enumerate(current_headers):
            if "状态" in h:
                status_idx = c_idx
            elif "路径" in h:
                path_idx = c_idx
            elif "关联主图" in h:
                linked_idx = c_idx
            elif "批次与关联" in h:
                batch_idx = c_idx
            elif "来源方式" in h:
                mode_idx = c_idx

        batch_val = cells[batch_idx] if 0 <= batch_idx < len(cells) else ""
        wave = current_wave
        if row_id.startswith("MS"):
            wave = 0
        elif row_id.startswith(("M", "E")):
            wave = 3
        elif "第1批" in batch_val or "第 1 批" in batch_val:
            wave = 1
        elif "第2批" in batch_val or "第 2 批" in batch_val or "后期排版" in batch_val:
            wave = 2

        status_val = cells[status_idx] if 0 <= status_idx < len(cells) else cells[-1]
        path_val = cells[path_idx] if 0 <= path_idx < len(cells) else ""
        linked_raw = cells[linked_idx] if 0 <= linked_idx < len(cells) else ""
        source_mode = cells[mode_idx] if 0 <= mode_idx < len(cells) else ""
        linked_main = re.findall(r"\bM\d+\b", batch_val or linked_raw)
        if not linked_main and source_mode:
            linked_main = re.findall(r"\bS\d+\b", source_mode)

        rows.append(
            ProjectRow(
                id=row_id,
                wave=wave,
                title=_extract_title_from_cells(row_id, cells, current_headers),
                linked_main=linked_main,
                source_mode=source_mode,
                status=status_val,
                asset_path="" if path_val in ("", "无", "—") else path_val.strip("` "),
                line_index=idx,
                headers=list(current_headers),
                cells=cells,
            )
        )
    return lines, rows


def _find_matching_work_dir(project_root: Path, row_id: str) -> Path | None:
    make_dir = project_root / "制作"
    if not make_dir.is_dir():
        return None
    exact_pattern = re.compile(rf"^{re.escape(row_id)}(?:$|_)")
    exact_matches = [p for p in sorted(make_dir.iterdir()) if p.is_dir() and exact_pattern.match(p.name)]
    if exact_matches:
        return exact_matches[0]
    sub_pattern = re.compile(rf"^{re.escape(row_id)}-")
    sub_matches = [p for p in sorted(make_dir.iterdir()) if p.is_dir() and sub_pattern.match(p.name)]
    return sub_matches[0] if sub_matches else None


def _find_matching_image(directory: Path, row_id: str, *, recursive: bool = False) -> Path | None:
    if not directory.is_dir():
        return None
    pattern = re.compile(rf"^{re.escape(row_id)}(?:$|[_.-])")
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    hits = [
        p
        for p in sorted(iterator)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and pattern.match(p.stem)
    ]
    return hits[0] if hits else None


HELPER_IMAGE_MARKERS = ("_已修复", "_预览", "_对比", "_遮罩", "_白底参考")


def _list_candidate_images(work_dir: Path | None) -> list[Path]:
    if not work_dir or not work_dir.is_dir():
        return []
    return [
        p
        for p in sorted(work_dir.iterdir())
        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTS
        and not any(m in p.stem for m in HELPER_IMAGE_MARKERS)
    ]


def sync_project_status(project_root: Path) -> dict[str, Any]:
    """Recalibrate project.md statuses and output preview thumbnails solely from real files on disk."""
    project_root = project_root.resolve()
    project_md_path = project_root / "project.md"
    lines, rows = parse_project_md(project_md_path)

    milestone_dir = project_root / "设定集" / "里程碑"
    final_dir = project_root / "成品"
    summary_counts: dict[str, int] = {}
    updated_rows = 0

    for row in rows:
        new_status = row.status
        new_path = row.asset_path

        ms_file = _find_matching_image(milestone_dir, row.id) if row.id.startswith("MS") else None
        final_file = _find_matching_image(final_dir, row.id, recursive=True) if not row.id.startswith("MS") else None
        work_dir = _find_matching_work_dir(project_root, row.id)
        has_prompt = bool(work_dir and (work_dir / "prompt.md").is_file())
        cand_images = _list_candidate_images(work_dir)
        cand_count = len(cand_images)

        explicit_file_ok = bool(new_path and (project_root / new_path).is_file())

        if ms_file:
            new_status = "已锁定"
            new_path = ms_file.relative_to(project_root).as_posix()
        elif row.id.startswith("MS") and row.status.startswith("已锁定") and explicit_file_ok:
            new_status = "已锁定"
        elif final_file:
            new_status = "已定稿"
        elif row.status.startswith("无需生图"):
            new_status = row.status
        elif cand_count > 0:
            new_status = f"候选已出({cand_count}张)"
        elif has_prompt:
            new_status = "提示词就绪"
        else:
            if row.status.startswith(("候选已出", "提示词就绪", "已定稿")):
                if row.id.startswith("MS"):
                    new_status = "待生成定调"
                elif "裁切派生" in row.source_mode:
                    new_status = "待派生"
                else:
                    new_status = "待写词"

        preview_img = final_file or (cand_images[-1] if cand_images else None)
        new_out = f'<img src="{preview_img.relative_to(project_root).as_posix()}" width="110">' if preview_img else "—"

        status_idx = -1
        path_idx = -1
        out_idx = -1
        for c_idx, h in enumerate(row.headers):
            if "状态" in h:
                status_idx = c_idx
            elif "路径" in h:
                path_idx = c_idx
            elif "当前出图" in h:
                out_idx = c_idx

        changed = False
        cells = list(row.cells)
        if 0 <= status_idx < len(cells) and cells[status_idx] != new_status:
            cells[status_idx] = new_status
            changed = True
        if 0 <= path_idx < len(cells) and new_path and cells[path_idx] != new_path:
            cells[path_idx] = new_path
            changed = True
        if 0 <= out_idx < len(cells) and cells[out_idx] != new_out:
            cells[out_idx] = new_out
            changed = True
        if changed:
            lines[row.line_index] = "| " + " | ".join(cells) + " |"
            updated_rows += 1

        summary_counts[new_status] = summary_counts.get(new_status, 0) + 1

    if updated_rows > 0:
        tmp = project_root / "project.md.tmp"
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, project_md_path)

    broken_asset_paths = audit_assets_md(project_root)

    return {
        "ok": True,
        "projectRoot": str(project_root),
        "updatedRows": updated_rows,
        "totalRows": len(rows),
        "statusBreakdown": summary_counts,
        "brokenAssetPaths": broken_asset_paths,
    }


def audit_assets_md(project_root: Path) -> list[str]:
    """Return missing relative/absolute image paths referenced in assets.md (ignores placeholders & deprecated notes)."""
    assets_md = project_root / "assets.md"
    if not assets_md.is_file():
        return []
    text = assets_md.read_text(encoding="utf-8", errors="ignore")
    broken: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if any(k in line for k in ("待填", "待按需", "已废弃", "已替代", "仅备用")):
            continue
        for raw in re.findall(r"`([^`\r\n]+\.(?:png|jpg|jpeg|webp|psd))`", line, re.I):
            ref = raw.strip()
            if not ref or ref in seen or "*" in ref or "<" in ref or ref.startswith("_"):
                continue
            if not (re.match(r"^[a-zA-Z]:[\\/]", ref) or "/" in ref or "\\" in ref):
                continue
            seen.add(ref)
            cand = Path(ref) if re.match(r"^[a-zA-Z]:[\\/]", ref) else (project_root / ref)
            if not cand.exists():
                broken.append(ref)
    return broken


def _validate_api_ref_path(resolved_path: str, project_root: Path) -> None:
    if resolved_path.startswith(("http://", "https://", "data:image/")):
        return
    p = Path(resolved_path)
    try:
        rel_posix = p.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel_posix = p.as_posix()
    if rel_posix.startswith("素材/飞书画布/") and not any(k in p.stem for k in ("草图", "线稿")):
        raise PipelineError(
            f"严禁将「素材/飞书画布/」中的画布参考截图（{rel_posix}）直接作为生图 API 垫图（@图N）！"
            "请仅喂入「设定集/白底图/」或「设定集/里程碑/」中的自有干净基准图。"
        )


def _resolve_project_file(raw_path: str, project_root: Path) -> str:
    clean = raw_path.strip("`'\"")
    if clean.startswith(("http://", "https://", "data:image/")):
        return clean
    candidate = Path(clean)
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve()
    if not candidate.is_file():
        raise PipelineError(f"提示词引用的素材文件不存在：{raw_path}")
    resolved_str = str(candidate)
    _validate_api_ref_path(resolved_str, project_root)
    return resolved_str


def parse_prompt_md(prompt_path: Path, project_root: Path) -> dict[str, Any]:
    """Parse 制作/<ID>_*/prompt.md into ratio, file/reference_files, and final_instruction."""
    if not prompt_path.is_file():
        raise PipelineError(f"找不到提示词文件：{prompt_path}")
    raw_text = prompt_path.read_text(encoding="utf-8").strip()
    fence_match = FENCE_RE.search(raw_text)
    if fence_match:
        meta_block = raw_text[: fence_match.start()] + "\n" + raw_text[fence_match.end() :]
        code_block = fence_match.group(1).strip()
    else:
        meta_block = ""
        code_block = raw_text

    ratio_match = RATIO_LINE_RE.search(code_block) or RATIO_LINE_RE.search(raw_text)
    ratio = ratio_match.group(1).lower() if ratio_match else "9:16"

    # Extract @图N -> path bindings (supports backticks, quotes, and spaces e.g. Eagle paths)
    at_map: dict[int, str] = {}
    search_sources = [meta_block] if meta_block.strip() else []
    search_sources.append(code_block)
    for src_text in search_sources:
        for match in AT_IMAGE_PATH_RE.finditer(src_text):
            num = int(match.group(1))
            if num in at_map:
                continue
            raw_val = next((g for g in match.groups()[1:] if g is not None), "").strip()
            looks_like_path = "/" in raw_val or "\\" in raw_val or any(raw_val.lower().endswith(ext) for ext in IMAGE_EXTS) or raw_val.startswith(("http://", "https://"))
            if looks_like_path:
                at_map[num] = _resolve_project_file(raw_val, project_root)

    target_match = TARGET_FILE_RE.search(meta_block or raw_text)
    target_raw = next((g for g in target_match.groups() if g is not None), "").strip() if target_match else ""
    target_resolved = _resolve_project_file(target_raw, project_root) if target_raw else None

    ordered_nums = sorted(at_map)
    source_file: str | None = None
    ref_files: list[str] = []
    if target_resolved:
        source_file = target_resolved
        for num in ordered_nums:
            resolved = at_map[num]
            if num == 1 and resolved == target_resolved:
                continue
            ref_files.append(resolved)
    else:
        ref_files = [at_map[num] for num in ordered_nums]

    final_instruction = code_block
    if not RATIO_LINE_RE.match(final_instruction.splitlines()[0] if final_instruction.splitlines() else ""):
        final_instruction = f"比例：{ratio}\n\n{final_instruction}"

    return {
        "ratio": ratio,
        "file": source_file,
        "reference_files": ref_files,
        "final_instruction": final_instruction.strip(),
    }


def _next_candidate_index(work_dir: Path) -> int:
    max_num = 0
    if work_dir.is_dir():
        for p in work_dir.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                m = CANDIDATE_NUM_RE.search(p.stem)
                if m:
                    max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def _strip_negative_lines_for_person_check(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("禁止：", "禁止:", "明确不采用：", "明确不采用:", "- 明确不采用：", "- 明确不采用:")):
            continue
        cleaned = PERSON_EXCLUSION_RE.sub("", line)
        kept.append(cleaned)
    return "\n".join(kept)


def _validate_person_card_binding(project_root: Path, row_id: str, final_instruction: str, ref_paths: list[str]) -> None:
    card_dir = project_root / "设定集" / "人物身份卡"
    if not card_dir.is_dir():
        return
    cards = [p for p in card_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not cards:
        return
    positive_body = _strip_negative_lines_for_person_check(final_instruction)
    if not PERSON_SIGNAL_RE.search(positive_body):
        return
    has_person_ref = any(
        ("人物身份卡" in Path(r).as_posix() or "模特" in Path(r).name)
        for r in ref_paths
    )
    if not has_person_ref:
        sample_rel = cards[0].resolve().relative_to(project_root.resolve()).as_posix()
        raise PipelineError(
            f"{row_id} 画面正文包含人物/手腕/衣袖描述，但未垫入人物身份卡！"
            f"请先在 制作/{row_id}_*/prompt.md 中绑定 @图N：{sample_rel}"
        )


def _parse_image_models(
    image_model: str = "banana2.1",
    image_models: list[str] | str | None = None,
) -> list[str]:
    raw_items: list[str] = []
    if isinstance(image_models, str):
        raw_items.extend(part.strip() for part in image_models.split(","))
    elif isinstance(image_models, (list, tuple)):
        for entry in image_models:
            raw_items.extend(part.strip() for part in str(entry).split(","))
    elif image_model:
        raw_items.extend(part.strip() for part in image_model.split(","))

    models: list[str] = []
    for item in raw_items:
        if item and item not in models:
            models.append(item)
    if not models:
        models = ["banana2.1"]
    if len(models) > 12:
        raise PipelineError(f"单节点多模型并发最多支持 12 个模型，当前传了 {len(models)} 个。")
    return models


def _supports_banana_thinking_level(model_id: str) -> bool:
    low = model_id.strip().lower()
    if "pro" in low:
        return False
    return low in ("banana", "banana2", "banana2.1", "banana-2.1", "nano-banana-2.1", "gemini-nano-banana-2.1") or (
        "gemini-3.1-flash-image" in low
    ) or ("banana-2" in low or "banana2" in low)


def _normalize_designflow_thinking_level(models: list[str] | str, thinking_level: str | None) -> str | None:
    model_list = [models] if isinstance(models, str) else list(models)
    if not any(_supports_banana_thinking_level(m) for m in model_list):
        return None
    raw = (thinking_level or "").strip()
    if raw:
        low = raw.lower()
        if low == "off":
            return None
        if low == "auto":
            return "auto"
        if low in ("minimal", "medium", "high"):
            return low.upper()
    return "HIGH"


def prepare_or_execute_batch(
    *,
    project_root: Path,
    wave: int | None = None,
    ids: list[str] | None = None,
    quality: str = "2k",
    image_model: str = "banana2.1",
    image_models: list[str] | str | None = None,
    thinking_level: str | None = None,
    count: int = 1,
    concurrency: int = 3,
    engine: str = "api",
    execute: bool = False,
) -> dict[str, Any]:
    if engine not in ("api", "designflow"):
        raise PipelineError(f"不支持的执行模式 engine={engine}（请使用 api 或 designflow）。")
    if engine == "designflow" and execute:
        raise PipelineError(
            "--engine designflow 仅用于 --prepare-batch 校验并生成 designflowItems，"
            "请直接由 Agent 调用 DesignFlow MCP designflow_generate_image 执行"
            "（直连 API 请使用 --engine api --execute）。"
        )
    models = _parse_image_models(image_model, image_models)
    if engine == "api" and len(models) > 1:
        raise PipelineError(
            "API 直连模式每次仅支持单个模型；同提示词多模型并发请改用 --engine designflow 并通过 DesignFlow MCP 单节点 models[] 执行。"
        )
    primary_model = models[0]
    project_root = project_root.resolve()
    _, rows = parse_project_md(project_root / "project.md")

    requested_ids = [i.strip() for i in (ids or []) if i.strip()]
    selected_rows: list[ProjectRow] = []
    if requested_ids:
        by_id = {r.id: r for r in rows}
        for rid in requested_ids:
            row = by_id.get(rid)
            if row is None and "-" in rid:
                base_id = rid.split("-", 1)[0]
                base_row = by_id.get(base_id)
                if base_row is not None and _find_matching_work_dir(project_root, rid) is not None:
                    row = ProjectRow(
                        id=rid,
                        wave=base_row.wave,
                        title=base_row.title,
                        linked_main=base_row.linked_main,
                        source_mode=base_row.source_mode,
                        status="提示词就绪",
                        asset_path=base_row.asset_path,
                        line_index=base_row.line_index,
                        headers=base_row.headers,
                        cells=base_row.cells,
                    )
            if row is None:
                raise PipelineError(f"在 project.md 中找不到编号：{rid}")
            if row.status.startswith("无需生图"):
                raise PipelineError(f"{rid} 标记为「{row.status}」，属于纯后期排版屏，不进入生图。")
            selected_rows.append(row)
    else:
        for row in rows:
            if wave is not None and row.wave != wave:
                continue
            if row.status.startswith(("无需生图", "已锁定", "已定稿")):
                continue
            if row.wave == 3 and row.status.startswith("待派生"):
                continue
            selected_rows.append(row)

    if not selected_rows:
        raise PipelineError("没有需要生图的待处理项（可能已全部定稿或均为纯后期排版）。")

    missing_prompts: list[str] = []
    batch_items: list[dict[str, Any]] = []
    designflow_items: list[dict[str, Any]] = []
    df_thinking = _normalize_designflow_thinking_level(models, thinking_level)
    for row in selected_rows:
        work_dir = _find_matching_work_dir(project_root, row.id)
        prompt_path = (work_dir / "prompt.md") if work_dir else None
        if not prompt_path or not prompt_path.is_file():
            expected_folder = f"制作/{row.id}_{sanitize_slug(row.title, row.id)}/prompt.md"
            missing_prompts.append(f"{row.id}（请先由 d-image-director 写入 {expected_folder}）")
            continue

        parsed = parse_prompt_md(prompt_path, project_root)
        all_refs = list(parsed["reference_files"]) + ([parsed["file"]] if parsed["file"] else [])
        _validate_person_card_binding(project_root, row.id, parsed["final_instruction"], all_refs)
        next_idx = _next_candidate_index(work_dir)
        safe_count = max(1, int(count))

        if engine == "designflow":
            # 严格保持 @图1..N 在 prompt.md 中的原始引用顺序
            ordered_refs = ([parsed["file"]] if parsed["file"] else []) + list(parsed["reference_files"])
            offset = 0
            chunk_idx = 0
            chunk_sizes: list[int] = []
            rem = safe_count
            while rem > 0:
                sz = min(4, rem)
                chunk_sizes.append(sz)
                rem -= sz
            model_multiplier = len(models)
            for sz in chunk_sizes:
                chunk_idx += 1
                total_outputs = sz * model_multiplier
                out_names = [f"{work_dir.name}/候选_{next_idx + offset + i:02d}.png" for i in range(total_outputs)]
                offset += total_outputs
                df_item: dict[str, Any] = {
                    "id": row.id if len(chunk_sizes) == 1 else f"{row.id}-g{chunk_idx}",
                    "title": f"第{row.wave}批 | {row.id} {row.title}",
                    "prompt": parsed["final_instruction"],
                    "model": primary_model,
                    "ratio": parsed["ratio"],
                    "sizePreset": quality.upper(),
                    "count": sz,
                    "referenceFiles": ordered_refs,
                    "outputDir": str(work_dir),
                    "outputNames": out_names,
                }
                if len(models) > 1:
                    df_item["models"] = list(models)
                if df_thinking:
                    df_item["thinkingLevel"] = df_thinking
                designflow_items.append(df_item)
        else:
            for cand_offset in range(safe_count):
                cand_name = f"候选_{next_idx + cand_offset:02d}.png"
                out_rel = f"{work_dir.name}/{cand_name}"
                item_id = row.id if safe_count == 1 else f"{row.id}-c{cand_offset + 1}"
                task_title = f"第{row.wave}批 | {row.id} {row.title}" + (f" #{cand_offset + 1}" if safe_count > 1 else "")
                batch_items.append(
                    {
                        "id": item_id,
                        "file": parsed["file"],
                        "reference_files": parsed["reference_files"],
                        "task": task_title,
                        "count": 1,
                        "output_name": out_rel,
                        "output_size": resolve_output_size(parsed["ratio"], quality),
                        "final_instruction": parsed["final_instruction"],
                    }
                )

    if missing_prompts:
        raise PipelineError("以下编号尚未准备 prompt.md，禁止用草稿偷跑生图：\n- " + "\n- ".join(missing_prompts))

    if engine == "designflow":
        return {
            "ok": True,
            "mode": "designflow_prepared",
            "engine": "designflow",
            "projectRoot": str(project_root),
            "itemsCount": len(designflow_items),
            "totalImages": sum(int(it["count"]) * len(it.get("models") or [it["model"]]) for it in designflow_items),
            "imageModel": primary_model,
            "imageModels": models,
            "designflowItems": designflow_items,
            "tempFileCleaned": True,
        }

    from datetime import datetime
    temp_dir = Path(tempfile.gettempdir()) / "dumik-runs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp_json = temp_dir / f"batch-{uuid.uuid4().hex[:10]}.json"

    try:
        tmp_json.write_text(json.dumps({"items": batch_items}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not execute:
            return {
                "ok": True,
                "mode": "dry_run_prepared",
                "engine": "api",
                "projectRoot": str(project_root),
                "itemsCount": len(batch_items),
                "imageModel": image_model,
                "items": [
                    {
                        "id": it["id"],
                        "outputSize": it["output_size"],
                        "outputName": it["output_name"],
                        "referenceCount": len(it["reference_files"]) + (1 if it["file"] else 0),
                    }
                    for it in batch_items
                ],
                "tempFileCleaned": True,
            }

        cmd = [
            sys.executable,
            str(IMAGE_RUNNER_SCRIPT),
            "--batch",
            "--results-input",
            str(tmp_json),
            "--output-dir",
            str(project_root / "制作"),
            "--image-model",
            primary_model,
            "--concurrency",
            str(concurrency),
        ]
        if thinking_level:
            cmd.extend(["--thinking-level", thinking_level])
        proc = subprocess.run(cmd, check=False, text=True)
        if proc.returncode != 0:
            raise PipelineError(f"批量生图执行失败（exit={proc.returncode}）。")
    finally:
        tmp_json.unlink(missing_ok=True)

    status_after = sync_project_status(project_root)
    return {
        "ok": True,
        "mode": "executed",
        "engine": "api",
        "projectRoot": str(project_root),
        "itemsSubmitted": len(batch_items),
        "imageModel": primary_model,
        "tempFileCleaned": not tmp_json.exists(),
        "statusSync": status_after,
    }


def promote_candidate(
    project_root: Path,
    *,
    item_id: str,
    candidate_file: Path,
    allow_low_res: bool = False,
) -> dict[str, Any]:
    """Promote an approved milestone or candidate image into 设定集/里程碑 or 成品/."""
    project_root = project_root.resolve()
    _, rows = parse_project_md(project_root / "project.md")
    row = next((r for r in rows if r.id == item_id), None)
    if row is None:
        raise PipelineError(f"在 project.md 中找不到编号：{item_id}")

    src = candidate_file if candidate_file.is_absolute() else (project_root / candidate_file)
    src = src.resolve()
    if not src.is_file():
        raise PipelineError(f"找不到要定稿的图片文件：{candidate_file}")

    if not allow_low_res:
        lower_parts = [p.lower() for p in src.parts]
        if any("user_uploaded" in p for p in lower_parts):
            raise PipelineError(
                "检测到源图来自聊天框附件（.user_uploaded），聊天框会自动压缩为 1024px 有损图！"
                "严禁直接当定稿归档，请向用户索要本机无损原图路径后再定稿（确需强制归档可加 --allow-low-res）。"
            )
        if not row.id.startswith("E"):
            try:
                from PIL import Image

                with Image.open(src) as im:
                    w, h = im.size
            except Exception:
                w = h = 0
            if max(w, h) > 0 and max(w, h) < 1500:
                raise PipelineError(
                    f"检测到待定稿图片分辨率偏低（{w}×{h}，长边 < 1500px），疑似压缩预览图！"
                    "请核对并传入 2K 无损原图路径（确需强制归档可加 --allow-low-res）。"
                )

    ext = src.suffix.lower() or ".png"
    slug = sanitize_slug(row.title, row.id)

    if row.id.startswith("MS"):
        dest_dir = project_root / "设定集" / "里程碑"
    elif row.id.startswith("S"):
        dest_dir = project_root / "成品" / "详情_790xn"
    elif row.id.startswith("M"):
        dest_dir = project_root / "成品" / "主图_3x4"
    elif row.id.startswith("E"):
        dest_dir = project_root / "成品" / "入口与SKU_1x1"
    else:
        raise PipelineError(f"无法识别编号归属目录：{item_id}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{row.id}_{slug}{ext}"
    if src != dest:
        shutil.copy2(str(src), str(dest))

    status_res = sync_project_status(project_root)
    result: dict[str, Any] = {
        "ok": True,
        "id": row.id,
        "promotedTo": dest.relative_to(project_root).as_posix(),
        "newStatus": "已锁定" if row.id.startswith("MS") else "已定稿",
        "statusSync": status_res,
    }
    if row.id.startswith("S") and row.linked_main:
        result["linkedMainToDerive"] = row.linked_main
        result["reminder"] = f"{row.id} 已定稿，请顺手从该 9:16 原片裁切/延展派生关联 3:4 主图：{'、'.join(row.linked_main)}"
    elif row.id.startswith("MS"):
        result["reminder"] = (
            f"{row.id} 已锁入 {result['promotedTo']}，请将光影与材质结论写入 design.md；"
            "里程碑齐备后，先延伸 8~12 件置景摆件库（重点款可出实物目录选样卡拍板样式）并排定全案饮品/食材错峰表，再进第 1 批详情生产。"
        )
    return result


def prepare_variant_batch(
    project_root: Path,
    *,
    variant_sku: str,
    variant_ref: Path,
    variant_desc: str,
    ids: list[str] | None = None,
    count: int = 2,
    quality: str = "2k",
) -> dict[str, Any]:
    """基于 成品/ 已定稿图批量生成多 SKU / 多配色一键换款 DesignFlow 并发任务（全落 %TEMP%，目标归档 成品/<SKU名>/）。"""
    ref_path = variant_ref if variant_ref.is_absolute() else (project_root / variant_ref).resolve()
    if not ref_path.is_file():
        raise PipelineError(f"新 SKU 白底参考图不存在: {ref_path}")

    finished_root = project_root / "成品"
    if not finished_root.is_dir():
        raise PipelineError(f"未找到 成品/ 目录，请先完成主推色定稿: {finished_root}")

    sku_slug = re.sub(r'[\\/:*?"<>|]+', "_", variant_sku.strip())
    if not sku_slug:
        raise PipelineError("--variant-sku 不能为空")
    target_out_dir = finished_root / sku_slug

    id_filter = {s.upper() for s in ids} if ids else None
    source_images: list[Path] = []
    for p in sorted(finished_root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        # Skip already-generated variant subfolder
        if target_out_dir in p.parents:
            continue
        if id_filter:
            m = re.match(r"^([A-Za-z]+\d+(?:-\d+)?)", p.stem)
            if not m or m.group(1).upper() not in id_filter:
                continue
        source_images.append(p)

    if not source_images:
        raise PipelineError("成品/ 中未找到可换款的定稿图片（可检查 --ids 过滤条件）。")

    model_priority = ["seedream-5.5", "seedream-5-pro", "banana2.1"]
    desc = (variant_desc or f"按@图2替换为{sku_slug}新款外观与配色").strip()
    prompt = (
        f"保持@图1的整体构图、背景环境、光影方向、景深、人物动作与留白布局完全不变。"
        f"仅将@图1中的产品主体严格对照@图2替换为新SKU款式：{desc}。"
        f"替换后的产品必须保持与原位置一致的透视比例，自然承接@图1原有的环境反光、高光与接触阴影。"
        f"严禁改变非产品区域、新增多余杂物或生成额外文字水印。"
    )

    items: list[dict[str, Any]] = []
    for src in source_images:
        ratio = "9:16"
        parent_name = src.parent.name
        if "3x4" in parent_name or src.stem.upper().startswith("M"):
            ratio = "3:4"
        elif "1x1" in parent_name or src.stem.upper().startswith("E"):
            ratio = "1:1"
        items.append(
            {
                "id": f"{src.stem}_{sku_slug}",
                "sourceFinished": str(src),
                "targetOutputDir": str(target_out_dir),
                "prompt": prompt,
                "ratio": ratio,
                "sizePreset": quality.upper(),
                "count": max(1, min(4, int(count))),
                "models": [model_priority[0]],
                "modelPriority": model_priority,
                "referenceFiles": [str(src), str(ref_path)],
            }
        )

    from datetime import datetime
    temp_dir = Path(tempfile.gettempdir()) / "dumik-runs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_json = temp_dir / f"variant-{sku_slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out_json.write_text(json.dumps({"sku": sku_slug, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "mode": "variant-sku",
        "sku": sku_slug,
        "count": len(items),
        "targetOutputDir": str(target_out_dir),
        "designflowItemsFile": str(out_json),
        "modelPriority": model_priority,
        "items": items,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DUMIK 无状态项目流水线调度（零本地 JSON 尾气，以真实文件为真相）。")
    parser.add_argument("--project-root", default=".", help="DUMIK 项目根目录")
    parser.add_argument("--status", action="store_true", help="扫描磁盘真实文件并刷新 project.md 状态列（默认动作）")
    parser.add_argument("--prepare-batch", action="store_true", help="校验目标批提示词并在系统临时目录预组批次（不调接口）")
    parser.add_argument("--execute", action="store_true", help="真正提交生图接口并在结束后自动清理临时批次 JSON")
    parser.add_argument("--wave", type=int, choices=(0, 1, 2, 3), default=None, help="指定波次：0=里程碑 1=主图共用 2=详情其余 3=独立1:1")
    parser.add_argument("--ids", default=None, help="手动指定编号列表，逗号分隔，如 S04,S16")
    parser.add_argument("--quality", choices=("2k", "4k"), default="2k", help="清晰度档位，默认 2k")
    parser.add_argument("--image-model", default="banana2.1", help="生图模型（默认 banana2.1；--engine designflow 时也支持逗号分隔多模型）")
    parser.add_argument("--image-models", default=None, help="DesignFlow 单节点多模型并发列表（逗号分隔，如 banana2.1,bananapro）")
    parser.add_argument("--thinking-level", default=None, help="Banana 思考深度（默认 high；支持 minimal/medium/high/off）")
    parser.add_argument("--count", type=int, default=1, help="每项生成候选数，默认 1")
    parser.add_argument("--concurrency", type=int, default=3, help="并发数，默认 3")
    parser.add_argument(
        "--engine",
        choices=("api", "designflow"),
        default="api",
        help="执行模式：api=直连拆 count:1 提交；designflow=输出保留单节点 count(1-4) 的 designflowItems",
    )
    parser.add_argument("--promote", default=None, help="将某编号候选图定稿晋升到 设定集/里程碑 或 成品/")
    parser.add_argument("--file", default=None, help="配合 --promote 使用的候选图文件路径")
    parser.add_argument("--allow-low-res", action="store_true", help="跳过定稿防压缩图门禁（允许 <1500px 或聊天框附件强制归档）")
    parser.add_argument("--variant-sku", default=None, help="多 SKU 批量一键换款：目标新 SKU 名称（归档至 成品/<SKU名>/）")
    parser.add_argument("--variant-ref", default=None, help="配合 --variant-sku 使用的新 SKU 白底参考图路径")
    parser.add_argument("--variant-desc", default="", help="配合 --variant-sku 使用的一句话颜色/材质差异说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    try:
        if args.variant_sku:
            if not args.variant_ref:
                raise PipelineError("使用 --variant-sku 时必须同时传入 --variant-ref <新SKU白底图路径>。")
            ids = [s.strip() for s in args.ids.split(",")] if args.ids else None
            res = prepare_variant_batch(
                project_root,
                variant_sku=args.variant_sku,
                variant_ref=Path(args.variant_ref),
                variant_desc=args.variant_desc,
                ids=ids,
                count=args.count,
                quality=args.quality,
            )
        elif args.promote:
            if not args.file:
                raise PipelineError("使用 --promote 时必须同时传入 --file <候选图路径>。")
            res = promote_candidate(
                project_root,
                item_id=args.promote.strip(),
                candidate_file=Path(args.file),
                allow_low_res=bool(args.allow_low_res),
            )
        elif args.execute or args.prepare_batch:
            ids = [s.strip() for s in args.ids.split(",")] if args.ids else None
            res = prepare_or_execute_batch(
                project_root=project_root,
                wave=args.wave,
                ids=ids,
                quality=args.quality,
                image_model=args.image_model,
                image_models=args.image_models,
                thinking_level=args.thinking_level,
                count=args.count,
                concurrency=args.concurrency,
                engine=args.engine,
                execute=bool(args.execute),
            )
        else:
            res = sync_project_status(project_root)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    try:
        scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import dumik_telemetry

        if args.variant_sku:
            t_mode = "variant-sku"
        elif args.promote:
            t_mode = "promote"
        elif args.execute:
            t_mode = f"execute-{args.engine}"
        elif args.prepare_batch:
            t_mode = f"prepare-{args.engine}"
        else:
            t_mode = "status"
        dumik_telemetry.report_event_async(event="invoke", skill="d-project-pipeline", mode=t_mode)
    except Exception:
        pass
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
