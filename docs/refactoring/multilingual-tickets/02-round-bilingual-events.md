# M2：共同輪次事件同筆雙語保存與即時重新顯示

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

操作員在監控中換語言，可閱讀共同輪次既有與新增事件；開發端及現場可從同一磁碟事件讀取繁中／英文。先相容擴充事件形式並接入共同輪次操作，保留未遷移 producer 的舊形式。

## Acceptance criteria

- [ ] 共同輪次開始、停止、結果、逾時、衝突及人工操作相關事件同筆有兩語說明、識別、參數與必要診斷，共用原事件時間、序號及身分。
- [ ] 畫面既有事件換語言不重新執行或寫出事件，不更改磁碟當時兩語內容。
- [ ] 既有 message、機器欄位與讀取相容，新增形式有明確解讀契約；兩語不是兩次操作，其他尚未遷移路徑仍可工作。
- [ ] 保存故障保留整筆雙語單位，部分寫入／重試不缺一語、不重複；共同輪次與磁碟重建一致。
- [ ] 監控與待確認切換保留結果、候選與警報；來源資料、狀態碼、放行政策維持。
- [ ] 以公開輪次入口、暫存磁碟及真正 Tk 事件顯示驗證兩語相同行為。

## Dependency

- M1 / [#14：主頁直覺語言選單與上次語言持久保存](https://github.com/Bowei1121/B518_205_207_ATE/issues/14) is verified in the M2 baseline and no longer blocks implementation. See the ancestry and evidence check in [M2 local validation](../evidence/multilingual-ticket-02/local-validation.md).
