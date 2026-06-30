# 検収用プロンプト

/jen-review
Review Target: <差分/PR/機能>
Acceptance Criteria:
- AC-001 ...
Run verification:
- git diff --check
- lint/typecheck/test/build if available
Output:
- ACCEPT/REJECT
- AC別判定
- 実行コマンドと結果
- 未確認
- 次の担当
