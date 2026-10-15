# HM6 — App 視窗矩陣

| 畫面／狀態 | 真 Tk 驗收與中英證據 | 結果 |
|---|---|---|
| 主頁 376px、圖示頂列、專案／機型選單、操作區狀態、KVM 單排 | `test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed`；`main-page-en.png`、`main-page-zh-TW.png`；`window-bounds.json/main_page` | 英文／繁中主頁所有列出的控件 bounds 逐項相等；停止與保存重試按鈕沒有被壓縮。 |
| KVM 雙排、狀態色、未用黑格 | `test_hm6_two_row_kvm_keeps_geometry_and_unused_slots_black`；`main-page-capacity12-en.png`；`window-bounds.json/main_page_capacity12`；`test_kvm_display_contract` | 12 格雙排；slot 12 保留 PASS 色、slot 13 為黑色未使用格；定位／狀態標記幾何和解碼契約保持。 |
| Logo 正常／缺失／損壞 | `test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog`；source asset SHA 見 `local-validation.md` | 固定 137×35 slot；缺失／損壞留白、不跳位、不彈窗。正式 bundle 以既有打包資產路徑與驗證測例檢查，未冒稱已簽章部署。 |
| 設定：配置、保存期限、事件／歷史入口 | `test_settings_layout_is_stable_across_languages_and_keeps_drafts`；`settings-configuration-en.png`、`settings-configuration-zh-TW.png`、`settings-bounds.json` | 三個設定頁均逐控件比較中英 bounds；草稿、長路徑、機型原生選擇、期限保存、匯入／匯出保持。截圖記錄配置頁；其餘頁以真控件 bounds 檢查。 |
| 衝突覆核 | `test_hm3_conflict_and_alarm_layout_stays_fixed_across_languages`；`conflict-review-en.png`、`conflict-review-zh-TW.png` | 長內容可捲動；選取／分隔位置／資料與 KVM 幾何在中英切換後保持。 |
| 整輪警報 | 同 HM3案例；`round-alarm-en.png`、`round-alarm-zh-TW.png` | 確認入口、待確認狀態及中英控制 bounds 保持。 |
| 歷史事件／來源異常 | `test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail`；`history-events-en.png`、`history-events-zh-TW.png`、`history-diagnostics-en.png`、`history-diagnostics-zh-TW.png` | 日期草稿、固定查詢、頁碼、選取與閱讀位置保持；異常與長原文可閱讀。 |
| App 診斷 | 同 HM4案例；`app-diagnostics-en.png`、`app-diagnostics-zh-TW.png` | 中英標題、按鈕、診斷詳細與閱讀位置保持。 |
| 關閉前保存／重試／取消 | `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`；`close-progress-en.png`、`close-progress-zh-TW.png` | 保存失敗保持視窗，實際重試完成後才可關閉；進度／語言限制／診斷／操作列 bounds 固定。 |
| 一般提示／Escape | `test_hm5_long_notice_stays_scrollable_and_fixed_across_languages`；`general-notice-en.png`、`general-notice-zh-TW.png` | 160行診斷可捲動，確認鈕焦點及中英幾何保持；Escape 關閉。 |
| 原生檔案對話框 | HMI 規格 A10／HM6 ticket 排除逐 App 淺色承諾；HM2 測例透過隔離 Temp 路徑實際使用 Import／Export | 保留 macOS 原生外觀與既有操作，不把原生視窗納入 App 自有樣式矩陣。 |

所有擷取均為目標 App 原生視窗的 Quartz 截圖，不含整個桌面背景。根目錄截圖為實際 macOS Dark 外觀，`system-light/` 中同名截圖為使用者切換至 Light 後的實際 Aqua 驗收；App 自有內容在兩種系統外觀下均固定淺色，原生標題列跟隨系統。主頁證據另包括六個完整底部操作按鈕的 bounds，中英逐項一致。
