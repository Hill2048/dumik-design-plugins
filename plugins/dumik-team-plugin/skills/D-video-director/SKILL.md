---
name: D-video-director
description: "视频导演总入口。统一已有视频分析、HTML 拉片报告、故事板、关键帧、深度视频和电影化运镜提示词；只输出分析或提示词，不提交视频生成。"
metadata:
  version: 0.1.1
---

# 视频导演

统一原 `D-video-report` 与 `D-storyboard` 的视频视觉入口。

## 模式

- `analyze`：对真实视频做完整拉片、抽帧、音频/字幕核对、运镜轨迹、视差和非线性速度分析，并生成可复查 HTML 报告。
- `storyboard`：输出连续分镜、关键帧、逐镜生视频提示词和产品身份锚点。
- `depth`：把深度视频的空间、遮挡、构图和运动转译成真实场景，不继承深度图外观。
- `cinematic`：在产品真实结构和卖点成立的前提下加入电影调度、物理光色和复合摄影机轨迹。

## 规则

- 有真实参考视频时先完整分析，再写基于该视频的最终提示词；看不清、听不清的内容不编造。
- 运镜写实体位移、同步旋转/推进、视差和速度曲线，不把复合运动粗化成单一“拉近”。
- 先判断视频的核心表达，再把画面与运镜作为同一条表达链分析。每个时间段同时记录：主体关系、构图重心、摄影机实体位移、元素自身运动、焦距变化、视线落点，以及这组变化服务的产品证据或叙事信息。焦距、机位和元素运动是不同变量，分别描述并标明是否同步，不能互相替代。
- 提示词只写视频和参考图中真实存在且需要控制的对象，不补写不存在的人物、道具、动作或声音。
- 本 skill 不提交生视频；明确生成时交给 `D-video-runner`。

## 模式资料

- `analyze`：读取 `references/report-data-schema.md`、`references/interactive-report.md`，脚本位于 `scripts/`，报告模板位于 `assets/report-template/`。
- `storyboard / depth / cinematic`：按需读取 `references/templates.md`、`references/depth-video.md`、`references/seedance-camera-codec.md` 及其他对应参考。
- 旧版完整规则保存在 `references/legacy/D-video-report.md` 和 `references/legacy/D-storyboard.md`。
