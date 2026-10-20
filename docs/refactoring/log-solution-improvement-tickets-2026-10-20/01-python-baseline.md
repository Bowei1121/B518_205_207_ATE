# LS1：開發與打包共同核對 Python 3.12.10

GitHub：[87](https://github.com/Bowei1121/B518_205_207_ATE/issues/87)；狀態：ready-for-agent；使用原生父子與阻擋關係。

## Parent

https://github.com/Bowei1121/B518_205_207_ATE/issues/86

## What to build

工程師在實際開發或打包入口可確認Python修訂版、套件與架構；環境不符時在執行驗收前獲得正確診斷。

規格覆蓋：使用情境 51；驗收情境 T19。

## Acceptance criteria

- [ ] 開發與打包共同核對實際Python3.12.10，不只看3.12或殼層命令名稱；錯誤版本或錯誤目標架構須清楚回報。
- [ ] 沿用專案指定PyInstaller6.16.0及PyObjC core／Cocoa／Quartz11.1，不順便升版；實際虛擬環境與套件資訊可查證。
- [ ] 既有原生輸入權限檢查、Tk桌面驗收與打包門檻維持，不為環境不足跳過原本要求。
- [ ] 在正確與不符條件的驗證案例中，從環境檢查入口觀察成功或可操作診斷；不得改變系統權限。
- [ ] 記錄可直接重現的開發及打包檢查方法，說明git更新不會同步套件；不改動其他macOS交付目標。
- [ ] 此票完成不等於新版App或目標機已驗收；完整發布留待LS8。

## Blocked by

None（可立即開始）。
