## Parent

https://github.com/Bowei1121/B518_205_207_ATE/issues/68

## What to build

工程師在設定各分頁及通知恢復視窗都能讀取雙語操作提示、停用原因及一致滑鼠／鍵盤狀態，而原操作效果不變。

## Acceptance criteria

- [x] 沿用 ST3 能力完成設定所有分頁及通知恢復兩分頁的適用控制覆蓋，包含瀏覽、配置、保存期限、動態重試及連結；更新全 App 清單。
- [x] 繁中／英文功能說明與快捷鍵符合實際效果，已知停用原因可查；保留開始／保存等短標籤，不改配置或恢復操作範圍。
- [x] 驗證滑鼠及 Tab／Shift+Tab 的懸停、焦點、按下、停用與狀態變更；說明出現不代表停用控制可執行。
- [x] 語言切換、切分頁、關閉／重開與控制重建後，提示正確更新且無孤立浮窗／定時工作，輸入、選取及閱讀位置維持。
- [x] 從真正設定及恢復操作確認效果維持，包括原生資料夾選擇器取消、草稿操作、保存／封存重試；不以增加 tooltip 字串就判定功能完成。（2026-10-16 真實英文 Settings 點擊 Browse 開啟 macOS `NSOpenPanel` 後，以滑鼠點 Cancel；handler 與最終讀回皆為 `/draft/active`，Settings 仍開啟。未修改原生畫面證據：`B518 Log Solution/docs/refactoring/evidence/st4-20261016/st4-native-chooser-cancel-en.png`、`st4-native-settings-after-cancel-en.png`。）
- [x] 提供兩語對應畫面與互動證據；不依賴 ST7 才能交付提示，若同時修改外觀則協調共享程式並在最終整合驗證。

## 本機 ST4 執行驗收（2026-10-16）

- 實作分支以整合 tip `9f7e81db38c14b62a4545439371a01378cf168aa` 為基準；本次只更新程式、測試、coverage 與本機證據，不更新 GitHub issue 狀態。
- 新增真正 Tk 設定／恢復窗口測試；測試先因缺少設定按鈕提示而失敗，再完成實作通過。測試另以 Quartz 原生滑鼠在 disabled「重試所選」懸停和按下：雙語原因可讀，`retry_saves` 未被呼叫；滑鼠移往主 App 窗口後 disabled 提示消失並顯示對應主頁提示。
- Settings 全部 14 個共用按鈕含三個動態路徑瀏覽都有集中雙語提示；Recovery 警報確認、保存重試與封存重試動態提示已覆蓋。提示切換語言時重排完整長文；關窗時移除各自的全域 Motion callback。
- macOS Python 3.8 Tk/Aqua 真 App：修正英文三分頁截圖選取後，使用可存取桌面的 `/usr/local/bin/python3.8` 重跑完整 ST4 清單，10/10 通過（24.399 秒）；focused Settings／Recovery tooltip 和畫面測試 1/1 通過。另以真實英文 Settings 點 Browse 開啟原生 `NSOpenPanel` 並用滑鼠點 Cancel，handler 回傳及最後讀回皆為 `/draft/active`，Settings 仍開啟；原生未修改證據見 `st4-native-chooser-cancel-en.png` 與 `st4-native-settings-after-cancel-en.png`。`py_compile`、`git diff --check` 及 language catalog 8/8 通過。
- `docs/refactoring/evidence/st4-20261016/` 保存實際 App 的 Settings 三分頁與 Recovery 兩分頁中英畫面、停用重試提示中英同畫面截圖及視窗 bounds。Tooltip 截圖是 Quartz 原生螢幕區域擷取，沒有拼貼或重畫。
- 尚未驗證工廠桌面與 KVM 實機，另列工廠驗收；本機 NSOpenPanel Cancel 已完成，不以 Escape 合成事件替代。
- 已使用既有 ST3 真實桌面證據驗收共通 Tab／Shift+Tab、焦點、hover、pressed 樣式；本次沒有修改 palette，淺藍 hover 與藍色焦點框仍屬試行方向。系統深淺外觀切換由 ST7 驗收；工廠桌面與 KVM 實機未測，另列 ST8。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/71

## 規格對照與共同契約

使用者故事：28、29、30、31、32、33、34、35、36、37、38、39、40、41、42、43、48、50、51、52。

沿用已確認真正 App／Tk 操作入口與既有公開輪次情境，不新增專供測試的業務接口，不把未提交暫稿當成已完成。保留 KVM 幾何與色彩、人工裁決、警報確認、雙語更新、保存及正常關閉保障。提供對應真正繁中／英文畫面與行為驗證，記錄已測環境；工廠驗收另列，不阻擋已完成程式與桌面驗證的整合。
