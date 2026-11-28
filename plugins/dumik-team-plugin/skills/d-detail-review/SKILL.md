---
name: d-detail-review
description: "详情页/主图排版终稿审查专家：自动带坐标标尺切片高清读图，逐屏对照飞书策划原图、project.md 规格真源与电商合规红线，查出文案错字、老模板残留、数据打架、漏填项与违禁词，并在原图上精准红框编号圈出标注，一键生成附带策划原图对照与可复制正确文案的离线交互式 HTML 审稿台及标注大图。不写生图提示词、不调付费生图接口。"
metadata:
  version: 0.1.0
---

# DUMIK 详情/主图终稿审查（d-detail-review）

本 skill 专职**已排版成品图（详情页长图 `790×N`、主图 `3:4`、车图 `1:1`）上线前的终稿审查**，彻底取代纯文字审稿清单：直接在成品图上**精准红框编号圈出问题位置**，并排**贴上对应的飞书策划原图**，给出**一键复制即可贴进 PS 的正确文案**。

> **与 `d-consistency-check` 的清晰分工**：
> - 单张 AI 生成的无字底图 vs 产品白底图的结构/外形/无字纯净度验收 → `d-consistency-check`；
> - **已排字合成的详情页/主图成品** vs **飞书策划原图 + `project.md` 规格真源 + 广告法合规**的图文终检与圈注交付 → 一律用本 skill `d-detail-review`。

## 参考文件硬门槛

进入本 skill 后先读 `references/review-checklist.md`（Windows 环境可运行插件根目录 `scripts/compile_reference_pack.ps1 -Skill d-detail-review -Mode review`）。本 skill 为纯本地审查与可视化标注，**严禁调用任何付费生图/视频接口**。

## 标准四步工作流

### Step 1：带像素坐标标尺自动切图（精确定位红框的基础）

收到待审成品图（1 张或多张，如桌面 `1.jpg`、`2.jpg`）后，**严禁直接看被缩成糊片的整张长图盲审**，必须先运行本 skill 自带切片脚本，把图片切成带 **X/Y 像素刻度标尺** 的高清条带放到 `%TEMP%\dumik-runs\review_slices\`：

```powershell
python "<插件根目录>\skills\d-detail-review\scripts\slice_for_review.py" ^
  --images "C:\Users\admin\Desktop\1.jpg" "C:\Users\admin\Desktop\2.jpg" ^
  --out-dir "$env:TEMP\dumik-runs\review_slices" ^
  --chunk-height 1800 --overlap 150
```

- 切片脚本会在每张条带顶部画 **X 轴像素刻度（每 100px）**、左侧画 **Y 轴原图真实绝对像素刻度（每 100px，对应原图 Y 坐标）**，同时在终端打印每张原图尺寸与切片文件列表。
- Agent 使用 `read_file` 分批并行读完**全部高清条带**，并同步读取项目根目录 `project.md`（唯一规格真源）以及 `素材/飞书画布/S01_画布原图.png` ~ `Sxx_画布原图.png`（或 `M01~M06` / `E01` 策划原图）。

### Step 2：六维逐字审查与精准取框

严格按 `references/review-checklist.md` 六大维度逐屏核对（错字/老模板残留、对照策划原图、参数与专业逻辑、图文一致性、合规违禁词与 `*` 号闭环、排版断行与空白漏填）。

对发现的每一条问题，依据切片边缘的 **真实像素刻度尺** 读出该问题在原图上的精确包围框 `bbox: [x1, y1, x2, y2]`（原图坐标系，**不含标尺边距**），按 `references/review-checklist.md` 的 JSON Schema 在 `%TEMP%\dumik-runs\review_input.json` 整理全部问题项（**严禁把 JSON 落盘在项目目录内**）。

每条问题支持极速简写（编写效率翻倍）：
- `id`：可省略，脚本自动按序编 `"01"`, `"02"`...
- `severity`：`"error"`（🔴 红灯必改：含错字/老模板/数据打架/**全部违禁词与合规缺失**，脚本内置违禁关键词防漏网自动升红）｜ `"missing"`（🟠 橙灯漏填）｜ `"warn"`（🔵 蓝灯优化）
- `screen`：所属屏号与简名（如 `"S03 假一罚万"`），**传了 `--project-root` 时可省略 `plan_ref`，脚本自动按屏号匹配 `素材/飞书画布/S03_画布原图.png`**
- `image_key`：目标图键名（单图可省，默认 `"1"`）；`images` 也支持直接写文件路径字符串数组
- `bbox`：`[x1, y1, x2, y2]`（原图真实像素坐标）
- `short_tag` / `title` / `issue`：红框极简标签、卡片标题、一句话错因
- `copy`（简写）或 `copy_blocks`：可直接写 `"copy": "正确文案"` 或 `["文案1", "文案2"]` 或 `[{"label": "...", "text": "..."}]`；卡片文本支持自由拖选 + 一键复制

### Step 3：一键生成红框标注图 + 离线悬浮画布 HTML 审稿台

运行标注与报告生成脚本：

```powershell
python "<插件根目录>\skills\d-detail-review\scripts\build_review_board.py" ^
  --spec "$env:TEMP\dumik-runs\review_input.json" ^
  --project-root "<当前项目根目录>"
```

脚本自动并行生成：
1. **极简悬浮画布离线 HTML 审稿台**：`终稿审查报告_<项目名>.html`（单文件自包含，无顶部通栏、无右边栏，英文/数字用 `Google Sans`，中文用 `MiSans`）
   - **居中：完整无缝连贯详情页**：多段详情图上下零缝隙拼成一条完整长图，原图直接带红/橙/蓝编号框，滚轮一滑到底
   - **左右两侧：悬浮批注卡片 + SVG 细引导线**：卡片按高度智能吸附在详情页左右空白处，细曲线直连对应红框；文案支持局部拖选 + 一键 `复制`；**放大版飞书策划原图**直接展示，点击打开原生 `<dialog>` 满屏灯箱（Esc / 点空白处即关，锁定底层不穿透滚动）
   - **右上角固定悬浮信息导航卡**：整合标题、进度条、红/橙/蓝筛选与可折叠**带局部缩略图的问题导航列表**（支持现代 CSS Scrollspy 滚动同步高亮，点哪条直达对应红框）
2. **红框标注成品大图**：`<原图名>_审稿标注.jpg`（全分辨率带红框与 `Google Sans + MiSans` 混排编号标签）

> **项目制标准落盘与零垃圾原则**：
> - 在 DUMIK 项目内审查时，直接传 `--project-root "<当前项目根目录>"`（省略 `--out-dir`），自动落盘到项目标准目录 **`成品/审稿报告/`**（`终稿审查报告_<产品名>.html` 与 `<原图名>_审稿标注.jpg`），零 `.json` 残留、不污染 `制作/` 候选数与 `project.md` 屏数；若用户显式要求输出到桌面或其他目录，再传 `--out-dir`。
> - 生成完成后**立即删除 `%TEMP%\dumik-runs\review_slices` 与 `review_input.json`**。

### Step 4：视觉抽检红框精度后交付

在最终回复用户前，必须用 `read_file` 抽查生成的红框标注图关键部位（或报告局部裁剪图），确认：
- 红框精准套住错字/错图，无明显偏移或裁切过紧；
- 编号与问题清单 100% 一一对应，中文字体清晰无方框乱码；
- 回复用户时提供点击直达的 `file:///` 链接（HTML 交互审稿台 + 标注大图）与 ≤10 行核心摘要，不刷屏重复长篇文案。
