# DUMIK 流程地图索引

项目 `AGENTS.md` 是日常协作与调度入口；`assets/agent-skill-routing.md` 是按需使用的能力目录，不覆盖项目定制。

## 生产入口

- `d-visual-plan`：需要时补充详情页或视频的卖点、视觉证据与策略，不重做已给定方案。
- `d-image-director`：普通改图、brief、四宫格、高清重绘、局部修复。
- `d-food-drink-stylist`：食饮与锅具王牌配菜本体造型与 3×3 高清垫图拆格（零光影/相机越权）。
- `d-brand-badge` / `d-badge-wash`：DUMIK 品牌 3D 扁六边形徽章设计 / 原外形小件脱壳洗材质。
- `d-prompt-reverse`：参考图反推可控结构化提示词草稿。
- `d-image-runner`：普通生图改图与 RunningHub 后处理。
- `d-video-director`：统一视频专业编译、分析、故事板、深度视频与导演调度，末端按目标模型适配。
- `d-video-runner`：按项目给定范围检查素材与参数，提交视频并保存结果。
- `d-project-pipeline`：按项目要求组织成组任务的依赖、并发、恢复与交付，不设置固定设计关卡。

## 验收与审查入口

- `d-consistency-check`：单张 AI 无字底图对照产品白底图的结构/外观/无字纯净度三态验收。
- `d-detail-review`：已排版详情页长图/主图终稿六维审查（对照飞书策划原图、规格真源与广告法合规，违禁/合规红灯），输出落 `成品/审稿报告/` 的悬浮连线 HTML 审稿台与红框标注大图。

## 支撑入口

- `d-init`：生成或维护项目入口；完整初始化时可登记项目级上下文钩子，不参与逐次调度。
- `d-api-test`：图片 API 基准测试。

## 已废弃入口（保留存档，默认不加载、不自动拉取）

- `d-psb-install`：PSB 智能对象工具已废弃并归档至 `archive/deprecated-psb-tools/`，不删除历史源码，不再参与自动路由，脚本默认也不再从 GitHub 拉取更新。

旧入口已归档到 `archive/merged-skills-legacy/`，不再参与自动路由。

`assets/workflow-map.html` 保留历史示意，不作为当前版本执行或确认规则。能力选择以 `agent-skill-routing.md` 为准，多轮恢复以 `task-state-contract.md` 为准；项目协作仍遵循项目 `AGENTS.md`。
