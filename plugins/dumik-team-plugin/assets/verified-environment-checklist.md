# DUMIK 插件已检查清单

检查时间：2026-09-08（Asia/Shanghai）

适用版本：

- 插件版本：`0.1.6`
- 当前生产 skill：`9` 个（6 个生产入口 + 3 个支撑入口）
- 详细版本：`assets/skill-versions.json`
- 统一路由：`assets/agent-skill-routing.md`
- 流程地图：`assets/workflow-map.md`

## 本次合并结果

- 图片策划与视频策划合并为 `d-visual-plan`。
- 普通改图、四宫格、高清修复和局部修复合并为 `d-image-director`。
- 图片生成与 RunningHub 后处理合并为 `d-image-runner`。
- 视频拉片、HTML 报告、故事板、深度视频和电影运镜合并为 `d-video-director`。
- 视频确认片与批量生成统一为 `d-video-runner`。
- 详情页项目制自动串跑统一为 `d-project-pipeline`。
- `d-init`、`d-api-test`、`d-psb-install` 保留为支撑入口。
- 旧 skill 已移动到 `archive/merged-skills-legacy/`，不再参与自动发现和新任务路由。

## 已完成检查

- 新生产 skill 均有 `SKILL.md` 和 `agents/openai.yaml`。
- 源目录和本机缓存已同步新的 skill 目录与模式名称。
- 图片、视频执行脚本和报告模板已合并到对应新入口的资源目录。
- 统一路由、README、流程地图、插件清单和版本清单已改用新名称。
- `d-image-director` 与 `d-video-director` 保留旧模式文档作为可按需读取的 legacy references。
- 参考素材“存在性优先、最小充分描述”规则已保留在图片和视频 director 入口。
- `git diff --check` 已通过。

## 未在本次执行的项目

- 未运行真实图片或视频生成任务。
- 未执行 Dreamina、RunningHub 或外部 API 提交。
- 未推送 GitHub，也未发布新的插件版本。

## 后续调用规则

- 只要用户要文字提示词，停在 `d-visual-plan` 或对应 director，不调用 runner。
- 只有用户明确要求生成、出图、出片、提交或批量，才进入 runner。
- 有真实参考视频时，先用 `d-video-director` 的 `analyze` 模式，再写故事板或深度视频提示词。
- 项目制详情页任务才进入 `d-project-pipeline`。
