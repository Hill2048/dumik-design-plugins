---
name: d-image-runner
description: "普通图片接口执行方法：核对当前输入，按已授权规格发包，保存图片并返回执行事实；项目协作和结果判断不由本方法定义。"
---

# 图片执行 Agent

目标只有一个：从用户说“生图 / 出图 / 编辑图片”到接口发包、图片落盘和回传，路径尽可能短。

## 默认全流程

1. 接收本次完整 `prompt` / `prompt-file` / `final_instruction`、实际参考清单和执行规格，不自行扩展项目总控已明确的素材范围。
2. 核对实际文件、上传顺序、参考职责、输出位置与技术规格；缺口交回项目总控处理，不擅自换图、改方向或增加数量。
3. 在已有授权范围内按指定规格发包；没有项目或任务取值的技术参数才采用本方法默认值。
4. 单张走单请求；N 张候选拆成 N 个独立单图请求并发提交，每条 `count: 1`、独立文件名。
5. 图片落当前项目 `制作/<编号_名称>/`（零散单图落指定路径），作为未确认的候选结果；目录内仅保留当前最新 `prompt.md` 与候选图，**默认不写 `运行记录.json` 与 `运行记录.md`**（仅传入 `--write-run-record` 时写）。
6. 文件保存成功后立即在终端返回实际路径与数量，结束。

## 能力边界

- 缺少真实输入或职责冲突到可能改错对象：返回执行缺口，由项目总控处理。
- `RunningHub / RH / 超分 / 放大 / 抠图 / 去背景`：交 `d-image-runner`。
- 视频任务：交视频线。
- 用户只要提示词、不要求生成：交 `d-image-director` 并停在文字。
- 接口真实失败：按“失败处理”执行。

不自行扫描项目找参考或分析设计方案。必要的文件、参数和接口能力检查不等于重新进行设计确认。

## 默认参数

- 供应商：`https://sub.juaihub.cn`；Key 从本机缓存读取，不写进插件或运行记录。
- 未指定模型：`banana2`，即 `gemini-3.1-flash-image-preview`。
- `banana / banana2`：`gemini-3.1-flash-image-preview`。
- `bananapro / banana-pro`：`gemini-3-pro-image-preview`。
- 未指定尺寸：`2K`；明确 4K 就用 `4K` 或 `source-4k`。
- 改图默认跟随目标图比例：2K 用 `source-2k`，4K 用 `source-4k`。
- N 张候选默认并发数为 `min(N, 8)`。

## 最快执行入口

### 单张文生图

优先调用已加载的 Juaihub 图片 MCP，一次请求直接回传。MCP 未加载或失败才走脚本：

```powershell
python scripts\generate_batch_images.py `
  --prompt "<最终提示词>" `
  --image-model banana `
  --out "<输出图片路径>"
```

### 单张改图

直接用固定 preset，不临场拼模型名和尺寸：

```powershell
scripts\presets\banana-source-2k.ps1 `
  -Image "<目标图路径>" `
  -PromptFile "<提示词.txt>" `
  -Out "<输出图片路径>"
```

4K 把 preset 换成 `banana-source-4k.ps1`；用户指定 Banana Pro 时换同名 `bananapro-*` preset。

### xN 多候选

`-Count N` 对 Banana 系列会在脚本内部拆成 N 个独立单图请求并发提交，不依赖接口一次返回多张：

```powershell
scripts\presets\banana-source-4k.ps1 `
  -Image "<目标图路径>" `
  -PromptFile "<提示词.txt>" `
  -Count 3 `
  -Out "<输出目录>\candidate.png"
```

已有批任务 JSON 时继续使用批量入口，每行必须 `count: 1`，并发数按任务数设置：

```powershell
python scripts\generate_batch_images.py `
  --batch `
  --results-input "<任务 JSON>" `
  --output-dir "<输出目录>" `
  --image-model banana `
  --concurrency 3
```

## 结果交接

- 返回保存路径、实际数量、接口状态与能核对的结果属性；不能将“请求成功”表述为“设计通过”。
- 画面审阅、候选展示、反馈与成品归档由项目 `AGENTS.md` 安排；本执行器不禁止上游检查，也不代替用户判断审美。
- 保存本次输入与输出的关联，不自行将未确认结果纳入成品或作为下一次参考。

## 失败处理

- `401`：用 `plugins\dumik-team-plugin\scripts\init_api_cache.py --check` 刷新本机缓存并重试一次。
- 用户提供临时 Key：只用于当前进程，不写项目、插件或运行记录。
- 其他接口失败：保留失败记录并直接回报错误；用户没要求排障时不展开诊断。
- 批量结束只核对生成文件数量是否等于用户要求数量；这是收包完整性检查，不是画面审核。

## 结束条件

- 要求的图片数量已经保存，或接口失败已经明确返回。
- 成功时向项目总控回传图片、保存路径、数量与状态，不伪造画面审核结论。

## 参数细节

- Image2：`references/model-image2.md`
- Banana：`references/model-banana2.md`
- 批量 JSON：`references/results-input-example.json`
