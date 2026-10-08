# 配置與測試輪次啟動組裝規格

## Problem Statement

操作員需要在選擇專案與機型後，以熟悉的操作可靠地開始測試。現在桌面介面同時理解配置驗證、平台監控建立、回呼順序、來源與顯示位置映射，以及 Session／audit 配置資訊的組裝規則。工程師變更平台或啟動流程時，必須跨畫面與輪次管理理解這些細節；部分啟動規則只能透過大量模擬畫面測試，增加無意改變現場操作、配置證據與失敗處理的風險。

本次問題是啟動準備責任分散，不是已證實的監控效能不足。剛完成的保存、關閉與期限清理安全性必須保留。

## Solution

集中啟動準備責任，以同一份固定測試配置完成驗證、平台監控與位置對應的組裝，並產生一致的 Session／audit 配置資訊。操作員仍使用原本的畫面與開始操作，既有提示文字、時機與操作效果不變。

輪次管理繼續負責接受開始、背景準備排程、逾時、停止及保存；桌面介面負責輸入、狀態呈現與提示。先建立並驗證集中準備 Module，再將 Tk 切換至新流程；所有既有平台通過程式與桌面驗證後交付，實際設備另階段現場驗收。

## User Stories

1. As an 操作員, I want 沿用專案與機型選擇方式, so that 不必重新學習開始測試的操作。
2. As an 操作員, I want 沿用開始按鈕, so that 架構改造不改變日常操作。
3. As an 操作員, I want 沿用視窗內與全域快捷鍵的既有操作, so that 原本的工作習慣仍適用。
4. As an 操作員, I want 無效配置在開始前被指出, so that 不會用錯誤配置建立新輪次。
5. As an 操作員, I want 必要來源路徑保持既有檢查, so that 缺少或無法讀取的來源不會被接受。
6. As an 操作員, I want 選填路徑保持原有空白與錯誤處理, so that 不會被要求填寫原本不需要的來源。
7. As an 操作員, I want 空白路徑不被當作目前目錄, so that 不會誤讀其他測試資料。
8. As an 操作員, I want 錯誤提示文字與出現時機保持一致, so that 現有操作指引仍然適用。
9. As an 操作員, I want 偏好保存失敗時沿用既有阻擋與畫面恢復, so that 不會在選擇未保存的情況下接受新輪次。
10. As an 操作員, I want 開始時固定本輪配置, so that 後續設定變更不會影響正在執行的測試。
11. As an 操作員, I want 來源位置仍對應到正確顯示位置, so that 結果與受測產品位置一致。
12. As an 操作員, I want 每個平台仍使用自己的解析規則, so that 不會因共用啟動流程誤判來源。
13. As an 操作員, I want 來源仍在背景準備, so that 原有視窗操作方式維持。
14. As an 操作員, I want 準備時間仍計入整輪期限, so that 改造不悄悄延長測試等待時間。
15. As an 操作員, I want 準備中停止後不再自動開始收集, so that 停止操作仍然有效。
16. As an 操作員, I want 準備期間逾時後不因來源稍後就緒而重啟, so that 期限與結果處理一致。
17. As an 操作員, I want 來源建立失敗時恢復原有控制與提示, so that 能按既有方式修正問題。
18. As an 操作員, I want 執行中重複開始維持原輪與畫面, so that 不會意外清空本輪結果。
19. As an 操作員, I want 待確認時各開始入口本次維持原行為, so that 行為修正能與架構改造分開驗收。
20. As an 操作員, I want 關閉保存中仍拒絕開始新輪, so that 不破壞完整保存後關閉的機制。
21. As an 操作員, I want 舊輪事件不影響新輪畫面, so that 換輪後顯示仍可信。
22. As an 工程師, I want Session 與 audit 從同一份固定配置產生資訊, so that 兩份紀錄能一致重建本輪設定。
23. As an 工程師, I want 保留既有配置格式與紀錄結構, so that 現有配置與紀錄讀取方式仍可使用。
24. As an 工程師, I want 啟動失敗輪次與事件仍被追蹤保存, so that 能排查失敗且正常關閉不遺失資料。
25. As an 工程師, I want 未映射來源仍保留既有證據處理, so that 不會為了畫面映射而漏掉來源資訊。
26. As an 工程師, I want 直接驗證啟動準備的公開行為, so that 不必建立 Tk 才能測試配置與組裝規則。
27. As an 工程師, I want 可控制來源準備速度與失敗, so that 能穩定重現逾時、停止與錯誤情境。
28. As an 工程師, I want 所有既有平台完成回歸驗證, so that 不會只改善單一平台卻破壞其他平台。
29. As an 工程師, I want 保留真正 Tk 操作測試, so that 無畫面測試通過仍有桌面行為證據。
30. As an 工程師, I want 分兩階段遷移並移除重複組裝, so that 正式版本只有一套啟動規則。
31. As an 工程師, I want 已支援平台參數仍可獨立更新配置, so that 這次改造不增加 App 重發布需求。
32. As an 維護者, I want 明確區分程式驗證與現場驗收, so that 不會把測試資料通過誤認為設備已驗收。

