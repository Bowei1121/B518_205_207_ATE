# 2026-08-31 專案摘要

## 多方案 Repo 拆分

- 現有 `Mac mini` repo 保留為 Arduino + Log 方案，沿用既有 Gitea 與 GitHub remote。
- 已建立並推送 Gitea private repos：`B518_JetKVM_Mirror`、`B518_JetKVM_Log`、`B518_AppleAgent_Research`。
- JetKVM mirror 的 `dev` branch 固定包含研究基準 `b3c29a44d9e2862b8ff7530830781803ce27b060` 與既有 tags；方案二以 `third_party/jetkvm` submodule 固定此版本。
- 方案二保留 KVM 上位機原始碼、設定、研究與測試素材；已排除可重建的 `build/`、`dist/`、快取、zip 與重複 JetKVM 拷貝。
- AppleAgent 文件已移至獨立研究 repo。

## 待續注意事項

- JetKVM private mirror 需保留官方 `upstream` remote，以便日後有選擇地同步官方更新。
- 三個方案雖已在 Git 與資料夾層級隔離，部署時仍應為各方案指定不同 TCP port、USB 裝置與 Log 路徑。
