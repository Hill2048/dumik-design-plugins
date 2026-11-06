---
name: d-video-director
description: "编写和追改视频提示词、分镜、关键帧，分析真实视频并交付拉片或 HTML 报告；模型名不改变此入口。纯卖点排序交 d-visual-plan，实际视频提交交 d-video-runner。"
metadata:
  version: 0.1.5
---

# 视频导演

本 skill 提供分镜、动作、镜头、连续性和提示词的专业方法。任务协作、已有决定的适用范围、确认与反馈归属由项目 `AGENTS.md` 负责；下面的编译步骤不是额外的用户审批流程。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加本次模式命中的条件文件；只有命中文件进入当前正文，读取完整规则包后才能分析视频、设计镜头或写 Prompt。不能只看文件名、链接、摘要或上一次对话内容。

先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-video-director -Mode <prompt|storyboard|image-to-video|depth|camera|report|interactive>`，再读取脚本返回的 `output_path`。规则包没有成功生成或没有读完时，不分析素材、不写最终 Prompt、不输出报告。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-video-report` 与 `D-storyboard` 的视频视觉入口。`prompt` 是唯一提示词编译主线；Seedance 2.5、Dreamina / Seedance 2.0 和 Veo 只在编译末端做模型适配，不再各自形成提示词模式。

## 唯一主线

按 [插件路由](../../assets/agent-skill-routing.md) 选择交付；连续追改按 [任务状态合同](../../assets/task-state-contract.md) 合并有效决定。切换模型仅做能力适配，不重设故事、参考职责或执行授权。

任何写、改、补全或返修视频提示词的任务，都按同一条链处理：

```text
目标与证据 → 故事合同 → 素材职责 → 内容设计与导演调度
→ 主任务与事件结构 → 镜头、声音和关键状态 → 最终 Prompt → 模型适配
```

1. 先确认视频要让观众理解、相信或记住什么；有真实视频时先取得可验证证据，看不清、听不清的内容不编造。
2. 锁定人物、产品、道具、场景、数量、关系、因果和起止状态，再逐份定义素材职责。
3. 每个画面先形成一句可拍的镜头命题，再依次判断观众位置、构图压力、视线入口与落点、主体动作、摄影机响应、物理光色、信息密度、节奏和连续性。摄影机运动必须由信息揭示、关系变化或产品证据触发；没有运动理由时使用克制静镜，不为“高级感”强加复杂运镜。
4. 把事件和镜头编译成一条干净 Prompt；产品任务先保证同一 SKU、结构、材质、关键部件和卖点证据，再决定风格强度。
5. 最后才按目标模型删减不支持的能力并整理独立执行参数，不得改写故事合同或素材映射。

## 输入与交付变化

下面三项不是独立提示词模式，只改变证据来源或交付结构：

- **已有视频分析**：作为统一主线的证据阶段，核对抽帧、音频/字幕、主体关系、镜头轨迹、视差和非线性速度。用户只要拉片报告时可在证据阶段结束并生成 HTML；还要提示词时继续走同一主线。
- **故事板**：在同一故事合同和导演调度上，把最终内容拆成连续分镜、关键帧、逐镜生视频提示词和必要的产品身份锚点；不是另一套创作逻辑。
- **深度视频**：只改变某份参考素材的职责。深度视频控制空间、姿态、位置、遮挡、构图、动作时序和摄影机轨迹，图片与文字控制身份、产品、材质、颜色、环境和光线；随后继续走同一主线。

## 共同规则

- 图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)，包括视频提示词和关键帧说明；统一使用 `@图1` 等，保留视频、音频各自引用类型。

- 先判断核心表达，再把主体关系、画面设计、摄影机与元素运动写成同一条证据或叙事链。
- 产品证明镜头先锁定不变量、变化量和可见结果；构图用不变量建立参照，用变化量制造压力，结束画面必须让结果无需文案也能读懂。
- 焦距、机位、摄影机实体位移和元素自身运动是不同变量，分别描述并标明是否同步；复合轨迹不能粗化成“镜头拉近”。
- 提示词只写素材中真实存在或用户明确要求且需要控制的对象，不补写无关人物、道具、动作或声音。
- 画幅、总时长、分辨率、帧率、模型和声音开关统一进入 `execution_spec`，不写进 `final_instruction`。
- 本 skill 不提交生视频；用户明确生成时，把最终 Prompt、素材清单和执行规格交给 `d-video-runner`。

## 资料路由

所有视频任务先核对本 skill 全部参考文件的登记，再读 `references/prompt-compiler.md` 和 `references/directing-design.md` 的正文；然后按任务追加并完整读取命中文件：

- 提示词构造方法论（MCSLA 五层、I2V 规则、身份块与动作块分离、角色资产家族、场景锚定、禁令字典、单变量迭代、6 轮诊断、反套话、镜头语言硬规则）：`references/video-methodology-mcsla.md`，所有提示词任务都读。
- 分镜与序列组织（三层结构、15 秒信封、密度判断、节奏预算算术、单调性审计、双对比切镜、连续性清单、交付前导演门禁）：`references/video-directing-shotlist.md`，写分镜、镜头表、多镜序列时读。
- 表演与故障诊断（五根柱子、从结局命名事件、眼睛必须有生命、状态而非过渡、失败模式表、帧级复核）：`references/video-acting-and-failure-modes.md`，有人物表演或需要诊断画面问题时读。
- 已有视频分析或 HTML 报告：`references/report-data-schema.md`；需要交互回看时再读 `references/interactive-report.md`，脚本和模板按文件说明读取。
- 故事板、关键帧或逐镜提示词：`references/templates.md`、`references/seedance-image-to-video.md`、`references/seedance-storyboard-driven.md`。
- 深度视频：`references/depth-video.md`。
- 需要精确复合摄影机轨迹：`references/seedance-camera-codec.md`。
- 只追溯旧规则时：明确读取对应的 `references/legacy/` 文件，但旧规则不能覆盖统一主线。

没有完成上述 `reference_set` 的实际读取时，停在准备阶段，不输出最终 Prompt、分镜或 HTML 报告，也不交给 `d-video-runner`。
