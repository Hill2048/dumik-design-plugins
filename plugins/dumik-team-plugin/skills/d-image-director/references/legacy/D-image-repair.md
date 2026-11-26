---
name: d-image-director
version: 0.2.0
description: "选片后的产品细节修复质量门（产品外扩切图 + 局部高对比色块破惰性 + 外扩边羽化无损贴回）。先分诊 passed / blocked / reroll；只修局部漂移的把手、盖子、五金、品牌区、材质、接缝。默认只出诊断、色块预览与修复词，不直接调付费生图接口。"
---

# 产品细节修复（外扩切图 + 局部色块法）

## 核心原理

1. **产品外扩切图（最大化 AI 分辨率）**：以 `product_box` 向外扩展 `20%` 并吸附到标准比例池（`1:1 / 3:4 / 4:3 / 2:3 / 3:2 / 9:16 / 16:9`），让 AI 的 2K 像素全部集中在产品与细节上，且外扩边界落在背景平滑区，贴回无接缝。
2. **白底图同步拆切对齐角度（最大程度防幻觉；手机广角图禁代结构锁）**：若 `设定集/白底图/` 是五视图或多角度拼图，**必须用 `--white-box`（批量用 `white_box`/`white_boxes`）裁出最匹配当前待修角度与状态（敞口/合盖）的单只或局部白底特写**，并自动补白对齐到与待修外扩图一致的比例再传 `@图2`，严禁整张五视图硬塞导致模型抄错角度或产生幻觉；**`@图2` 结构厚度唯一认棚拍白底图**，手机近拍实拍图（易带广角拉厚或非目标开合态）仅用来校准色相与表面光感写进提示词，禁直接替代白底锁结构；预览联系表同步显示 3 格（原切片｜洋红遮罩｜裁切对齐白底）。
3. **局部涂高对比色块（打破模型照抄惰性）**：在产品外扩图上，用实心高对比色块（默认荧光洋红 `#FF00FF`，避开产品固有色时可改 `#00FF00`）覆盖具体不对的局部 `defect_boxes`，抹除旧的错误结构先验，强迫模型严格对照 `@图2`（裁切对齐后的白底图）重绘。
4. **单 PSD + 单 PNG 原地覆写贴回（严禁堆出重复 PSD；纯色背景校边缘色差）**：同一原候选图无论修几轮，**固定只维护 1 个融合预览图 `<原候选名>_repaired.png` + 1 个多候选分层源档 `<原候选名>_repaired.psd`**（底层「原图」100% 原像素 + 顶层「修复候选_01」「修复候选_02」…各自附带独立可编辑羽化蒙版，默认仅候选_01 显示其余隐藏）；每轮修完**先覆写融合 PNG 给用户直看**，并原地替换同一个 `_repaired.psd`，**严禁层层追加 `_jm55` / `_lid` / `_v2` 后缀在目录里留一堆重复 PSD**；贴回纯色光滑棚拍背景时须核查外扩边色差并做边缘色差校准与宽羽化，杜绝矩形框印。
5. **零项目垃圾**：切片、带色块待修图、联系表与任务 JSON 全部落在系统 `%TEMP%\dumik-runs\repair-*`，项目内不留任何 `.json` 队列。

## 底图源选择铁律（防多轮串联变红变糊）

- **严禁无脑一直垫上一轮刚生成的 `*_已修复.png`**：每串联垫 1 轮都会叠加重采样发糊与洋红残余偏色，导致整图越来越红、越来越糊。
- **重修同一部位 / 重抽不满意**：**100% 强制回到最开始的原始干净原图**重新切图与填色块，绝不拿上一轮未达标的修复图当底图。
- **修同一张图的另一个独立部位（如第 1 轮修好杯身、第 2 轮修盖子）**：
  - **优先回原始干净原图**单切新部位（使每个部位最多只经历 **1 次** AI 重绘，零代际衰减），修好后作为独立图层（如 `修复_杯盖`）贴进同一份 `<原名>_已修复.psd`。
  - **仅当新部位与上一轮已确认修好的部位直接物理重叠、必须承接上一轮结构**时，才基于已确认的 `*_已修复.png` 切图，且串联上限严格 ≤ 1 轮。

## 极速执行与极简确认（反拖沓、反废话）

- **提速**：进入 `repair` 模式**免跑重型 `compile_reference_pack.ps1` 与插件更新检查**，只读本文件；1 轮内并行看「待修图 + 白底图」直接给框跑 `mask_repair.py`，不反复试错。
- **极简确认模板（硬上限 ≤5 行，严禁贴整段 Prompt 代码块或复述 `%TEMP%` / 零垃圾 / 羽化蒙版等技术废话）**：
  - 第 1 行：预览图链接（`*_预览图.png` 或 `色块联系表.png`）
  - 第 2 行：`修 N 处：部位1问题｜部位2问题｜部位3问题`（一句话浓缩）
  - 第 3 行：`没问题回「修」，用 即梦 5.5（<比例> · 2K · x2）开跑并贴回分层 PSD。`
  - **中文命名铁律**：所有切片、候选、修复预览与最终输出必须用中文命名（如 `候选_01.png`、`<原名>_已修复.png`、`<原名>_已修复.psd`），严禁 `s01_float_1.png`、`_repaired.png` 等英文文件名或英文后缀；同图多轮修复原地覆写唯一 `<原名>_已修复.png` 与 `<原名>_已修复.psd`。
  - 仅用户主动说「看提示词」时才展示完整 Prompt 代码块；用户直接说「直接修 / 修完给我」时跳过确认一步跑完。

