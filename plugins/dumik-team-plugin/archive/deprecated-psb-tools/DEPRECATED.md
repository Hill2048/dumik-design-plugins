# 已废弃（DEPRECATED）：PSB 智能对象工具（`d-psb-install`）

> **状态：已废弃（保留存档，不删除文件，默认不再加载也不自动拉取）**

## 变更说明

- `d-psb-install` 技能已从 DUMIK Team Plugin 活跃技能目录（`skills/`）移出并归档至此目录，不再参与默认技能发现、自动路由或插件更新校验。
- 历史资产与安装脚本完整保留在仓库中，**不予删除**，仅作历史追溯参考：
  - 技能说明：`archive/deprecated-psb-tools/d-psb-install/SKILL.md`
  - 面板源码：`assets/psb-smart-object-tools/`（UXP / CEP）
  - 历史安装包：`dist/psb-smart-object-tools-uxp-*.ccx`
  - 安装脚本：`scripts/install_psb_smart_object_tools.ps1`、`scripts/install_psb_smart_object_tools_mac.sh`
- 安装脚本已改为**默认不从 GitHub 拉取远端更新**（`SkipRemoteCheck` 默认生效）；如确需临时拉取远端包，必须显式传入 `-AllowRemoteFetch`（Windows）或 `ALLOW_REMOTE_FETCH=1`（macOS）。
