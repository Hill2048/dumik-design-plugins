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
    "重新升成",
    "还是生成",
    "都生成",
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
MODEL_HINTS = (
    "banana2.1",
    "banana2",
    "bananapro",
    "banana-pro",
    "banana",
    "pro",
    "即梦",
    "seedream",
    "image2.6",
    "image2.5",
    "image2",
)
CONCURRENCY_OR_COUNT_RE = re.compile(r"(?:并发|[x×]\s*\d+|各\s*\d+\s*张|分别|多模型)", re.IGNORECASE)
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


def has_unfilled_prop_bible(project_root: Path) -> bool:
    """检查是否已锁定里程碑，但 assets.md（兼容老项目 design.md）里的置景摆件库尚未填实。"""
    rows = _extract_project_rows(project_root)
    has_locked_ms = any(rid.startswith("MS") and st.startswith("已锁定") for rid, (st, _) in rows.items())
    if not has_locked_ms:
        return False
    target = project_root / "assets.md"
    if not target.is_file():
        target = project_root / "design.md"
    if not target.is_file():
        return False
    text = target.read_text(encoding="utf-8", errors="replace")
    if "风格摆件库" not in text and "置景摆件库" not in text:
        return False
    in_prop_sec = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and ("风格摆件库" in stripped or "置景摆件库" in stripped):
            in_prop_sec = True
            continue
        if in_prop_sec and stripped.startswith("##"):
            break
        if in_prop_sec and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 3 and re.fullmatch(r"\d{1,2}", cells[0]):
                if not any(ph in cells[1] for ph in ("待规划", "待填")):
                    return False
    return True


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


