# DUMIK Team Plugin 0.1.5 更新公告

本次更新完成图片与视频工作流的入口合并，减少重复 skill，统一路由、执行边界和参考素材规则。

## 主要更新

- 图片与视频流程从 15 个活动入口收敛为 9 个活动入口：6 个生产入口、3 个支撑入口。
- `D-detail-plan` 与 `D-video-plan` 合并为 `D-visual-plan`，统一图片详情页策划和视频转化策划。
- `D-image-prompt`、`D-image-HD`、`D-image-repair` 与 `D-grid-prompt` 合并为 `D-image-director`。
- `D-image-run` 与 `D-rh` 合并为 `D-image-runner`，统一生图、并发候选与 RunningHub 后处理。
- `D-video-report` 与 `D-storyboard` 合并为 `D-video-director`，统一拉片、HTML 报告、故事板、深度视频和复合运镜。
- `D-video-run` 统一为 `D-video-runner`，保留确认片优先和批量生成闸门。
- `D-detail-auto` 统一为 `D-project-pipeline`，承接项目制 pilot、方向确认、批量生成、局部修复和终审。
- 原 12 个旧入口及其资源完整归档到 `archive/merged-skills-legacy/`，用于追溯，不再作为新任务入口。
- 图片和视频提示词统一采用“存在性优先、最小充分描述”：不补写画面中不存在的主体、动作、道具、声音，也不为不存在的对象添加负面约束。
- 源仓库与本机插件缓存完成同步，旧入口引用全部切换到新的合并入口。

## 验证

- 图片批处理与深度视频单元测试：`4 passed`。
- Python 编译检查、Node 脚本语法检查、JSON 解析和 `git diff --check`：通过。
- 活动 skill 数量：9 个；源仓库与本机缓存文本/配置一致。

市场发布标签：`0.1.5`；插件包内部版本保持 `0.5.22`。
