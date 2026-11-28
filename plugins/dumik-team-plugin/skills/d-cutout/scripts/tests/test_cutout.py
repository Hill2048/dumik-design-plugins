#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import struct
import sys

import cv2
import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cutout  # noqa: E402


def _make_metallic_donut_with_specular(size: int = 240) -> np.ndarray:
    """
    构造经典测试图（纯白底）：
    - 深古铜金厚外环（含抗锯齿过渡）
    - 环壁内部带一条冲到 RGB(255,255,255) 的明亮银白金属高光带（外围被浅银灰 RGB(215) 包裹）
    - 中心有一个被深古铜内壁 360° 围住的真正纯白背景孔洞
    """
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    c = size // 2
    # 深古铜外环 (r=85)
    cv2.circle(img, (c, c), 85, (72, 54, 40), -1, lineType=cv2.LINE_AA)
    # 浅银灰金属机身 (r=74)
    cv2.circle(img, (c, c), 74, (215, 214, 212), -1, lineType=cv2.LINE_AA)
    # 金属机身顶部冲到纯白 RGB(255,255,255) 的高光斑（绝对不能被误抠！）
    cv2.ellipse(img, (c, c - 56), (26, 9), 0, 0, 360, (255, 255, 255), -1, lineType=cv2.LINE_AA)
    # 深古铜内壁 (r=38)
    cv2.circle(img, (c, c), 38, (64, 48, 36), -1, lineType=cv2.LINE_AA)
    # 真正的中心纯白背景孔洞 (r=28)
    cv2.circle(img, (c, c), 28, (255, 255, 255), -1, lineType=cv2.LINE_AA)
    return img


def test_solid_preserves_white_specular_and_punches_real_hole(tmp_path: Path) -> None:
    src = tmp_path / "donut.png"
    out = tmp_path / "donut_cut.png"
    prev = tmp_path / "donut_preview.png"
    Image.fromarray(_make_metallic_donut_with_specular()).save(src)

    res = cutout.process_one(src, out, mode="auto", crop=False, preview_path=prev, export_psd=True)
    assert res["ok"] is True
    assert res["engine"] == "solid"
    assert res["holes_punched"] == 1
    assert out.is_file()
    assert prev.is_file()
    assert Path(res["psd"]).is_file()

    rgba = np.array(Image.open(out).convert("RGBA"))
    c = 120
    # 1. 外部背景完全透明
    assert rgba[5, 5, 3] == 0
    # 2. 中心真孔洞完全透明
    assert rgba[c, c, 3] == 0
    # 3. 顶部 RGB(255,255,255) 金属高光必须 100% 不透明（绝不抠穿！）
    assert rgba[c - 56, c, 3] == 255
    # 4. 校验 PSD 头为 8BPS 4 通道 RGBA
    psd_bytes = Path(res["psd"]).read_bytes()
    assert psd_bytes[:4] == b"8BPS"
    channels = struct.unpack(">H", psd_bytes[12:14])[0]
    assert channels == 4


def test_no_white_halo_on_dark_background(tmp_path: Path) -> None:
    src = tmp_path / "circle.png"
    out = tmp_path / "circle_cut.png"
    img = np.full((180, 180, 3), 255, dtype=np.uint8)
    cv2.circle(img, (90, 90), 60, (48, 36, 28), -1, lineType=cv2.LINE_AA)
    Image.fromarray(img).save(src)

    res = cutout.process_one(src, out, mode="solid", crop=False)
    assert res["ok"] is True
    rgba = np.array(Image.open(out).convert("RGBA"))
    # 半透明边缘像素经过 Color Decontamination 后，不应残留亮白 RGB（均值应显著低于 140）
    semi = (rgba[:, :, 3] > 20) & (rgba[:, :, 3] < 235)
    assert np.any(semi)
    mean_edge_luma = float(rgba[:, :, :3][semi].mean())
    assert mean_edge_luma < 120.0


def test_complex_background_auto_rejects(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    noisy = rng.integers(20, 235, size=(160, 160, 3), dtype=np.uint8)
    src = tmp_path / "scene.png"
    Image.fromarray(noisy).save(src)

    res = cutout.process_one(src, mode="auto")
    assert res["ok"] is False
    assert res["status"] == "NEEDS_AI_MATTING"


def test_glass_and_shadow_modes(tmp_path: Path) -> None:
    # Glass mode: semi-transparent grey-tinted glass square on pure white
    src_g = tmp_path / "glass.png"
    out_g = tmp_path / "glass_cut.png"
    g = np.full((160, 160, 3), 255, dtype=np.uint8)
    g[40:120, 40:120] = (205, 208, 212)  # ~20% opacity glass body
    cv2.rectangle(g, (40, 40), (120, 120), (80, 82, 86), 2)
    Image.fromarray(g).save(src_g)

    res_g = cutout.process_one(src_g, out_g, mode="glass", crop=False)
    assert res_g["ok"] is True
    rgba_g = np.array(Image.open(out_g).convert("RGBA"))
    assert rgba_g[5, 5, 3] == 0
    # 玻璃内部应呈现半透明（非 0 非 255）
    assert 20 < int(rgba_g[80, 80, 3]) < 160

    # Shadow mode: dark object + soft drop shadow below on white
    src_s = tmp_path / "shadow.png"
    out_s = tmp_path / "shadow_cut.png"
    s = np.full((180, 180, 3), 255, dtype=np.uint8)
    cv2.ellipse(s, (90, 126), (48, 12), 0, 0, 360, (195, 195, 195), -1)
    s = cv2.GaussianBlur(s, (15, 15), 4.0)
    cv2.rectangle(s, (50, 45), (130, 120), (50, 40, 35), -1)
    Image.fromarray(s).save(src_s)

    res_s = cutout.process_one(src_s, out_s, mode="shadow", crop=False)
    assert res_s["ok"] is True
    rgba_s = np.array(Image.open(out_s).convert("RGBA"))
    assert rgba_s[80, 90, 3] == 255       # solid object
    assert 15 < int(rgba_s[128, 90, 3]) < 150  # soft preserved shadow
    assert rgba_s[5, 5, 3] == 0           # clean background


def test_manual_punch_and_keep(tmp_path: Path) -> None:
    src = tmp_path / "manual.png"
    out = tmp_path / "manual_cut.png"
    img = _make_metallic_donut_with_specular()
    Image.fromarray(img).save(src)

    # Keep the center hole manually -> should NOT punch it
    res = cutout.process_one(src, out, mode="solid", crop=False, keep_pts=[(120, 120)])
    assert res["ok"] is True
    rgba = np.array(Image.open(out).convert("RGBA"))
    assert rgba[120, 120, 3] == 255
