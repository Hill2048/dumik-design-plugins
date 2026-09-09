---
name: d-video-runner
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
- 不负责策略、视频分析或故事板；分别交给 `d-visual-plan` 或 `d-video-director`。

## 核心编译器与执行边界

- 所有视频 `final_instruction` 都应来自 `d-video-director` 的核心提示词编译器，不再区分“普通模板”和“2.5 模板”。执行前仍必须经过额度提示、确认片和批量闸门。
- 模型、画幅、总时长、分辨率、帧率和声音开关放在页面/API 或任务行的 `execution_spec` 中，不写回 `final_instruction`；参考文件路径放在素材字段，不塞进 Prompt。
- Runner 根据目标模型做最后能力检查。Seedance 2.5、Dreamina 2.0 和 Veo 共享故事合同与素材职责，但不共享接口能力或参数范围。
- 用户要求真实提交 Seedance 2.5 时，先按最新 `dreamina <subcommand> -h` 或目标连接器确认 2.5 入口；不可用时报告执行能力缺口，不静默改投 2.0。
- 首帧/尾帧、关键帧、视频编辑和延长必须使用后端实际支持的对应接口；不能因为 Prompt 已经正确就宣称执行器支持。

完整执行规则保存在 [references/legacy/D-video-run.md](references/legacy/D-video-run.md)，脚本位于 `scripts/`。