## Implementation Decisions

- 建立集中啟動準備 Module；其 Interface 接收已選定的測試配置與既有建立環境，對外提供驗證後的固定配置、平台監控組裝能力及 Session／audit 所需配置資訊。這是責任契約，不預先綁定類別數量或方法名稱。
- Interface 不接收 Tk widget，不要求呼叫端理解回呼 holder、來源位置列表或配置證據組裝順序；Implementation 集中這些知識，提高 Depth 與 Locality。平台擴充共用此準備流程，形成 Leverage。
- Tk 保留取得使用者選擇、顯示狀態、提示錯誤、保存偏好與呼叫既有輪次開始入口的協調；偏好保存仍在接受新輪前完成。既有配置管理保留設定畫面及匯入匯出責任。
- RoundCoordinator 保留輪次接受、來源背景準備排程、輪次識別、事件歸屬、期限、停止、結果判定與保存。集中準備 Module 不另建輪次狀態機、背景工作排程或保存生命週期。
- 沿用 PlatformRegistry 的平台定義與建立能力，平台 Adapter 保留來源格式與證據語意；ConfiguredMonitor 保留雙向位置轉換及未映射來源處理，不為減少檔案數而刪除具有實際責任的 Module。
- 在來源背景準備前固定選定測試配置。平台、容量、位置對應、路徑、逾時及版本資訊均由同一份固定配置衍生；之後不得重新讀取畫面目前選擇來組裝本輪資訊。
- Session 的配置快照與 audit 的配置背景資訊保留各自既有結構及欄位含義；共用原始配置不代表強迫兩份紀錄格式相同，也不引入新 schema 版本。平台所用已驗證路徑與紀錄所保存的原配置路徑保留現有差異，不擅自改寫原值。
- 必要路徑必須是存在且可讀取、可進入的目錄；選填路徑空白仍可省略，非空則依既有規則檢查。空白不當作目前目錄；使用原平台路徑標籤與原錯誤提示。
- 維持時序：配置與路徑驗證 → 固定本輪配置並顯示啟動中 → 保存偏好 → 接受輪次 → 背景建立來源與關聯紀錄 → 依原規則開始收集並通知來源就緒。不得把來源建立提前至接受輪次前，或把同步驗證與偏好保存改成背景工作。
- 接受輪次與來源就緒是兩個時點，來源準備耗時仍計入整輪期限。組裝、事件轉送與準備期間的停止／期限檢查保留原順序及歸屬，不能用新的準備完成時間覆寫接受開始時間。
- 配置、路徑與偏好保存的同步失敗不接受新輪次；恢復與提示沿用既有流程。接受後的背景建立失敗保留失敗輪次及事件，恢復原有畫面控制，繼續受跨輪追蹤與保存關閉契約保護。
- 準備期間停止或逾時後，來源稍後返回不得重新開始收集；準備中要求關閉，仍由既有關閉協調等待及保存，不由準備 Module 提早宣告完成。
- 執行中重複開始不換輪、不重設結果；關閉保存中拒絕開始。AWAITING_REVIEW 的直接開始處理與快捷鍵現有差異依 A5 保留，獨立修正不納入本次。
- 保留舊輪事件隔離、未知同輪來源的採用政策、原衝突裁決與 KVM 顯示契約。重構不得新增或重複發送事件、改變保存與結果放行的既有政策。
- 第一階段建立集中準備 Module 及行為測試，不切換 Tk 正式入口；第二階段接入 Tk，驗證所有既有平台後移除舊組裝。正式交付只有一套啟動規則，不長期維護平行選項。
- 遵循 ADR 0003、0005、0008，並維持 ADR 0001、0002、0004、0006、0007 的相關既有契約。本次沒有需重議 ADR 的取捨，也不將實作責任寫成新的領域詞彙。

