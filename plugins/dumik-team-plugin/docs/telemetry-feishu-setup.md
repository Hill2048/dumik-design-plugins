# 飞书多维表格统计配置指南

用于统计全团队每个 Skill 的调用次数与插件下载/安装/更新次数。只上报匿名计数，绝不上传提示词、图片、文件名或 API Key。

## 1. 在飞书新建一张多维表格

新建数据表（例如命名为 `DUMIK 使用统计`），添加以下 8 列：

| 列名 | 飞书字段类型 | 对应 JSON 字段 | 说明 |
| --- | --- | --- | --- |
| 事件类型 | 单选 / 文本 | `event` | `invoke`（调用）/ `install`（首次安装）/ `update`（更新）/ `download`（工具下载） |
| Skill 名称 | 单选 / 文本 | `skill` | 如 `d-image-director`、`d-image-runner`、`dumik-team-plugin` |
| 模式 | 文本 | `mode` | 如 `detail`、`generate`、`postprocess`（安装/更新时为空） |
| 插件版本 | 文本 | `plugin_version` | 如 `0.2.15` |
| 宿主 | 单选 / 文本 | `host` | `antigravity` / `codex` / `zcode` / `local` |
| 系统 | 文本 | `os` | `windows` |
| 匿名设备ID | 文本 | `device_id` | 12 位单向哈希，用于去重统计使用人数，不暴露个人信息 |
| 时间 | 文本 / 日期 | `timestamp` | ISO-8601 时间戳 |

## 2. 开启自动化 Webhook

1. 点击多维表格右上角 **「自动化」** → **「创建自动化流程」**。
2. 触发条件选择 **「当接收到 Webhook 请求时」**，复制生成的 **Webhook 地址**。
3. 执行动作选择 **「新增记录」**，选择刚才的数据表，并将 Webhook 参数中的上述 8 个字段映射到对应列，保存并启用流程。

## 3. 填入插件配置并测试

将复制的 Webhook 地址填入 `plugins/dumik-team-plugin/assets/telemetry-config.json` 的 `webhookUrl` 字段，然后运行以下命令验证联通：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "plugins\dumik-team-plugin\scripts\report_skill_telemetry.ps1" -Event invoke -Skill d-image-director -Mode detail -Test
```

看到输出 `"status":"ok"` 且多维表格出现一条新记录即配置成功。随后在飞书多维表格中新建「仪表盘」，即可按 `Skill 名称`、`事件类型`、`匿名设备ID（去重）` 随时查看调用排行与下载人数。

> 如个人本机需关闭上报，设置环境变量 `DUMIK_TELEMETRY_DISABLED=1` 即可。
