# M5 native file-dialog acceptance — 2026-10-09

## Environment and isolation

The user operated the actual M5 source App at HEAD `ef6222220423aee83de5910a0bc1c6309b1df2f6` (code/test revision `a90be28c8b1615b408aaf6147572e603dff5338e`) on the macOS desktop. The launcher redirected App root, preferences, sessions, retention ledger and App journal into `/private/tmp/B518-M5-native-muzx9vrb`. No mock chooser or controlled return value was used in this manual run. No monitoring was started and no production records, sources or exports were used.

The launcher created a portable test catalog, a source-folder directory, an existing export sentinel and baseline hashes. It observed draft paths and public App-event save status without intercepting widget actions. The user opened, selected and cancelled the native dialogs using the real Settings buttons and Cmd+Shift+G navigation.

## User-confirmed operations

| Language | Actual operations | Result |
| --- | --- | --- |
| English | Folder chooser cancellation, then selection of source-folder | User reported normal cancellation and correct returned path; live draft contained the exact selected path. |
| English | Import cancellation, then opening import-test.json | User explicitly confirmed original path stayed unchanged on cancellation. Screenshot `截圖 2026-10-09 10.56.04.png` showed “Configuration validated, imported, and saved.”; fresh disk profiles matched the imported catalog. |
| English | Export cancellation, save as export-test.json, then existing-export.json with overwrite declined | User confirmed all three operations completed. New export matched saved profiles; sentinel hash was unchanged. |
| Traditional Chinese | Switch main-page language with Settings left open; repeat folder cancel/select, import cancel/open, export cancel/save as export-test-zh.json, and decline existing-file overwrite | User reported “結果一切正常”. New Chinese-mode export matched saved profiles; sentinel hash remained unchanged and Settings showed “已匯出 4 組配置。” |
| End of run | Close Settings, then close main App normally | User reported “已正常關閉”; the launcher exited 0 with APP_CLOSED. |

## Native OS presentation boundary

The folder chooser screenshot `截圖 2026-10-09 10.53.39.png` showed an actual macOS NSOpenPanel with Cancel/Choose and “Macintosh HD” as its current location. It did not visibly render the App-supplied “Choose Configuration Path” title. No visible native title or type label is claimed where the OS panel did not expose one. The prior controlled Tk tests verify localized title/filetypes arguments; this manual run verifies real native selection, cancellation, path return and overwrite refusal. System-owned presentation remains governed by macOS, as specified. App-owned Settings copy and operation results visibly used the selected language.

## Fresh disk validation

A new `MachineProfileStore` loaded the isolated preferences with language `zh-TW`, four profiles and no error. A fresh `read_app_event_store` validated seven contiguous events: one startup, two path selections, two imports and two exports. All contained both en/zh-TW messages and no round_id. There were no extra successful-operation records for cancelling or refusing overwrite.

Both export files structurally matched the saved catalog. The existing export SHA-256 remained `7f35d158622eebba7595986d7a7754a040c1a96394bac3eef50a57d256029ae0` before and after both languages' overwrite-decline operations. Structured results are in [native-dialog-disk-result.json](native-dialog-disk-result.json).

M5 acceptance 5 is now passed using real desktop operations plus the prior title/type argument and failure tests. This closes the last product acceptance gap. Gitea synchronization and ticket-branch cleanup remain deferred; they are delivery tasks rather than unverified product behavior.
