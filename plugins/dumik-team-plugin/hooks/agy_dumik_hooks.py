#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity lifecycle hook harness for DUMIK Team Plugin.

Handles SessionStart, PreInvocation, and Stop cleanly:
- Returns fast neutral no-ops for non-DUMIK workspaces.
- Checks 24KB rule-cap health on AGENTS.md + @-includes.
- Injects turn-scoped deterministic skill routing, authorization status, and
  relevant project.md rows on new user turns without flooding follow-up steps.
- Guards Stop when stray JSON/.pytest_cache clutter or unsynced project.md state exists.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


MAX_RULE_BYTES = 24000
WARN_RULE_BYTES = 20000
AT_INCLUDE_RE = re.compile(r"@\[[^\]]*\]\(([^)\s]+)\)")
ROW_ID_RE = re.compile(r"\b((?:MS|S|M|E)\d{1,3}(?:-\d{1,2})?)\b", re.IGNORECASE)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
CLUTTER_JSON_NAMES = {"run-state.json", "canvas-manifest.json", "results-input.json", "拆解清单.md"}

EXECUTION_WORDS = (
    "开始生图",
    "生图",
    "出图",
    "跑图",
    "跑批",
    "批量跑",
    "重新生成",
    "还是生成",
    "再抽",
    "重抽",
    "补抽",
    "重跑",
    "放大",
    "超分",
    "抠图",
    "去背景",
    "调用接口",
    "生视频",
    "出视频",
    "确认片",
)
FORBID_EXEC_WORDS = ("不要生成", "先不生成", "先不出图", "不生图", "只写提示词", "不调接口", "先不跑")


def find_dumik_project_root(payload: dict[str, Any]) -> Path | None:
    candidates: list[str] = []
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        candidates.append(cwd.strip())
    for wp in payload.get("workspacePaths") or []:
        if isinstance(wp, str) and wp.strip() and wp.strip() not in candidates:
            candidates.append(wp.strip())

    for raw in candidates:
        p = Path(raw)
        if not p.is_dir():
            continue
        for cur in (p, *p.parents):
            has_core = (cur / "design.md").is_file() and (cur / "project.md").is_file()
            has_dirs = (cur / "设定集").is_dir() and (cur / "制作").is_dir()
            if has_core or (has_dirs and (cur / "AGENTS.md").is_file()):
                return cur.resolve()
    return None


def measure_agents_expanded_bytes(project_root: Path) -> tuple[int, list[str]]:
    agents_path = project_root / "AGENTS.md"
    if not agents_path.is_file():
        return 0, []
    text = agents_path.read_text(encoding="utf-8", errors="replace")
    total = len(text.encode("utf-8"))
    included: list[str] = []
    for match in AT_INCLUDE_RE.finditer(text):
        rel = match.group(1).strip()
        target = (project_root / rel).resolve()
        if target.is_file():
            included.append(rel)
            total += target.stat().st_size
    return total, included


def detect_project_clutter(project_root: Path) -> list[str]:
    issues: list[str] = []
    if (project_root / ".pytest_cache").exists():
        issues.append(".pytest_cache")
    for p in project_root.iterdir():
        if p.is_file() and (p.suffix.lower() == ".json" or p.name in CLUTTER_JSON_NAMES):
            issues.append(p.name)
    make_dir = project_root / "制作"
    if make_dir.is_dir():
        for p in make_dir.rglob("*.json"):
            issues.append(p.relative_to(project_root).as_posix())
    return issues[:8]


def _extract_project_rows(project_root: Path) -> dict[str, tuple[str, str]]:
    pm = project_root / "project.md"
    if not pm.is_file():
        return {}
    rows: dict[str, tuple[str, str]] = {}
    headers: list[str] = []
    for line in pm.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("|"):
            headers = []
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{3,}:?", c or "---") for c in cells):
            continue
        if any(h in cells[0] for h in ("编号",)):
            headers = cells
            continue
        m = re.match(r"^(MS\d+|S\d+|M\d+|E\d+)\b", cells[0])
        if not m or not headers:
            continue
        rid = m.group(1)
        status_idx = next((i for i, h in enumerate(headers) if "状态" in h), len(headers) - 1)
        status = cells[status_idx] if status_idx < len(cells) else ""
        summary_parts = [
            c for i, c in enumerate(cells)
            if i != 0 and i != status_idx and c and not c.startswith("<img")
        ]
        summary = " | ".join(summary_parts)[:140]
        rows[rid] = (status, summary)
    return rows


