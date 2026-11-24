# DUMIK 流程地图索引

项目 `AGENTS.md` 是日常协作与调度入口；`assets/agent-skill-routing.md` 是按需使用的能力目录，不覆盖项目定制。

## 生产入口

- `d-visual-plan`：需要时补充详情页或视频的卖点、视觉证据与策略，不重做已给定方案。
- `d-image-director`：普通改图、brief、四宫格、高清重绘、局部修复。
- `d-image-runner`：普通生图改图与 RunningHub 后处理。
- `d-video-director`：统一视频专业编译、分析、故事板、深度视频与导演调度，末端按目标模型适配。
- `d-video-runner`：按项目给定范围检查素材与参数，提交视频并保存结果。
- `d-project-pipeline`：按项目要求组织成组任务的依赖、并发、恢复与交付，不设置固定设计关卡。

## 支撑入口

- `d-init`：生成或维护项目入口；完整初始化时可登记项目级上下文钩子，不参与逐次调度。
- `d-api-test`：图片 API 基准测试。

## 已废弃入口（保留存档，默认不加载、不自动拉取）

- `d-psb-install`：PSB 智能对象工具已废弃并归档至 `archive/deprecated-psb-tools/`，不删除历史源码，不再参与自动路由，脚本默认也不再从 GitHub 拉取更新。

旧入口已归档到 `archive/merged-skills-legacy/`，不再参与自动路由。

`assets/workflow-map.html` 保留历史示意，不作为当前版本执行或确认规则。能力选择以 `agent-skill-routing.md` 为准，多轮恢复以 `task-state-contract.md` 为准；项目协作仍遵循项目 `AGENTS.md`。
