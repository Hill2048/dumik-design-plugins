# DUMIK 插件已检查清单

检查时间：2026-09-07（Asia/Shanghai）

适用版本：

- 插件版本：`0.5.22`
- 技能数量：`15`
- 详细版本：`assets/skill-versions.json`
- 拉片网页：`D-video-report 0.3.0`
- 图像提示词与高清修复：`D-image-prompt 0.4.0` + `D-image-HD 0.2.0`
- 视频策划与分镜：`D-video-plan 0.1.6` + `D-storyboard 1.4.0`
- 深度视频执行：`D-video-run 0.2.0`

## 已确认正确

- `skills` 下 15 个技能目录全部存在 `SKILL.md`。
- `.codex-plugin/plugin.json` 与 `assets/skill-versions.json` 均可解析，插件版本一致，均已登记 `D-video-report`。
- `D-video-report` 已接入统一路由、README、流程地图、D-init 视频总导演模板和 `D-video-plan` 交接。
- `D-video-report` 包含固定网页模板、报告数据协议、页面构建脚本、交互规范和关键帧下载数据脚本。
- 拉片模板已用真实图片和视频构建预览；桌面与移动端截图无横向溢出，筛选、字幕搜索、时间跳转通过 Playwright 测试。
- 深度视频已明确为提示词与参考组织方式，不是新模型；底层继续走 Seedance `multimodal2video`。
- 深度引导任务校验已通过 3 项测试：正常挂载 `reference_videos`、缺深度视频拦截、误走 Veo 拦截。
- 人物身份卡拼接脚本、线稿色块高清修复脚本均通过语法和命令入口检查。
- 全包 15 个技能、18 个 JSON、16 个 Python 脚本、8 个 JavaScript 脚本和现有 4 项单元测试已复查通过。
- `build_frame_download_data.mjs` 通过 `node --check`，并用真实 PNG 生成过 `frame-downloads.js`；图片数量、输出文件和相对路径键均正确。
- 本机 Python 可用：`Python 3.12.10`。
- 本机 FFmpeg / FFprobe 可用：`8.1.2`。
- 本机 Node.js 可用：`v26.5.1`。
- 本机 Dreamina CLI 可用。
- 图片生成、视频生成和视频证据报告脚本均存在。
- API 本机缓存存在且检测到非空 Key；清单不记录、不展示 Key。
- NAS 图片配置存在；公网 tunnel 属动态项，不在本清单固化可用状态。
- 插件包敏感信息扫描通过：未发现明文 API Key、Bearer token 或私钥。

## 后续调用规则

插件版本仍为 `0.5.22` 且本清单存在时：

- 不重复检查插件目录、技能数量、版本矩阵、Python、FFmpeg、FFprobe、Node、Dreamina 和敏感信息。
- 只检查本次项目目录、输入视频、输出路径、字幕/音轨和任务所需工具是否仍可调用。
- 实际调用图片或视频接口前，仍轻量确认本次 Key、额度、登录和权限。
- `D-video-report` 只有在需要本地关键帧下载数据时才检查 Node；普通抽帧只检查 FFmpeg / FFprobe。
- 使用动态公网 URL 前必须重新确认可达性。

## 清单失效条件

- 插件版本、技能版本、目录结构、执行脚本或模型接口规范变化。
- 用户明确要求重新全量检查。
- 工具命令或脚本实际执行失败。

清单失效后重新检查并更新本文件，不能继续引用旧结论。
