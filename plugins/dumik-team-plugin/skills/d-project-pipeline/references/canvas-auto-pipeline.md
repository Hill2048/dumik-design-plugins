# 无状态 9:16 主图优先流水线编排

本方法衔接根目录 `project.md` 与 `制作/<编号_名称>/prompt.md`，使用 `skills/d-project-pipeline/scripts/build_canvas_pipeline.py` 做**零本地运行垃圾**的批次调度、真实文件状态校准与定稿晋升归档。

- **项目内绝不写入** `run-state.json`、`wave*.json` 或 `运行记录.json/.md`。
- 需要批量提交给 `generate_batch_images.py --batch` 的任务单，只临时写入系统 `%TEMP%\dumik-runs\`，跑完即焚。

## 一、四段分波次执行顺序

| 波次 | 来源筛选（读 `project.md`） | 内容与停靠节点 | 默认规格 |
| --- | --- | --- | --- |
| 第 0 批 | `--wave 0`（`MS*`） | **视觉里程碑设定**：白底身份卡、首屏 KV、超级符号与场景母版；确认定稿后用 `--promote` 锁入 `设定集/里程碑/` 并沉淀光影材质公式进 `design.md` | `9:16-2k` |
| 第 1 批（最优先） | `--wave 1`（`S*` 主图共用） | **主图×详情共用核心画面**：按 `9:16` 三段式无字母版出图，定稿入 `成品/详情_790xn/` 时顺带派生关联 `3:4` 主图 | `9:16-2k` / `9:16-4k` |
| 第 2 批 | `--wave 2`（`S*` 其余分屏） | **详情页其余分屏**：继承 `design.md` 视觉母体出纯无字底图；标为 `无需生图（后期排版）` 的报告/参数屏自动跳过 | `9:16-2k` / `9:16-4k` |
| 第 3 批 | `--wave 3`（`M*` / `E*`） | **独立主图与入口/SKU**：仅执行未关联第 1 批母片的独立 `3:4` 主图或竖图裁切不下的 `1:1` 入口/SKU 底图 | `3:4` 或 `1:1` |

## 二、常用调度命令

```powershell
# 1. 根据 制作/、设定集/里程碑/、成品/ 真实文件校准 project.md 状态列（不改图、不写 JSON）
python "<插件根目录>\skills\d-project-pipeline\scripts\build_canvas_pipeline.py" --project-root "<项目根目录>" --status

# 2. 干跑校验第 1 批 prompt.md 是否写齐（缺失时明确报错，不调接口、不留临时文件）
python "<插件根目录>\skills\d-project-pipeline\scripts\build_canvas_pipeline.py" --project-root "<项目根目录>" --prepare-batch --wave 1

# 3. 仅在用户明确下令「开始生图 / 出图 / 批量跑图」后执行真实批量提交（支持 --ids MS02,S04）
python "<插件根目录>\skills\d-project-pipeline\scripts\build_canvas_pipeline.py" --project-root "<项目根目录>" --execute --wave 1 --quality 2k --image-model banana2

# 4. 定稿晋升：把选中候选图拷入 设定集/里程碑/ 或 成品/ 并自动更新 project.md
python "<插件根目录>\skills\d-project-pipeline\scripts\build_canvas_pipeline.py" --project-root "<项目根目录>" --promote S04 --file "制作/S04_钛好舀/候选_01.png"
```

## 三、跨技能交接与硬约束

1. **必须走 `d-image-director` 的 `detail` 模式写完 `prompt.md` 再跑批**：编写第 0 批里程碑与第 1~3 批分屏 `制作/<编号_名称>/prompt.md` 时，统一使用 `d-image-director` 的 `detail` 模式（可细分为 `detail-macro` / `detail-contrast` / `detail-scene`），严格落实参考图三级保真度（`@图1 [结构锁死]`、`@图2 [属性迁移：仅迁光影色温与台面质感，禁抄构图]`、`@图3 [动作引导]`）及 `project.md` 指定的交替 `机位景别` 与 `PS留白要求`，严禁直接拿草稿偷跑接口。
2. **默认 `9:16` 纯无字底图**：全画幅严格禁排版文字、价格角标、数字标尺、引导线与放大圆框，所有后期排版留给用户在 PS 中处理。
3. **授权边界**：`--status`、`--prepare-batch` 与写 `prompt.md` 均不花费任何生图额度；唯有用户明确授权「开始生图 / 出图」后才传 `--execute`。
