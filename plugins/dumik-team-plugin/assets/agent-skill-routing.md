# DUMIK 唯一路由合同

本文件是 DUMIK Team Plugin 的唯一能力路由。项目根目录的 `AGENTS.md` 优先决定项目协作、授权、确认和目录；本文件只决定当前工作应进入哪个插件 skill。9 个 skill 是专业入口，不互相争夺总控，也不在没有明确条件时串联。

## 判定顺序

按下面顺序只选一个主 `route_id`：

1. 先看用户要交付什么：提示词、策略、审核、实际执行、基准测试、项目入口或工具安装。
2. 再看媒体类型：图片或视频。
3. 再看操作类型：改写、规划、生成、后处理或批量。
4. 数量与授权分开判断：“批量写提示词”仍是文字任务，多候选生成可直接交 runner；只有需要跨步骤依赖、恢复与执行编排时才使用 pipeline。项目制本身不是生成授权。

“提示词、改图指令、分镜、故事板”优先进入 director；“生成、出图、出片、提交、调用接口、放大、抠图、去背景”才进入 runner。Runner 不替用户重新设计提示词；缺少完整提示词时退回对应 director。

## 图片路由

```text
image.prompt
  用户要写/改/优化图片提示词、改图指令、材质、场景、局部修复、高清重绘或方向探索；支持有图与纯文字创作
  -> d-image-director

image.strategy
  详情页结构、卖点顺序、视觉证据或图片创意策略，且当前不是具体单图提示词
  -> d-visual-plan

image.execute
  明确要求生图、出图、改图执行、调用图片接口、批量候选、放大、超分、抠图或去背景
  -> d-image-runner

image.batch
  明确要求成组图片的跨步骤执行编排、自动串跑或恢复已有流水线；不因“批量写词”、项目制或单纯多候选生成触发
  -> d-project-pipeline
  -> 按任务依赖交给 d-image-director / d-image-runner
```

单图“给我提示词”不进入 `image.execute`；只说“改图”但没有明确执行动作时，先按 `image.prompt` 处理。用户明确说“现在执行 / 调接口 / 出图”时，才切换到 `image.execute`。

## 视频路由

```text
video.strategy
  视频卖点顺序、转化逻辑、证据链、开头钩子或内容策略
  -> d-visual-plan

video.prompt
  视频提示词、故事板、连续分镜、关键帧、已有视频分析、拉片、口播字幕、HTML 证据报告或导演调度
  -> d-video-director

video.execute
  明确要求生成视频、出确认片、提交 Dreamina / Seedance / Veo 或批量执行
  -> d-video-runner
```

`d-video-director` 是视频文字与证据分析入口；`d-video-runner` 只负责实际提交。视频模型名称只影响末端适配，不改变主路由。

## 支撑路由

```text
project.entry
  初始化或维护项目 AGENTS.md / design.md / 项目上下文钩子
  -> d-init

api.benchmark
  新增或更换图片 API，比较模型成功率、尺寸、比例、速度或画面保持度
  -> d-api-test

psb.install
  安装或更新 PSB 智能对象工具
  -> d-psb-install
```

## 同一任务的路线锁

- 同一任务一旦确定 `route_id`，后续“再改、继续、加强、换材质、不要阴影、文字更清楚、改成银色”等反馈默认沿用原路线，不重新选 skill。
- 新增图片先判断是补充、替换还是新目标；保持文件身份与职责。实际输入重排时同步更新全部编号引用，不能为保留旧编号而错配图片。
- 只有用户明确改交付类型、媒体类型、执行授权、项目或产品，才解除路线锁。
- 缺提示词时由对应 director 准备，再回 runner 执行；避免无新缺口的往返。关键帧静态画面可交图片 director 编译，视频 director 保留镜头连续性，不重复策划。
- 批量任务由 `d-project-pipeline` 持有编排状态，单项提示词仍由 `d-image-director` 或 `d-video-director` 生成，实际执行再交 runner。

## 输出与恢复

- 文字任务停在对应 director / plan；只有用户明确要求实际生成、提交或后处理才进入 runner。
- 任务状态、路线锁、目标素材、参考职责、已确认决定和最后完整 Prompt 按 [任务状态合同](task-state-contract.md) 记录。
- 最终 Prompt 必须独立可用，不用“上一版、沿用之前、同上、其他不变”等省略有效决定。具体空间位置和视频事件先后不是聊天上下文，不按单词机械禁用。
- `@图1` 等图片引用只表示本次实际输入顺序；职责以 Prompt 中的角色说明为准，不默认把 `@图1` 当目标图。

旧 skill 和旧路由只在 `archive/` 中追溯，不参与当前选择。任何新增 skill 必须先补充本文件的唯一 `route_id`、触发条件、排除条件和交接关系，再进入插件。
