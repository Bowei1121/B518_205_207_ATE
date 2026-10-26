# GitHub 雲端 M1／macOS 15 自動測試與打包

本流程使用 GitHub-hosted `macos-15` 虛擬機。GitHub 目前將此標籤配置為 Apple Silicon M1／arm64；不是 `macos-15-intel`，也不使用會隨時間換版的 `macos-latest`。每次 job 都建立新 VM，結束後回收，不需自備 Mac、SSH 或註冊 self-hosted runner。

## 觸發與下載

1. 對 `B518-Log-Solution` 提出 PR，或將變更合併至此整合分支。變更須涉及 `B518 Log Solution/` 或此 workflow。
2. 在 repo 的 **Actions → Log Solution M1 macOS 15** 檢視執行結果。
3. 成功後在該次執行頁的 **Artifacts** 下載 `B518-Log-Solution-macOS15-arm64-執行編號-重跑次數`。解開外層 artifact，即可取得 App ZIP、SHA-256 與 `build-info.txt`。
4. `B518-test-evidence-*` 包含環境、測試／打包紀錄與測試產生的畫面證據；失敗時也嘗試上傳。兩類 artifact 均保存 14 天。

GitHub Actions 必須在 repo 中啟用，且允許此 workflow 使用的官方 `actions/checkout` 與 `actions/upload-artifact`。私有 repo 會使用帳號可用的 Actions 分鐘與儲存額度。

workflow 也宣告 `workflow_dispatch`，但 GitHub 要求該 workflow 存在於 repo 的**預設分支**才接受手動觸發。目前預設分支是 `main`，產品整合分支是 `B518-Log-Solution`；只合併至產品分支後，先使用 PR／push 自動觸發或 Actions 的 Re-run jobs。若需要 Run workflow 按鈕，另將此 workflow 檔納入 `main`；本次不更改 repo 的預設分支。

## 每次 job 的步驟

```text
建立 macos-15 VM → checkout 本次待驗證 commit
→ 安裝 Python.org 3.12.10 universal2（固定 SHA-256、驗證套件簽章）
→ 確認 M1／原生 arm64／macOS 15／桌面使用者／Python 與 Tk
→ 選用至少 1920×1080 邏輯像素的桌面模式，記錄實際解析度
→ 安裝固定版本依賴 → 原生輸入權限檢查
→ B518_TK_TESTS=1 執行既有完整自動測試套件
→ PyInstaller → bundle 架構／最低系統／依賴檢查
→ ad-hoc 簽章與驗證 → ZIP → SHA-256 再核對 → 上傳
```

沿用 `scripts/build_macos15_arm64_log_solution.sh` 的完整測試與建置閘門；測試或權限檢查失敗就不交付安裝包，不藉由停用 Tk 或改用 view-cache 截圖放行。原有明確標示人工驗收的測試仍需人工執行，請以測試 log 的 skipped 項目確認範圍。

雲端映像會更新。原生滑鼠／鍵盤投遞、視窗截圖與像素斷言能否在該次 VM 通過，須由實際 workflow 證明；不能僅憑 `runs-on` 或 bundle 靜態檢查宣稱完整桌面驗收成功。雲端測試不包含真實 ATE、JetKVM 或工廠即時 Log 配對。

GitHub VM 的顯示器不一定是 Retina。NSView 截圖像素尺寸依該原生視窗的 `backingScaleFactor()` 檢查；仍核對真實截圖與 Tk 幾何，不將測試固定為某台開發機的 2 倍倍率。

## 版本與追溯

CI 傳入 `--preserve-version`，直接使用 repo 的 `VERSION`，重跑不自動加版或回推 commit。正式升版時，將 `VERSION` 更新納入產品 PR；`build-info.txt` 記錄實際 checkout SHA、ref、執行網址、重跑次數、macOS、晶片與安裝套件版本。PR 測試記錄的是 GitHub 待合併的測試 commit，可能不同於 PR head SHA。

不帶參數的本機打包仍在測試通過後遞增 patch。CI 產物沿用 ad-hoc 簽章，未加入 Developer ID／notarization；產物是候選安裝包，不會自動更新產線或發布正式 Release。

## 參考

- [GitHub-hosted runner 規格與每次建立新 VM](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [手動執行 workflow 的預設分支條件](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Python.org 3.12.10 universal2 安裝包](https://www.python.org/downloads/release/python-31210/)
- [GitHub macOS 映像的原生畫面權限配置](https://github.com/actions/runner-images/blob/main/images/macos/scripts/build/configure-tccdb-macos.sh)
