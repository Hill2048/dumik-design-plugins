---
name: d-video-runner
description: "视频生成执行入口。负责确认片、普通视频、深度视频和 Dreamina / Seedance / Veo 批量提交；上游必须已有完整提示词和参考素材。"
metadata:
  version: 0.1.1
---

# 视频执行器

图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)，统一为 `@图1` 等。提交前核对图片顺序与素材映射；如平台需要专用标记，仅在执行适配层按实际绑定转换，不能改动素材职责或模型参数。

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一视频生成提交入口。项目 `AGENTS.md` 决定是否需要确认片、确认时机及批量范围；本 skill 只负责执行资料与参数检查、提交和收取结果，不重新定义协作流程。

## 规则

- 只有用户明确说生成、出确认片、批量提交或调用视频模型时才执行。
- 上游必须提供比例、时长、完整提示词、首帧/参考素材和输出路径。
- 按项目给定的确认安排组织试片或批量；仍需确认的任务等待，已经满足的确认不重复执行。
- 支持普通参考视频、`depth_video`、Dreamina / Seedance / Veo；具体参数以当前 CLI 或接口帮助为准。
- 不负责策略、视频分析或故事板；分别交给 `d-visual-plan` 或 `d-video-director`。

## 核心编译器与执行边界

- 所有视频 `final_instruction` 都应来自 `d-video-director` 的专业编译方法，不再区分“普通模板”和“2.5 模板”。执行前核对本次授权、费用范围、真实素材与后端能力，不额外添加固定设计关卡。
- 模型、画幅、总时长、分辨率、帧率和声音开关放在页面/API 或任务行的 `execution_spec` 中，不写回 `final_instruction`；参考文件路径放在素材字段，不塞进 Prompt。
- Runner 根据目标模型做最后能力检查。Seedance 2.5、Dreamina 2.0 和 Veo 共享故事合同与素材职责，但不共享接口能力或参数范围。
- 用户要求真实提交 Seedance 2.5 时，先按最新 `dreamina <subcommand> -h` 或目标连接器确认 2.5 入口；不可用时报告执行能力缺口，不静默改投 2.0。
- 首帧/尾帧、关键帧、视频编辑和延长必须使用后端实际支持的对应接口；不能因为 Prompt 已经正确就宣称执行器支持。

完整执行规则保存在 [references/legacy/D-video-run.md](references/legacy/D-video-run.md)，脚本位于 `scripts/`。
