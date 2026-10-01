# Issue tracker: GitHub

議題與新規格使用 Bowei1121/B518_205_207_ATE 的 GitHub Issues。
使用 gh CLI，明確傳入 --repo Bowei1121/B518_205_207_ATE，避免多 remote 歧義。

- 發布：`gh issue create --repo Bowei1121/B518_205_207_ATE --title "..." --body-file <檔案>`
- 讀取：`gh issue view <編號> --repo Bowei1121/B518_205_207_ATE --comments`
- 列表：`gh issue list --repo Bowei1121/B518_205_207_ATE --state open`
- 更新標籤：`gh issue edit <編號> --repo Bowei1121/B518_205_207_ATE --add-label "..."`
- 移除標籤：使用 `--remove-label`。
- 留言：`gh issue comment <編號> --repo Bowei1121/B518_205_207_ATE --body-file <檔案>`
- 關閉：`gh issue close <編號> --repo Bowei1121/B518_205_207_ATE`

PRs as a request surface: no.

既有 docs/refactoring/ 規格與 tickets 保留為原始紀錄；
本次設定不自動建立對應遠端議題。若後續遷移，記錄本機文件與 issue 的對照。

使用 wayfinder 時，以 wayfinder:map 議題保存總覽，
子議題使用 wayfinder:research、wayfinder:prototype、wayfinder:grilling 或 wayfinder:task。
優先使用 GitHub 子議題及原生依賴；不支援時以任務清單、
Part of #編號 與 Blocked by: #編號 記錄關係。
只認領無未完成依賴且未指派的工作；完成後記錄結果、關閉議題並更新總覽。
