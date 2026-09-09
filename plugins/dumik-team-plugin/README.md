# DUMIK 团队插件

这是给 DUMIK 团队共享的 Codex 插件包，保留本项目最核心的统一路由、项目入口协议、已检查清单、图片提示词、改图指令、单图生图/改图、明确批量时的批量改图、RunningHub 后处理、统一视频故事板、视频写作和批量生视频流程。图片/视频的总监判断已并入 AGENTS.md，不再是独立 skill。

## 已收纳流程

- `d-init`：项目初始化。新仓库/新电脑装好插件后跑一次，按模板生成项目入口文件（AGENTS.md、design.md），按需建第一个项目目录并做环境检查；只补缺不覆盖。项目根就是用户指定的项目文件夹，不生成任何指针或历史文件。
- `d-api-test`：新增或更换 API 时运行固定基准。当前内置双参考改图题，可测试 Gemini Flash / Pro 和 GPT Image 2.5 Flare / Sunburst 的多尺寸、多比例、速度与画面保持；Image2.5 自动使用官方合法的 1K、2K、最大尺寸矩阵。
- `d-psb-install`：安装或更新 Photoshop PSB 智能对象工具，默认走 UXP，自动核对 GitHub 版本并验证安装结果。
- 总监判断（已并入 AGENTS.md，非独立 skill）：图片/视频任务先按 AGENTS.md 总监职责给一句判断、决定是否进入项目制，再按统一路由分流到下面的 D-* skill。原 `ecom-visual-director` / `tvc-director` 已归档在 `archive/directors-merged-into-agents-md/`。
- `d-visual-plan`：统一图片详情页策略和视频转化策划，负责视觉设定、卖点证据、创意方向、证据链和转化节奏。
- `d-image-director`：统一普通改图、视觉 brief、四宫格发散、线稿色块高清重绘和产品局部修复。
- `d-image-runner`：统一普通生图/改图、多候选并发和 RunningHub 放大、超分、抠图、去背景。
- `d-video-director`：以 Seedance 2.5 方法升级的提示词编译器为核心，统一任意视频提示词、已有视频分析、HTML 拉片报告、故事板、关键帧、深度视频和电影化复合运镜；目标模型只在末端适配。
- `d-video-runner`：统一确认片、普通视频、深度视频和 Dreamina / Seedance / Veo 批量提交。
- `d-project-pipeline`：详情页项目制 pilot、方向闸门、校准回写、批量出图、局部修复和终审。
- 旧入口已归档到 `archive/merged-skills-legacy/`，仅用于追溯，不再作为新任务入口。

## 流程地图

- Markdown 版：`assets/workflow-map.md`
- 可视化版：`assets/workflow-map.html`
- Agent 路由：`assets/agent-skill-routing.md`
- 项目入口与环境协议（唯一来源）：`assets/project-env-protocol.md`
- 已检查清单：`assets/verified-environment-checklist.md`

## 团队使用建议

优先把任务说成真实工作目标，例如“这张锅图保留结构，改成天猫主图风格”“根据这些参考图写改图指令”“批量给这组图片写提示词”“把这个卖点写成 30 秒视频分镜”。

图片改图默认遵守本项目规则：先判断图片角色，锁定产品结构和品牌区域，明确比例和目标图，最终给可直接复制的中文改图指令。

所有图片和视频技能默认只交付文字提示词、brief、脚本或分镜，不自动生图、不自动生视频、不调用生成接口。只有明确要求“生图 / 出图 / 生成图片 / 调用接口 / 生成视频 / 调用即梦”时才进入实际生成。进入项目制或批量执行前，先按 `assets/project-env-protocol.md` 确认项目根：用户指定了项目文件夹就直接以该文件夹为项目根，没指定就先问项目文件夹路径和项目类型；用户也可以切换项目或本次不进入项目。项目根不写指针文件。

所有视频提示词先经过 `d-video-director/references/seedance25-prompt-compiler.md`：先锁故事合同和素材职责，再组织事件、镜头与声音，最后适配 Seedance 2.5、Dreamina 2.0 或 Veo。模型、画幅、时长、分辨率、帧率和声音开关属于执行规格，不写进最终 Prompt。

## 钩子

`hooks/` 只保留团队默认触发提示；完整路由以 `assets/agent-skill-routing.md` 为准。图片、视频任务先按 AGENTS.md 总监职责给一句判断，再按统一路由把任务交给对应技能。

## 注意

插件不包含历史输出图片、临时项目、采集流程、个人缓存或 API Key。图片接口默认使用 `https://sub.juaihub.cn`；同时优先读取本机缓存：先运行 `scripts/init_api_cache.py`，它会从 `CODEX_HOME/config.toml` 和 `CODEX_HOME/auth.json` 读取可用 URL + key，写入本机 `CODEX_HOME/dumik-team-plugin/api_settings.py`。日常调用先读这个缓存；命令行显式参数可覆盖；没有缓存时再读 Codex 配置、环境变量，最后回到 `sub.juaihub.cn`。批量生视频需要本机已登录并可用的 `dreamina` CLI。

本机缓存只留在用户电脑，不进公开插件包；任何脚本都不能打印 key 或 token。

默认不自动生图。只有明确要求“生图 / 出图 / 生成图片 / 调用接口”时才调用图片接口；没有明确说批量时，默认按单图处理。

生图前先选模型：`gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`、`banana2` 或 `bananapro`。用户只说 `image2.5` 时使用质量优先的 Sunburst；需要快速迭代时使用 Flare。插件全局默认仍为 `banana2`。

各 skill 版本号见 `assets/skill-versions.json`。
