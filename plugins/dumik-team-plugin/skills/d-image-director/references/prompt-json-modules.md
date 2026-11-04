# JSON / 模块库字段化

模块库便于复用与批量，**不能替代**控制层检查点。字段空着就要标待确认，不能靠 JSON 形状假装已锁结构。

## 何时用

- 成组主图/详情要稳定字段，交给 pipeline 或表格。
- 需要人机都勾选：已锁 / 自由 / 禁止。
- 与 runner 的 batch 输入对齐时，字段名保持稳定。

## 建议字段（可删减）

```json
{
  "task_id": "",
  "ratio": "2:3",
  "refs": [
    {"tag": "@图1", "role": "structure"},
    {"tag": "@图2", "role": "lighting_mood"}
  ],
  "p0_structure": {
    "silhouette": "locked",
    "parts": [],
    "logo_policy": "placeholder_or_post"
  },
  "control_zone": "",
  "free_zone": "",
  "priority": {"P0": [], "P1": [], "P2": []},
  "segments": {
    "style": "",
    "subject_lock": "",
    "scene": "",
    "camera": "",
    "light": "",
    "material": "",
    "quality": "",
    "negative": ""
  },
  "series_rules_ref": "design.md#设计语言",
  "human_priority_judged": false
}
```

## 硬规则

1. `human_priority_judged: false` 时，禁止把反推或自动填空结果当最终交付（见 `d-prompt-reverse`）。
2. 空的 `p0_structure` 不得生成「看起来完整」的假 JSON 应付检查。
3. 模块拼装后仍须输出符合 `prompt-contract.md` 的可读 Prompt 正文（或明确由下游编译）。
4. JSON 不是新的控制真理：冲突时以原图结构 + 用户确认 + 控制层为准。

## 与 Skill 链

字段填完 → `d-image-director` 编译正文 →（可选）`d-consistency-check` → 用户授权后 `d-image-runner`。模块库不跳过 director。


## 批量注意

字段化后仍逐条编译可读 Prompt；禁止只把 JSON 丢给模型当唯一输入（除非下游明确支持且仍含自然语言主体锁）。
