# DUMIK 统一路由

本文件是图片和视频任务的唯一分流表。先判断最终交付，再进入一个主 skill；不要让用户在同一阶段选择多个旧入口。

## 图片线

```text
详情页策略 / 视觉设定 / 卖点证据 / 创意方向
  -> d-visual-plan (mode=image)

普通改图 / 多参考融合 / 洗图 / KV / brief / 材质与场景
  -> d-image-director (mode=edit 或 brief)

四宫格抽卡 / 单卖点发散 / 全幅候选
  -> d-image-director (mode=direction)

图片变脏 / 线稿色块重绘 / 高清修复
  -> d-image-director (mode=hd)

产品局部漂移 / 把手盖子五金 / 品牌区 / 局部切贴
  -> d-image-director (mode=repair)

明确生图 / 改图 / 图片并发
  -> d-image-runner (mode=generate)

RunningHub / 放大 / 超分 / 抠图 / 去背景
  -> d-image-runner (mode=postprocess)

详情页项目制自动串跑 / pilot / 校准 / 批量 / 终审
  -> d-project-pipeline
```

## 视频线

```text
视频卖点顺序 / 转化逻辑 / 证据链 / 开头钩子
  -> d-visual-plan (mode=video)

写 / 改 / 优化任意视频提示词
  -> d-video-director（唯一提示词编译主线）

已有视频拉片 / 关键帧 / 口播字幕 / HTML 证据报告
  -> d-video-director（先做证据分析；只要报告时在此结束）

故事板 / 连续分镜 / 关键帧 / 逐镜提示词
  -> d-video-director（统一主线 + 故事板交付结构）

深度视频转真实场景
  -> d-video-director（深度素材职责 + 统一主线）

内容设计 / 电影调度 / 物理光色 / 复合运镜
  -> d-video-director（所有提示词共同设计层，不设独立模式）

明确生成视频 / 确认片 / 批量提交 Dreamina、Seedance 或 Veo
  -> d-video-runner
```

## 支撑入口

- `d-init`：新项目或新电脑初始化。
- `d-api-test`：图片 API 基准测试，不参与日常生产。
- `d-psb-install`：PSB 智能对象工具安装与更新。

## 路由纪律

- 只要用户要文字提示词，停在 director/plan，不调用执行器。
- `prompt` 是唯一提示词编译主线；已有视频分析是证据阶段，故事板是交付结构，深度视频是素材职责变化，三者都不能另起一套提示词逻辑。
- 只有用户明确要求生成、出图、出片、提交或批量，才进入 runner。
- 有真实参考视频时先完成证据分析，再沿统一主线输出单条 Prompt、故事板或深度转译结果。
- 参考素材中不存在的主体、道具、动作和声音，不写进最终提示词或负面约束。
- 旧 skill 已移入 `archive/merged-skills-legacy/`，只用于追溯，不再作为新任务入口。
