# HF1 真實輸入診斷

使用者回報主頁 Tab 無法聚焦、按鈕需點數次。此缺陷仍待重現與修復，不能以本文件或 smoke 結果判為通過。

## 已確認與排除

- 沙盒內 Tk abort 不代表目標 Mac 不能建窗；沙盒外可執行真正 Aqua Tk。
- 真正 App 的 Tk 合成 Tab 可從主視窗移到設定、語言控制；合成按下／放開可開設定。
- 最小真實 Aqua 視窗顯示 tooltip 前後，AppKit keyWindow/mainWindow 相同，tooltip 的 `canBecomeKeyWindow` 為 false。現有證據不支持「tooltip 成為 key window」假說。
- Quartz 原生滑鼠投遞在不含 tooltip 的單按鈕案例也未收到按下／放開；此 harness 不能當作產品故障證據。未依此修改產品。

## 45 秒真鍵鼠流程

先關閉原本 App，避免同時操作兩份。

在 Git repo 根目錄執行：

```zsh
python3 "B518 Log Solution/scripts/diagnose_hmi_input.py" --seconds 45
```

1. 第 0–10 秒：單擊 App 標題列，按 Tab 三次、Shift+Tab 一次，再按 Space 或 Return。觀察焦點及視窗。
2. 第 10–25 秒：滑鼠停在齒輪，等提示出現後單擊一次；若沒開，等兩秒再點一次。若開啟設定，關閉設定視窗。
3. 第 25–40 秒：用同樣方式操作鈴鐺，關閉恢復視窗後再按 Tab。
4. 到期經 App 原本的完整保存流程關閉；若顯示保存問題，保留畫面與紀錄，不強制結束程序。

程式會列印 `input-trace.jsonl` 與 `input-summary.json` 路徑，請提供這兩份與「哪次按鍵／單擊沒反應」的文字描述。

可用 `--output /absolute/path/to/evidence` 指定輸出目錄。正式偏好只讀取副本，偏好修改、sessions、App events 寫到獨立暫存目錄；全域快捷鍵不註冊。不要啟動監控。

紀錄只包括控制項 ID、Tab/Shift+Tab/Space/Return、焦點、滑鼠按下／放開、設定／恢復 callback 時間、UI heartbeat 間隔及可用時的 AppKit activation/keyWindow。不記錄輸入內容。程式不自動判定驗收通過。

## 診斷工具驗證

真實 Aqua smoke：

```zsh
python3 "B518 Log Solution/scripts/diagnose_hmi_input.py" --seconds 5 --output /private/tmp/hf1-input-smoke
```

已在沙盒外執行，exit 0，產生 trace/summary，經正常保存流程關閉。這只驗證工具生命週期；沒有取代使用者真鍵鼠重現。
