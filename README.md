# DUMIK Codex 插件市场

这是 DUMIK 团队共用的 Codex 插件市场仓库。

## 当前插件

- `dumik-team-plugin`
- 市场标签：`0.1.6`
- 插件版本：`0.1.6`
- 内容：以设定集为核心的图片与视频工作台、图片提示词与线稿色块重绘、图片生成与修复、详情页流程、视频证据报告、电影调度、烹饪动态、复合运镜、深度视频参考、故事板与视频执行

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

## 更新规则

更新插件时同步修改 `plugins/dumik-team-plugin/.codex-plugin/plugin.json` 里的版本号，并重新提交到 `main`。

改动插件名或插件目录时，同时更新 `.codex-plugin/marketplace.json` 和 `.claude-plugin/marketplace.json` 两处。