## Testing Decisions

- 使用者在 A7 已確認測試 Seams，並在完整討論結論確認時再次採用；不需重複訪談。主要新增 Seam 是集中啟動準備 Module 的公開 Interface；輪次執行測試優先沿用更高層的 RoundCoordinator 公開行為，桌面行為沿用真正 Tk 入口。不為每個內部步驟新增測試 Seam。
- 好測試驗證輸入後可觀察的監控行為、輪次狀態、畫面內容與磁碟證據，不以私有 helper、特定 class 數量、呼叫次數或 mock 呼叫鏈為主要判定。
- 準備 Module 使用真實暫存目錄與測試資料，驗證必要／選填路徑、固定配置、容量、位置對應及兩份配置資訊一致性。變更外部配置或畫面選擇後，本輪仍使用原固定值。
- 沿用可注入時鐘、可控制 monitor factory 與既有 Session／audit 磁碟查詢方式，重現緩慢準備、建立失敗、停止與逾時；不用長時間實際等待作為主要測試。
- 沿用既有 ConfiguredMonitor 容量、位置順序、雙向轉換及未映射來源案例；沿用平台受控來源解析測試與共同輪次保存／關閉測試。
- 真正 Tk 覆蓋開始按鈕、視窗內快捷鍵、全域快捷鍵要求送回 Tk 事件迴圈後的操作、提示文字與恢復狀態。全域快捷鍵測試不得只據此宣稱作業系統或現場鍵盤整合已驗收。
- 所有註冊平台均覆蓋：Atlas DFU／FCT、B482 BT、RS-WMT BT，以及受控 sample-json FCT。樣本平台用於受控驗證，不能代替實際平台解析或現場驗收。
- 新 Seam 測試與現有測試共同驗證，避免另寫一套與正式入口不同的配置規則。接入 Tk 後移除失去意義的舊 mock 細節測試，保留其有效行為情境。

### 程式與桌面驗收矩陣

