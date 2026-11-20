---
name: d-prompt-reverse
description: "反推参考图结构为可控草稿（须先由人判定主次与控制区，再交 d-image-director 编译终稿）。不直接当最终提示词也不调生图。"
metadata:
  version: 0.1.0
---

# 提示词反推（人判主次）

本 skill 把参考图拆成**可编辑的控制草稿**，不是自动生成可直接出片的最终 Prompt。

## 参考文件硬门槛

遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。必读：`references/reverse-protocol.md`。需要套用分段/六段时再读 `../d-image-director/references/prompt-segments.md` 与 `six-structure.md`（Grok Bot / Linux 直接 Read，可跳过 PowerShell 编译，不可跳过正文）。

## 会话级自动更新

Windows 可按插件惯例运行 `update_dumik_plugin.ps1`（同会话一次）。**Grok Bot / Linux** 跳过该脚本。

## 硬规则

1. **人先判主次**：先输出「主控制 / 次要 / 可忽略」三栏，再写 Prompt 草稿。用户未判且对话里也未指定时，先问 1–3 个关键优先级，禁止直接交长 Prompt 当完成。
2. **禁止一键交卷**：模型「根据图片生成提示词」的原始输出只能当素材，必须经主次过滤与控制区标注后才可称草稿完成。
3. **不默认终稿**：草稿交付须标注「待人确认优先级后，交 d-image-director 编译终稿」；用户明确「就按此终稿」且主次已判，才可格式化为 prompt-contract 终稿。
4. 不调用生图接口；不替代 `d-consistency-check`。

## 流程

1. 标明参考图 `@图N`。  
2. 人（或用户指令）填写主次与控制区/自由区。  
3. 按 `reverse-protocol.md` 拆：主体锁、光影、构图、材质、可迁移/不可迁移项。  
4. 输出结构化草稿 + 风险（易漂部件、乱字、广角等）。  
5. 用户确认后 → `d-image-director` 出符合合同的终稿 → 授权后 runner。

## 模式资料

- 必读：`references/reverse-protocol.md`
- 路由：`image.reverse`（见 `assets/agent-skill-routing.md`）
