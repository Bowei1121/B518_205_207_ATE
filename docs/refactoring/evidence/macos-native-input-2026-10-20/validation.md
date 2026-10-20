# macOS 原生輸入權限與測試收尾（2026-10-20）

## 原因與範圍

使用者從 Terminal 執行唯讀 Quartz 檢查，回報 `post=False listen=False policy=0`；開啟 Terminal 輔助使用權限並重新啟動後，回報 `post=True listen=True policy=0`。原生鍵盤投遞與滑鼠提示測試需要事件投遞權限。Codex 啟動環境原本已具備權限，四項指定失敗測試以 PTY 重跑全過（21.725 秒），無法以該結果代替使用者 Terminal 的驗證。沒有證據指向 M4 特有晶片問題。

建置新增唯讀 `CGPreflightPostEventAccess` 檢查；拒絕時以非零狀態停止並提供輔助使用設定指引，不自動請求或變更權限、不跳過驗收。listen 權限只記錄，不作為門檻。

完整測試另重現 `test_manual_stop_can_be_explicitly_cancelled_without_erasing_results` 的暫存目錄刪除競態：第二輪仍可能保存資料時目錄先被移除，出現 Directory not empty。改以 finally 釋放來源準備閘門、停止輪次、要求關閉並斷言完整保存完成，才離開暫存目錄。原有結果／稽核斷言保留，未吞掉例外。

## 驗證

- 修正前完整測試：551 項，1 error、3 skips，161.845 秒；error 為上述目錄收尾競態，原四項 UI 案例通過。
- 相關回歸：收尾案例及權限允許／拒絕檢查，共 3 項通過。
- 隔離副本使用本機 `.venv-macos15_0-arm64-log-solution`、Python 3.12.10 執行原建置腳本，設定 `B518_H8_CAPACITY_ROOT=/tmp/b518-hmi-20261016/capacity-50k`。
- 完整含 Tk、容量驗證：551 項，550 通過，1 項既有人工 Light/Dark 切換驗收未執行，193.962 秒。無 failure/error。
- 建置 exit 0；PyInstaller、macOS 15 arm64 bundle 相容性、codesign deep strict 驗證完成。
- 產物：`/tmp/b518-native-input-20261020/build-validation/dist-macos15_0-arm64/B518-Log-Solution-V0.1.5-macOS15.0-arm64.zip`。
- ZIP SHA-256：`c3b2122c8d5772f67f63cb0deaa98c6274e9d07982252c97a29a2ed0ee159c21`。
- 本次建置使用副本，原始使用者 VERSION 與未追蹤 spec 與 `/tmp/b518-native-input-20261020` 的備份逐位元相同，未提交。

## 尚待確認

使用者已回報 Terminal 權限通過，但尚未回報該 Terminal 重新建置結果；不能將隔離建置成功宣稱為使用者原啟動環境已完成驗證。人工系統外觀切換驗收也尚未執行。
