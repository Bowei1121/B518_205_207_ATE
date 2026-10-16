## Parent

https://github.com/Bowei1121/B518_205_207_ATE/issues/68

## What to build

操作員看到設定、等比例 Logo、待確認、鈴鐺及地球一致對齊，兩徽章完整可讀而不遮擋，語言入口精簡且可用。

## Acceptance criteria

- [x] 維持左側設定／Logo 與右側待確認／鈴鐺／語言排列及主頁固定寬度，整排圖示和 Logo 垂直對齊。
- [x] Logo 保留原比例縮小至一般按鈕可見高度，徽章浮出高度不納入；載入失敗仍保留配置空間，不顯示 B518 LOG 替代。
- [x] ⚠️ 採右上角圓形紅底白字事項數，零筆隱藏；沿用待確認事項，不新增去重或併入鈴鐺，開窗不清零、完成裁決依既有狀態減少。
- [x] 兩徽章保留完整頂部及相鄰空間，鈴鐺可向左下調整但不任意搬動 KVM 區；零、一及多位數不截斷、不覆蓋鄰近入口、不自行改為 9+，數量及語言變動不推動按鈕。
- [x] 🌐 僅圖示、移除原生箭頭與過量留白，不靠裁切元件藏箭頭；保留足夠點擊範圍、目前語言、選單選取／取消、鍵盤開啟與 Tab／Shift+Tab。鍵盤與真實滑鼠入口／選取均已驗證，見驗收紀錄。
- [x] 原鈴鐺計數、恢復效果及關閉保存期間語言切換限制維持。
- [x] 真正輪次情境驗證待確認生命週期；兩語畫面量測 Logo 比例、頂部範圍、按鈕與徽章不相交、KVM 定位及格位；不只塞假計數標籤驗收。

## Blocked by

無，可立即開始。

## 規格對照與共同契約

使用者故事：12、13、14、15、16、17、18、19、20、21、22、23、24、25、26、27、49、50、51。

沿用已確認真正 App／Tk 操作入口與既有公開輪次情境，不新增專供測試的業務接口，不把未提交暫稿當成已完成。保留 KVM 幾何與色彩、人工裁決、警報確認、雙語更新、保存及正常關閉保障。提供對應真正繁中／英文畫面與行為驗證，記錄已測環境；工廠驗收另列，不阻擋已完成程式與桌面驗證的整合。

## 實作驗收紀錄（2026-10-16）

- Aqua 的原生 `ttk.Menubutton` 箭頭不在 `TMenubutton` 的 ttk layout，刪除 layout element 無效。實作改用可見的 icon-only `ttk.Button` 搭配同一個原生 Tk `Menu`，按鈕 Space／Return／Down 只在啟用時呼叫一次選單入口，不裁切控制。
- 原生 Menu 的 Down、Return 選取、Escape 取消沿用既有 Tk 操作；顯示 Menu 前先關閉語言提示。UI 回歸改用 `CGEventPostToPid` 對測試 App PID 送真實鍵盤事件。
- 真實 Tk/Aqua App 鍵盤測試通過：Quartz Tab/Space/Down/Return/Escape 選單路徑。使用者於真正 B518 App 視窗以滑鼠點地球並選取「繁體中文」，程式讀回 `current_language=zh-TW` 並保存單窗畫面 `toolbar-language-menu-manual-pointer-zh-TW-app.png`；滑鼠開啟與選取契約通過。輪次內 12 筆裁決衝突與 1 筆警報的獨立計數、開窗不清除、人工裁決更新和 KVM 幾何回歸通過；最新中英文雙徽章 App 畫面已檢查。三次 Quartz 測試注入失敗已記為測試工具限制，未當成產品通過證據。含 WeChat 通知的全螢幕原圖已排除，未納入證據。
- 程式與本機桌面驗收完成；工廠/KVM 實機項目尚未執行，列為現場驗收。詳見 [ST2 acceptance notes](../evidence/st2-20261016/acceptance-notes.md)。
- 逐項測試命令、測量及畫面來源見 [ST2 acceptance notes](../evidence/st2-20261016/acceptance-notes.md)。
