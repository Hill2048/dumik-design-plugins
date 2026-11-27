---
name: d-food-drink-stylist
description: "基于 1000+ 张 Pinterest 实拍精析与内置 31 张轻量 3×3 高清垫图库（279 张互不重样无水印参考、单格严格 1024×1024 + 一键拆单格脚本）的食饮本体视觉造型技能。专注负责杯壶、煎锅、炒锅、小奶锅/雪平锅、厨电与餐具项目的食材本体、饮品、锅具王牌配菜与中西美食的选品排期、造型结构与微观口感物理；严格不越权写光影、相机、景深与场景台面（全部交还 design.md 与 d-image-director），仅交付食饮本体方案与描述片段，不调付费生图接口。"
metadata:
  version: 1.2.0
---

# 饮品与美食视觉造型师（d-food-drink-stylist · v1.2.0）

专门根治 AI 生成食材、饮品、锅具配菜与中西美食时常见的 **「塑料/蜡像假食感（缺微观生物与烹饪物理）」** 与 **「菜摊/外卖/平庸堆砌感（缺造型结构与留白克制）」** 两大通病。

## 职责红线（绝不与 `design.md` / `d-image-director` 打架）

- **本 skill 只管 3 件事**：
  1. **选品与排期**：按产品（杯壶 / 煎锅 / 炒锅 / 小奶锅 / 餐具 / 厨电）选出最能证明卖点、相邻屏不撞色的食材、饮品或菜品；
  2. **造型与三层结构**：立体顶构、刀工切面朝向、器皿留白（35%~45%）与锅内露底保护（保留 25%~35% 可见锅面展露锅体材质）；
  3. **微观物质与口感物理**：把“糯/酥/嫩/鲜/香/辣、冰冽/丝绒/气泡/醇厚”翻译成肉眼可见的食物/液体物理细节，并锁死不透明杯防透视。
- **本 skill 严禁越权写 4 件事**（一律交还项目 `design.md` 与 `d-image-director`）：
  - ❌ **不写光影**：不规定光源方向、窗影、硬软光比、色温、阴影衰减或焦散；
  - ❌ **不写相机与光学**：不写相机品牌、焦段、光圈、景深或胶片颗粒；
  - ❌ **不写场景台面与背景**：不规定微水泥、木桌、石板或棚拍背景；
  - ❌ **不写大画面机位与构图**：只管食物/饮品在杯/盘/锅内部的形态与朝向。

## 内置高清垫图库与一键拆单格（`assets/moodboards/` · 统一 `3×3` · 单格 `1024×1024`）

已内置 **27 张食饮图板 + 4 张摆件图板（共 31 张轻量 `3×3` 图板、279 张互不重样无水印高清单格，完整索引见 `assets/moodboards/INDEX.md`）**：
- **高定饮品（4 张 · 36 格）**：`饮品_01_冷萃咖啡与厚乳.jpg` ~ `饮品_04_热饮与立体顶构.jpg`
- **食材本体与香料坚果（6 张 · 54 格）**：`食材_01_鲜果切面与囊瓣.jpg` ~ `食材_06_浆果坚果与咖啡豆.jpg`
- **中餐常见餐系（4 张 · 36 格）**：`中餐_01_红烧炖肉与硬菜.jpg` ~ `中餐_04_清蒸川湘与糖水.jpg`
- **西日烘焙轻食甜品（4 张 · 36 格）**：`西日_01_法式起酥与可颂.jpg` ~ `西日_04_早午餐酸面包与轻食碗.jpg`
- **三大锅具王牌配菜（9 张 · 81 格）**：`煎锅_01~03`（27 格） | `炒锅_01~03`（27 格） | `奶锅_01~03`（27 格）
- **静奢高定摆件器皿（`d-image-director/assets/moodboards/` · 4 张 · 36 格）**：`摆件_01_金属水晶与黄铜托盘.jpg` ~ `摆件_04_玻璃水壶香座与餐具.jpg`

**拆单格垫 `@图1` 标准命令**（先 `read_file` 看目标 `3×3` 图板选格号 `1..9`，1 秒裁出 `1024×1024` 单格到 `%TEMP%\dumik-runs\` 喂 `referenceFiles`）：
```powershell
python "<插件根目录>\skills\d-food-drink-stylist\scripts\crop_moodboard_tile.py" --board "煎锅_03_冰花锅贴带子北非蛋.jpg" --tile 1 --out "$env:TEMP\dumik-runs\ref_冰花锅贴.jpg"
```

## 参考文档按需读取

1. **必读基础**：`references/editorial-realism-and-aesthetics.md`（去塑料感 5 类微观物理 + 器皿材质 + 色彩克制三角）与 `references/culinary-physics-deep-analysis.md`（六大口感物理可视化 + 三层风味建筑结构 + 8 大烹饪技法）；
2. **锅具项目（煎锅/炒锅/小奶锅/雪平锅）**：必读 `references/cookware-300-food-pairing-dna.md`；
3. **饮品/杯壶项目**：必读 `references/drink-physics-deep-analysis.md` + `references/beverage-food-catalog.md`；
4. **食材本体 / 生鲜原材**：必读 `references/ingredient-anatomy-dna.md`；
5. **中餐 / 西日成品菜**：加读 `references/pinterest-100-chinese-food-dna.md` 或 `references/pinterest-100-food-dna.md`。

## 跨端兼容（Codex / Antigravity / Claude Code / DSH / Linux）

- **Codex / Windows 参考包编译**：可运行 `scripts/compile_reference_pack.ps1 -Skill d-food-drink-stylist -Mode <drink|ingredient|cookware|chinese|western|all>` 一次打包对应参考文档；Linux / Grok Bot 环境直接按需 `read_file` 读取下方对应参考即可。
- **DSH / DesignFlow 垫图协同**：用 `crop_moodboard_tile.py` 裁出的 `1024×1024` 单格写入系统 `%TEMP%\dumik-runs\`，直接传入 `d-image-runner` / `designflow_generate_image` 的 `referenceFiles`（`@图1` 等），严禁在项目目录内残留临时切片。

## 交付方式

- 只输出 **「食饮选品排期」** 与 **「可直接嵌入 `d-image-director` 提示词的食饮本体造型片段（80~180 字）」**，不自行写整屏光影/相机/场景词，也不调付费生图接口。
