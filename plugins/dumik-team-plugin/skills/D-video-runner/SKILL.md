---
name: D-video-runner
description: "视频生成执行入口。负责确认片、普通视频、深度视频和 Dreamina / Seedance / Veo 批量提交；上游必须已有完整提示词和参考素材。"
metadata:
  version: 0.1.0
---

# 视频执行器

统一视频生成提交入口，保留原 `D-video-run` 的确认片和批量闸门。

## 规则

- 只有用户明确说生成、出确认片、批量提交或调用视频模型时才执行。
- 上游必须提供比例、时长、完整提示词、首帧/参考素材和输出路径。
- 默认先生成 1 条确认片；用户确认后才进入批量。
- 支持普通参考视频、`depth_video`、Dreamina / Seedance / Veo；具体参数以当前 CLI 或接口帮助为准。
- 不负责策略、视频分析或故事板；分别交给 `D-visual-plan` 或 `D-video-director`。

完整执行规则保存在 [references/legacy/D-video-run.md](references/legacy/D-video-run.md)，脚本位于 `scripts/`。
