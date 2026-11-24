# DUMIK 团队视觉工作流（Antigravity 全局规则）

- 插件根目录：`C:\Users\admin\.gemini\config\plugins\dumik`（实时映射 `plugins\dumik-team-plugin`），已启用 `hooks.json` 生命周期检查；详细路由表见 `assets/agent-skill-routing.md`。

## 一、技能按需激活表（禁止绕开 Skill 硬干）

| 用户需求 | 激活 Skill | 关键动作 |
| --- | --- | --- |
| 新建项目目录、关联/增量同步飞书（`--sync`）、改项目规约 | `d-init` | 先要飞书链接；跑 `init_dumik_project.py`，生成三文档后抛场景拍板清单；`AGENTS.md` 仅 `@` 内联 `design.md`（防超 24KB 截断，`project.md` 按需查阅） |
| 飞书拆解策划、卖点去重翻译、全页场景与人物判定 | `d-visual-plan` | 提炼每屏核心物理证明与场景错峰矩阵；纯报告/规格屏标 `无需生图（后期排版）` |
| 写/改里程碑或详情主图 `prompt.md`、四宫格/高清重绘/局部修复 | `d-image-director` | `detail` 模式跑 `compile_reference_pack.ps1`；覆盖写入 `制作/<编号_名称>/prompt.md`；不触发付费生图 |
| 明确下令生成/出图/重抽/放大/抠图（或按波次批量跑与晋升定稿） | `d-image-runner` / `d-project-pipeline` | 区分 **DesignFlow 模式（默认，画布在线）** 与 **API 直连模式（离线/指定兜底）**：DesignFlow 走 `designflow_generate_image`（同提示词多张单节点传 `count: 1..4`；同词多模型/跨渠道如 `banana2.1` + `bananapro` **只调 1 次传 `models: [...]` 并发**，严禁分两次调用或拆节点；多屏批量传 `items` 并发，`designflow_export_image` 落盘）；API 直连走 `build_canvas_pipeline.py --engine api --execute` 经 `%TEMP%\dumik-runs\` 拆 `count: 1` 并发；默认锁定 **`Banana 2.1` · `9:16` · `2K` · `x2`**，非明确申明不切模型 |
| 对照白底图做结构与画面纯净度审稿 | `d-consistency-check` | 输出一致/不一致/无法判断三态表 |
| 从参考图反推结构化草稿 / 视频分镜与生成 | `d-prompt-reverse` / `d-video-director` / `d-video-runner` | 反推先人判主次；视频提及模型名不代表生图授权 |

## 二、全案不可破底线

1. **纯无字底图 + 真实参考隔离**：除产品本体原生丝印/刻字或用户明确指定画内结构字外，严禁标题、卖点字、标尺、引线、圆框；带水印/UI 的 `素材/飞书画布/` 截图仅作写词前看图用，**严禁喂入 API**；实景生活屏优先直垫干净真机实拍图，**凡出现任何人物（含仅露手/腕/袖/肩背特写）必须无例外垫入人物身份卡**。
2. **零本地运行垃圾**：项目内禁止落盘 `.json` 队列、`拆解清单.md`、`.pytest_cache` 或 `运行记录`；生图结束立刻 `--status` 同步 `project.md` 并清理 `%TEMP%\dumik-runs\`。
3. **授权与汇报**：未收到用户本轮明确下令「开始生图 / 出图 / 生成 / 跑图」前绝不调付费接口；列举任何编号必须写成 **`编号 4~6字卖点`**（如 `S01 健康对比`），极简中文人话，不自建 PR/分支。

## 三、插件发版与公告规则

- 用户要求更新并推送本插件到 GitHub 时，递增版本号（默认 `+0.0.1`）同步更新 `.codex-plugin/plugin.json`、`plugin.json`、`assets/skill-versions.json`，并运行 `scripts/release_dumik_plugin.ps1 -NotesFile "<公告>"` 发新 GitHub Release。
- 公告必须基于 `git log <上个tag>..HEAD` 汇总**全部**实际变化，**禁止写 `# DUMIK Team Plugin v...` 重复一级标题**，按 `✨ 新功能 / ⚡ 优化与改进 / 🐛 问题修复` 列 `- **加粗人话小标题**：一两句讲清变化`，末尾附 `compare/<上个tag>...v<新版本>` 链接。
