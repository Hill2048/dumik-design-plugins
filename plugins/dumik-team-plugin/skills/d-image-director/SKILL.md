---
name: d-image-director
description: "图片创作与修复总入口。统一普通改图、视觉 brief、四宫格发散、线稿色块高清重绘和产品局部修复；只写提示词时停在文字，明确生图时交给 d-image-runner。"
metadata:
  version: 0.1.0
---

# 图片导演

统一原 `D-image-prompt`、`D-image-HD`、`D-image-repair` 和 `D-grid-prompt` 的图片创作入口。

## 模式

- `edit`：普通改图、多参考融合、洗图、KV、场景、材质和人物锁定。
- `brief`：从零规划图片视觉方向；缺少产品策略时先回 `d-visual-plan`。
- `direction`：单卖点 2×2 四宫格探方向，选中后展开独立候选。
- `hd`：线稿 → 色稿 → 真实画面提示词 → 高清重绘。
- `repair`：只诊断和修复已选图片中真实存在的局部产品漂移。

## 共同规则

- 多参考图先短写每张图的真实职责；只出现实际存在并需要控制的内容。
- 采用最小充分描述：不补写画面里没有的人物、手部、食材、厨具、火焰、声音或其他道具，也不为不存在的对象添加负面词。
- 产品轮廓、比例、关键部件、材质和品牌区优先于风格描述。
- 只写提示词时不调用接口；明确生图、改图或批量生成时，将最终任务交给 `d-image-runner`。

## 模式资料

- `edit / brief`：按需读取 [references/legacy/D-image-prompt.md](references/legacy/D-image-prompt.md) 和 [references/templates.md](references/templates.md)。
- `direction`：按需读取 [references/legacy/D-grid-prompt.md](references/legacy/D-grid-prompt.md)。
- `hd`：按需读取 [references/legacy/D-image-HD.md](references/legacy/D-image-HD.md)，执行脚本位于 `scripts/hd/`。
- `repair`：按需读取 [references/legacy/D-image-repair.md](references/legacy/D-image-repair.md)，局部脚本位于 `scripts/repair/`。

统一输出比例、参考图职责、主指令和最小风险约束；不要让多个旧模式重复拼接整段提示词。
