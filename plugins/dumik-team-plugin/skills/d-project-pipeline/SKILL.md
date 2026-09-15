---
name: d-project-pipeline
description: "成组图片任务的执行编排。按项目 AGENTS.md 给定的协作与确认安排组织任务、并发、恢复和交付，不重新定义设计判断；只在用户明确要求批量或自动串跑时使用。"
metadata:
  version: 0.1.0
---

# 项目流水线

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

成功时静默继续。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

本 skill 提供批量组织与断点恢复方法，不是项目总控。策略、确认节点、反馈范围和交付标准由项目 `AGENTS.md` 与当前任务给定。

## 编排方法

1. 把本次已明确的画面需求整理为独立任务，保留各自输入、输出名和依赖。
2. 缺少本次确需的策略或提示词时，调用对应专业方法，不重做已经确定的阶段。
3. 将依赖已满足且获准执行的任务交给 `d-image-runner`，记录状态，恢复时先核实已有提交。
4. 依据项目总控给出的留用、修复或重做决定推进相应任务；互不依赖的部分无需全量等待。
5. 按项目确认结果交付。是否先试跑、展示几张、在哪里等待，不由本 skill 固定规定。

只在用户明确说项目制、批量、自动串跑或 Agent 模式时进入；普通单图任务回到 `d-image-director`。

任务状态与批量执行方法见 [references/legacy/D-detail-auto.md](references/legacy/D-detail-auto.md)。
