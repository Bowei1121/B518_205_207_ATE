# GitHub Issues 與本機驗收對帳 — 2026-10-21

## 範圍與結果

- Repository：Bowei1121/B518_205_207_ATE；逐張讀取 #1–#94，排除 PR。
- 本機產品工作樹：B518 Log Solution，對帳時 HEAD `9b2f0fa7ae7b82c3217a0576f28769acd0534b63`；原工作樹乾淨。
- GitHub PR #95–#103 已逐張讀取，均為 merged；#103 整合 commit 為 `50a6303d584fc2bcab1f0848b06534cd1de1ee35`。本機 remote-tracking ref 當時仍在較舊版本，不用它冒充即時遠端狀態。
- 修改34張Issue正文，補勾259項；新增42則驗收留言（含7張父規格）。所有更新後正文、Issue原開關狀態與留言全文均重新GET讀回相符。
- 僅將有證據的空框改為勾選，未重寫需求文字、修改標籤、關閉／重開Issue、修改產品／測試或重新執行產品測試。
- 工具回傳成功之外，已核對每則留言實際存在，連結如下。既有失敗、skip及歷史版本限制仍在原證據中保留。

## 判定與尚缺證據

| 票組 | 結果與限制 |
| --- | --- |
| M10 #23／父#13 | 補勾4項source條件；10/12 source與整合均371 tests OK、322/322資源。全部16組含正式發布，未全滿足；正式bundle雙語啟動及目標OS／HMI／KVM仍待驗。10/20其他版本arm64建置紀錄不冒充這些全項結果。 |
| QP #48–#53／父#46 | 補勾48項；42故事、逐票及最終整合驗收已有紀錄。 |
| HM #54–#59／父#47 | 補勾48項；45故事、全視窗、實際Light/Dark及雙語bounds已有紀錄。QP／HM最終493項為492通過、1項選用H8 fixture跳過。 |
| HF #61–#64／父#60 | 補勾28項；既有完成留言與真App／Tk、雙語畫面及操作證據一致。#65–#67原核取已正確。 |
| ST7 #75／父#68 | 原有4勾、2未勾維持。最終source真Tk 11/11與語言／KVM 15/15已有證據；原打包.app變色症狀之重現／修復前後仍缺當時bundle路徑與版本。 |
| ST8 #76 | 本機整合8項補勾；52故事與41按鈕矩陣存在，保留OPEN，不將source外觀驗收當ST7原bundle症狀修復。 |
| LI #78–#85／父#77 | 補勾70項；LI8 AC1–11、88故事、公開輪次／磁碟重建／真App驗收完成。LI3 audit補存及LI6手冊後續缺口有最終整合完成紀錄。1.2為當時契約，後續LS版1.3不可混用。 |
| LS1–LS6 #87–#92／父#86 | 補勾42項；PR #95–#100已合併。早期LS2 Tk exit134等缺口由後續LS8相應案例及完整log補足，未把當時失敗改說成通過。 |
| LS7 #93 | 4勾／4未勾；App契約1.3、責任區分、Claude交接及缺環境說明完成。實際JetKVM接收像素≥12×12、遠端壓縮／遮擋／正常與凍結樣本仍待驗。 |
| LS8 #94 | 7勾／1未勾；本機整合實跑於7168e5e，580項為577通過／3跳過。此整合版本arm64原生bundle／簽章／M4 macOS15目標機仍缺；JetKVM配對由#93追蹤。 |

ST7補驗證據位於獨立遠端提交 `8a9789d4c1307b5a6d4fd5597e395c20d97f4849`，沒有包含在本機當前tree；已透過GitHub按該完整SHA讀取README核對，未捏造本機檔案或改用錯誤版本連結。其他對帳證據固定至本機可核對且GitHub可讀的 `9b2f0fa7ae7b82c3217a0576f28769acd0534b63`。

LS8追溯：實測 `7168e5eae414d0a1394b8ab4da4d02b591b886aa` → 僅README連結修正 `f8043c608e73432e1a6551cc34bc7db1a7690639` → 整合 `b24ab21c3bd498518fbff2a036e8e2d85dc5dd26`。後兩個SHA沒有宣稱重跑套件；PR #103只補正文追溯。完整log結尾已實際讀取：Ran 580 tests in 351.704s / OK (skipped=3)。

