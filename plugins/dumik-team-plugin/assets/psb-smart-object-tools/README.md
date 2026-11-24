# [已废弃 / DEPRECATED] PSB 智能对象工具

> **状态：已废弃（保留存档，不删除文件，默认不再加载也不自动拉取）**
>
> 本工具已从 DUMIK Team Plugin 活跃技能中移除（技能存档见 `archive/deprecated-psb-tools/`）。本目录完整保留历史源码供参考；安装脚本默认不再从 GitHub 拉取更新，仅在手动显式指定 `-AllowRemoteFetch`（Windows）或 `ALLOW_REMOTE_FETCH=1`（macOS）时才访问远端。

Photoshop 面板，用来处理大 PSB/PSD 里的智能对象。

## 稳定版

`cep/`

装到：

`%APPDATA%\Adobe\CEP\extensions\psb-smart-object-tools`

打开：

`窗口 > 扩展功能（旧版） > PSB 智能对象工具`

## UXP 版

`uxp/`

Mac 默认使用 UXP。当前 UXP 版已做完整迁移，包含：

- 转链接
- 收集链接
- 找回丢失链接
- 嵌回文件
- 提取文字
- 清元数据
- 清废链接
- 锐化导出

## Codex 自动安装

让 Codex 使用 DUMIK 插件里的 `d-psb-install` 技能，或直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File "<插件根>\scripts\install_psb_smart_object_tools.ps1"
```
