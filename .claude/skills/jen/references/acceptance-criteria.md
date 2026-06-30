# Acceptance Criteria

すべてのACは検証可能にする。

## Template

```yaml
- id: AC-001
  statement: ユーザーが何をできるか
  proof: 何を見れば満たしたと判断できるか
  verification: 実行コマンド、テスト、画面確認、レビュー観点
  risk: low
  owner: jen-verifier
  status: pending
```

## 良いAC

- 具体的な入力/出力がある。
- テストまたは画面確認で判定できる。
- 非機能要件も含む。
- Out of Scopeを明確にする。

## 悪いAC

- 「いい感じにする」
- 「バグがない」
- 「高速にする」だけで測定不能
