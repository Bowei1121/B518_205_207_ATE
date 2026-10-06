# Ticket 17 本機驗證紀錄

日期：2026-10-06（Asia/Taipei）

程式來源固定基準：`e3f4eb5541f70e326a7ede99b2bc342bd6d850b1`

Ticket 執行分支：`codex/ticket-17`；驗證包含該分支的 build-check 變更。

## 執行環境

| 項目 | 實際值 |
| --- | --- |
| macOS | 15.7.9，build 24G830 |
| CPU／Python 執行架構 | Intel x86_64 |
| Python | 3.8.10，`/Library/Frameworks/Python.framework/Versions/3.8/bin/python3` |
| 可用發布 build target | 無；Intel target 要求 Catalina 10.15 + Python 3.12，Apple Silicon targets 要求原生 arm64 + Python/Tk 3.12 |

## 驗證結果

| 驗證層 | 命令 | 結果 |
| --- | --- | --- |
| 聚焦打包驗證測試 | `python3 scripts/run_tests.py test_verify_macos_bundle` | 20 tests 通過。涵蓋 arm64／x86_64、Info.plist 最低版本、Mach-O load command、相依路徑、外部／缺失依賴及 Python/Tk 前置函式；bundle 是測試 fixture，非發行產物。 |
| 完整本機測試 | `python3 scripts/run_tests.py`，桌面 Tk 可用 | 最後一次完整重跑為 188 tests 通過，22.621 秒。sandbox 執行遇 Tk 初始化 exit 134；桌面環境同命令成功，只有桌面結果計為通過。 |
| deadline 來源 Tk 回放 | `python3 -u tools/smoke_deadline_app.py` | 通過。包含正常／未放滿／全空輪次、individual TIMEOUT／STOPPED、round alarm、alarm 與 conflict 的兩種操作次序及 final-only RS-WMT。結果由隔離合成來源產生。 |
| KVM 標記來源 Tk 回放 | `B518_SMOKE_TICKET=17 B518_SMOKE_EVIDENCE_DIR=/private/tmp/ticket17-tk-evidence python3 -u tools/smoke_state_marker_app.py` | 通過。Contract 1.1 的 standby／monitoring／review／complete／new round／manual stop；視窗 `376 × 682` Tk units、縮放約 1.0、capture `752 × 1420` pixels；衝突及警報視窗均沒有覆蓋固定辨識區；容量 20 捲動後定位列仍可見。截圖為隔離來源 App 視窗。 |
| build 腳本語法 | `zsh -n scripts/build_macos10_14_log_solution.sh scripts/build_macos15_arm64_log_solution.sh scripts/build_macos26_arm64_log_solution.sh` | 通過。 |
| 本機 Python/Tk target preflight | `python3 scripts/check_macos_build_python.py --architecture x86_64` | 按設計拒絕：需要 Python 3.12；實際 interpreter 是 3.8.10。此為環境不符合結果，不是 target pass。 |

受控 Tk 回放機器紀錄及窗口捕捉見 [`source-tk-replay/run.json`](source-tk-replay/run.json) 和同資料夾 PNG。`run.json` 明載 capture source 為 Quartz window capture、`physical_kvm_available: false`；測試 SN 為 synthetic，沒有實際 KVM 或 ATE 動作。

## 尚未驗收

- 沒有實際建立任何 PyInstaller `.app`／ZIP，沒有執行發行 bundle 上的資源、配置、快捷鍵、前景顯示或完整一輪驗收。
- 沒有針對產物執行 `codesign`／`codesign --verify` 或 SHA-256 sidecar 校驗。Build scripts 的 ad-hoc signature 路徑與靜態 verifier 由程式及測試覆蓋，不代表簽章或分發政策已通過；Developer ID／notarization 仍未提供／驗收。
- Intel macOS 10.14／10.15、Apple Silicon macOS 15.x（含最低 15.0）及 26.x 目標機尚無本票實測。需要可用的原生 builder、實際設備與現場人員／TE 部署紀錄。
- 尚未取得 RS-WMT 現場資料時機；本機平台測試及 synthetic replay 不代替實際來源更新時序。
- 當時 Ticket 18 的同輪來源採用政策仍未決；這是 2026-10-06 Ticket 17 本機驗證階段的歷史紀錄。Ticket 18 其後已由使用者定案並合併，當前政策見 ADR 0006 與本票發行指南的「Ticket 18 已定案政策」。

## Ticket 18 主線整合後驗證｜2026-10-06

- Ticket 17 已將主線 `3d15abf77575b9b1b5db2b1f878846c930c9d5e3` 合併進工作分支，其中已包含 Ticket 18 政策與實作；衝突只在兩票更新的跨日摘要，已保留雙方紀錄。整合後完整 `python3 scripts/run_tests.py` 通過 193 tests（22.930 秒），三個 build 腳本 `zsh -n` 通過，`git diff --check` 通過。這些檢查只驗證本機程式與受控案例，不替代尚未建立的發行 bundle 或目標環境驗收。
- 尚未取得適用的建置主機、目標設備、現場資料及所需簽章政策；沒有建立或聲稱存在 `.app`／ZIP、codesign 驗證或 SHA-256 產物證據。
- 整合後 Standards／Spec 審查基準為 `3d15abf77575b9b1b5db2b1f878846c930c9d5e3`，Ticket 分支 HEAD `1b444ecb587a826f46b04fc686eb598fc9936058`，兩軸均無未解發現。Ticket 17 以 merge commit `883d9f4448ab36b388f4fb01ece66ff406871f31` 合入主線，合併後全套 193 tests 通過並推送至 Gitea／GitHub。因 AC 2、3、4 未驗收，Ticket 分支保留供後續接續；此狀態不改變任何 bundle 或現場項目為待驗。

## 型別檢查

本 repository 沒有已配置的 mypy、pyright 或其他型別檢查命令。Python 語法檢查、打包 verifier 測試與完整行為測試均不標示為型別檢查通過。

## 審查修正

- 固定基準 Standards 審查指出 10.14／26 build scripts 在 verifier 後又重複 `lipo` 架構檢查。已移除重複 shell loops，統一由 `verify_macos_bundle.py` 檢查全部 Mach-O；聚焦 20 tests、完整 188 tests 與三個 zsh 語法檢查修正後均通過。
- Spec 審查指出各目標 macOS 實機驗收尚未執行，因此即使驗收紀錄已明確分層，ticket AC 4 仍須保持未勾選。現已取消勾選；AC 2、3、4 未完成時維持 blocked。
