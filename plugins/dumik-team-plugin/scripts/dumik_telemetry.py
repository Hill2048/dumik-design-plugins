#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DUMIK 轻量级异步埋点模块（零外部依赖，兼容 Windows / macOS / Linux）。

与 report_skill_telemetry.ps1 使用完全一致的 Feishu Bitable Webhook JSON 字段：
  event, skill, mode, plugin_version, host, os, device_id, timestamp

核心保障：
1. 自动在 PYTEST_CURRENT_TEST / DUMIK_TELEMETRY_DISABLED=1 时静默跳过，绝不污染真实统计表。
2. report_event_async() 启动独立脱钩子进程（Windows CREATE_NO_WINDOW | DETACHED_PROCESS），
   父脚本（如 Hook / CLI）15ms 内无阻塞退出，不丢包、不弹窗、不拖慢对话。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
from typing import Any
from urllib import request as urllib_request


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_telemetry_config(webhook_override: str = "") -> dict[str, Any]:
    root = _plugin_root()
    cfg_path = root / "assets" / "telemetry-config.json"
    enabled = True
    url = ""
    timeout = 6
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            if "enabled" in raw:
                enabled = bool(raw["enabled"])
            if raw.get("webhookUrl"):
                url = str(raw["webhookUrl"]).strip()
            if raw.get("timeoutSeconds") and int(raw["timeoutSeconds"]) > 0:
                timeout = int(raw["timeoutSeconds"])
        except Exception:
            pass
    env_url = os.environ.get("DUMIK_TELEMETRY_WEBHOOK", "").strip()
    if env_url:
        url = env_url
    if webhook_override.strip():
        url = webhook_override.strip()
    return {"enabled": enabled, "webhook_url": url, "timeout_seconds": timeout}


def resolve_plugin_version(version_override: str = "") -> str:
    if version_override.strip():
        return version_override.strip()
    ver_path = _plugin_root() / "assets" / "skill-versions.json"
    if ver_path.is_file():
        try:
            data = json.loads(ver_path.read_text(encoding="utf-8-sig"))
            if data.get("pluginVersion"):
                return str(data["pluginVersion"]).strip()
        except Exception:
            pass
    return "unknown"


def resolve_host_app(host_override: str = "") -> str:
    if host_override.strip():
        return host_override.strip().lower()
    root_str = str(_plugin_root()).lower()
    if ".gemini\\config\\plugins" in root_str or ".gemini/config/plugins" in root_str:
        return "antigravity"
    if ".codex\\" in root_str or ".codex/" in root_str or os.environ.get("CODEX_HOME"):
        return "codex"
    if ".zcode\\" in root_str or ".zcode/" in root_str:
        return "zcode"
    if os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or os.environ.get("AGY_CONVERSATION_ID"):
        return "antigravity"
    return "local"


def get_anonymous_device_id() -> str:
    host_name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "unknown"
    try:
        user_name = getpass.getuser()
    except Exception:
        user_name = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    raw = f"{host_name}|{user_name}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:12]


def build_payload(
    *,
    event: str = "invoke",
    skill: str = "dumik-team-plugin",
    mode: str = "",
    version: str = "",
    host: str = "",
) -> dict[str, Any]:
    os_name = platform.system().lower() or "windows"
    if os_name == "darwin":
        os_name = "macos"
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "event": event,
        "skill": skill,
        "mode": mode,
        "plugin_version": resolve_plugin_version(version),
        "host": resolve_host_app(host),
        "os": os_name,
        "device_id": get_anonymous_device_id(),
        "timestamp": ts,
    }


def _is_suppressed(force: bool = False) -> bool:
    if force:
        return False
    if os.environ.get("DUMIK_TELEMETRY_DISABLED") == "1":
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return False


def send_event_sync(
    *,
    event: str = "invoke",
    skill: str = "dumik-team-plugin",
    mode: str = "",
    version: str = "",
    host: str = "",
    webhook_override: str = "",
    force: bool = False,
) -> dict[str, Any]:
    if _is_suppressed(force=force):
        return {"status": "suppressed"}
    cfg = load_telemetry_config(webhook_override=webhook_override)
    if (not cfg["enabled"] and not force) or not cfg["webhook_url"]:
        return {"status": "disabled"}

    payload = build_payload(event=event, skill=skill, mode=mode, version=version, host=host)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        cfg["webhook_url"],
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=cfg["timeout_seconds"]) as resp:
            resp_text = resp.read().decode("utf-8", errors="replace")
        return {"status": "ok", "sent": payload, "response": resp_text[:300]}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "sent": payload}


def report_event_async(
    *,
    event: str = "invoke",
    skill: str = "dumik-team-plugin",
    mode: str = "",
    version: str = "",
    host: str = "",
) -> bool:
    """在脱钩子进程中异步发送埋点，绝不阻塞父脚本、不抛异常。"""
    if _is_suppressed(force=False):
        return False
    try:
        cfg = load_telemetry_config()
        if not cfg["enabled"] or not cfg["webhook_url"]:
            return False
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--send-now",
            "--event",
            event,
            "--skill",
            skill,
        ]
        if mode:
            cmd.extend(["--mode", mode])
        if version:
            cmd.extend(["--version", version])
        if host:
            cmd.extend(["--host", host])

        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DUMIK 飞书多维表格埋点工具")
    ap.add_argument("--event", default="invoke", choices=["invoke", "install", "update", "download"])
    ap.add_argument("--skill", default="dumik-team-plugin")
    ap.add_argument("--mode", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--webhook", default="")
    ap.add_argument("--send-now", action="store_true", help="同步立即发送（供异步子进程调用）")
    ap.add_argument("--test", action="store_true", help="强制同步发送并打印返回结果")
    args = ap.parse_args(argv)

    if args.test or args.send_now:
        res = send_event_sync(
            event=args.event,
            skill=args.skill,
            mode=args.mode,
            version=args.version,
            host=args.host,
            webhook_override=args.webhook,
            force=args.test,
        )
        if args.test:
            print(json.dumps(res, ensure_ascii=False))
            return 0 if res.get("status") == "ok" else 1
        return 0

    report_event_async(
        event=args.event,
        skill=args.skill,
        mode=args.mode,
        version=args.version,
        host=args.host,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
