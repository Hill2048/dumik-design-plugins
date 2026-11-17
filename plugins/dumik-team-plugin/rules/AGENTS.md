# DUMIK 团队视觉工作流（Antigravity 规则）

- 当前插件根目录为 `C:\Users\admin\.gemini\config\plugins\dumik`（通过 NTFS 软连接实时指向 `C:\Users\admin\Documents\Codex\dumik-design-plugins\plugins\dumik-team-plugin`）。
- 能力路由唯一来源：`assets/agent-skill-routing.md`；项目文件夹结构与零垃圾协议：`assets/project-env-protocol.md`；单图状态约定：`assets/task-state-contract.md`。

## 一、一文件夹一项目（建档即完整上下文闭环）

1. **一键建档（`d-init`，脚本 `skills/d-init/scripts/init_dumik_project.py`）**：新建一个项目文件夹后，可用实拍图 + 飞书链接（或先用纯实拍图）直接初始化，自动整理根目录散放实拍图进 `素材/实拍原图/`、注册白底图进 `设定集/白底图/`、拆解飞书文档写入根目录 `project.md`，并生成 `AGENTS.md`（原生 `@` 内联挂载 `project.md` 与 `design.md`）与 `design.md`。
2. **增量同步（`--sync`）**：飞书画布有修改时直接重拉对比更新 `project.md`，自动保留已锁定里程碑、已定稿状态与 `design.md` 已确认设定；日常打开项目文件夹直接读根目录三文档即可续做，无需用户重述背景。

## 二、零本地运行垃圾铁律

- **项目内禁止沉淀过程文件**：严禁在项目目录生成 `.json` 队列、`canvas-manifest.json`、`拆解清单.md`、`run-state.json`、`wave*.json` 或 `运行记录.json/.md`。批量执行参数走系统 `%TEMP%\dumik-runs\` 用完即毁，技能参考拼装包继续只走 `%TEMP%`。
- **制作目录按需创建、单版覆盖**：`制作/` 下不预建空目录；正在动工或返修的画面只在 `制作/<编号_名称>/prompt.md` 覆盖维护**当前最新生效的一版完整提示词**与 `@图N` 绑定；是否定稿以 `设定集/里程碑/` 与 `成品/` 里的真实图片为准，通过 `build_canvas_pipeline.py --status` 校准进 `project.md`。

## 三、卖点四层纯视觉翻译 + 纯无字底图 + 9:16 分批交付

1. **卖点翻译与导演控制（`d-visual-plan` + `d-image-director` `detail` 模式）**：
   - 先过「第一眼爽点 → 信任硬证据 → 日常顾虑兜底」去重排主次；
   - 把抽象卖点强转为物理画面证据（参照物满载 / 光学微距 / 极端动作对比）；纯检测报告与纯规格参数直接标 `无需生图（后期排版）`；
   - 将第 0 批里程碑定调的「材质光学公式与光影空间母体」锁进 `design.md`；拆解与写词同步遵循纵向序列导演法则——相邻分屏自动交替 `机位景别` 防连续三屏重样，编写 `prompt.md` 走 `d-image-director` `detail` 模式并严守「画布参考图先看后译、严禁喂入 API `@图N`」，只绑 `@图1 [结构锁死]`、`@图2 [属性迁移：禁抄构图]`、`@图3 [动作引导]` 与物理瞬态视线流；
   - **AI 只出纯无字画面底图，排版全部人工 PS 完成**：`project.md` 内保留运营原主副标题与批注供判断留白密度及 PS 直接复制，但画面正片除产品真实原生丝印/刻字外，严禁标题、卖点字、数字标尺、角标、图标、指示引线与放大圆框，并按文案密度预留干净低反差负空间。
2. **四批出图与 `9:16` 同源母版**：第 0 批视觉里程碑定调 → 第 1 批（最优先）主图共用的详情核心屏（按 `9:16` 三段式构图，一图通吃 `790xn` / `3:4` 主图 / `1:1` 入口）→ 第 2 批详情其余分屏 → 第 3 批无法复用的独立 `1:1` 入口/SKU；默认生图画幅统一 `9:16`（`9:16-2k` `1152x2048` / `9:16-4k` `2160x3840`）。

## 四、授权边界与表达要求

- 默认只停在项目建档、拆解清单与 `prompt.md` 中文提示词，**绝不自动调用付费生图接口**；只有用户明确下令「开始生图 / 出图 / 批量跑图 / 调用接口」时，才由 `d-project-pipeline` + `d-image-runner` 执行真实生图；出图后可用 `d-consistency-check` 对照白底原图与画面纯净度验收。
- 向用户汇报与输出清单保持极简中文人话，不出现多余分层字母代号，不擅自新建 Git 分支、提交 PR 或推送远端。

## 五、插件更新与发版规则

- 当用户要求更新并推送本插件到 GitHub 时，必须同步递增版本号（默认 `+0.0.1`，如 `0.2.2` → `0.2.3`，除非用户另行指定）并发行新的 GitHub Release。
- 需同步更新 3 处版本字段：`plugins/dumik-team-plugin/.codex-plugin/plugin.json`（`version`）、`plugins/dumik-team-plugin/plugin.json`（`version`）、`plugins/dumik-team-plugin/assets/skill-versions.json`（`pluginVersion`）。
- **必须编写更新公告并随 Release 发布**（禁止只用自动生成的 Full Changelog 空壳）：
  - **禁止标题重复**：GitHub Release 标题固定为 `DUMIK Team Plugin v<版本号>`，公告正文**禁止再写 `# DUMIK Team Plugin v<版本号>` 一级标题**，直接从一句话概括开头。
  - **对比上一个发行版汇总全部更新**：必须基于 `git log <上一个发行tag>..HEAD` 汇总从上个正式发行版到本版的**全部**实际变化（不能只写最后一次提交）。
  - 分类列出变更（按需选用 `## ✨ 新功能`、`## ⚡ 优化与改进`、`## 🐛 问题修复`）。
  - 每条格式：`- **加粗人话小标题**：一两句讲清对使用者的实际变化，不列内部文件名、函数名或 commit hash。`
  - 末尾附上完整对比链接：`[查看与 <上一个发行tag> 的完整差异](https://github.com/Hill2048/dumik-design-plugins/compare/<上一个发行tag>...v<版本号>)`。
- 优先执行 `plugins/dumik-team-plugin/scripts/release_dumik_plugin.ps1 -NotesFile "<公告文件>"` 完成「版本号 `+0.0.1` → 提交 → 推送 `main` → `gh release create v<新版本>` 发行新版本与公告」。
