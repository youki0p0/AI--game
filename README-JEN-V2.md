# Jen v2 Claude Code Pack

Jen v2 は、Claude Code 内で動かすPMO型AI開発オーケストレーターです。
ユーザーはゴールだけを出し、Jenが Mission Brief / Acceptance Criteria / Task Ledger を作り、専門subagentへ委譲し、検証・差し戻し・リリース準備まで進めます。

## 入れるもの

- `.claude/agents/`: 専門subagent定義
- `.claude/skills/jen/`: Jen本体スキル
- `.claude/skills/jen-longrun/`: 長時間自走用スキル
- `.claude/skills/jen-repair/`: バグ修復用スキル
- `.claude/skills/jen-review/`: 検収・レビュー用スキル
- `.claude/skills/jen-release/`: PR/リリース準備用スキル
- `.claude/hooks/`: 破壊的操作防止とログ
- `.claude/memory/`: 台帳テンプレート
- `.claude/prompts/`: コピペ用プロンプト
- `.github/workflows/jen-ci.yml`: 汎用CI例
- `AGENTS.md`: Codex/GitHub系agentにも読ませる共通指示

## 初回セットアップ

1. このZIPをリポジトリ直下で展開する。
2. `.gitignore.jen-snippet` の内容を `.gitignore` に追記する。
3. `.claude/settings.jen.example.json` を確認し、使う場合は `.claude/settings.json` にコピーする。
4. `.claude/hooks/*.py` と `.claude/skills/jen/scripts/*` を目視確認する。
5. Claude Codeを起動し、`/agents` で `jen-*` agents が見えるか確認する。
6. `/jen` または `/jen-longrun` を実行する。

## 最初の実行例

```text
/jen conduct
Goal: サインアップ後のオンボーディング画面を改善し、初回ユーザーが3分以内に主要機能へ到達できるようにする。
Must Have:
- 既存デザイントークンに合わせる
- モバイル対応
- 既存テストを壊さない
Out of Scope:
- 課金導線の変更
- DB schema変更
Acceptance Criteria:
- 初回画面に次アクションが表示される
- 空状態とエラー状態がある
- lint/typecheck/testが通る
```

## 長時間自走例

```text
/jen-longrun
Goal: 管理画面のユーザー一覧に検索・フィルタ・ページングを追加し、テストとPR準備まで進める。
Constraints:
- DB migrationなし
- 本番deployなし
- 仕様不明は既存UIに合わせて仮決めし .jen/assumptions.md に記録
- Verifier ACCEPTまで完了扱いにしない
```

## 注意

- 本番deploy、DB破壊的変更、secret変更、課金設定、外部サービス契約はHuman Gateです。
- hooksは安全寄りですが、リポジトリに合わせて必ず確認してください。
- `.jen/` は実行ログ・台帳用です。通常はGit管理しません。
