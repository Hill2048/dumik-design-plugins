# DUMIK 流程地图索引

权威路由只看 `assets/agent-skill-routing.md`。

## 生产入口

- `d-visual-plan`：图片详情页与视频转化策划。
- `d-image-director`：普通改图、brief、四宫格、高清重绘、局部修复。
- `d-image-runner`：普通生图改图与 RunningHub 后处理。
- `d-video-director`：以 Seedance 2.5 内核统一编译视频提示词，再叠加视频分析、故事板、深度视频和电影化运镜。
- `d-video-runner`：确认片与批量视频生成提交。
- `d-project-pipeline`：详情页项目制 pilot、校准、批量、修复和终审。

## 支撑入口

- `d-init`：工作台初始化。
- `d-api-test`：图片 API 基准测试。
- `d-psb-install`：PSB 工具安装与更新。

旧入口已归档到 `archive/merged-skills-legacy/`，不再参与自动路由。

可视化地图在 `assets/workflow-map.html`，执行时以统一路由文件为准。
