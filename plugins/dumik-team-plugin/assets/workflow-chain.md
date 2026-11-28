# 工作流可测与信息传递

Skill 是可测流程封装，不是文章收藏。相邻步骤必须能传**结构化信息**，不能只传「感觉更好了」。

## 可测标准

| 步骤 | 可测输出 |
| --- | --- |
| 任务拆解 | 五格表（目标/主体/关系/约束/标准） |
| 策划 | 卖点顺序 + 证据类型 + 模块列表 |
| 写词 | 独立完整 Prompt + 控制区/自由区 + 禁止段 |
| 反推 | 人判主次记录 + 结构化草稿（非终稿除非人确认） |
| 出图 | 文件路径 + 模型/参数记录（密钥不进文档） |
| 验收 | 分项三态表 + 总判 |
| 本地精抠 | 无损 RGBA 透明底 PNG（可选 2 层 PSD）+ `%TEMP%` 双底对比验收板 |
| 终稿审查 | 红框编号标注大图 + 悬浮连线离线 HTML 审稿台（含策划原图对照与一键复制文案，违禁/合规红灯） |

上一步缺可测输出时，下一步不得用散文假装已完成。

## 信息传递最小集

跨 skill 交接至少保留：

1. 目标图 / 结构真源 `@图N` 与职责  
2. 仍有效的系列规则或 design 设计语言要点  
3. P0 不可改清单（或「与控制层默认相同」）  
4. 本轮唯一变化点  
5. 验收标准或已知风险

禁止：「按之前的来」且不附完整 Prompt 或五格。

## 完整端到端标准生产线（一条线串通全部 15 个技能与配套工具）

```text
Stage 1 · 建档与拆解（d-init + d-visual-plan）
  └─ init_dumik_project.py 生成四文档（AGENTS.md 仅内联纯视觉宪法 design.md；资产路径/哈希/摆件库/食材表落 assets.md；分屏总账落 project.md）
  └─ 白底多图先用 prep_reference_assets.py（stitch-white 拼 2K 多视图身份卡 / compress-refs 超限大图 2K 瘦身）
  ↓
Stage 2 · 第 0 批里程碑锁调（MS01~MS04：d-image-director detail → d-image-runner → --promote）
  └─ 定稿锁入 设定集/里程碑/；纯审美/光影/材质公式写进 design.md，路径与 local-asset: 登记进 assets.md
  ↓
Stage 3 · 置景摆件库 & 饮品/食材预规划（MS05 · 里程碑锁调后、进详情批量前必做）
  └─ d-visual-plan 协同 d-food-drink-stylist 梳理 8~12 件风格摆件 + 全案饮品/食材/锅具王牌配菜错峰表写入 assets.md
  └─ 重点摆件与食饮可从内置 31 张 3×3 高清图板（单格 1024×1024）用 crop_moodboard_tile.py 裁单格作 @图 参考，交 d-image-director + d-image-runner 出选样卡拍板入 设定集/摆件身份卡/
  ↓
Stage 4 · 第 1~3 批详情/主图/入口批量生产（d-project-pipeline + d-image-director + d-food-drink-stylist + d-image-runner）
  └─ 写每屏 prompt.md 强制三层垫图隔离（L1 必带，严禁垫 制作/ 未定稿候选图），从 assets.md 领用摆件（≤3件）与饮品并回填屏号
  └─ 含食饮/锅具配菜屏由 d-food-drink-stylist 提供纯本体造型与微观物理片段（零光影/相机越权），由 d-image-director 统一套场景光影与机位；洗图走 wash_prep.py；品牌扁六边形 3D 徽章走 d-brand-badge，旧标原外形洗材质走 d-badge-wash；纯白/纯色底 3D 立体字、徽章、小件与透明玻璃出图后无缝交 d-cutout 0.5 秒本地精抠无损透明底 PNG/PSD；反推参考走 d-prompt-reverse
  └─ 明确授权后默认 DesignFlow / DSH 单节点并发（count/models/items），优先按 nodeId 导图落盘（全中文命名），跑 --status 同步
  ↓
Stage 5 · 三态验收 & 局部无损修复（d-consistency-check → d-image-director repair + d-image-runner）
  └─ 局部漂移走 mask_repair.py（0~1 百分比坐标 + --white-slot 自动切五视图 + 洋红破惰性 + 强制回原始干净图防变红）
  └─ 优先 即梦 5.5 ＞ 即梦 5.0 Pro ＞ Banana 2.1，贴回原地覆写唯一 <原名>_已修复.png/.psd（纯色底加 --match-border-color）
  ↓
Stage 6 · 定稿晋升与多 SKU 延展（d-project-pipeline）
  └─ --promote 防压缩图门禁（拦截 .user_uploaded/ 与 <1500px）晋升 成品/，支持 --variant-sku 多配色批量换款
  ↓
Stage 7 · 终稿排版审查与上线把关（d-detail-review）
  └─ 设计师在 PS 排完详情长图/主图后，slice_for_review.py 带 X/Y 像素刻度尺切高清条带，逐屏对照 素材/飞书画布/ 与 project.md 规格真源做六维终检（违禁/合规一律红灯）
  └─ build_review_board.py 自动落盘 成品/审稿报告/：居中连贯详情长图 + 左右悬浮卡片 + SVG 细引导线 + 放大策划原图 + 一键复制文案（全插件统一中文 MiSans / 英数 Google Sans）
  ↓
Stage 8 · 全链路护航与观测（agy_dumik_hooks.py + dumik_telemetry.py）
  └─ 25 轮长会话 /compact 提醒、追改防漂移、置景表未填提醒、Stop 清垃圾/同步检查、飞书多维表格全链路异步埋点
```

`d-project-pipeline` 只编排依赖与恢复，不替代上述任一专业输出。


## 反模式

1. Director 输出依赖聊天省略语，Runner 无法单凭文件执行。  
2. 验收只说「感觉漂了」无分项三态。  
3. Pipeline 自动连跑但中间 Prompt 未完整落盘。  
4. 反推草稿未标人确认就被 runner 拿去出图。

## 飞书画布与单项目文件夹成套流水线补充标准

- **建档拆解输出**：由 `d-init`（`scripts/init_dumik_project.py`）与 `d-visual-plan`（`canvas` 模式）直接生成根目录四文档（`AGENTS.md`、`design.md`、`assets.md`、`project.md`），项目内严禁残留 `.json` 队列、`拆解清单.md` 或 `运行记录`。
- **单图写词载体**：`d-image-director` 按 `project.md` 编号为已动工的画面在 `制作/<编号_名称>/prompt.md` 覆盖维护最新完整无字底图提示词与 `@图N` 绑定；纯报告/规格屏跳过不建目录。
- **无状态批次与授权**：`build_canvas_pipeline.py` 只在用户明确下令「开始生图 / 出图 / 批量跑图」时，才于系统 `%TEMP%` 组批次并调用 `d-image-runner` 提交，跑完立即删掉临时文件并依真实文件刷新 `project.md`。

## 一句话

**每一步留下下一双眼睛（人或下一个 skill）不靠聊天记忆也能继续的东西。**
