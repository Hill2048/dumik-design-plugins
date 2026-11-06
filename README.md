# DUMIK Codex 插件市场

这是 DUMIK 团队共用的 Codex 插件市场仓库。

## 当前插件

- `dumik-team-plugin`
- 市场标签：`v0.1.15`
- 插件版本：`0.1.15`
- 内容：项目 `AGENTS.md` 总控、`design.md` 与设定集事实层、图片与视频专业方法、成组任务执行、项目入口维护，以及统一的 `@图N` 素材引用合同
- 更新公告：[v0.1.15 视频方法论扩充](RELEASE_NOTES_0.1.15.md)

## v0.1.15 的新增

`d-video-director` 吸收 Higgsfield《Hell Grind》生产方法论（源自 `OSideMedia/higgsfield-ai-prompt-skill`），
只取方法论、剔除全部工具与执行层，新增三份参考：

- `video-methodology-mcsla.md`：MCSLA 五层、T2V/I2V 双范式、身份块与动作块分离、角色资产家族、场景 GEO 锚定、禁令字典、单变量迭代、6 轮诊断、反套话
- `video-directing-shotlist.md`：三层结构、15 秒信封密度判断、节奏预算算术闸门、单调性审计、双对比切镜、连续性清单、导演门禁
- `video-acting-and-failure-modes.md`：表演五根柱子、眼睛必须有生命、状态而非过渡、12 种失败模式与对策、帧级复核

注意：运行 `compile_reference_pack.ps1` 必须用 `pwsh`（PowerShell 7），用 `powershell` 5.1 会因无 BOM 中文按 ANSI 读取而解析失败。

## v0.1.12 的分工

- 项目 `AGENTS.md` 规定协作、决定继承、确认时机和调度，可按项目微调。
- `design.md` 与设定集记录产品、场景、角色及确认状态，不负责流程。
- 专业 skills 提供图片、视频、策略和批量方法；执行器负责准确提交与保存结果。
- `d-init` 创建或局部维护项目入口，不是日常调度 skill。已有项目定制不被升级自动覆盖。
- 完整初始化可登记项目级 `design.md` 加载钩子；Codex 写入 `.codex`，ZCode 写入 `.zcode` 并打开运行时开关，两者互不覆盖。只写入口或维护规则不顺带安装。钩子需宿主信任，脚本验证不等于宿主已经自动触发。

## 团队安装方式

### Codex

在 Codex 里打开“添加插件市场”，填写：

- 来源：`https://github.com/Hill2048/dumik-codex-plugins`
- Git 引用：`main`
- 稀疏路径：留空

### ZCode

在 ZCode 里添加插件市场，来源填：

- `Hill2048/dumik-codex-plugins`（或 `https://github.com/Hill2048/dumik-codex-plugins`）

安装后搜索 `DUMIK Team Plugin` 即可使用。

## Marketplace 清单

两个平台的清单文件名和格式不同，仓库同时保留：

- Codex：`.codex-plugin/marketplace.json`
- ZCode：`.claude-plugin/marketplace.json`

ZCode 只识别根目录 `marketplace.json` 和 `.claude-plugin/marketplace.json`，不会读取 `.codex-plugin/marketplace.json`；只保留 Codex 清单会导致 ZCode 报 `Marketplace manifest not found in GitHub repo`。两边改动要保持插件名、路径一致。

公开版插件不内置 API Key。批量出图时请在本机设置 `OPENAI_API_KEY`，或运行脚本时传入 `--api-key`。

各 skill 版本号见 `plugins/dumik-team-plugin/assets/skill-versions.json`。

从 `v0.1.7` 起，DUMIK 提供会话级官方 `main` 快进更新检查。`v0.1.8` 中仅维护项目规则或只生成入口文档的 `d-init` 任务跳过插件更新；完整工作台初始化保留检查。自动更新不会覆盖有未提交修改的源码，也不会自动重写项目 `AGENTS.md`。`v0.1.9` 起 `d-init` 的加载钩子安装器按宿主写入 Codex 或 ZCode 的项目配置。`v0.1.10` 起，存在本地定制时更新器明确返回 `skipped`，保留修改且不误报更新成功。

## 更新规则

更新插件时同步修改 `plugins/dumik-team-plugin/.codex-plugin/plugin.json` 里的版本号，并重新提交到 `main`。

改动插件名或插件目录时，同时更新 `.codex-plugin/marketplace.json` 和 `.claude-plugin/marketplace.json` 两处。