## 全部94張Issue盤點

核取數只計Issue正文，不把留言中的逐項對照重複算入。無核取清單的規格顯示0/0，不代表沒有需求或已完成。原Issue狀態全部保留。

| Issue | 標題 | 原狀態（維持） | 更新前已勾/全部 | 更新後已勾/全部 | 驗收留言／處理 |
| --- | --- | --- | --- | --- | --- |
| [#1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1) | 輪次紀錄生命週期：可復原保存、完整保存後關閉與保存期限（ADR 0007／0008） | closed | 7/7 | 7/7 | 核取無需變動 |
| [#2](https://github.com/Bowei1121/B518_205_207_ATE/issues/2) | 完成輪次後回收 audit writer，人工操作仍可保存 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#3](https://github.com/Bowei1121/B518_205_207_ATE/issues/3) | 本輪保存失敗可有序重試，且不漏寫或重複 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#4](https://github.com/Bowei1121/B518_205_207_ATE/issues/4) | 換輪後仍追蹤並補存所有未保存輪次 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#5](https://github.com/Bowei1121/B518_205_207_ATE/issues/5) | 所有本次執行紀錄完整保存後才正常關閉 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#6](https://github.com/Bowei1121/B518_205_207_ATE/issues/6) | 完整保存的已結束輪次產生可信封存時間 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#7](https://github.com/Bowei1121/B518_205_207_ATE/issues/7) | 工程師可持久設定全域輪次保存天數 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#8](https://github.com/Bowei1121/B518_205_207_ATE/issues/8) | 背景清理到期整輪紀錄，保留摘要並可恢復失敗 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#9](https://github.com/Bowei1121/B518_205_207_ATE/issues/9) | 人工衝突彈窗：精簡對照、紅色粗體差異與詳細資訊分區 | closed | 3/3 | 3/3 | 核取無需變動 |
| [#10](https://github.com/Bowei1121/B518_205_207_ATE/issues/10) | 衝突彈窗提供四項精簡對照與可拖曳詳細分區 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#11](https://github.com/Bowei1121/B518_205_207_ATE/issues/11) | 差異兩側紅色粗體並辨識同名不同來源 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#12](https://github.com/Bowei1121/B518_205_207_ATE/issues/12) | 多候選覆核與持續刷新維持雙區資訊一致 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13) | 美國工廠部署：即時語言切換與雙語 App 事件紀錄（ADR 0009） | open | 9/13 | 9/13 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/13#issuecomment-6305667326) |
| [#14](https://github.com/Bowei1121/B518_205_207_ATE/issues/14) | 主頁直覺語言選單與上次語言持久保存 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#15](https://github.com/Bowei1121/B518_205_207_ATE/issues/15) | 共同輪次事件同筆雙語保存與即時重新顯示 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#16](https://github.com/Bowei1121/B518_205_207_ATE/issues/16) | 已支援平台事件與來源錯誤完整接入雙語 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#17](https://github.com/Bowei1121/B518_205_207_ATE/issues/17) | 無輪次 App 事件雙語保存與可理解錯誤復原 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#18](https://github.com/Bowei1121/B518_205_207_ATE/issues/18) | 工程師設定與配置操作換語言不丟失輸入 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#19](https://github.com/Bowei1121/B518_205_207_ATE/issues/19) | 衝突與警報即時翻譯並保留人工決定狀態 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#20](https://github.com/Bowei1121/B518_205_207_ATE/issues/20) | 保存與關閉流程的雙語提示及語言切換協調 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#21](https://github.com/Bowei1121/B518_205_207_ATE/issues/21) | 歷史事件按語言顯示且不改寫舊紀錄 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#22](https://github.com/Bowei1121/B518_205_207_ATE/issues/22) | App 層雙語事件按自身時間安全清理 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#23](https://github.com/Bowei1121/B518_205_207_ATE/issues/23) | 完成全 App 翻譯覆蓋與發布資源驗收 | open | 0/9 | 4/9 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/23#issuecomment-6305595796) |
| [#24](https://github.com/Bowei1121/B518_205_207_ATE/issues/24) | 配置與測試輪次啟動組裝：集中準備流程並維持既有行為 | closed | 3/3 | 3/3 | 核取無需變動 |
| [#25](https://github.com/Bowei1121/B518_205_207_ATE/issues/25) | 集中啟動準備，驗證配置與輪次紀錄一致性 | closed | 11/11 | 11/11 | 核取無需變動 |
| [#26](https://github.com/Bowei1121/B518_205_207_ATE/issues/26) | 桌面開始操作接入集中準備流程 | closed | 11/11 | 11/11 | 核取無需變動 |
| [#27](https://github.com/Bowei1121/B518_205_207_ATE/issues/27) | 移除舊組裝流程，完成交付驗證 | closed | 11/11 | 11/11 | 核取無需變動 |
| [#28](https://github.com/Bowei1121/B518_205_207_ATE/issues/28) | 多視窗語言更新通知與清理原因語意表述 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#29](https://github.com/Bowei1121/B518_205_207_ATE/issues/29) | 語言通知、失敗提示與重試 | closed | 10/10 | 10/10 | 核取無需變動 |
| [#30](https://github.com/Bowei1121/B518_205_207_ATE/issues/30) | 設定與查閱視窗接入語言通知 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#31](https://github.com/Bowei1121/B518_205_207_ATE/issues/31) | 衝突、警報與關閉視窗接入 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#32](https://github.com/Bowei1121/B518_205_207_ATE/issues/32) | 移除舊刷新流程，完成第一項驗收 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#33](https://github.com/Bowei1121/B518_205_207_ATE/issues/33) | 新舊清理摘要相容讀取與原因呈現 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#34](https://github.com/Bowei1121/B518_205_207_ATE/issues/34) | 輪次清理與封存驗證產生雙語原因 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#35](https://github.com/Bowei1121/B518_205_207_ATE/issues/35) | App 事件清理產生雙語原因 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#36](https://github.com/Bowei1121/B518_205_207_ATE/issues/36) | 畫面統一使用原因表述，完成第二項驗收 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#37](https://github.com/Bowei1121/B518_205_207_ATE/issues/37) | 歷史事件日期查詢、背景分頁與可重建索引 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#38](https://github.com/Bowei1121/B518_205_207_ATE/issues/38) | H1：日期查詢與首批結果 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#39](https://github.com/Bowei1121/B518_205_207_ATE/issues/39) | H2：重新查詢、取消與視窗生命週期 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#40](https://github.com/Bowei1121/B518_205_207_ATE/issues/40) | H3：完整分頁與按需查看詳細資料 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#41](https://github.com/Bowei1121/B518_205_207_ATE/issues/41) | H4：持久索引與增量查詢 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#42](https://github.com/Bowei1121/B518_205_207_ATE/issues/42) | H5：異常提示、索引降級與重試 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#43](https://github.com/Bowei1121/B518_205_207_ATE/issues/43) | H6：固定結果與保存、清理共存 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#44](https://github.com/Bowei1121/B518_205_207_ATE/issues/44) | H7：圖示操作與即時雙語整合 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#45](https://github.com/Bowei1121/B518_205_207_ATE/issues/45) | H8：大量資料驗收與舊流程收尾 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#46](https://github.com/Bowei1121/B518_205_207_ATE/issues/46) | 歷史查詢結果準備：可靠總數、500筆預載與共用資料回收 | closed | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/46#issuecomment-6305668434) |
| [#47](https://github.com/Bowei1121/B518_205_207_ATE/issues/47) | HMI：固定雙語布局、圖示工具列與淺色外觀 | closed | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/47#issuecomment-6305669368) |
| [#48](https://github.com/Bowei1121/B518_205_207_ATE/issues/48) | QP1：重查重用固定原文 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/48#issuecomment-6305598203) |
| [#49](https://github.com/Bowei1121/B518_205_207_ATE/issues/49) | QP2：可靠總數與前500筆先發布 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/49#issuecomment-6305600156) |
| [#50](https://github.com/Bowei1121/B518_205_207_ATE/issues/50) | QP3：500筆快取與閱讀優先載入 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/50#issuecomment-6305602229) |
| [#51](https://github.com/Bowei1121/B518_205_207_ATE/issues/51) | QP4：後續批次失敗與同版本重試 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/51#issuecomment-6305604167) |
| [#52](https://github.com/Bowei1121/B518_205_207_ATE/issues/52) | QP5：重查取消與共用資料回收整合 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/52#issuecomment-6305606524) |
| [#53](https://github.com/Bowei1121/B518_205_207_ATE/issues/53) | QP6：成本對照與完整交付驗收 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/53#issuecomment-6305609486) |
| [#54](https://github.com/Bowei1121/B518_205_207_ATE/issues/54) | HM1：主頁圖示頂列與操作區狀態 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/54#issuecomment-6305611475) |
| [#55](https://github.com/Bowei1121/B518_205_207_ATE/issues/55) | HM2：設定視窗固定雙語布局 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/55#issuecomment-6305614801) |
| [#56](https://github.com/Bowei1121/B518_205_207_ATE/issues/56) | HM3：衝突與警報視窗固定雙語布局 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/56#issuecomment-6305616478) |
| [#57](https://github.com/Bowei1121/B518_205_207_ATE/issues/57) | HM4：歷史與診斷視窗固定雙語布局 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/57#issuecomment-6305618261) |
| [#58](https://github.com/Bowei1121/B518_205_207_ATE/issues/58) | HM5：保存關閉與一般提示視窗固定雙語布局 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/58#issuecomment-6305620319) |
| [#59](https://github.com/Bowei1121/B518_205_207_ATE/issues/59) | HM6：全App淺色一致性與整體驗收 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/59#issuecomment-6305622987) |
| [#60](https://github.com/Bowei1121/B518_205_207_ATE/issues/60) | HMI 後續改善：圖示辨識、通知整合與設定／摘要穩定性 | closed | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/60#issuecomment-6305670328) |
| [#61](https://github.com/Bowei1121/B518_205_207_ATE/issues/61) | HF1：改善頂列四個圖示的辨識度 | closed | 0/6 | 6/6 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/61#issuecomment-6305625640) |
| [#62](https://github.com/Bowei1121/B518_205_207_ATE/issues/62) | HF2：鈴鐺整合整輪警報、保存與封存操作 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/62#issuecomment-6305627806) |
| [#63](https://github.com/Bowei1121/B518_205_207_ATE/issues/63) | HF3：鈴鐺異常計數與數量徽章 | closed | 0/7 | 7/7 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/63#issuecomment-6305629748) |
| [#64](https://github.com/Bowei1121/B518_205_207_ATE/issues/64) | HF4：精簡主頁，建立底部狀態與診斷入口 | closed | 0/7 | 7/7 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/64#issuecomment-6305634852) |
| [#65](https://github.com/Bowei1121/B518_205_207_ATE/issues/65) | HF5：設定頁瀏覽按鈕與三等分排列 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#66](https://github.com/Bowei1121/B518_205_207_ATE/issues/66) | HF6：修復清理摘要空白與捲軸跳動 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#67](https://github.com/Bowei1121/B518_205_207_ATE/issues/67) | HF7：整體桌面驗收與回歸確認 | closed | 8/8 | 8/8 | 核取無需變動 |
| [#68](https://github.com/Bowei1121/B518_205_207_ATE/issues/68) | Slot 與頂列 HMI 改善：十列捲動、雙徽章、全按鈕提示與固定淺色 | open | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/68#issuecomment-6305671371) |
| [#69](https://github.com/Bowei1121/B518_205_207_ATE/issues/69) | ST1：Slot 最多十列與灰色停用捲軸 | closed | 5/5 | 5/5 | 核取無需變動 |
| [#70](https://github.com/Bowei1121/B518_205_207_ATE/issues/70) | ST2：頂列對齊、雙徽章與精簡語言入口 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#71](https://github.com/Bowei1121/B518_205_207_ATE/issues/71) | ST3：主頁按鈕的完整提示與互動狀態 | closed | 7/7 | 7/7 | 核取無需變動 |
| [#72](https://github.com/Bowei1121/B518_205_207_ATE/issues/72) | ST4：設定與通知恢復視窗的按鈕提示 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#73](https://github.com/Bowei1121/B518_205_207_ATE/issues/73) | ST5：裁決、警報及關閉保存流程的按鈕提示 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#74](https://github.com/Bowei1121/B518_205_207_ATE/issues/74) | ST6：歷史查詢與診斷視窗的按鈕提示 | closed | 6/6 | 6/6 | 核取無需變動 |
| [#75](https://github.com/Bowei1121/B518_205_207_ATE/issues/75) | ST7：通知與恢復視窗固定淺色修復 | open | 4/6 | 4/6 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/75#issuecomment-6305635819) |
| [#76](https://github.com/Bowei1121/B518_205_207_ATE/issues/76) | ST8：整體桌面驗收與全按鈕覆蓋核對 | open | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/76#issuecomment-6305637624) |
| [#77](https://github.com/Bowei1121/B518_205_207_ATE/issues/77) | 規格：Log Solution 儀器狀態、人工停止與顯示契約 1.2 | open | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/77#issuecomment-6305672201) |
| [#78](https://github.com/Bowei1121/B518_205_207_ATE/issues/78) | LI1：正常輪次的準備、監控就緒與活動顯示 | closed | 0/10 | 10/10 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/78#issuecomment-6305639566) |
| [#79](https://github.com/Bowei1121/B518_205_207_ATE/issues/79) | LI2：人工停止保留結果並完整交付 | closed | 0/10 | 10/10 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/79#issuecomment-6305641639) |
| [#80](https://github.com/Bowei1121/B518_205_207_ATE/issues/80) | LI3：啟動失敗待確認與人工復位 | closed | 0/9 | 9/9 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/80#issuecomment-6305643333) |
| [#81](https://github.com/Bowei1121/B518_205_207_ATE/issues/81) | LI4：FCT 120秒與整輪未開始警報 | closed | 0/9 | 9/9 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/81#issuecomment-6305645142) |
| [#82](https://github.com/Bowei1121/B518_205_207_ATE/issues/82) | LI5：人工核對後取消並重新開始 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/82#issuecomment-6305646891) |
| [#83](https://github.com/Bowei1121/B518_205_207_ATE/issues/83) | LI6：指定事件提升視窗且不搶焦點 | closed | 0/6 | 6/6 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/83#issuecomment-6305648680) |
| [#84](https://github.com/Bowei1121/B518_205_207_ATE/issues/84) | LI7：左定位點移位與本機幾何定稿 | closed | 0/7 | 7/7 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/84#issuecomment-6305650324) |
| [#85](https://github.com/Bowei1121/B518_205_207_ATE/issues/85) | LI8：本程式整合驗收與契約1.2交付 | closed | 0/11 | 11/11 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/85#issuecomment-6305651889) |
| [#86](https://github.com/Bowei1121/B518_205_207_ATE/issues/86) | 規格：Log Solution 架構優化、監控計時與獨立畫面心跳 | open | 0/0 | 0/0 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/86#issuecomment-6305673217) |
| [#87](https://github.com/Bowei1121/B518_205_207_ATE/issues/87) | LS1：開發與打包共同核對 Python 3.12.10 | closed | 0/6 | 6/6 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/87#issuecomment-6305655475) |
| [#88](https://github.com/Bowei1121/B518_205_207_ATE/issues/88) | LS2：統一開始監控與正確的失敗原因 | closed | 0/7 | 7/7 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/88#issuecomment-6305657202) |
| [#89](https://github.com/Bowei1121/B518_205_207_ATE/issues/89) | LS3：集中歷史查詢、取消與視窗生命週期 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/89#issuecomment-6305658755) |
| [#90](https://github.com/Bowei1121/B518_205_207_ATE/issues/90) | LS4：正常監控的固定分秒計時與耗時保存 | closed | 0/8 | 8/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/90#issuecomment-6305660762) |
| [#91](https://github.com/Bowei1121/B518_205_207_ATE/issues/91) | LS5：中止、失敗與補存時保留正確監控時間 | closed | 0/6 | 6/6 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/91#issuecomment-6305662348) |
| [#92](https://github.com/Bowei1121/B518_205_207_ATE/issues/92) | LS6：全狀態半秒四格心跳與同列顯示 | closed | 0/7 | 7/7 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/92#issuecomment-6305664123) |
| [#93](https://github.com/Bowei1121/B518_205_207_ATE/issues/93) | LS7：實測顯示契約並交付 Claude 橋接資料 | open | 0/8 | 4/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/93#issuecomment-6305665956) |
| [#94](https://github.com/Bowei1121/B518_205_207_ATE/issues/94) | LS8：整體桌面驗收、打包與交付證據 | open | 0/8 | 7/8 | [已讀回留言](https://github.com/Bowei1121/B518_205_207_ATE/issues/94#issuecomment-6305590900) |
