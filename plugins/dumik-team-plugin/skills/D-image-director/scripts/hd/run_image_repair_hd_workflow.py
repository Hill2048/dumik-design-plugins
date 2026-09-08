#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


SKILLS_ROOT = Path(__file__).resolve().parents[3]
IMAGE_BATCH_SCRIPT = SKILLS_ROOT / "D-image-runner" / "scripts" / "generate_batch_images.py"


def run_command(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def build_lineart_prompt(subject_hint: str | None = None) -> str:
    parts = [
        "把原图转化为干净流畅的纯线稿，仅保留黑白两色。",
        "确保黑白层次清晰、线条干净、结构稳定、边缘明确。",
        "去除多余杂色、灰脏感、渐变和脏污纹理。",
        "保持原图主体造型、比例、透视、结构关系不变。",
        "不要上色，不要阴影，不要材质纹理，只输出高清黑白线稿。",
    ]
    if subject_hint:
        parts.append(f"主体补充说明：{subject_hint.strip()}。")
    return "".join(parts)


def build_color_draft_prompt(subject_hint: str | None = None) -> str:
    parts = [
        "把原图转化为干净平整的固有色色稿，只保留画面中各物体本身的固有色和清晰色块关系。",
        "确保不同物体之间的固有色对比和前后层次明确，色块边界贴合原图轮廓。",
        "去除多余杂色、渐变、阴影、高光、反射、纹理、噪点和灰脏感。",
        "保持原图主体造型、比例、透视、构图、物体位置和遮挡关系不变。",
        "不要线稿，不要明暗塑形，不要新增或删除物体，只输出纯色块色稿。",
    ]
    if subject_hint:
        parts.append(f"主体补充说明：{subject_hint.strip()}。")
    return "".join(parts)


def build_final_prompt(scene_prompt: str) -> str:
    return (
        "图片1是结构线稿，负责主体造型、轮廓、比例、透视、构图、物体位置和遮挡关系；"
        "图片2是固有色色稿，负责各物体的基础配色和色块边界。"
        "严格依据图片1还原结构，依据图片2恢复固有色，再根据下面的中文画面提示词重建真实材质、明暗和光影："
        f"{scene_prompt.strip()}\n"
        "最后生成一张高清、干净、无脏污、无灰感、边缘清晰、材质明确的最终图。"
        "约束：不要改变图片1的主体结构、比例、透视、构图和部件关系；"
        "不要改变图片2的物体固有色；不要新增、删除或替换物体；不要生成伪文字、脏边、噪点或塑料感。"
    )


def call_image_batch(
    *,
    image: Path,
    references: list[Path],
    prompt: str,
    image_model: str,
    output_size: str,
    out_path: Path,
) -> None:
    cmd = [
        sys.executable,
        str(IMAGE_BATCH_SCRIPT),
        "--image",
        str(image),
        "--prompt",
        prompt,
        "--image-model",
        image_model,
        "--output-size",
        output_size,
        "--out",
        str(out_path),
    ]
    for reference in references:
        cmd.extend(["--reference", str(reference)])
    run_command(cmd, cwd=IMAGE_BATCH_SCRIPT.parent)


def image2_safe_size(image_path: Path, long_edge: int = 2048) -> str:
    with Image.open(image_path) as image:
        width, height = image.size
    if width >= height:
        target_width = long_edge
        target_height = max(16, round(height * long_edge / width / 16) * 16)
        target_width = max(16, round(target_width / 16) * 16)
    else:
        target_height = long_edge
        target_width = max(16, round(width * long_edge / height / 16) * 16)
        target_height = max(16, round(target_height / 16) * 16)
    return f"{target_width}x{target_height}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 4-step HD repair workflow.")
    parser.add_argument("--image", required=True, help="Source image path.")
    parser.add_argument("--output-dir", required=True, help="Workflow output directory.")
    parser.add_argument(
        "--scene-prompt",
        help="Finished Chinese scene prompt describing the actual image content.",
    )
    parser.add_argument(
        "--reverse-prompt",
        help="Deprecated alias for --scene-prompt.",
    )
    parser.add_argument("--lineart-model", default="image2")
    parser.add_argument("--color-model", default="image2")
    parser.add_argument("--final-model", default="image2")
    parser.add_argument("--final-size")
    parser.add_argument("--blur-radius", type=float, default=10.0, help=argparse.SUPPRESS)
    parser.add_argument("--subject", help="Optional subject hint.")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_prompt = (args.scene_prompt or args.reverse_prompt or "").strip()
    if not scene_prompt:
        raise SystemExit(
            "Missing --scene-prompt: pass a finished Chinese description of the actual image, "
            "not an instruction asking another model to reverse-prompt it."
        )

    lineart_path = output_dir / "01-lineart.png"
    lineart_prompt_path = output_dir / "01-lineart-prompt.txt"
    color_draft_path = output_dir / "02-color-draft.png"
    color_prompt_path = output_dir / "02-color-draft-prompt.txt"
    scene_prompt_path = output_dir / "03-scene-prompt.txt"
    final_prompt_path = output_dir / "04-final-prompt.txt"
    final_image_path = output_dir / "05-final.png"
    run_record_path = output_dir / "repair-run.json"

    lineart_prompt = build_lineart_prompt(args.subject)
    lineart_prompt_path.write_text(lineart_prompt, encoding="utf-8")
    lineart_size = "source-2k"
    if args.lineart_model.lower() in {"image2", "gpt-image-2"}:
        lineart_size = image2_safe_size(image_path, long_edge=2048)
    call_image_batch(
        image=image_path,
        references=[],
        prompt=lineart_prompt,
        image_model=args.lineart_model,
        output_size=lineart_size,
        out_path=lineart_path,
    )

    color_prompt = build_color_draft_prompt(args.subject)
    color_prompt_path.write_text(color_prompt, encoding="utf-8")
    color_size = "source-2k"
    if args.color_model.lower() in {"image2", "gpt-image-2"}:
        color_size = image2_safe_size(image_path, long_edge=2048)
    call_image_batch(
        image=image_path,
        references=[],
        prompt=color_prompt,
        image_model=args.color_model,
        output_size=color_size,
        out_path=color_draft_path,
    )

    scene_prompt_path.write_text(scene_prompt, encoding="utf-8")

    final_prompt = build_final_prompt(scene_prompt)
    final_prompt_path.write_text(final_prompt, encoding="utf-8")

    final_size = args.final_size
    if not final_size and args.final_model.lower() in {"image2", "gpt-image-2"}:
        final_size = image2_safe_size(image_path, long_edge=2048)
    elif not final_size:
        final_size = "source-2k"

    call_image_batch(
        image=lineart_path,
        references=[color_draft_path],
        prompt=final_prompt,
        image_model=args.final_model,
        output_size=final_size,
        out_path=final_image_path,
    )

    run_record = {
        "image": str(image_path),
        "lineart_image": str(lineart_path),
        "lineart_prompt_file": str(lineart_prompt_path),
        "color_draft_image": str(color_draft_path),
        "color_draft_prompt_file": str(color_prompt_path),
        "scene_prompt_file": str(scene_prompt_path),
        "final_prompt_file": str(final_prompt_path),
        "final_image": str(final_image_path),
        "lineart_model": args.lineart_model,
        "color_model": args.color_model,
        "final_model": args.final_model,
        "final_size": final_size,
        "subject": args.subject or "",
    }
    run_record_path.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
