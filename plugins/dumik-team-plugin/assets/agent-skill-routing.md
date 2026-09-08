# DUMIK 统一路由

本文件是图片和视频任务的唯一分流表。先判断最终交付，再进入一个主 skill；不要让用户在同一阶段选择多个旧入口。

## 图片线

```text
详情页策略 / 视觉设定 / 卖点证据 / 创意方向
  -> D-visual-plan (mode=image)

普通改图 / 多参考融合 / 洗图 / KV / brief / 材质与场景
  -> D-image-director (mode=edit 或 brief)

四宫格抽卡 / 单卖点发散 / 全幅候选
  -> D-image-director (mode=direction)

图片变脏 / 线稿色块重绘 / 高清修复
  -> D-image-director (mode=hd)

产品局部漂移 / 把手盖子五金 / 品牌区 / 局部切贴
  -> D-image-director (mode=repair)

明确生图 / 改图 / 图片并发
  -> D-image-runner (mode=generate)

RunningHub / 放大 / 超分 / 抠图 / 去背景
  -> D-image-runner (mode=postprocess)

详情页项目制自动串跑 / pilot / 校准 / 批量 / 终审
  -> D-project-pipeline
```

## 视频线

```text
视频卖点顺序 / 转化逻辑 / 证据链 / 开头钩子
  -> D-visual-plan (mode=video)

已有视频拉片 / 关键帧 / 口播字幕 / HTML 证据报告
  -> D-video-director (mode=analyze)

故事板 / 连续分镜 / 关键帧 / 逐镜提示词
  -> D-video-director (mode=storyboard)

深度视频转真实场景 / 复合运镜 / 电影调度
  -> D-video-director (mode=depth 或 cinematic)

明确生成视频 / 确认片 / 批量提交 Dreamina、Seedance 或 Veo
  -> D-video-runner
```

## 支撑入口

- `D-init`：新项目或新电脑初始化。
- `D-api-test`：图片 API 基准测试，不参与日常生产。
- `D-psb-install`：PSB 智能对象工具安装与更新。

## 路由纪律

- 只要用户要文字提示词，停在 director/plan，不调用执行器。
- 只有用户明确要求生成、出图、出片、提交或批量，才进入 runner。
- 有真实参考视频时，先 `D-video-director analyze`，再进入 `storyboard / depth`。
- 参考素材中不存在的主体、道具、动作和声音，不写进最终提示词或负面约束。
- 旧 skill 已移入 `archive/merged-skills-legacy/`，只用于追溯，不再作为新任务入口。
