---
name: d-video-director
description: "视频导演与提示词编译总入口。统一视频提示词、已有视频分析、HTML 拉片报告、故事板、关键帧、深度视频和电影化运镜；只输出分析或提示词，不提交视频生成。"
metadata:
  version: 0.1.1
---

# 视频导演

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

成功时静默继续。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-video-report` 与 `D-storyboard` 的视频视觉入口。所有视频提示词先经过 Seedance 2.5 方法升级而来的核心编译器，再按目标模型做执行适配。

## 模式

- `analyze`：对真实视频做完整拉片、抽帧、音频/字幕核对、运镜轨迹、视差和非线性速度分析，并生成可复查 HTML 报告。
- `prompt`：默认提示词模式。把文字和可选多模态素材编译成单条干净 Prompt，再按目标模型输出独立执行参数。
- `storyboard`：输出连续分镜、关键帧、逐镜生视频提示词和产品身份锚点。
- `depth`：把深度视频的空间、遮挡、构图和运动转译成真实场景，不继承深度图外观。
- `cinematic`：在产品真实结构和卖点成立的前提下加入电影调度、物理光色和复合摄影机轨迹。
- `seedance25`：`prompt` 的兼容别名；明确目标为 Seedance 2.5 时启用 2.5 模型适配器。

## 规则

- 有真实参考视频时先完整分析，再写基于该视频的最终提示词；看不清、听不清的内容不编造。
- 运镜写实体位移、同步旋转/推进、视差和速度曲线，不把复合运动粗化成单一“拉近”。
- 先判断视频的核心表达，再把画面与运镜作为同一条表达链分析。每个时间段同时记录：主体关系、构图重心、摄影机实体位移、元素自身运动、焦距变化、视线落点，以及这组变化服务的产品证据或叙事信息。焦距、机位和元素运动是不同变量，分别描述并标明是否同步，不能互相替代。
- 提示词只写视频和参考图中真实存在且需要控制的对象，不补写不存在的人物、道具、动作或声音。
- 本 skill 不提交生视频；明确生成时交给 `d-video-runner`。
- 任何写、改、补全或返修视频提示词的任务，都必须先读 `references/seedance25-prompt-compiler.md`。核心先完成“故事合同 → 素材职责 → 主任务路由 → 阶段/关键帧 → 镜头与声音 → 最终 Prompt”，再叠加当前模式资料和目标模型适配器。
- 核心编译器的规则优先于旧模板；模式资料只补充产品、故事板、深度、电影调度或执行细节，不能覆盖故事合同、素材映射、参数分离和输出合同。
- `analyze` 只做证据报告时无需加载核心编译器；一旦同时交付最终提示词，就必须加载。
- 画幅、总时长、分辨率、帧率、模型和声音开关统一作为执行参数，不写进 `final_instruction`。未明确目标模型时只产出模型中立 Prompt，不擅自切换模型。

## 模式资料

- `analyze`：读取 `references/report-data-schema.md`、`references/interactive-report.md`，脚本位于 `scripts/`，报告模板位于 `assets/report-template/`。
- `prompt / storyboard / depth / cinematic / seedance25`：先读取 `references/seedance25-prompt-compiler.md`。
- `storyboard` 再按需读取 `references/templates.md`、`references/seedance-image-to-video.md`、`references/seedance-storyboard-driven.md`。
- `depth` 再读取 `references/depth-video.md`；`cinematic` 再读取 `references/cinematic-commercial-staging.md` 与 `references/seedance-camera-codec.md`。
- 旧版完整规则保存在 `references/legacy/D-video-report.md` 和 `references/legacy/D-storyboard.md`，只用于追溯；其中的提示词格式不得覆盖核心编译器。
