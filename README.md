# DUMIK Codex 插件市场

DUMIK 团队共用的视觉工作流插件市场仓库，同时兼容 Codex 与 ZCode。

## 当前插件

- **插件名**：`dumik-team-plugin`（DUMIK Team Plugin）
- **当前版本**：见 [plugin.json](plugins/dumik-team-plugin/.codex-plugin/plugin.json) 与 [skill-versions.json](plugins/dumik-team-plugin/assets/skill-versions.json)
- **更新公告**：全部正式版本与变更说明统一发布在 [GitHub Releases](https://github.com/Hill2048/dumik-codex-plugins/releases)

## 核心能力

- **一文件夹一项目建档（`d-init`）**：实拍图 + 飞书画布链接一键初始化项目，自动整理实拍图、注册白底基准、拆解画布生成 `project.md`、`design.md` 与 `AGENTS.md`，并支持 `--sync` 增量同步。
- **视觉策划与纯无字底图（`d-visual-plan` + `d-image-director`）**：卖点四层纯视觉翻译、纵向序列导演交替景别、9:16 分批出图，AI 只出纯无字画面底图并预留排版留白。
- **图片执行与一致性验收（`d-image-runner` + `d-consistency-check` + `d-project-pipeline`）**：统一单图/批量并发出图、RunningHub 放大抠图、三态结构验收与零本地运行垃圾流水线。
- **视频工作流（`d-video-director` + `d-video-runner`）**：统一故事合同、素材职责、导演调度与提示词编译，适配 Seedance 2.5、Dreamina 与 Veo 批量生成。
- **辅助工具（`d-api-test` + `d-psb-install` + `d-prompt-reverse`）**：API 基准测试、Photoshop PSB 智能对象工具安装、参考图提示词反推。

## 团队安装方式

### Codex

在 Codex 里打开「添加插件市场」：

- 来源：`https://github.com/Hill2048/dumik-codex-plugins`
- Git 引用：`main`
- 稀疏路径：留空

### ZCode

在 ZCode 里添加插件市场，来源填：

- `Hill2048/dumik-codex-plugins`（或 `https://github.com/Hill2048/dumik-codex-plugins`）

安装后搜索 `DUMIK Team Plugin` 即可使用。

## Marketplace 清单与密钥说明

- 仓库同时维护 Codex（`.codex-plugin/marketplace.json`）与 ZCode（`.claude-plugin/marketplace.json`）两套清单，改动插件名或路径时需两边同步。
- 公开仓库不内置 API Key。使用图片接口前请在本机配置 `OPENAI_API_KEY`（或运行 `scripts/init_api_cache.py` 写入本机缓存），或调用脚本时传入 `--api-key`。

## 开发与发版规则

- 插件规范与发版规则见 [AGENTS.md](plugins/dumik-team-plugin/rules/AGENTS.md)。
- 推送更新并正式发版时，使用 `plugins/dumik-team-plugin/scripts/release_dumik_plugin.ps1` 自动递增版本号（默认 `+0.0.1`）并随附对比上一发行版的更新公告发布到 GitHub Releases。