def _strip_quoted_lines(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    stripped = "\n".join(lines).strip()
    return stripped if stripped else text


def classify_user_intent(user_text: str, project_root: Path) -> dict[str, Any]:
    text = (user_text or "").strip()
    active_text = _strip_quoted_lines(text)
    lowered = active_text.lower()

    has_model_and_batch = any(m in lowered for m in MODEL_HINTS) and bool(CONCURRENCY_OR_COUNT_RE.search(active_text))

    if any(k in active_text for k in FORBID_EXEC_WORDS):
        auth = "forbidden"
    elif any(k in active_text for k in EXECUTION_WORDS) or has_model_and_batch:
        auth = "authorized"
    else:
        auth = "unconfirmed"

    mentioned_ids: list[str] = []
    for raw_id in ROW_ID_RE.findall(text):
        norm = raw_id.upper()
        if norm not in mentioned_ids:
            mentioned_ids.append(norm)

    is_pure_archive = any(k in active_text for k in ("作为", "设为", "归档", "存进")) and not any(
        k in active_text for k in ("提示词", "prompt", "写", "改", "生成", "生图", "出图", "重抽")
    )

    if any(k in active_text for k in ("初始化", "建档", "增量同步", "同步画布", "项目规约", "改规则")) or "--sync" in lowered:
        skill, mode = "d-init", "init/maintain"
    elif any(k in active_text for k in ("验收", "审稿", "一致性", "三态", "对比原图")):
        skill, mode = "d-consistency-check", "review"
    elif any(k in active_text for k in ("反推", "拆参考图", "还原提示词")):
        skill, mode = "d-prompt-reverse", "reverse"
    elif not is_pure_archive and any(k in active_text for k in ("清洗徽章", "徽章", "勋章", "认证标", "角标", "小铭牌", "纯色平面图")):
        skill = "d-badge-wash -> d-image-runner" if auth == "authorized" else "d-badge-wash"
        mode = "wash + execute" if auth == "authorized" else "wash"
    elif any(k in active_text for k in ("飞书", "策划", "卖点排序", "详情结构", "场景矩阵")):
        skill, mode = "d-visual-plan", "canvas/image"
    elif any(k in active_text for k in ("视频", "分镜", "拉片", "seedance", "dreamina", "veo")):
        skill = "d-video-runner" if auth == "authorized" else "d-video-director"
        mode = "generate" if auth == "authorized" else "prompt"
    elif any(k in active_text for k in ("流水线", "定稿", "晋升", "--status", "--promote", "状态校准")):
        skill, mode = "d-project-pipeline", "image"
    elif auth == "authorized" and mentioned_ids and not any(k in active_text for k in ("重写", "只改词", "改一下提示词")):
        skill, mode = "d-image-director -> d-project-pipeline/d-image-runner", "detail + execute"
    elif auth == "authorized":
        skill, mode = "d-image-runner", "generate"
    elif not is_pure_archive and any(k in active_text for k in ("身份卡", "摆件", "选样", "四视图")):
        skill, mode = "d-image-director", "edit-prop"
    elif mentioned_ids or any(k in active_text for k in ("提示词", "prompt", "改图", "重绘", "四宫格", "场景", "构图")):
        skill, mode = "d-image-director", "detail"
    else:
        skill, mode = "按 AGENTS.md 路由", "general"

    return {
        "auth": auth,
        "skill": skill,
        "mode": mode,
        "mentioned_ids": mentioned_ids[:8],
    }


def _state_file_path() -> Path:
    state_dir = Path(tempfile.gettempdir()) / "dumik-runs"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "agy-hook-state.json"


def _load_hook_state() -> dict[str, Any]:
    sf = _state_file_path()
    try:
        data = json.loads(sf.read_text(encoding="utf-8")) if sf.is_file() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_hook_state(data: dict[str, Any]) -> None:
    if len(data) > 40:
        keys = list(data.keys())[-20:]
        data = {k: data[k] for k in keys}
    try:
        _state_file_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _get_conv_entry(data: dict[str, Any], conv_id: str) -> dict[str, Any]:
    raw = data.get(conv_id)
    if isinstance(raw, str):
        entry: dict[str, Any] = {"turn_sig": raw, "last_route_key": "", "seen_rows": {}, "warned_bytes": False, "turn_count": 0}
    elif isinstance(raw, dict):
        entry = {
            "turn_sig": str(raw.get("turn_sig") or ""),
            "last_route_key": str(raw.get("last_route_key") or ""),
            "seen_rows": dict(raw.get("seen_rows")) if isinstance(raw.get("seen_rows"), dict) else {},
            "warned_bytes": bool(raw.get("warned_bytes", False)),
            "turn_count": int(raw.get("turn_count") or 0),
        }
    else:
        entry = {"turn_sig": "", "last_route_key": "", "seen_rows": {}, "warned_bytes": False, "turn_count": 0}
    data[conv_id] = entry
    return entry


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
        f"[DUMIK 项目挂钩] {root.name}（共 {len(rows)} 项：{counts_txt}｜规则 {expanded_bytes}B / 上限 {MAX_RULE_BYTES}B，内联：{', '.join(includes) or '无'}）",
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
    if not user_text.strip():
        return {"injectSteps": []}

    turn_sig = hashlib.sha256(f"{conv_id}\n{user_text}".encode("utf-8")).hexdigest()[:16]
    state = _load_hook_state()
    entry = _get_conv_entry(state, conv_id)
    if entry["turn_sig"] == turn_sig:
        return {"injectSteps": []}
    entry["turn_sig"] = turn_sig
    entry["turn_count"] = int(entry.get("turn_count") or 0) + 1
    turn_count = entry["turn_count"]

    route = classify_user_intent(user_text, root)
    route_key = f"{route['skill']}|{route['mode']}|{route['auth']}"
    prev_route_key = entry["last_route_key"]
    entry["last_route_key"] = route_key

    lines: list[str] = []
    is_meaningful_route = (route["mode"] != "general") or (route["auth"] != "unconfirmed")
    if is_meaningful_route and route["skill"].startswith("d-"):
        try:
            scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import dumik_telemetry

            primary_skill = route["skill"].split("->", 1)[0].strip()
            dumik_telemetry.report_event_async(
                event="invoke",
                skill=primary_skill,
                mode=route["mode"],
                host="antigravity",
            )
        except Exception:
            pass
    if is_meaningful_route and route_key != prev_route_key:
        auth_tag = {
            "authorized": "已授权可执行",
            "forbidden": "禁止生图（仅文本）",
            "unconfirmed": "仅文本/禁调接口",
        }[route["auth"]]
        if route["mode"] == "general":
            lines.append(f"[DUMIK 授权] {auth_tag}")
        else:
            lines.append(f"[DUMIK 路由] `{route['skill']}` ({route['mode']}) ｜ {auth_tag}")

    if route["mentioned_ids"]:
        all_rows = _extract_project_rows(root)
        seen_rows = entry["seen_rows"]
        hit_lines = []
        for mid in route["mentioned_ids"]:
            base = mid.split("-", 1)[0]
            info = all_rows.get(mid) or all_rows.get(base)
            if info:
                st, summary = info
                row_sig = f"{st}|{summary}"
                if seen_rows.get(mid) != row_sig:
                    seen_rows[mid] = row_sig
                    hit_lines.append(f"  - {mid}（{st}）：{summary}")
        if hit_lines:
            lines.append("- `project.md` 摘要：\n" + "\n".join(hit_lines))

    expanded_bytes, _ = measure_agents_expanded_bytes(root)
    if expanded_bytes > WARN_RULE_BYTES:
        if not entry["warned_bytes"]:
            lines.append(f"- 警告：`AGENTS.md` 展开达 {expanded_bytes}B（上限 {MAX_RULE_BYTES}B），请精简 `design.md`。")
            entry["warned_bytes"] = True
    else:
        entry["warned_bytes"] = False

    # 长会话防失忆提醒（25 轮起每 15 轮提醒一次 /compact）
    if turn_count >= 25 and (turn_count == 25 or (turn_count - 25) % 15 == 0):
        lines.append(
            f"- 提醒：当前会话已连续 {turn_count} 轮，上下文偏长易丢设定（氛围/已用饮品/道具），建议择机用 `/compact` 压缩上下文。"
        )

    # 追改/生图防漂移提醒（非局部修复时强提醒：禁垫 L3 候选图、必带里程碑、核对已用饮品道具）
    is_img_route = any(s in route["skill"] for s in ("d-image-director", "d-image-runner", "d-project-pipeline"))
    is_repair_turn = ("repair" in route["mode"]) or ("修复" in user_text)
    is_rework_cue = any(k in user_text for k in ("重新", "重抽", "氛围", "不要", "换", "再"))
    if is_img_route and not is_repair_turn and (route_key != prev_route_key or is_rework_cue):
        lines.append(
            "- 防漂移底线：严禁拿 `制作/` 未定稿候选图当垫图；必须带 L1 白底图 + 已定稿里程碑母版，并核对 `assets.md` 已用饮品/摆件防重复。"
        )
    has_detail_id = any(mid.startswith(("S", "M")) and not mid.startswith("MS") for mid in route["mentioned_ids"])
    if is_img_route and not is_repair_turn and has_detail_id and has_unfilled_prop_bible(root):
        lines.append(
            "- 前置置景提醒：里程碑已锁定，但 `assets.md` 风格摆件库尚未填实；建议先梳理 8~12 件风格摆件（重点款可出目录选样卡拍板）与饮品/食材错峰表，再批量开写详情。"
        )

    _save_hook_state(state)
    if not lines:
        return {"injectSteps": []}
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
