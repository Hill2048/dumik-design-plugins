#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


DEFAULT_ROOT = Path.cwd()


def clean_name(value: str) -> str:
    value = value.strip() or "视频项目"
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "视频项目"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create consistent DUMIK project folders without nested timestamps.")
    parser.add_argument("--project-name", help="Chinese project name.")
    parser.add_argument(
        "--root",
        default=None,
        help="Optional parent directory when creating by --project-name.",
    )
    parser.add_argument(
        "--output-path",
        help="Exact confirmed project folder. Overrides --project-name and --root.",
    )
    args = parser.parse_args()

    if args.output_path:
        project_dir = Path(args.output_path).resolve()
    elif args.project_name and args.root:
        project_dir = Path(args.root).resolve() / clean_name(args.project_name)
    else:
        parser.error("请传入明确的 --output-path 项目文件夹路径（或同时传入 --project-name 与 --root）。")

    folders = (
        "素材/实拍原图",
        "设定集/白底图",
        "设定集/里程碑",
        "设定集/必渲特写",
        "制作",
        "成品/详情_790xn",
        "成品/主图_3x4",
        "成品/入口与SKU_1x1",
        "成品/视频",
    )
    for folder_name in folders:
        (project_dir / folder_name).mkdir(parents=True, exist_ok=True)

    print(project_dir)
    for folder_name in folders:
        print(project_dir / folder_name)


if __name__ == "__main__":
    main()
