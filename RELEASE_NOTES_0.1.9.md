# DUMIK Team Plugin v0.1.9 更新公告

发布日期：2026-09-15

本次对比正式标签 `v0.1.8`（`e7e69e3`），只扩展项目级上下文加载钩子的宿主覆盖范围，不改动图片、视频方法与执行脚本。

**核心变化：项目上下文钩子从只支持 Codex，扩展为 Codex 与 ZCode 双宿主；同一项目可以两套并存，互不覆盖。**

## 与 v0.1.8 对比

| 方面 | v0.1.8 | v0.1.9 |
| --- | --- | --- |
| 钩子宿主 | 只登记 Codex 项目 `.codex/hooks.json` | 按宿主登记 Codex `.codex/hooks.json` 或 ZCode `.zcode/config.json` |
| 加载器 | 仅接受 `.codex/hooks` 安装位置 | 同一份加载器接受 `.codex/hooks` 与 `.zcode/hooks` |
| 安装方式 | `--project-root` | `--project-root` 加 `--host auto\|codex\|zcode`，默认自动判断 |
| ZCode 运行时开关 | 未涉及 | 安装时确保 `hooks.enabled` 为 `true`；该值被显式设为 `false` 时报错退出，不改写用户设置 |
| 同项目双宿主 | 不存在该情形 | Codex 与 ZCode 两套配置和加载器并存，重复执行仍不重复注册 |
| 测试 | 18 项 | 27 项，覆盖两条安装与加载路径 |

## 1. 加载器支持两种安装位置

`hooks/load-project-context.js` 不再要求安装目录名必须是 `.codex`，改为接受 `.codex` 与 `.zcode`。其余行为不变：

- 只读取绑定项目的 `design.md`，不重复注入 `AGENTS.md`，不扫描图片、聊天或凭据。
- 会话工作目录不在该项目内时静默跳过；文件链接指向项目外时不读取。
- 单文件读取上限 16 KiB，超出部分明确标注截断；只读文件，不启动网络或常驻进程。
- 出错时静默退出，不阻塞启动，也不回显输入载荷。

## 2. 安装器按宿主写入

```
node "<当前插件目录>/skills/d-init/scripts/install-project-context-hook.js" --project-root "<项目绝对路径>" --host auto
```

- `auto`（默认）按是否存在 `ZCODE_` 环境变量判断宿主，判断不确定时应显式传入 `codex` 或 `zcode`。
- Codex：合并 `.codex/hooks.json` 的一个 `SessionStart` 加载项，并放置 `.codex/hooks/dumik-project-context.cjs`。
- ZCode：合并 `.zcode/config.json` 的 `hooks.events.SessionStart`，把 `hooks.enabled` 置为 `true`，并放置 `.zcode/hooks/dumik-project-context.cjs`。ZCode 只在 `hooks.enabled` 为真时运行工作区钩子，因此该值由安装器补齐。
- 同一项目可为两个宿主各装一套，两套配置与加载器互不覆盖。
- 重复执行不重复注册；已有加载器或同名钩子与预期不同时保留原内容并报告冲突。
- `.zcode/config.json` 中 `hooks.enabled` 被显式设为 `false` 时，安装器报错退出且不改写该设置：这是用户有意关闭的运行时开关，应由用户决定。
- 不修改全局配置、权限、信任记录、`AGENTS.md` 或 `design.md`。

## 3. `d-init` 的宿主说明

`d-init` 0.3.2 增加：按宿主选择插件列表命令（Codex `codex plugin list`、ZCode `zcode plugins list`）定位插件目录；钩子安装步骤写明 `--host` 取值、两套写入目标，以及两个宿主各自的信任要求。

## 4. 信任与生效边界

两个宿主都要求项目配置层受信任。Codex 用 `/hooks` 审阅确认；ZCode 未信任时状态为 `workspace_hooks_pending_trust`，钩子被阻塞，由用户在客户端确认或用 `zcode hooks trust` 授权。改动配置或加载器内容会改变摘要，信任随之失效，需要重新授权。安装器不写信任记录、不修改权限、不使用绕过参数。

**配置成功不等于宿主已触发。** 本次验证到：生成配置可被 ZCode 自身解析（`zcode hooks trust status` 正确列出事件、匹配器、命令与来源，状态为待信任），安装后的加载器在隔离项目中能注入 `design.md` 并跳过非目标事件。未验证真实宿主的自动触发，仍需宿主信任与实际事件确认。

## 验证范围

- 9 个 skill 结构校验通过。
- 项目上下文加载器与安装器：27 项本地测试通过（18 项既有用例全部保留，新增 9 项 ZCode 用例）。
- 图片执行脚本：4 项测试通过。
- 视频执行脚本：3 项测试通过。
- 自动更新脚本：4 项隔离仓库测试通过。
- 合计 38 项本地自动化测试通过；另检查插件结构、版本清单和 JSON 示例。

本次没有提交真实生图、生视频或外部付费生成任务；不以文档或模拟测试结果承诺生成质量、接口额度、服务可用性或宿主自动触发。图片线与视频线的生成脚本相对 `v0.1.8` 没有改动。

## 升级说明

- 插件版本升级到 `0.1.9`，9 个既有 skill 名称不变，不新增日常调度入口。
- `v0.1.8` 已登记的项目 `.codex` 钩子继续有效，本次不会自动改写或迁移；需要 ZCode 一侧时，用 `--host zcode` 另行登记。
- 使用新版技能建议在新会话中验证。已有未提交源码改动仍会阻止自动快进更新，不会强制覆盖。

完整差异：https://github.com/Hill2048/dumik-codex-plugins/compare/v0.1.8...v0.1.9
