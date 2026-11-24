# DUMIK Team Plugin

面向 DUMIK 团队的电商视觉与视频工作流插件包，提供统一项目建档、路由规范、视觉策划、图片/视频导演与批量执行能力。

## 核心工作流

1. **一文件夹一项目建档（`d-init`）**
   - 用实拍图和飞书画布链接一键初始化项目文件夹，自动整理 `素材/实拍原图/`、注册 `设定集/白底图/`，写入 `project.md`、`design.md` 与 `AGENTS.md`，并支持 `--sync` 增量同步。
2. **零本地运行垃圾**
   - 项目目录内不生成 `.json` 队列或运行记录文件；批量执行临时参数走系统 `%TEMP%\dumik-runs\`，用完即毁。
3. **默认只交付提示词，不自动花钱出图**
   - 所有图片与视频技能默认停在拆解清单与文字提示词阶段；仅当用户明确下令生图、出图或生成视频时，才调用生成接口。
4. **纯无字底图 + 9:16 分批交付**
   - 画面正文不渲染营销文案、标尺或角标（保留产品原生丝印/刻字），按「第 0 批里程碑 → 第 1 批主图共用核心屏 → 第 2 批其余分屏 → 第 3 批独立 1:1 入口」推进。

## 包含技能（10 个活跃技能）

- `d-init`：项目初始化、目录整理与飞书画布增量同步
- `d-visual-plan`：详情页结构、卖点四层纯视觉翻译与视频转化策划
- `d-image-director`：图片提示词与改图指令编写（`detail / edit / brief / direction / hd / repair`）
- `d-image-runner`：单图/多候选/批量出图与 RunningHub 放大抠图后处理
- `d-project-pipeline`：成组图片跨步骤依赖与流水线恢复
- `d-consistency-check`：原产品图与生成图三态一致性验收
- `d-prompt-reverse`：参考图反推提示词草稿
- `d-video-director`：视频内容设计、分镜导演与提示词编译
- `d-video-runner`：确认片、普通视频与批量视频提交
- `d-api-test`：图片 API 基准测试

## 已废弃技能（保留存档，默认不加载、不拉取）

- `d-psb-install`（PSB 智能对象工具）：已废弃并归档至 `archive/deprecated-psb-tools/`（保留 `assets/psb-smart-object-tools/` 源码与脚本，不删除），不再随插件默认加载或自动从 GitHub 拉取更新。

## 关键索引

- 全局规则：[rules/AGENTS.md](rules/AGENTS.md)
- 能力路由：[assets/agent-skill-routing.md](assets/agent-skill-routing.md)
- 项目结构协议：[assets/project-env-protocol.md](assets/project-env-protocol.md)
- 单图状态约定：[assets/task-state-contract.md](assets/task-state-contract.md)
- 各 skill 版本：[assets/skill-versions.json](assets/skill-versions.json)

## 本机接口配置

插件不包含个人缓存或 API Key。图片接口默认走 `https://sub.juaihub.cn`，可通过本机环境变量 `OPENAI_API_KEY`、命令行 `--api-key` 或 `scripts/init_api_cache.py` 写入本机 `CODEX_HOME/dumik-team-plugin/api_settings.py`（不进插件仓库）。
