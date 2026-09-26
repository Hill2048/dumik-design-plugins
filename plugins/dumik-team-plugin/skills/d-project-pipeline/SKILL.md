---
name: d-project-pipeline
description: "编排成组图片的跨步骤依赖、自动串跑和流水线恢复。只批量写提示词仍交 d-image-director，单纯生成多个候选交 d-image-runner；项目制本身不触发生成或固定确认关卡。"
metadata:
  version: 0.1.3
---

# 项目流水线

所有任务行中的图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)，统一为 `@图1` 等；每条任务单独核对图片顺序，不沿用另一任务的编号映射。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加当前项目状态和任务命中的导演/Runner 规则；只有命中文件进入当前正文，读取完整规则包后才能创建任务行、推进状态、提交执行或恢复断点。

进入流水线前先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-project-pipeline -Mode <image|video|mixed>`，再读取脚本返回的 `output_path`。导演和 Runner 的任务包仍需按各自 skill 重新编译，不能把流水线包当成执行包。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

本 skill 提供批量组织与断点恢复方法，不是项目总控。策略、确认节点、反馈范围和交付标准由项目 `AGENTS.md` 与当前任务给定。

## 编排方法

1. 把本次已明确的画面需求整理为独立任务，保留各自输入、输出名和依赖。
2. 缺少本次确需的策略或提示词时，调用对应专业方法，不重做已经确定的阶段。
3. 将依赖已满足且获准执行的任务交给 `d-image-runner`，记录状态，恢复时先核实已有提交。
4. 依据项目总控给出的留用、修复或重做决定推进相应任务；互不依赖的部分无需全量等待。
5. 按项目确认结果交付。是否先试跑、展示几张、在哪里等待，不由本 skill 固定规定。

按 [插件路由](../../assets/agent-skill-routing.md) 判断是否需要跨步骤执行编排，不凭“项目制、批量、Agent”单个词触发。按 [任务状态合同](../../assets/task-state-contract.md) 复用现有 `run-state.json` 保存有效决定，不维护两套状态。

任务状态与批量执行方法见 [references/legacy/D-detail-auto.md](references/legacy/D-detail-auto.md)，进入流水线前必须完整读取；任务行引用的导演和 runner 规则也必须沿引用链读取。
