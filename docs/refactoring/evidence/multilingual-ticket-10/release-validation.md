# M10 發布與 bundle 驗收

狀態：**待符合政策的建置主機及目標設備；尚未產生本票正式產物。**  
程式／測試版本查核：`e8a309fd1fac186832c5825c803e4299932f206b`。本紀錄不代表簽章、bundle、最低 OS、目標設備或現場驗收通過。

## 發布政策與本機 preflight

以目前 Python 專案的 [README](../../../../B518%20Log%20Solution/README.md) 與 [Ticket 17 發布指南](../../../../B518%20Log%20Solution/docs/TICKET17_MACOS_RELEASE_AND_FIELD_ACCEPTANCE.md) 為準；不沿用舊摘要的環境狀態。

| 目標 | 指定建置環境 | 本次主機狀態 | 結果 |
| --- | --- | --- | --- |
| Intel macOS 10.14／10.15 | Intel Catalina 10.15.x、x86_64、可載入 Tk 的 Python 3.12 | macOS 15.7.9、Intel x86_64；系統 Python 3.8.10 | 不符合政策 |
| Apple Silicon macOS 15.x | Apple Silicon 原生 arm64、macOS 15+、Python.org 3.12.10 universal2 且 Tk 可用 | 主機為 Intel x86_64；指定 Python.org 路徑 `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12` 不存在 | 不符合政策 |
| Apple Silicon macOS 26.x 測試目標 | Apple Silicon 原生 arm64、macOS 26+、Homebrew Python 3.12 且 Tk 可用 | 本機 macOS 15.7.9、Intel x86_64 | 不符合政策 |

實際查核命令與結果：

```text
sw_vers -productVersion                 -> 15.7.9
uname -m                                -> x86_64
python3 --version                       -> Python 3.8.10
/usr/local/bin/python3.12 --version     -> Python 3.12.13
/usr/local/bin/python3.12 -c 'import tkinter; print(tkinter.TkVersion)' -> 9.0
Python.org 3.12.10 指定路徑             -> 不存在
```

三個目標 `build-*`、`dist-*` 目錄及目標虛擬環境在本次查核時都不存在。沒有執行任何 build script，因此沒有遞增 `VERSION`、刪除／建立 build 與 dist 內容、輸出 ZIP、簽章或產物雜湊。這避免使用不相符的 Intel macOS 15／Python 3.8 或 Homebrew Tk 9 繞過文件規定的建置門檻。

本機已完成的 source 驗收是另一層：`B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 在 source 程式／測試 SHA `e8a309fd1fac186832c5825c803e4299932f206b` 通過 365 tests（97.910 秒，含真 Tk）。另以此 SHA 單獨重跑整合多視窗 Tk 案例，1 test 通過。`test_verify_macos_bundle` 對 verifier／preflight 邊界的單元測試也在完整套件中通過；單元測試不等於實際產物驗證。

## 尚需在符合政策的環境完成

1. 取得當前 `Multilingual/ticket-10` 最終程式及資源 commit，在已支援矩陣的建置主機登入桌面執行 preflight。Intel 10.14 產物要用 Intel Catalina；Apple Silicon 15 產物需原生 arm64 macOS 15+ 與 Python.org 3.12.10；26.x 僅依既有 26.x 測試矩陣建置。
2. 建置前記錄來源 commit、工作樹、主機 macOS、CPU 架構、Python 路徑／版本、Tk 版本、工具與目標版本。先確認對應 target 的舊產物是否需要保留，才執行現有 build script；不可改版本以取得綠燈。
3. 執行既有目標 build script，保存其測試、preflight、VERSION、建置、靜態 verifier、ZIP 與 SHA-256 輸出。對實際產物執行 `shasum -a 256 -c <zip>.sha256`、`scripts/verify_macos_bundle.py` 及指南規定的 ad-hoc codesign 驗證。記錄 `Info.plist` 版本、最低 OS、架構、所有載入相依及翻譯資源實際路徑。
4. 從該 bundle 實際啟動 App，在隔離 App 根目錄操作英文／繁中、設定、事件／歷史、錯誤診斷及必要多視窗路徑，並確認事件／偏好重讀與 KVM 版面。建立產物來源 commit 與 SHA-256 的對應記錄。
5. 依發布指南在適用目標 macOS／設備完成實際啟動與操作驗收，分開記錄建置成功、靜態 bundle 查核、bundle 操作、最低 OS／目標設備及現場結果。Ad-hoc 簽章不可描述為 Developer ID 或 notarization。

建置或翻譯資源變更後，重新執行相應測試；bundle 驗收後若程式或資源再變更，必須用新 SHA 重建並重跑適用發布檢查。正式 bundle／目標環境驗收未完成前，M10 不符合合併條件，票分支必須保留。
