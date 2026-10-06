# T1：完成輪次後回收 audit writer，人工操作仍可保存

## Parent

Part of [規格 Issue #1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1)。依 ADR 0007／0008 與已確認拆票方案實作。

## What to build

先整理保存工作者的生命週期，讓多輪長時間運轉不累積 audit writer；保留約 0.2 秒空閒退出、有新工作再啟動的行為。操作員停止讀檔後仍可處理衝突與警報，新增紀錄仍可保存且重建，不改逐筆落盤或 flush 語意。

## Acceptance criteria

- [ ] 受控多輪完成、排空及空閒後，audit worker 不隨已結束輪次線性累積。
- [ ] 空閒退出後新增紀錄能重新保存；退出與新增工作競爭不漏寫或留下無 worker 的待保存工作。
- [ ] 停止讀檔後的衝突處理與警報確認可從磁碟重建，事件順序及既有 fsync／flush 契約維持。
- [ ] 共享路徑鎖安全評估及必要回收不破壞同路徑互斥，仍使用中的鎖不會被替換。
- [ ] 經共同輪次公開入口及暫存磁碟驗證，包含反覆輪次與同步競爭；不以私有 helper 呼叫次數驗收。

## Blocked by

None (can start immediately).