## 只做三件事

1. 先分诊：`passed`（直接定稿）/ `blocked`（仅局部漂移，进修复）/ `reroll`（大轮廓/比例/SKU 错，回抽卡重出）
2. `blocked` 才修：标出 `product_box` 与 `defect_boxes` → 切外扩图 + 填色块 → 出预览/联系表确认 → 写极简修复词（≤250 字；按实物真实光泽度精准写材质，忌直写「PP/塑料」出廉价感，实物为哑光件时禁加「骨瓷/亮高光」防油光反光）
3. 授权出图并贴回复核：最多两轮

## 单张修复流程（`scripts/repair/mask_repair.py`）

1. **极速报框（免手算像素）**：
   - `--product-box`、`--defect-box`、`--white-box` 均支持 **`0~1` 百分比坐标**（如 `0.25 0.30 0.75 0.70`）或绝对像素，直接按视觉占比报框即可；遇到复杂场景拿不准时，可先跑 `python scripts/prep_reference_assets.py grid-overlay --image "<原图>"` 在 `%TEMP%` 叠一层 10×10 标尺网格，1 次报准。
   - 若 `设定集/白底图/` 是五视图/多视角拼图，直接传 **`--white-slot N`**（1 开始，从上到下、从左到右）自动识别并裁出第 N 只视角，免手算 `--white-box`。
2. **准备外扩色块图与预览**（不调付费接口）：
   ```powershell
   python scripts/repair/mask_repair.py prepare-single `
     --image "<待修原整图>" --white-ref "<设定集/白底图/基准图>" --white-slot 2 `
     --product-box 0.25 0.30 0.75 0.70 --defect-box 0.55 0.38 0.70 0.52 `
     --defect-desc "按白底图还原扁平 D 型一体焊把与倒角"
   ```
   将产出的 `*_预览图.png`（左原切片 / 中洋红遮罩 / 右裁切白底）交用户确认。
3. **授权发包生图**：用户明确下令「开始修复 / 出图」后，交 `d-image-runner`（默认 DesignFlow MCP `2K · x2`，`@图1` 涂色块外扩图 + `@图2` 白底基准图，显式传入脚本返回的 `ratio`）；**产品修复模型优先级固定为：`即梦 5.5`（`seedream-5.5`）＞ `即梦 5.0 Pro`（`seedream-5-pro`）＞ `Banana 2.1`（`banana2.1`）**（首选不可用时按序降级）。
4. **无损贴回整图并清理 `%TEMP%`**（纯色/奶油/棚拍光滑背景建议加 `--match-border-color` 自动消除边缘色差框印）：
   ```powershell
   python scripts/repair/mask_repair.py paste-single `
     --meta "<temp>/*_meta.json" --repaired "<AI修好的外扩图>" `
     --out "<项目>/制作/<编号_名称>/<原名>_已修复.psd" --match-border-color --cleanup
   ```

## 批量修复流程（项目制多屏选片后）

1. **批量分诊**：扫完当前批次候选图，将 `blocked` 项与每张图的 `product_box`、`defect_boxes`、`defect_desc` 写入 `%TEMP%\dumik-runs\修复清单.json`（`passed` 与 `reroll` 自动跳过）。
2. **一键切图涂色块 + 生成联系表**：
   ```powershell
   python scripts/repair/mask_repair.py prepare-batch `
     --manifest "%TEMP%\dumik-runs\修复清单.json" --project-root "<项目根目录>"
   ```
   先将 `色块联系表.png` 给用户 5 秒核对每张图的外扩范围与色块覆盖是否准确。
3. **一次并发出图**：用户确认并下令「开始修复」后，直接读取 `%TEMP%\...\designflow_items.json` 经 `d-image-runner` 走 DesignFlow MCP `items[]` 并发跑图（离线走直连并发）。
4. **一键批量无损贴回 + 清理**：
   ```powershell
   python scripts/repair/mask_repair.py paste-batch `
     --workdir "<temp>/repair-xxx" --repaired-dir "<AI修好图目录>" --cleanup
   ```
   完成后跑 `build_canvas_pipeline.py --status` 刷新 `project.md`，再交 `d-consistency-check` 做复核。

## 代码精准修标 / 擦字 / 数码屏改色（`scripts/repair/logo_patch.py`，零 AI 漂移）

当只需修复**平面/圆柱曲面丝印 LOGO**、**抹除按钮/屏幕假字**或**黑屏数码管改色**（不需要 AI 重画整块结构）时，优先走 `scripts/repair/logo_patch.py`（OpenCV 四角透视 + 圆柱弯曲 + 表面肌理置换 + PS 同款混合模式 + 可选 IOPaint/OpenCV 擦旧字 + 同步输出带独立透明图层与真实混合模式的 `.psd`）：

```powershell
# 1) 平面/圆柱透视贴真标（有旧乱码时加 --erase-quad；圆柱杯身改 --mode cylinder）
python scripts/repair/logo_patch.py patch-logo `
  --image "<待修原图>" --logo "<透明底LOGO.png>" `
  --quad x1 y1 x2 y2 x3 y3 x4 y4 --mode perspective `
  --blend multiply --opacity 0.90 --displace 0.65 `
  --out "<输出.psd>" --preview-png "<预览.png>"

# 2) 黑屏数码读数无损改色（如荧光橙 #FF5E00）
python scripts/repair/logo_patch.py recolor-led `
  --image "<待修原图>" --screen-box 0.06 0.70 0.28 0.88 `
  --color "#FF5E00" --out "<输出.psd>" --preview-png "<预览.png>"
```
