# Claude Code Project Instructions: Jen v2

このプロジェクトでは Jen v2 PMO 運用を使う。

## 常時守ること

- 実装前に目的、非目的、受入条件を確認する。
- 大きな変更は `route` ではなく `conduct` でDAG化する。
- 自分で抱え込まず、適切な `jen-*` subagent に委譲する。
- 受入条件に紐づかない提案は `.jen/ideas.md` に送る。
- 不明点は `確定 / 未確認 / 仮定` に分ける。
- 本番deploy、DB破壊的変更、secret、認証/決済/権限、外部費用はHuman Gate。
- 完了宣言はVerifier ACCEPT後。

## 推奨状態ファイル

- `.jen/mission.md`
- `.jen/tasks.json`
- `.jen/assumptions.md`
- `.jen/decisions.md`
- `.jen/verification.md`
- `.jen/handoff.md`
