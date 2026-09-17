---
name: d-image-director
description: "图片创作与修复总入口。统一普通改图、视觉 brief、四宫格发散、线稿色块高清重绘和产品局部修复；只写提示词时停在文字，明确生图时交给 d-image-runner。"
metadata:
  version: 0.1.1
---

# 图片导演

本 skill 提供图片专业方法，不承担项目总控。任务意图、有效决定、提问与确认方式由项目 `AGENTS.md` 给定；参考资料中的流程与展示范例不另设项目协作规则。

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-image-prompt`、`D-image-HD`、`D-image-repair` 和 `D-grid-prompt` 的图片创作入口。

## 模式

- `edit`：普通改图、多参考融合、洗图、KV、场景、材质和人物锁定。
- `brief`：按任务要求构思图片视觉方向；确有策略缺项时才使用 `d-visual-plan`。
- `direction`：把给定表达展开为有意义的候选差异；四宫格是可选表现形式，不规定方向数或确认关卡。
- `hd`：线稿 → 色稿 → 真实画面提示词 → 高清重绘。
- `repair`：只诊断和修复已选图片中真实存在的局部产品漂移。

## 共同规则

- 多参考图先短写每张图的真实职责；只出现实际存在并需要控制的内容。
- 采用最小充分描述：不补写画面里没有的人物、手部、食材、厨具、火焰、声音或其他道具，也不为不存在的对象添加负面词。
- 产品轮廓、比例、关键部件、材质和品牌区优先于风格描述。
- 只写提示词时不调用接口；明确生图、改图或批量生成时，将最终任务交给 `d-image-runner`。

## 模式资料

- `edit / brief`：交付提示词前必须读取 [references/legacy/D-image-prompt.md](references/legacy/D-image-prompt.md)，不能只读本入口就输出；[references/templates.md](references/templates.md) 按需读取。
- `direction`：按需读取 [references/legacy/D-grid-prompt.md](references/legacy/D-grid-prompt.md)。
- `hd`：按需读取 [references/legacy/D-image-HD.md](references/legacy/D-image-HD.md)，执行脚本位于 `scripts/hd/`。
- `repair`：按需读取 [references/legacy/D-image-repair.md](references/legacy/D-image-repair.md)，局部脚本位于 `scripts/repair/`。

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