def detect_unsynced_work_dirs(project_root: Path) -> list[str]:
    make_dir = project_root / "制作"
    pm_path = project_root / "project.md"
    if not make_dir.is_dir() or not pm_path.is_file():
        return []
    unsynced: list[str] = []
    rows = _extract_project_rows(project_root)
    for rid, (status, _) in rows.items():
        if status.startswith(("已锁定", "已定稿", "无需生图")):
            continue
        exact = re.compile(rf"^{re.escape(rid)}(?:$|_)")
        dirs = [d for d in make_dir.iterdir() if d.is_dir() and exact.match(d.name)]
        if not dirs:
            continue
        d = dirs[0]
        cands = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        if cands and not status.startswith(f"候选已出({len(cands)}张)"):
            unsynced.append(f"{rid}: 磁盘{len(cands)}张 vs 账本「{status}」")
        elif (d / "prompt.md").is_file() and not cands and status in ("待写词", "待派生", "待生成定调"):
            unsynced.append(f"{rid}: 有prompt.md vs 账本「{status}」")
    return unsynced[:6]


def classify_user_intent(user_text: str, project_root: Path) -> dict[str, Any]:
    text = (user_text or "").strip()
    lowered = text.lower()

    if any(k in text for k in FORBID_EXEC_WORDS):
        auth = "forbidden"
    elif any(k in text for k in EXECUTION_WORDS):
        auth = "authorized"
    else:
        auth = "unconfirmed"

    mentioned_ids: list[str] = []
    for raw_id in ROW_ID_RE.findall(text):
        norm = raw_id.upper()
        if norm not in mentioned_ids:
            mentioned_ids.append(norm)

    if any(k in text for k in ("初始化", "建档", "增量同步", "同步画布", "项目规约", "改规则")) or "--sync" in lowered:
        skill, mode = "d-init", "init/maintain"
    elif any(k in text for k in ("验收", "审稿", "一致性", "三态", "对比原图")):
        skill, mode = "d-consistency-check", "review"
    elif any(k in text for k in ("反推", "拆参考图", "还原提示词")):
        skill, mode = "d-prompt-reverse", "reverse"
    elif any(k in text for k in ("飞书", "策划", "卖点排序", "详情结构", "场景矩阵")):
        skill, mode = "d-visual-plan", "canvas/image"
    elif any(k in text for k in ("视频", "分镜", "拉片", "seedance", "dreamina", "veo")):
        skill = "d-video-runner" if auth == "authorized" else "d-video-director"
        mode = "generate" if auth == "authorized" else "prompt"
    elif any(k in text for k in ("流水线", "定稿", "晋升", "--status", "--promote", "状态校准")):
        skill, mode = "d-project-pipeline", "image"
    elif auth == "authorized" and mentioned_ids and not any(k in text for k in ("重写", "只改词", "改一下提示词")):
        skill, mode = "d-image-director -> d-project-pipeline/d-image-runner", "detail + execute"
    elif auth == "authorized":
        skill, mode = "d-image-runner", "generate"
    elif any(k in text for k in ("身份卡", "摆件", "选样", "四视图")):
        skill, mode = "d-image-director", "edit-prop"
    elif mentioned_ids or any(k in text for k in ("提示词", "prompt", "改图", "重绘", "四宫格", "场景", "构图")):
        skill, mode = "d-image-director", "detail"
    else:
        skill, mode = "按 AGENTS.md 路由", "general"

    has_person_cards = (project_root / "设定集" / "人物身份卡").is_dir() and any(
        p.is_file() and p.suffix.lower() in IMAGE_EXTS for p in (project_root / "设定集" / "人物身份卡").iterdir()
    )

    return {
        "auth": auth,
        "skill": skill,
        "mode": mode,
        "mentioned_ids": mentioned_ids[:8],
        "has_person_cards": has_person_cards,
    }


def _should_inject_this_turn(conv_id: str, user_text: str) -> bool:
    if not user_text.strip():
        return False
    state_dir = Path(tempfile.gettempdir()) / "dumik-runs"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "agy-hook-state.json"
    turn_sig = hashlib.sha256(f"{conv_id}\n{user_text}".encode("utf-8")).hexdigest()[:16]
    try:
        data = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    if data.get(conv_id) == turn_sig:
        return False
    data[conv_id] = turn_sig
    if len(data) > 40:
        # Keep only the most recent 20 conversations
        keys = list(data.keys())[-20:]
        data = {k: data[k] for k in keys}
    try:
        state_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return True


