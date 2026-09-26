---
name: d-api-test
description: "DUMIK API 基准测试入口。用于新增或更换图片 API 时，用固定双参考改图题测试模型可用性、尺寸、比例、速度和画面保持度；普通生图不走这里。"
metadata:
  version: 0.1.4
---

# API 基准测试

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加本次 API 和模型命中的规范；只有命中文件进入当前正文，读取完整规则包后才能发包或比较结果。

开始测试前先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-api-test -Mode <image|copy|video> -Model <模型名>`，再读取脚本返回的 `output_path`。规则包没有成功生成或没有读完时，不发包。

图片提示词与报告中的引用遵循 [图片引用格式](../../assets/image-reference-format.md)，统一为 `@图1` 等；固定素材文件名和模型名不改。对照历史基准时记录引用格式变化，不能把提示词版本差异误当成模型质量变化。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

先判断测试域：

遵循 [插件路由](../../assets/agent-skill-routing.md)。只有明确的 API 基准或模型比较需求才执行测试；普通生图失败的排障不自动变成付费基准测试。

- 图片 API：使用当前已实现的固定测试题，必须完整读取 `references/image-benchmark.md`；支持 Gemini Flash / Pro 与 GPT Image 2.5 Flare / Sunburst。
- 文案 API：尚未建立基准；用户明确要求时再新增独立测试题和脚本。
- 视频 API：尚未建立基准；用户明确要求时再新增独立测试题和脚本。

## 图片测试

1. 确认被测 `base_url`、模型名和临时密钥来源，不把密钥写入插件、任务单或报告。
2. 先用 `--dry-run` 检查 18 条任务，再明确告知用户将产生 18 次图片生成费用。
3. 用户确认执行后，运行 `scripts/run_image_benchmark.py`。脚本复用 `d-image-runner` 的发包层，不在本 skill 复制接口实现。
4. 检查 `summary.md`、两张九宫格和失败记录。技术通过不等于画面通过，必须人工复核食材替换、结构保持、水印和清晰度。
5. 对比不同 API 时保持测试图、提示词、模型、尺寸、比例、并发数一致；否则明确写“仅供参考”。
6. 默认每个模型最多运行 30 分钟；超时后停止该模型，并从已经落盘的图片恢复部分结果，未完成项记失败。

## 边界

- 这是供应商和模型基准，不替代 `d-image-runner` 的日常生图。
- 不因测试失败自动切换生产 API。
- 不在报告中记录完整 Key、Authorization 请求头或响应中的敏感字段。
- 单次结果受队列波动影响；需要正式选型时至少跑三轮，再比较中位数和成功率。

## 结束条件

- 任务数、成功数、失败数、实际尺寸、比例误差和耗时已记录。
- 结果图已做人工画面复核。
- 结论明确区分接口可用性、速度和画面质量。
