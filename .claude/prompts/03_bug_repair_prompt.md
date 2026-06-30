# バグ修復用プロンプト

/jen-repair
Bug: <症状>
Expected: <期待動作>
Observed: <実際の動作>
Evidence: <ログ/スクショ/スタックトレース>

Rules:
- まず再現手順を固定する。
- 憶測修正しない。
- 根本原因を1〜3文で書く。
- 最小修正にする。
- 可能なら回帰テストを追加する。
- VerifierでACCEPT/REJECTを出す。