def handle_session_start(payload: dict[str, Any]) -> dict[str, Any]:
    root = find_dumik_project_root(payload)
    if not root:
        return {"injectSteps": []}

    expanded_bytes, includes = measure_agents_expanded_bytes(root)
    rows = _extract_project_rows(root)
    clutter = detect_project_clutter(root)
    unsynced = detect_unsynced_work_dirs(root)

    status_counts: dict[str, int] = {}
    for st, _ in rows.values():
        key = st.split("(", 1)[0]
        status_counts[key] = status_counts.get(key, 0) + 1
    counts_txt = " / ".join(f"{k}:{v}" for k, v in status_counts.items()) or "空表"

    lines = [
        f"[DUMIK 项目挂钩已激活] 根目录：{root.name}（总账本共 {len(rows)} 项：{counts_txt}）",
        f"- 规则体量：`AGENTS.md` 含 `@` 展开共 {expanded_bytes}B（上限 {MAX_RULE_BYTES}B，内联：{', '.join(includes) or '无'}）",
        "- 核心入口：写/改词先用 `d-image-director` 跑 `compile_reference_pack.ps1`；批量出图走 `build_canvas_pipeline.py`；总账本 `project.md` 按编号用 `read_file` 按需读取。",
    ]
    if expanded_bytes > WARN_RULE_BYTES:
        lines.append(f"- 警告：`AGENTS.md` 展开逼近/超出 {MAX_RULE_BYTES}B，务必精简 `design.md` 且严禁内联整本 `project.md`！")
    if clutter:
        lines.append(f"- 待清理垃圾文件：{', '.join(clutter)}")
    if unsynced:
        lines.append(f"- 状态未同步：{'; '.join(unsynced)}（建议跑 `--status`）")

    return {"injectSteps": [{"systemMessage": {"systemMessage": "\n".join(lines)}}]}


def handle_pre_invocation(payload: dict[str, Any]) -> dict[str, Any]:
    root = find_dumik_project_root(payload)
    if not root:
        return {"injectSteps": []}
    conv_id = str(payload.get("conversationId") or "default")
    user_text = str(payload.get("lastUserInput") or "")
    if not _should_inject_this_turn(conv_id, user_text):
        return {"injectSteps": []}

    route = classify_user_intent(user_text, root)
    auth_desc = {
        "authorized": "已授权（可执行生图/后处理，仍须先备齐完整 prompt.md）",
        "forbidden": "禁止生图（用户明确要求仅出文字/暂不调用接口）",
        "unconfirmed": "未检测到明确生图口令（默认只停在文本/提示词，禁偷跑接口）",
    }[route["auth"]]

    lines = [
        f"[DUMIK 本轮路由] 推荐入口：`{route['skill']}`（mode={route['mode']}）｜授权状态：{auth_desc}",
    ]
    if route["has_person_cards"]:
        lines.append("- 硬检提示：项目含 `设定集/人物身份卡/`，凡出现人物/手/腕/袖必传人物卡；严禁传入 `素材/飞书画布/` 脏截图。")

    if route["mentioned_ids"]:
        all_rows = _extract_project_rows(root)
        hit_lines = []
        for mid in route["mentioned_ids"]:
            base = mid.split("-", 1)[0]
            info = all_rows.get(mid) or all_rows.get(base)
            if info:
                st, summary = info
                hit_lines.append(f"  - {mid}（{st}）：{summary}")
        if hit_lines:
            lines.append("- 命中 `project.md` 摘要（需细节请 `read_file`）：\n" + "\n".join(hit_lines))

    return {"injectSteps": [{"systemMessage": {"systemMessage": "\n".join(lines)}}]}


def handle_stop(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("continuationActive"):
        return {"decision": "stop"}
    if payload.get("terminationReason") != "NO_TOOL_CALL":
        return {"decision": "stop"}
    root = find_dumik_project_root(payload)
    if not root:
        return {"decision": "stop"}

    problems: list[str] = []
    clutter = detect_project_clutter(root)
    if clutter:
        problems.append(f"发现项目内禁止保留文件: {', '.join(clutter)}")
    unsynced = detect_unsynced_work_dirs(root)
    if unsynced:
        problems.append(f"磁盘与 project.md 状态未同步: {'; '.join(unsynced)}")

    if problems:
        return {
            "decision": "continue",
            "reason": "DUMIK Harness 收尾检查未通过，请处理后结束：" + "；".join(problems),
        }
    return {"decision": "stop"}


def dispatch_hook(payload: dict[str, Any]) -> dict[str, Any]:
    event = str(payload.get("hookEventName") or "")
    if event == "SessionStart":
        return handle_session_start(payload)
    if event == "PreInvocation":
        return handle_pre_invocation(payload)
    if event == "Stop":
        return handle_stop(payload)
    return {}


def main() -> int:
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        out = dispatch_hook(payload)
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:
        # Never crash the host agent loop on hook telemetry errors.
        sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
