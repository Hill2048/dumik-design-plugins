---
name: D-init
version: 0.2.0
description: "DUMIK 工作台初始化。在新仓库/新电脑装好插件后跑一次：先问项目类型（图片 / 视频 / 混合），生成执行入口和项目视觉设定文件，按设定集核心目录创建项目，初始化 API 缓存并做环境检查。只补缺不覆盖已有文件。"
---

# 工作台初始化

解决两个问题：一，插件随 GitHub/缓存走，但项目入口文件不随插件走；二，把执行规范、工具入口、视觉设定和参考来源边界固定在项目文件中，避免每个任务临场猜目录和参考。

## 触发

- 初始化工作台 / 初始化项目 / 新仓库初始化 / 装好插件怎么开始。
- 进入任务时发现仓库根缺 `AGENTS.md` 或 `CURRENT_PROJECT.md`，且用户要开展项目制工作。

不触发：入口文件齐全的老仓库日常任务（那直接按 AGENTS.md 走）。

## 硬规则

- **第一个问题永远是项目类型**：图片项目 / 视频项目 / 混合项目。用户已经说明时不重复问；项目类型决定初始化哪些图片/视频制作目录。
- **只补缺，不覆盖**。已存在的入口文件一律不动，只报告"已存在，跳过"；用户明确说重置才允许覆盖，覆盖前先改名留底（`<名>.bak-<日期>`）。
- 默认参考只来自项目 `design.md` 和 `设定集`；其他位置的文件只有用户明确给出时才可用于本次任务。
- 不写 API Key 进任何仓库文件；Key 只进本机 `CODEX_HOME\dumik-team-plugin\api_settings.py`。
- 最后交付清单：生成了什么、跳过了什么、缺什么要用户补。

## 步骤

### 1. 问项目类型（必问，先于一切）

图片项目 / 视频项目 / 混合项目。用户已在请求里说清的不重复问。

### 2. 检查现状

先确定工作台根与当前项目根。用户已在具体项目目录中时，直接使用该目录，不嵌套创建 `project/<项目名>`，不重复问已知项目名或类型。工作台的指针不能覆盖用户明确指定的当前项目。

列出仓库根的 `AGENTS.md`、`CLAUDE.md`、`CURRENT_PROJECT.md`、`CONTEXT.md` 是否存在；确认插件路径（`plugins\dumik-team-plugin` 或本机插件缓存）。

### 3. 生成入口文件（缺哪个补哪个）

按 [references/entry-templates.md](references/entry-templates.md) 拼装，替换插件路径占位符：

- `AGENTS.md` = 执行规范、工具入口和项目协作规则；图片/视频/混合项目均以 `设定集` 为核心，不生成旧的 `原图`、`参考`、`输出` 目录规则。
- `CLAUDE.md`：一行 `@AGENTS.md` 引用，Claude Code 与 Codex 共用入口。
- `CURRENT_PROJECT.md`：空指针模板。
- `design.md`：项目视觉设定模板，记录产品、场景、角色及确认状态。
- `CONTEXT.md`：折叠规则头。

项目根只补 `AGENTS.md`、`design.md`；不另建 `agent.md`。工作台指针和历史留在工作台根，`CLAUDE.md` 仅在需要 Claude 入口时补充。已有工作台入口不代替项目自己的执行规范与视觉设定。

### 4. 首个项目（可选，问一句）

要建：按 `assets\project-env-protocol.md` 问项目名，调对应 `init_project.py`（图片用 `D-image-run`、视频用 `D-video-run` 的脚本）建目录，写 `CURRENT_PROJECT.md` 指针。不建：跳过。

用户已要求初始化当前项目时，直接建已确定的项目。混合项目将两个初始化脚本的 `--output-path` 指向同一项目目录。只补缺；旧项目不自动搬迁，只有用户要求整理或迁移时才按实际文件处理。

### 5. 环境初始化

- 跑插件根 `scripts\init_api_cache.py` 初始化本机 API 缓存（已有则跳过）。
- 按协议的工具检查节做轻量检查：Python、关键脚本、缓存可读；视频项目加查 `dreamina` CLI。
- 缺 Key/登录这类自动修不了的，列进"待用户补"清单，不阻塞完成。

### 6. 交付清单

输出：项目类型、生成的文件、跳过的文件、项目目录（如建了）、环境检查结果、待补项。在 `CONTEXT.md` 写一条初始化记录。

## 升级已有工作台

老仓库的 AGENTS.md 还在引用总监 skill 时，经用户确认后做一次升级：把对应总监职责节并进 AGENTS.md，删掉指向 `ecom-visual-director` / `tvc-director` skill 的字样（这两个 skill 已归档）。同样先留底再改。

## 交接

- 初始化完成后的任务分流：先读项目 `AGENTS.md`、`design.md` 和相关 `设定集`，再按 `assets\agent-skill-routing.md` 路由到底层 skill。
- 项目入口、目录、归档规则：`assets\project-env-protocol.md`。