| 情境 | 入口與證據 | 通過條件 |
| --- | --- | --- |
| 無效配置／未知平台 | 準備 Interface、Tk | 提示與原行為一致，不接受新輪、不建立來源 |
| 必要路徑空白、不存在或不可讀 | 真實暫存目錄、Tk | 不接受新輪；空白不指向目前目錄 |
| 選填路徑空白／非空無效 | 準備 Interface | 空白按原規則省略；無效非空阻擋開始 |
| 偏好保存失敗 | Tk、輪次快照 | 不接受新輪，原提示與控制恢復維持 |
| 固定配置與雙份證據 | 準備 Interface、Session／audit | 平台、容量、映射、路徑、逾時與版本對應同一份配置；格式不變 |
| 各平台正常開始 | 準備 Interface、既有平台與輪次入口、Tk | 容量、來源建立、位置、結果與事件維持原行為 |
| 慢速準備 | 控制來源、時鐘、RoundCoordinator | 接受時間不被就緒時間覆寫；準備耗時計入期限 |
| 背景建立失敗 | 輪次、Tk、真實磁碟紀錄 | 保留失敗輪次與事件，原提示與控制恢復，保存責任不遺失 |
| 準備中停止／逾時 | 控制來源、RoundCoordinator | 晚到的準備完成不重新開始收集 |
| 執行中重複開始 | Tk／快捷鍵、輪次快照 | 原輪與結果保持，不重設畫面 |
| 待確認時重複開始 | 直接開始與兩種快捷鍵各別測試 | 不建立新輪；各入口副作用保持查證的基準差異 |
| 關閉保存中開始／準備中關閉 | Tk、RoundCoordinator、磁碟重建 | 拒絕新開始；既有保存與關閉完整性維持 |
| 舊輪延遲事件／未映射來源 | 輪次、ConfiguredMonitor、Tk | 不覆寫新輪畫面；來源證據按原規則保留 |
| 改造後保存、封存與清理 | 既有輪次生命週期回歸測試 | 跨輪待保存追蹤、失敗重試、封存與刪除保護不退化 |

完成新行為測試、相關既有回歸測試、專案必要檢查與桌面驗證後，才可交付第二階段。記錄實際執行結果與未驗證項目，不能引用先前測試數字作為本次通過證據。

## Out of Scope

- 工程師設定畫面重設計、配置匯入匯出改造、新配置格式或新平台解析器。
- 輪次結果判定、衝突裁決、未知同輪來源採用政策與 KVM 契約變更。
- 保存生命週期重新拆分、writer 政策、封存格式與期限清理政策變更。
- 待確認時所有開始入口無副作用的行為修正；僅保留基準行為測試並另案追蹤。
- 提示改寫、多語言實作與另存 App 層雙語事件；由既有多語言工作負責。
- 更換 Python／Tk、現有 macOS 打包方式、外部解析器動態載入。
- 為未來假設需求新增 Adapter、以拆檔數量作為完成標準，或承諾未量測的效能改善。
- 在此階段宣稱實際工廠設備與資料已完成現場驗收。

## Further Notes

### R1 verification coverage

R1 is implemented without switching the formal Tk entry point. Its current-run preparation, platform, disk, timing, and failure evidence is recorded in [R1 local validation](evidence/round-start-assembly-ticket-01/local-validation.md). The 14 scenario groups in the R1 ticket are mapped there to new R1 tests, inherited regression tests, or work explicitly left to R2/R3; this coverage does not claim desktop migration or field-device acceptance.

R2 connects the formal Tk button and keyboard entry paths to the R1 public preparation interface. Its 14-scenario coverage and R2 acceptance evidence are tracked in [R2 local validation](evidence/round-start-assembly-ticket-02/local-validation.md). The R2 tests distinguish newly added desktop coverage from inherited R1/coordinator regression evidence; they do not claim R3's old-path cleanup, complete release sign-off, OS-level global-hotkey field acceptance, or physical factory-device acceptance.

- 日期：2026-10-08。來源：`ROUND_START_ASSEMBLY_DISCUSSION_2026-10-08.md` 的 A1–A7；使用者已同意完整結論並要求轉為規格。
- 討論事實查證基準為 4d7754c；制定規格時 HEAD 為 332a451，新增提交為 C1 合併驗證文件。開始實作前須再次核對最新程式，遇到契約差異先記錄，不暗中改變已確認需求。
- 遠端規格議題：[GitHub #24](https://github.com/Bowei1121/B518_205_207_ATE/issues/24)，標籤為 ready-for-agent。本次不拆開發票、不直接實作程式。
- 現場驗收另階段以工程師認可的實際配置與各平台來源，核對正常啟動、位置／結果呈現、停止、失敗提示及保存關閉；記錄設備、配置版本、驗收結果與限制。程式測試不替代現場驗收，設備及時程由後續安排確定。
