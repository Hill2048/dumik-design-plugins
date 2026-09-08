---
name: D-visual-plan
description: "图片详情页与电商视频的前置策划入口。按 image / video 模式规划视觉设定、卖点证据、创意方向或视频转化结构；只输出策划，不生成图片或视频。"
metadata:
  version: 0.1.0
---

# 视觉策划

统一图片和视频的策略入口，避免分别记忆 `D-detail-plan` 与 `D-video-plan`。

## 模式

- `image`：固化产品/场景视觉设定，规划详情页结构、卖点顺序、视觉证据和 3-4 个创意方向。需要四宫格或候选发散时，在本 skill 内继续进入 `direction` 子阶段，或交给 `D-image-director` 的 `direction` 模式。
- `video`：规划人群、痛点、卖点顺序、开头钩子、证据链、可见障碍和转化节奏。需要拆镜头时交给 `D-video-director`。

## 边界

- 只输出策略、视觉设定和结构，不调用图片或视频接口。
- 用户明确要求提示词时，图片交 `D-image-director`，视频交 `D-video-director`。
- 用户明确要求实际生成时，先完成对应提示词，再交给 `D-image-runner` 或 `D-video-runner`。
- 只写当前任务真实需要的主体、卖点和场景，不凭空补充画面元素。

## 输出

`image` 输出：项目视觉设定、详情页结构、卖点视觉证据、创意方向。

`video` 输出：目标人群、核心障碍、卖点顺序、证据链、开头钩子、节奏和下一步镜头需求。

详细旧规则保存在 [references/legacy/D-detail-plan.md](references/legacy/D-detail-plan.md) 和 [references/legacy/D-video-plan.md](references/legacy/D-video-plan.md)，只在对应模式需要时读取。
