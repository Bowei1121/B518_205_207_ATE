# Slot、頂列及按鈕提示開發票

來源：[Spec](../HMI_SLOT_TOOLBAR_SPEC_2026-10-16.md)／[GitHub #68](https://github.com/Bowei1121/B518_205_207_ATE/issues/68)。使用者已核可八張切片與依賴；目前只有規劃與發布，不代表程式已完成。

| 票 | 內容 | GitHub | 前置 |
| --- | --- | --- | --- |
| ST1 | [Slot 最多十列與灰色停用捲軸](01-slot-scroll.md) | [#69](https://github.com/Bowei1121/B518_205_207_ATE/issues/69) | 無 |
| ST2 | [頂列對齊、雙徽章與精簡語言入口](02-toolbar-badges.md) | [#70](https://github.com/Bowei1121/B518_205_207_ATE/issues/70) | 無 |
| ST3 | [主頁按鈕的完整提示與互動狀態](03-main-button-feedback.md) | [#71](https://github.com/Bowei1121/B518_205_207_ATE/issues/71) | 無 |
| ST4 | [設定與通知恢復視窗的按鈕提示](04-settings-recovery-feedback.md) | [#72](https://github.com/Bowei1121/B518_205_207_ATE/issues/72) | ST3 |
| ST5 | [裁決、警報及關閉保存流程的按鈕提示](05-review-close-feedback.md) | [#73](https://github.com/Bowei1121/B518_205_207_ATE/issues/73) | ST3 |
| ST6 | [歷史查詢與診斷視窗的按鈕提示](06-history-diagnostics-feedback.md) | [#74](https://github.com/Bowei1121/B518_205_207_ATE/issues/74) | ST3 |
| ST7 | [通知與恢復視窗固定淺色修復](07-recovery-light-theme.md) | [#75](https://github.com/Bowei1121/B518_205_207_ATE/issues/75) | 無 |
| ST8 | [整體桌面驗收與全按鈕覆蓋核對](08-integrated-desktop-acceptance.md) | [#76](https://github.com/Bowei1121/B518_205_207_ATE/issues/76) | ST1、ST2、ST3、ST4、ST5、ST6、ST7 |

## 執行與邊界

- ST1、ST2、ST3、ST7 無前置；ST4／ST5／ST6 等 ST3；ST8 等前七票全部完成。只認領前置已完成的工作。
- 無功能依賴不等於適合並行修改同一個 Tk 模組；共享修改須協調，真正桌面驗證避免焦點及系統外觀互相干擾。
- ST3 在主頁完整交付提示與互動能力，ST4–ST6 逐批擴至可獨立驗證的視窗；不是只建立底層類別後等最後才可操作。每批保持原操作契約及測試可通過，無需另外拆純重構票。
- 每張有對應行為及真正繁中／英文畫面驗證。試行樣式由真正畫面確認，不能以產生色值或舊驗收宣稱已核可。
- ST8 重用前票有效證據，只補整合及缺漏，不加入無關數小時歷史容量測試。工廠驗收另列，不阻擋已完成程式及桌面驗證的整合。
- 既有未驗收程式暫稿不自動採用；實作從當下已提交版本查核，保留較新的 macOS 幾何修正。不得覆寫他人的程式或未追蹤證據。
- 每票標記 ready-for-agent，遠端使用原生子議題與阻擋關係；正文另保留可離線閱讀的依賴。本次不修改父規格正文或關閉父議題。

## 52 項故事覆蓋

- 故事 1：ST1；ST8 整合確認。
- 故事 2：ST1；ST8 整合確認。
- 故事 3：ST1；ST8 整合確認。
- 故事 4：ST1；ST8 整合確認。
- 故事 5：ST1；ST8 整合確認。
- 故事 6：ST1；ST8 整合確認。
- 故事 7：ST1；ST8 整合確認。
- 故事 8：ST1；ST8 整合確認。
- 故事 9：ST1；ST8 整合確認。
- 故事 10：ST1；ST8 整合確認。
- 故事 11：ST1；ST8 整合確認。
- 故事 12：ST2；ST8 整合確認。
- 故事 13：ST2；ST8 整合確認。
- 故事 14：ST2；ST8 整合確認。
- 故事 15：ST2；ST8 整合確認。
- 故事 16：ST2；ST8 整合確認。
- 故事 17：ST2；ST8 整合確認。
- 故事 18：ST2；ST8 整合確認。
- 故事 19：ST2；ST8 整合確認。
- 故事 20：ST2；ST8 整合確認。
- 故事 21：ST2；ST8 整合確認。
- 故事 22：ST2；ST8 整合確認。
- 故事 23：ST2；ST8 整合確認。
- 故事 24：ST2；ST8 整合確認。
- 故事 25：ST2；ST8 整合確認。
- 故事 26：ST2；ST8 整合確認。
- 故事 27：ST2；ST8 整合確認。
- 故事 28：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 29：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 30：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 31：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 32：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 33：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 34：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 35：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 36：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 37：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 38：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 39：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 40：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 41：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 42：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 43：ST3、ST4、ST5、ST6；ST8 整合確認。
- 故事 44：ST7；ST8 整合確認。
- 故事 45：ST7；ST8 整合確認。
- 故事 46：ST7；ST8 整合確認。
- 故事 47：ST7；ST8 整合確認。
- 故事 48：ST4、ST5、ST6、ST7；ST8 整合確認。
- 故事 49：ST1、ST2、ST3；ST8 整合確認。
- 故事 50：ST2、ST4、ST5、ST6、ST7；ST8 整合確認。
- 故事 51：ST1、ST2、ST3、ST4、ST5、ST6、ST7；ST8 整合確認。
- 故事 52：ST3、ST4、ST5、ST6；ST8 整合確認。
