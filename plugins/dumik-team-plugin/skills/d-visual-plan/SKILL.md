---
name: d-visual-plan
description: "规划详情页结构、卖点顺序、视觉证据与视频转化策略。单图材质或颜色追改不重新策划；图片提示词交 d-image-director，视频分镜与提示词交 d-video-director，不执行生成。"
metadata:
  version: 0.1.4
---

# 视觉策划

点名图片素材时遵循 [图片引用格式](../../assets/image-reference-format.md)，统一为 `@图1` 等；策划序号、模块序号与图片引用分开。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加本次图片、视频或 Seedance 模式命中的条件文件；只有命中文件进入当前正文，读取完整规则包后才能输出策略结论。

先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-visual-plan -Mode <image|video|seedance>`，再读取脚本返回的 `output_path`。规则包没有成功生成或没有读完时，不输出策略结论。

本 skill 是按需使用的策略方法，不是项目必经入口。是否探索、复用哪些决定、怎样确认与回写，均由项目 `AGENTS.md` 决定；已有策略作为输入，不重新策划。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一图片和视频的策略入口，避免分别记忆 `D-detail-plan` 与 `D-video-plan`。

## 模式

按 [插件路由](../../assets/agent-skill-routing.md) 处理明确的策略需求或专业入口指出的必要策略缺口；单图追改保持原路线，不因出现“质感、创意”就重开策划。多轮决定按 [任务状态合同](../../assets/task-state-contract.md) 维护。

- `image`：针对本次策略缺项整理详情页结构、卖点顺序、视觉证据或表达方向，不规定方向数量；需要画面展开时使用 `d-image-director`。
- `video`：规划人群、痛点、卖点顺序、开头钩子、证据链、可见障碍和转化节奏。需要拆镜头时交给 `d-video-director`。

## 边界

- 只输出策略、视觉设定和结构，不调用图片或视频接口。
- 用户明确要求提示词时，图片交 `d-image-director`，视频交 `d-video-director`。
- 用户明确要求实际生成时，先完成对应提示词，再交给 `d-image-runner` 或 `d-video-runner`。
- 只写当前任务真实需要的主体、卖点和场景，不凭空补充画面元素。
- 白底图只能用于确认产品外观、结构、颜色、丝印和配件关系；不得据此填写或推断场景、台面、背景道具、整体风格、光线、色温、构图、机位、文案排版等“统一视觉方向”。缺方向素材时保留待确认，不用白底棚拍表现代填。

## 输出

`image` 输出：项目视觉设定、详情页结构、卖点视觉证据、创意方向。

`video` 输出：目标人群、核心障碍、卖点顺序、证据链、开头钩子、节奏和下一步镜头需求。

详细规则保存在 [references/legacy/D-detail-plan.md](references/legacy/D-detail-plan.md) 和 [references/legacy/D-video-plan.md](references/legacy/D-video-plan.md)，进入对应模式时必须读取，不得只看链接或依赖旧上下文。
