# QP1–QP6 與 HM1–HM6 整合執行紀錄 — 2026-10-15

## 固定基準

- 專案分支：`B518-Log-Solution`
- 整合分支：`codex/qp-hmi-full-integration-20261015`
- 整合起始審查基準：`3517e75a794d1b9ba45c3bc17633f6b9abbfb405`
- 每票固定審查基準：各票 worktree 建立時的整合分支 HEAD；記錄於下表，完成後不隨整合分支移動。

## 執行規則

- Query tickets: #48–#53 (QP1–QP6), parent specification #46.
- HMI tickets: #54–#59 (HM1–HM6), parent specification #47.
- Each ticket uses an isolated worktree and branch. Validate and review against its recorded base, then merge into this integration branch.
- Re-evaluate native issue dependencies after every integration. QP chain: #48 → #49 → (#50 and #51) → #52 → #53. HMI implementation is serialized by shared UI files; #59 follows #54–#58. Query and HMI tracks may run concurrently, while full Tk suites and heavy measurements are staggered.
- Close a child issue only after its acceptance evidence and integration are complete. Close #46/#47 only after every requirement in the corresponding parent specification is verified.
- Final integration review uses the fixed start SHA above, not a moving merge base. Complete regression and standards/spec dual-axis review before merging back to `B518-Log-Solution` and pushing every configured remote.

## Ticket ledger

| Issue | Ticket | Branch | Fixed review base | Status |
|---:|---|---|---|---|
| #48 | QP1 | `codex/qp1-20261015` | `31d08141add7bf9a936e701d99f193455bf40ede` | integrated at `94d98b1`; closed after acceptance |
| #49 | QP2 | `codex/qp2-20261015` | `94d98b192f5521bb27faa7d61c44fd10d766b737` | integrated at `61dccbc`; closed after acceptance |
| #50 | QP3 | `codex/qp3-20261015` | `61dccbc088dab9e48a643c711d49c74d2abb520f` | integrated at `e59a343`; fixed-base Standards/Spec reviews clean; 64 query/language + 2 true-Tk integrated checks passed; closed after acceptance |
| #51 | QP4 | `codex/qp4-20261015` | `61dccbc088dab9e48a643c711d49c74d2abb520f` | integrated at `7627bd6`; 63 query/language + 3 true-Tk integration checks passed; fixed-base Spec review clean; Standards review clean through implementation, remaining commits were tests/docs only; closed after acceptance |
| #52 | QP5 | `codex/qp5-20261015` | `f4fa96812ee5bae6cde33fb90de174ab0ab5ad2b` | integrated at `990a3d8`; 58 query/storage + 3 true-Tk lifecycle checks passed on ticket and integration branches; fixed-base scope/standards review clean; closed after acceptance |
| #53 | QP6 | `codex/qp6-20261015` | `990a3d87193035e9dc235fb8f765267fdd8f820a` | ready; unblocked after #52 acceptance; worktree creation pending |
| #54 | HM1 | `codex/hm1-20261015` | `31d08141add7bf9a936e701d99f193455bf40ede` | integrated at `a429138`; closed after acceptance |
| #55 | HM2 | `codex/hm2-20261015` | `53ccf8577440d1b04e4da2403a6bbe9f30fa68e6` | integrated at `c80ddb8`; closed after acceptance |
| #56 | HM3 | `codex/hm3-20261015` | `0a877eb8dbb97e60fdf7e6309080019f06de69d2` | integrated at `b513c78`; closed after acceptance |
| #57 | HM4 | `codex/hm4-20261015` | `b513c78981159ac1fbfbd67c797ddfcf93ab5080` | integrated at `62e027f`; fixed-base dual-axis review clean; 107 related non-Tk and 2 true-Tk integration checks passed; closed after acceptance |
| #58 | HM5 | `codex/hm5-20261015` | `eda24aae7eac0197650ea7273b17870e7bc03e2d` | integrated at `2665485`; fixed-base standards/spec review clean; 90 related integration tests + 2 true-Tk checks passed; closed after acceptance |
| #59 | HM6 | `codex/hm6-20261015` | `c9b19934462acdda7cddd62012fc4b76b5b99fbc` | in progress; found/fixing clipped home controls and language-shifting profile fields; final matrix/regression pending |

## QP6 integration note

QP6 merge commit: `362c235dbae526dcf99189e78b38e85647d2de06`. The combined query/display/capacity/retention/language/monitoring regression passed 166 tests on the integration branch. The five true-Tk acceptance tests also passed on the integration branch in the interactive Aqua slot (13.552s); the initial non-escalated shell attempt aborted before test setup because it lacked desktop permission. The full final integration regression and dual-axis review remain mandatory before merging to `B518-Log-Solution` or closing parent #46/#47.
