# DUMIK 项目上下文钩子

这里提供加载器源文件，不注册插件级或全局钩子。`d-init` 在完整初始化用户选定的项目时运行：

```powershell
node "<当前插件目录>/skills/d-init/scripts/install-project-context-hook.js" --project-root "<选定项目的绝对路径>"
```

安装器只向该项目写入：

- `.codex/hooks.json`：合并一个 `SessionStart` 加载项，保留用户其他钩子。
- `.codex/hooks/dumik-project-context.cjs`：独立的只读加载器，不依赖会变动的插件缓存路径。

重复初始化不会重复注册。已有加载器或同名钩子与预期不同时，保留原内容并报告冲突，不覆盖项目定制。不修改全局配置、权限、信任记录、`AGENTS.md` 或 `design.md`。

## 加载范围

- 根据安装位置固定项目根目录，不从工作目录向上搜索其他项目。
- 钩子只读取该根目录的 `design.md`，不读取或再次注入 `AGENTS.md`；后者由 Codex 原生项目指令机制处理。会话工作目录不在该项目内时静默跳过；文件链接指向项目外时不读取。
- `design.md` 是视觉设定资料，不代表额外执行授权。若原生项目指令未加载，不用此钩子越过信任或权限限制补注入 `AGENTS.md`。
- 不读取聊天记录、凭据或图片目录，也不自动把设定图传给生成模型。
- 每个文件最多读取 16 KiB；超出部分明确标为截断，并保留完整文件路径供按需读取。加载器只读文件，不启动网络、生成或后台常驻进程。
- 成功时只注入上下文，不用 `systemMessage` 制造启动警告。

## 触发与生效

`SessionStart` 匹配 `startup`、`resume`、`clear` 和 `compact`。它不按每条消息重复注入。

初始化时当前会话已启动，安装不能补发已经过去的启动事件；`d-init` 当场读取 `design.md`，仅在 `AGENTS.md` 本次新建、改动或尚未加载时再读取它。后续会话启动、恢复或上下文压缩后，钩子只补充读取 `design.md`。这不意味着同一会话的所有生命周期事件共用一份注入记录；每次匹配事件仍会重新读取当前设定。

Codex 要求项目配置层受信任，并要求用户首次审阅、信任新钩子的定义；钩子修改后也可能需要重新信任。使用 `/hooks` 查看与确认，不写信任存储、不使用绕过参数。配置落盘和脚本测试成功不等于宿主已经触发，未实际验证时应报告“已配置，自动触发待首次信任确认”。

官方依据：
- https://learn.chatgpt.com/docs/hooks
- https://learn.chatgpt.com/docs/agent-configuration/agents-md

## 本地验证

```powershell
node --test "<当前插件目录>/skills/d-init/scripts/tests/project-context-hook.test.js"
```

测试使用隔离的临时项目，不触发模型或外部服务。已有 `dumik-image-defaults.md` 仅是历史文字提示，不是运行中的钩子。
