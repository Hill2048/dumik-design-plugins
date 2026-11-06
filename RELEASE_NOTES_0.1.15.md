# DUMIK Team Plugin 0.1.15

## 本次更新：吸收 Higgsfield《Hell Grind》生产方法论

来源：`OSideMedia/higgsfield-ai-prompt-skill`（864★，32 子技能）。
该仓库源自 Higgsfield 官方开源的 95 分钟 AI 长片《Hell Grind》工程档案
（15 人 / 14 天 / 50 万美元 / 115,446 次生成 / 4 万余条提示词）。

原仓库 31,694 行 markdown 中**只取方法论、剔除全部工具与执行层**
（CLI、MCP、`models_explore`、模型参数枚举、账号与授权流程均未引入），
蒸馏为三份中文方法论，并入 `d-video-director`。

### 新增参考文件

| 文件 | 内容 |
|---|---|
| `references/video-methodology-mcsla.md` | MCSLA 五层公式、T2V/I2V 双范式、一镜一主动作、情绪可观察化、身份块与动作块分离、角色资产家族、场景 GEO 锚定、禁令字典、单变量迭代、6 轮诊断、反套话词表、镜头语言硬规则、年龄中性写法、对白容量 |
| `references/video-directing-shotlist.md` | 三层结构（全局风格前缀 / `@` 资产表含保真等级 / 具名分场）、单场提示词固定顺序、15 秒信封密度判断、节奏预算算术闸门、单调性审计、双对比切镜、连续性清单、交付前 10 条导演门禁 |
| `references/video-acting-and-failure-modes.md` | 表演五根柱子、从结局命名事件、倾听与反应、眼睛必须有生命、状态而非过渡、12 种失败模式与对策、帧级复核 |

### 与 DUMIK 原有体系的适配

- **MCSLA 的 M 层**只进 `execution_spec`，正文只写 C/S/L/A——不改动 DUMIK 的参数分离原则。
- 新方法论定位为**补充层**，冲突时以 `prompt-compiler.md` 与 `directing-design.md` 为准。
- 只补充 DUMIK 原未覆盖的规则：身份/动作分离、单变量迭代、6 轮诊断、反套话、双对比切镜、年龄中性、对白容量、节奏预算、单调性审计、失败模式表。

### 路由变更

`scripts/compile_reference_pack.ps1` 的 `d-video-director` 分支新增三条选择规则：

- `video-methodology-mcsla.md` —— 所有提示词任务必读
- `video-directing-shotlist.md` —— `storyboard|shot|shotlist|keyframe|scene|sequence|prompt|pipeline|director` 模式命中
- `video-acting-and-failure-modes.md` —— `acting|performance|character|dialogue|troubleshoot|diagnose|fix|failure|repair|report|analysis` 模式命中

### 验证

`compile_reference_pack.ps1` 六种模式全部编译通过：

```
prompt / storyboard / report / camera / depth / image-to-video
→ status=compiled，reference_count=20
```

规则包正文实测包含 MCSLA、身份块与动作块分离、节奏预算等内容。

### 已知事项

- **必须用 `pwsh`（PowerShell 7）运行** `compile_reference_pack.ps1`。
  用 `powershell`（5.1）会因无 BOM 中文内容按 ANSI 读取而解析失败。
  这是既有问题，非本次引入。

### 版本

- `dumik-team-plugin`: 0.1.14 → **0.1.15**
- `d-video-director` SKILL.md metadata: 0.1.4 → **0.1.5**
