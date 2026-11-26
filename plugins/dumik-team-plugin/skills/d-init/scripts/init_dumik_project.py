#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified DUMIK project initializer and Feishu incremental synchronizer.

Creates a self-contained project folder with:
- Standard folders: 素材/实拍原图, 设定集/{白底图,里程碑,必渲特写}, 制作, 成品/{详情_790xn,主图_3x4,入口与SKU_1x1}
- Exactly three clean root Markdown docs: AGENTS.md, design.md, project.md
- Zero JSON queues, zero run logs, and zero pre-created empty task folders under 制作/.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PARSE_CANVAS_SCRIPT = PLUGIN_ROOT / "skills" / "d-visual-plan" / "scripts" / "parse_feishu_canvas.py"
INSTALL_HOOK_SCRIPT = PLUGIN_ROOT / "skills" / "d-init" / "scripts" / "install-project-context-hook.js"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
STANDARD_DIRS = (
    "素材/实拍原图",
    "设定集/白底图",
    "设定集/里程碑",
    "设定集/必渲特写",
    "制作",
    "成品/详情_790xn",
    "成品/主图_3x4",
    "成品/入口与SKU_1x1",
)


def _load_parser_module():
    existing = sys.modules.get("parse_feishu_canvas")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("parse_feishu_canvas", PARSE_CANVAS_SCRIPT)
    if not spec or not spec.loader:
        raise RuntimeError(f"无法加载飞书拆解脚本：{PARSE_CANVAS_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["parse_feishu_canvas"] = mod
    spec.loader.exec_module(mod)
    return mod


def _unique_dest(dest_dir: Path, filename: str) -> Path:
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    idx = 2
    while True:
        alt = dest_dir / f"{stem}_{idx}{suffix}"
        if not alt.exists():
            return alt
        idx += 1


def organize_root_images(project_root: Path) -> list[str]:
    """Move loose top-level image files into 素材/实拍原图 without overwriting existing files."""
    dest_dir = project_root / "素材" / "实拍原图"
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for entry in sorted(project_root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in IMAGE_EXTS:
            continue
        target = _unique_dest(dest_dir, entry.name)
        shutil.move(str(entry), str(target))
        moved.append(target.relative_to(project_root).as_posix())
    return moved


def register_white_bg_files(project_root: Path, paths: list[str]) -> list[str]:
    """Copy explicit white-background reference images into 设定集/白底图/."""
    dest_dir = project_root / "设定集" / "白底图"
    dest_dir.mkdir(parents=True, exist_ok=True)
    registered: list[str] = []
    resolved_dest_dir = dest_dir.resolve()
    for raw in paths:
        src = Path(raw)
        if not src.is_absolute():
            src = (project_root / src).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"找不到指定的白底参考图：{raw}")
        if src.parent.resolve() == resolved_dest_dir:
            rel = src.relative_to(project_root.resolve()).as_posix()
            if rel not in registered:
                registered.append(rel)
            continue
        target = _unique_dest(dest_dir, src.name)
        shutil.copy2(str(src), str(target))
        registered.append(target.relative_to(project_root).as_posix())
    return registered


def render_project_agents_md(project_name: str) -> str:
    """Keep root AGENTS.md under ~1.2KB and inline only design.md to avoid 24KB rule truncation."""
    return f"""# {project_name} — 项目工作规约

- 本目录即独立项目根，不建跨项目指针或历史日志。
- **9:16 纯无字画面底图**：除产品原生丝印/刻字外，严禁任何文字、数字标尺、角标与引线，按 `project.md` 留白。
- **零运行垃圾**：禁写 `.json` 队列、`拆解清单.md` 或运行记录；制作只按需建 `制作/<编号_名称>/prompt.md` 覆盖维护最新版。
- **参考与授权**：白底只锁结构固有色；光色从 `design.md` 与 `设定集/`；飞书参考图只读不喂 API；未收「开始生图/出图」绝不调付费接口。
- **汇报带短卖点**：列编号必附4~6字卖点（如 `S01 健康对比`），一眼扫完，忌裸号或长句。
- **防截断按需读账本**：`project.md` 体量大，不整本内联，按当前编号按需读取或跑 `--status`。

## 项目上下文自动挂载

@[design.md](design.md)
"""


def render_design_md(project_name: str, white_bg_paths: list[str]) -> str:
    wb_lines = "\n".join(f"  - `{p}`" for p in white_bg_paths) if white_bg_paths else "  - 待补齐（放入 `设定集/白底图/`）"
    status_line = "白底已锁，待里程碑定调光影母体" if white_bg_paths else "待补齐白底参考与里程碑定调"
    return f"""# {project_name} — 视觉宪法

- 当前锁定状态：{status_line}

## 一、产品身份锁（7 维解剖档案 · 严禁漂移）

- 白底结构基准图（优先补齐正视/侧视/顶视/底视/内腔五视图或身份卡）：
{wb_lines}
- **外轮廓与比例**：精确尺寸与视觉比例（如宽口矮胖/修长直筒、壁厚与底角弧度）｜禁画变形雷区：待看白底图填实
- **表面材质与微观肌理**：主体固有色、微观纹理颗粒/反差/受光折射与边缘高光（写清与易错材质如喷砂/哑光漆的区别）：待看白底图填实
- **关键部件解剖表**（建档看白底图逐项填实，看不见的标「待补视角」绝不瞎编）：

| 部件 | 位置与连接方式 | 精准形态、厚度倒角与细部结构 | 易错禁画 |
| --- | --- | --- | --- |
| 主体/开口 | 待填 | 待填 | 待填 |
| 手柄/接口 | 待填 | 待填 | 待填 |
| 盖子/开关/五金 | 待填 | 待填 | 待填 |

- **原生 Logo / 刻字 / 钢印落位**：文字内容、所在面、工艺（微刻/钢印/丝印）与比例（远景不强求清晰字形，近景/修复必还原）：待看白底图填实
- **状态切换规则**：无盖/合盖/装饮品/展开态各自必须保留或隐藏的部件：待填
- **按需摘取复用短句（只取本屏可见部位，画面拍不到的严禁写入提示词）**：
  - `主体基础`：待填（仅写所有视角共用的廓形与主材质，≤40 字）
  - `局部/状态按需追加`：仅拍到对应面或处于对应状态时再拼入（如合盖再加盖子句、拍内腔再加钢印句、近景再加微刻句）。

## 二、材质光学公式（第 0 批里程碑确认后锁死）

- 主材质光学表现：待定调（例：金属宽倒角漫反射/拉丝纹理、木材天然纤维暖色）
- 副材质与接触表现：待定调

## 三、统一空间与光影母版（第 0 批里程碑确认后锁死）

- 光影基调：待定调（光源方向、软硬光比、台面接触阴影）
- 色彩与台面材质家族：待定调
- 超级符号（视觉锤）：待定调

## 四、全案硬禁令

- 全画面严禁生成任何后期排版标题、卖点文案、数字标尺、指示引线、放大圆框、水印或装饰角标。
- 所有画面必须按 `project.md` 预留干净低反差的后期 PS 排版负空间。
"""


def update_design_md_white_bg(design_path: Path, white_bg_paths: list[str]) -> None:
    if not white_bg_paths:
        return
    text = design_path.read_text(encoding="utf-8")
    existing = set(re.findall(r"`(设定集/白底图/[^`]+)`", text))
    new_paths = [p for p in white_bg_paths if p not in existing]
    if not new_paths:
        return
    if "待补齐（放入 `设定集/白底图/`）" in text:
        replacement = "\n".join(f"  - `{p}`" for p in white_bg_paths)
        text = text.replace("  - 待补齐（放入 `设定集/白底图/`）", replacement)
        text = text.replace("待补齐白底参考与里程碑定调", "白底已锁，待里程碑定调光影母体")
    elif "- 白底结构基准图" in text:
        add_lines = "\n".join(f"  - `{p}`" for p in new_paths)
        text = re.sub(r"(- 白底结构基准图[^\n]*\n)", rf"\1{add_lines}\n", text, count=1)
    design_path.write_text(text, encoding="utf-8")


def render_empty_project_md(
    *,
    project_name: str,
    raw_photos: list[str],
    white_bg_paths: list[str],
) -> str:
    raw_txt = "、".join(f"`{p}`" for p in raw_photos[:8]) if raw_photos else "待放入 `素材/实拍原图/`"
    wb_path = "、".join(white_bg_paths) if white_bg_paths else "无"
    wb_status = "已锁定" if white_bg_paths else "待补齐白底参考"
    return f"""# {project_name} — 项目总账本

- 飞书源：未绑定（可随时提供飞书链接执行增量同步）
- 默认生图画幅：**9:16 竖版**（纯无字底图，人工后期 PS 排版）
- 参考图隔离铁律：表中「画布原参考」仅作写词前视觉读图参考，严禁作为生图 API 垫图（`@图N` 仅用 `设定集/白底图/` 与 `设定集/里程碑/`）
- 批次统计：第 0 批里程碑 4 项 ｜ 待拆解卖点与详情分屏

## 一、核心策划分析（卖点提纯与唯一规格真源）

- 实拍原图：{raw_txt}
- 核心卖点与实测规格：待补充文字卖点或关联飞书策划画布。

## 二、第 0 批：视觉里程碑设定（定调后锁入 design.md）

| 编号 | 里程碑项 | 画幅 | 状态 | 定稿/参考路径 | 定调重点 |
| --- | --- | --- | --- | --- | --- |
| MS01 | 产品白底身份卡（结构与材质锁） | 9:16 | {wb_status} | {wb_path} | 锁产品真实结构、固有色与材质光学反射 |
| MS02 | 首屏 KV 视觉定调 | 9:16 | 待生成定调 | 无 | 定光影、背景基调、负空间比例与纯无字画面 |
| MS03 | 超级符号 / 核心视觉锤 | 9:16 | 待生成定调 | 无 | 提炼跨屏复用的高辨识视觉锤 |
| MS04 | 核心使用场景母版 | 9:16 | 待生成定调 | 无 | 统一台面材质与真实自然环境逻辑 |

## 三、3:4 主图转化序列（门面点击逻辑与同源裁切对照）

| 编号 | 画布原参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字画面与来源方式 | 当前出图 | 状态 |
| --- | --- | --- | --- | --- | --- |
| — | — | 待拆解或用户补充主图规划 | — | — | — |

## 四、详情页纵向叙事全表（第 1 批（最优先）★主图同源屏 + 第 2 批其余分屏，按阅读顺序顺排）

| 编号 | 批次与关联 | 画布原参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字底图拍法 & PS留白 | 机位景别 | 当前出图 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | 待补充详情分屏规划（纯报告/参数屏将标为无需生图） | — | — | — | — |

## 五、第 3 批：独立 1:1 入口车图与 SKU 底图

| 编号 | 画布原参考 | 交付规格 & 运营原主副标题/批注 | 纯无字底图拍法 & 来源方式 | 当前出图 | 状态 |
| --- | --- | --- | --- | --- | --- |
| — | — | 暂无独立 1:1 入口图或 SKU 底图 | — | — | — |
"""


def _write_utf8_no_bom(path: Path, content: str) -> None:
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _apply_white_bg_to_project_md(project_md_path: Path, white_bg_paths: list[str]) -> None:
    if not white_bg_paths or not project_md_path.exists():
        return
    joined = "、".join(white_bg_paths)
    lines = project_md_path.read_text(encoding="utf-8").splitlines()
    changed = False
    out_lines: list[str] = []
    for ln in lines:
        if ln.startswith("| MS") and ("白底" in ln or "身份" in ln):
            parts = ln.split("|")
            if len(parts) >= 7:
                cur_status = parts[4].strip()
                cur_path = parts[5].strip()
                if cur_status in ("待补齐白底参考", "待生成定调"):
                    parts[4] = " 已锁定 "
                if cur_path in ("", "无"):
                    parts[5] = f" {joined} "
                ln = "|".join(parts)
                changed = True
        out_lines.append(ln)
    if changed:
        _write_utf8_no_bom(project_md_path, "\n".join(out_lines) + "\n")


def init_project(
    *,
    project_root: Path,
    project_name: str | None = None,
    feishu_url: str | None = None,
    whiteboard_tokens: list[str] | None = None,
    download_assets: bool = False,
    sync: bool = False,
    white_bg_inputs: list[str] | None = None,
    organize_root: bool = True,
    host: str = "none",
    default_ratio: str = "9:16",
    all_doc_boards: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    for rel_dir in STANDARD_DIRS:
        (project_root / rel_dir).mkdir(parents=True, exist_ok=True)

    moved_raw = organize_root_images(project_root) if organize_root else []
    registered_wb = register_white_bg_files(project_root, white_bg_inputs or [])
    existing_wb = [
        p.relative_to(project_root).as_posix()
        for p in sorted((project_root / "设定集" / "白底图").glob("*"))
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    all_raw = [
        p.relative_to(project_root).as_posix()
        for p in sorted((project_root / "素材" / "实拍原图").glob("*"))
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]

    display_name = (project_name or project_root.name or "DUMIK视觉项目").strip()
    agents_path = project_root / "AGENTS.md"
    design_path = project_root / "design.md"
    project_md_path = project_root / "project.md"

    created_files: list[str] = []
    if not agents_path.exists():
        _write_utf8_no_bom(agents_path, render_project_agents_md(display_name))
        created_files.append("AGENTS.md")

    if not design_path.exists():
        _write_utf8_no_bom(design_path, render_design_md(display_name, existing_wb))
        created_files.append("design.md")
    elif registered_wb:
        update_design_md_white_bg(design_path, registered_wb)

    parser_mod = _load_parser_module()
    effective_url = feishu_url
    effective_tokens = list(whiteboard_tokens or [])
    if sync and not effective_url and not effective_tokens and project_md_path.exists():
        extracted = parser_mod.extract_feishu_url_from_project_md(project_md_path.read_text(encoding="utf-8"))
        if extracted.startswith("whiteboard:"):
            effective_tokens = [t.strip() for t in extracted.split(":", 1)[1].split(",") if t.strip()]
        elif extracted:
            effective_url = extracted

    manifest_summary: dict[str, Any] | None = None
    if effective_url or effective_tokens:
        manifest, written_pm, _, _ = parser_mod.fetch_and_parse(
            url=effective_url,
            whiteboard_tokens=effective_tokens,
            project_root=project_root,
            default_ratio=default_ratio,
            download_assets=download_assets,
            all_doc_boards=all_doc_boards,
            write_project_md=True,
            sync_existing=sync,
        )
        if written_pm and existing_wb:
            _apply_white_bg_to_project_md(written_pm, existing_wb)
        manifest_summary = manifest.get("summaryCounts")
        if "project.md" not in created_files:
            created_files.append("project.md")
    elif not project_md_path.exists():
        _write_utf8_no_bom(
            project_md_path,
            render_empty_project_md(
                project_name=display_name,
                raw_photos=all_raw,
                white_bg_paths=existing_wb,
            ),
        )
        created_files.append("project.md")
    elif existing_wb:
        _apply_white_bg_to_project_md(project_md_path, existing_wb)

    hook_result: dict[str, Any] | None = None
    if host in ("codex", "zcode"):
        proc = subprocess.run(
            ["node", str(INSTALL_HOOK_SCRIPT), "--project-root", str(project_root), "--host", host],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"安装 {host} 上下文钩子失败：{(proc.stderr or proc.stdout).strip()}")
        try:
            hook_result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            hook_result = {"raw": proc.stdout.strip()}

    return {
        "ok": True,
        "projectRoot": str(project_root),
        "projectName": display_name,
        "createdOrUpdated": created_files,
        "movedRootImages": moved_raw,
        "whiteBgRefs": existing_wb,
        "feishuSummary": manifest_summary,
        "hook": hook_result,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键初始化或增量同步 DUMIK 项目文件夹（三文件闭环，零本地 JSON 尾气）。")
    parser.add_argument("--project-root", default=".", help="项目根目录路径（绝不嵌套创建子项目文件夹）")
    parser.add_argument("--project-name", default=None, help="项目显示名称，默认取文件夹名")
    parser.add_argument("--feishu-url", default=None, help="飞书 wiki / docx / whiteboard 策划链接")
    parser.add_argument("--whiteboard-token", action="append", default=[], help="直接指定飞书画板 token，可传多个")
    parser.add_argument("--download-assets", action="store_true", help="下载飞书画布有效参考图到 素材/飞书画布/")
    parser.add_argument("--sync", action="store_true", help="增量同步已有 project.md（保留已锁定/已定稿状态）")
    parser.add_argument("--white-bg", action="append", default=[], help="指定产品白底图路径，自动拷入 设定集/白底图/ 并写入 design.md")
    parser.add_argument("--no-organize-root-images", action="store_true", help="不自动把根目录散放图片移入 素材/实拍原图/")
    parser.add_argument("--default-ratio", default="9:16", help="默认生图画幅，默认 9:16")
    parser.add_argument("--all-doc-boards", action="store_true", help="拆解飞书文档内全部规划画布")
    parser.add_argument("--host", choices=("none", "codex", "zcode"), default="none", help="可选安装 Codex 或 ZCode 会话上下文钩子")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        res = init_project(
            project_root=Path(args.project_root),
            project_name=args.project_name,
            feishu_url=args.feishu_url,
            whiteboard_tokens=args.whiteboard_token,
            download_assets=bool(args.download_assets),
            sync=bool(args.sync),
            white_bg_inputs=args.white_bg,
            organize_root=not bool(args.no_organize_root_images),
            host=args.host,
            default_ratio=args.default_ratio,
            all_doc_boards=bool(args.all_doc_boards),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    try:
        scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import dumik_telemetry

        dumik_telemetry.report_event_async(event="invoke", skill="d-init", mode="sync" if args.sync else "init")
    except Exception:
        pass
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
