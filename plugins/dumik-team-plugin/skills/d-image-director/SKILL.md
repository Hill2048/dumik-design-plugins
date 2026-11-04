---
name: d-image-director
description: "编写或修改图片提示词与改图指令（有图/纯文字均可）。五模式：edit=改图/多参考/洗图/KV/场景/材质；brief=构思视觉方向；direction=候选方向/四宫格；hd=线稿色稿高清重绘；repair=局部产品漂移。写词前过控制层（P0–P2/分段/条件模块）。反推参考图提示词→d-prompt-reverse；策略→d-visual-plan；生图→d-image-runner；三态验收→d-consistency-check。连续短反馈沿用当前文字任务。"
metadata:
  version: 0.3.0
---

# 图片导演

本 skill 提供图片专业方法，不承担项目总控。任务意图、有效决定、提问与确认方式由项目 `AGENTS.md` 给定；参考资料中的流程与展示范例不另设项目协作规则。

统一原 `D-image-prompt`、`D-image-HD`、`D-image-repair` 和 `D-grid-prompt` 的图片创作入口。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加本轮命中的条件文件；只有命中文件进入当前正文，读取完整规则包后才能分析画面或写 Prompt。不能把链接当目录，也不能以“当前上下文已经有”替代本轮读取。

Windows / 有 PowerShell 时：先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-image-director -Mode <edit|brief|direction|hd|repair> -Model <模型名>`，再读取脚本返回的 `output_path`。规则包没有成功生成或没有读完时，不进入画面分析。

**Grok Bot / Linux：** 若 `compile_reference_pack.ps1` 或 PowerShell 不可用，跳过编译脚本，但必须用真实文件工具直接 `Read` Mode 路由表中本轮命中的全部文件（含 `control-layer.md` 与 `prompt-contract.md`）；不得因跳过脚本而跳过参考正文。读完命中文件后再写 Prompt。

## Mode 路由表

加载本 skill 后的**第一动作**：只选下表中的 **一个** mode，然后**只读**该 mode 命中的参考文件。默认禁止通读全部 `references/legacy/`。

| Mode | 触发（用户说法/任务形态） | 必读命中文件 |
| --- | --- | --- |
| `edit` | 改图、多参考、洗图、KV、场景、材质/人物锁定、连续追改 | **核心**：`control-layer.md` + `prompt-contract.md` + `prompt-segments.md` + `six-structure.md` + `legacy/D-image-prompt.md`；人物/材质/返修/空间/模板再读 `templates.md` |
| `brief` | 按任务构思视觉方向；尚未要完整可复制改图指令 | 同 edit 核心四件 + legacy prompt（edit/brief 共用） |
| `direction` | 方向差异、候选发散、四宫格探索 | `control-layer.md` + `prompt-contract.md` + `prompt-segments.md` + `legacy/D-grid-prompt.md` |
| `hd` | 线稿/色稿/高清重绘、结构锁后再上真实材质 | `control-layer.md` + `prompt-contract.md` + `prompt-segments.md` + `legacy/D-image-HD.md`；执行脚本时再读 `scripts/hd/` |
| `repair` | 只修已选图局部产品漂移，不重做整图 | `control-layer.md` + `prompt-contract.md` + `legacy/D-image-repair.md`；局部脚本再读 `scripts/repair/` |

### 条件命中（任务匹配再读；禁止无匹配时通读）

| 条件 | 追加读取 |
| --- | --- |
| 白底转场景 / 白底进场景 | `white-to-scene.md` |
| 光影专项、调性反差、实拍+C4D 分工 | `lighting-control.md` |
| 机位/焦距/景深/广角风险 | `camera-language.md` |
| 真实感、世界逻辑、轻微不完美 | `realism.md` |
| 多角度成套、Logo 后期叠 | `multi-view-lock.md` |
| 模特佩戴/持握同框 | `model-product.md`（可与 `templates.md` 人像段并用） |
| 要 JSON/模块字段化 | `prompt-json-modules.md` |
| 用户要反推/拆参考图提示词 | **不在本 skill 硬写终稿** → 交 `d-prompt-reverse` |

选错 mode 时先改 mode 再读对应文件，不要把多个 legacy 拼成一份 Prompt。**禁止默认通读全部 legacy 与全部条件模块。**

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

**Grok Bot / Linux：** 跳过上述 Windows 自动更新脚本；需要更新时按宿主约定更新插件仓库，不把跳过更新当成跳过参考读取。

## 模式

选择遵循 [插件路由](../../assets/agent-skill-routing.md)；多轮追改读取 [任务状态合同](../../assets/task-state-contract.md)，先确定修改部件和当前有效属性，再写独立完整正文。模式细则以上方 **Mode 路由表** 为准。

- `edit`：普通改图、多参考融合、洗图、KV、场景、材质和人物锁定。
- `brief`：按任务要求构思图片视觉方向；确有策略缺项时才使用 `d-visual-plan`。
- `direction`：把给定表达展开为有意义的候选差异；四宫格是可选表现形式，不规定方向数或确认关卡。
- `hd`：线稿 → 色稿 → 真实画面提示词 → 高清重绘。
- `repair`：只诊断和修复已选图片中真实存在的局部产品漂移。

## 控制层检查（写 Prompt 前）

选好 mode 并读完命中参考后、动笔写 Prompt 前，必须过一遍（细则见 `references/control-layer.md`）：

1. **P0/P1/P2**：结构永不交易；品牌清晰次之；氛围可让步。
2. **结构锁（P0）**：比例、轮廓、关键部件、接口/按键、材质固有色、Logo/丝印区 — 不得重设计；看不见的标「无法从当前图确认」，不瞎补。
3. **去抽象化**：位置、机位、占比、光向、不可改项写清。
4. **控制区 vs 自由区**：锁死与可发挥必须明示。
5. **负面禁止项单独成段**：只写本任务真实风险。
6. **系列规则 / design 设计语言**：有则强制读并继承；无则标待确认。
7. **线稿分工**（有线稿时）：产品线稿锁结构，场景线稿锁构图。
8. **分段顺序**：风格→主体锁→场景→机位→光影→材质→质量→禁止（见 `prompt-segments.md`）；需要叙事骨架时再用 `six-structure.md`。

## 共同规则

- 多参考图先短写每张图的真实职责；只出现实际存在并需要控制的内容。
- 采用最小充分描述：不补写画面里没有的人物、手部、食材、厨具、火焰、声音或其他道具，也不为不存在的对象添加负面词。
- 产品轮廓、比例、关键部件、材质和品牌区优先于风格描述。
- 做风格或光影追改时，先把“更暗、更通透、更电影”等抽象判断翻译成曝光关系、光比、阴影边缘和材质反射。阴天不等于整体欠曝：要写明均匀漫射光、收窄光比、提亮暗部、软化投影并保留暗部细节。
- 改色时优先保留主体材质的固有色，再写目标色彩如何进入暗部、中灰和高光；不要用“压低黄色、压低绿色、消除高光”这类单独的负向词把木材、植被或金属的真实颜色抽干。
- 材质必须写光打在表面上的结果。户外金属要承接天空的宽面积冷白漫反射，木材保留真实暖色与纤维层次，地面和主体要有统一的环境反射、接触阴影和边缘光，不能只堆“油润、真实、高级”。
- 写多图前复核目标图和参考图的实际状态，特别是原片、调色片和效果片混在一起时；目标图由本次要修改的素材决定，不由图号或画面明暗猜定。职责有冲突就指出并澄清，不能把已经调坏的效果片当成原始结构目标。
- 只写提示词时不调用接口；明确生图、改图或批量生成时，将最终任务交给 `d-image-runner`。
- 用户只要「对比原图审结构 / 一致性验收」时交给 `d-consistency-check`，本 skill 不代替三态审稿。
- 用户要「反推 / 拆参考图提示词」时交给 `d-prompt-reverse`（人判主次）；本 skill 不接一键终稿。

## 五维画面编译

每次写图片提示词都按以下顺序检查，不能只描述风格结果：

1. **职责解构**：先给每张输入绑定真实职责，分开结构、构图、光影、色调、材质和局部替换；主体轮廓、比例、关键部件与连接方式优先锁定。
2. **抽象转具象**：把“高级、通透、有质感、电影感”翻译成厚度、倒角、粗糙度、反射形态、接触阴影、边缘光和中灰过渡。
3. **光影按物理关系写**：明确光源位置与软硬，区分降曝光和改光比；需要阴天时写收窄光比、提亮暗部、软化投影和空间进深。
4. **色彩保护固有色**：用正向色彩倾向描述暗部、中灰和高光，保留木材、植被、食材等主体的固有色，不用粗暴去色制造暗调。
5. **动作闭环**：主指令明确写出保留什么、替换什么、移除什么、改善什么；只加画面中实际存在或用户明确要求的元素，不靠无关负面词填充。

## 模式资料

进入本 skill 后：先按 **Mode 路由表** 选定唯一 mode；再读该 mode **必读**文件；仅当任务匹配时追加**条件命中**文件。`references/original.md` 仅追溯旧口径时按需读。信息传递与可测标准见 [`../../assets/workflow-chain.md`](../../assets/workflow-chain.md)。

- `edit / brief`：核心四件（control-layer / prompt-contract / prompt-segments / six-structure）+ `legacy/D-image-prompt.md`；人物/材质等再读 `templates.md`；条件表按需。
- `direction`：control-layer + prompt-contract + prompt-segments + `legacy/D-grid-prompt.md`。
- `hd`：control-layer + prompt-contract + prompt-segments + `legacy/D-image-HD.md`，脚本见 `scripts/hd/`。
- `repair`：control-layer + prompt-contract + `legacy/D-image-repair.md`，脚本见 `scripts/repair/`。

没有完成必读命中文件的实际读取时，停在准备阶段，不输出最终 Prompt，也不交给 `d-image-runner`。

统一输出比例、参考图职责、主指令和最小风险约束；不要让多个旧模式重复拼接整段提示词。

## 改图提示词交付检查

图片编号与素材映射遵循 [图片引用格式](../../assets/image-reference-format.md)，统一使用 `@图1`、`@图2` 等。此规则也适用于高清修复、局部修复和方向探索，不限于普通改图；模型参数与文件名保持原样。

适用于 `edit / brief` 的最终图片提示词；用户仅问原因、讨论方向或要求差异说明时，不强套完整提示词格式。项目规则与用户明确指定的格式优先。

- 默认首行只写标准比例 `比例：1:1` 等；最终提示词放在可复制代码块内，块内首行重复同一比例。
- 多图按实际配套输入顺序用 `@图1 / @图2 / ...` 简述职责，角色说明放在代码块开头一次写清；单图省略角色行。主指令用一段描述画面，末尾一句集中收口关键约束。
- 默认提示词 250–450 字，复杂任务最多 600 字；不在每段重复结构保护与禁止项。代码块外需要说明变化时，只给 2–4 条短句。
- 追改先核对原目标、仍有效的参考职责和本轮变化。补充参考不自动替换旧参考；如精简输入，明确哪些图片不再传入、其仍有效的信息如何保留，不能静默漏图或重编号。
- 将“体积感、整体感、质感”等要求转成厚度、倒角、反射、粗糙度、光影等可见变化；不据此擅自重做未受影响的配色、排版或机位。只有确实阻碍执行的歧义才提问。
- 交付前单独检查代码块：离开聊天历史仍能知道改谁、改什么、每张图的用途；本轮未要求改变的决定保持有效。不得用“沿用之前”代替完整描述。
