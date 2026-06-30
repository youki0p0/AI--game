# Jen v2 設計書 — Claude Code PMO型オーケストレーター実装案

作成日: 2026-06-26  
対象: Claude Code / Claude subagents / Claude Code skills / GitHub / 個人開発リポジトリ  
前提: 既存の `jen-orchestrator-install.zip` を確認済み。v1のFugu型ルーティング思想は残し、PMO運用・長時間自走・品質ゲート・破壊防止・提案取り込みを強化する。

---

## 0. 結論

Jen v1の一番良いところは、「メインセッションが自分で全部やらず、ルーター/PMOに徹する」という思想です。これはかなり筋が良いです。AI開発が破綻する最大の原因は、1つの会話が調査・設計・実装・デバッグ・検収・雑談を全部抱え込み、コンテキストが汚れて“自分の作ったものを自分で甘く見る”ことだからです。

ただし、v1のままだと長時間自走で壊れやすいです。理由は明確で、PMOに必要な「台帳」「受入条件」「変更境界」「人間承認ゲート」「失敗時の再計画」「検証証跡」がまだ薄いからです。v2では、Jenを単なるルーターではなく、**Mission Control + Task Ledger + Quality Gate + Proposal Intake** を持つPMOにします。

最も推奨する構成は、最後に出す3案のうち **標準構成** です。軽量構成より自走性能と正確性が高く、重厚構成ほど壊れません。個人開発者が今日からGitHub/Claude Codeに入れて運用できる現実解です。

---

## 1. 現在のJen構想の評価

### 1.1 良い点

1. **ルーターがPMOに徹する思想が良い**  
   AIが全部を1文脈で抱え込むより、PMOが仕事を切り分け、専門エージェントへ渡し、検収する方が破綻しにくいです。v1の「ルーターは解かない」は強いルールです。

2. **scout / research / builder / frontend / test / architect / debugger / verifier の分担が自然**  
   個人開発でよく詰まる工程をほぼカバーしています。特に `debugger` と `verifier` を分けているのは良いです。修正者と検収者を分離するだけで、合格判定の甘さが減ります。

3. **route と conduct の2モードが良い**  
   単発タスクはroute、多段タスクはconductという分け方は正しいです。全部をDAGにすると重く、全部を単発ルーティングにすると長時間タスクが迷子になります。

4. **Verifier REJECT → 差し戻し/昇格の考えが良い**  
   AI開発では「一発で正解」より「失敗を検知して戻れる」ことが重要です。v1はここを押さえています。

5. **Claude Code Only という制約が実用的**  
   外部APIや独自サーバを前提にしないので、個人開発者が入れやすいです。設定ファイル、サブエージェント、スキル、hooksで完結させるのは現実的です。

### 1.2 危険な点

1. **“完了”の定義がまだ弱い**  
   VerifierがACCEPTするだけでは不十分です。何を満たせばACCEPTなのか、受入条件・テスト・実行ログ・未確認事項が明示されていないと、Verifierも雰囲気で合格を出します。

2. **長時間自走でスコープが膨らむ**  
   AIは「ついでに改善」を始めがちです。良い発想は必要ですが、実装範囲に勝手に入れると破綻します。提案は `Now / Later / Reject` に分け、Nowに入れる条件を厳しくする必要があります。

3. **DAG並列化はファイル衝突に弱い**  
   依存がないと思って並列化しても、同じファイル・同じ設定・同じ型定義を触ると衝突します。worktreeや担当ファイル範囲の宣言が必要です。

4. **モデル昇格だけでは正確性は上がり切らない**  
   haiku→sonnet→opusの昇格は有効ですが、品質はモデルだけでなく、証拠・テスト・受入条件・ソースの鮮度で決まります。

5. **read-onlyとBashの関係が曖昧**  
   VerifierやtestがBashを使うと、コマンド次第でファイルが変わります。hooksで危険コマンドを止める、検証コマンドを限定する、実行前後でdiffを見る、という運用が必要です。

### 1.3 実運用で破綻しやすい点

- 調査結果がログ化されず、後続エージェントが同じ探索を繰り返す。
- 仕様不明時に勝手な決め打ちが入る。
- Verifierが「テストを走らせた」だけで、受入条件を見ない。
- UI改善でデザイン崩れを検知できない。
- 長時間作業中に最初のゴールを忘れ、局所最適に走る。
- 失敗時に同じ修正を繰り返す。
- 破壊的操作、DB変更、環境変数、デプロイ、課金設定をAIが勝手に触る。
- “良い提案”が仕様変更として混入し、ユーザーの意図を壊す。

### 1.4 PMOとして足りない点

PMOに必要なのは「誰に振るか」だけではありません。以下が足りません。

- Mission Brief: 目的、非目的、制約、完成条件。
- Acceptance Criteria: 検収可能な条件。
- Task Ledger: タスクID、状態、担当、依存、証跡。
- Decision Log: なぜその設計にしたか。
- Assumption Log: 未確認だが仮置きしたこと。
- Risk Register: 破壊的変更、セキュリティ、互換性、コスト。
- Change Boundary: 触ってよいファイル/触ってはいけないファイル。
- Quality Gate: build/lint/typecheck/test/e2e/security/review。
- Human Gate: 人間が決めるべき点。
- Handoff: 中断・再開用の要約。

### 1.5 AIエージェント設計として足りない点

- エージェント間の出力形式が統一されていない。
- 「確定」「推測」「未確認」の分離が弱い。
- 提案エージェントの出力を実装へ取り込むルールがない。
- self-repairの最大回数、昇格条件、停止条件が弱い。
- verifierが証拠を要求する仕組みが弱い。
- 長時間ループでのコンテキスト圧縮/再開用メモリ設計が弱い。
- file isolation / worktree / branch policy が薄い。

---

## 2. より良い全体アーキテクチャ

### 2.1 基本方針

Jen v2は、以下の5層に分けます。

1. **User / President**  
   ゴール、優先順位、人間承認が必要な判断を出す。

2. **Jen PMO / Mission Control**  
   ゴールを受入条件に変換し、タスク台帳を作り、専門エージェントを起動し、品質ゲートを管理する。

3. **Specialists**  
   scout / research / product / UX / builder / frontend / test / architect / debugger / security / monetization / release。

4. **Verifier Layer**  
   通常Verifier、厳格Verifier、必要に応じてsecurity/UX/contrarianを検収に参加させる。

5. **Repository Control Plane**  
   `.jen/` 状態ファイル、`.claude/` 設定、hooks、Git branch/worktree、CI、PR。

Jen v1のFugu型ルーティングを、v2ではPMO運用へ拡張します。Fuguの「小さなポリシーが複数モデルへ振る」発想は残します。ただし、個人開発では学習済みヘッドより、透明なルール・ログ・テスト・受入条件の方が重要です。

### 2.2 Claude Code / subagents の役割分担

| レイヤー | 担当 | 推奨モデル | 理由 |
|---|---|---:|---|
| Jen PMO | 目的維持、分解、台帳、差し戻し | Sonnet high / 重い時 Opus | ルーティングと判断が主。毎回Opusだと高い |
| scout | ローカル探索 | Haiku | 速く安く、read-only向き |
| research | 公式ドキュメント調査 | Sonnet | 古い情報・API差分の読み分けが必要 |
| product-strategist | 価値・仕様改善 | Sonnet | 発想と実装現実性のバランス |
| ideation | 改善案の発散 | Sonnet/Haiku | 広く出す。採用は別ゲート |
| UX critic | UI/UXレビュー | Sonnet | ユーザー体験と実装妥当性 |
| builder | 一般実装 | Sonnet | 主力。安定と速度 |
| frontend | UI実装 | Sonnet | 既存規約に合わせる |
| test | テスト設計・実行 | Sonnet | 仕様をテストへ写像する必要あり |
| architect | 難設計・境界・性能 | Opus | 高難度判断 |
| debugger | 原因不明バグ | Opus | 仮説検証と切り分けが重い |
| verifier | 通常検収 | Sonnet | v1のHaikuより厳しめにする |
| strict-verifier | 高リスク検収 | Opus | auth/payment/security/DB/破壊的変更 |
| release-manager | PR/リリース準備 | Sonnet | 証跡整理と手順化 |

### 2.3 どれをPMOにするべきか

PMOは **Jen PMO** だけです。architectをPMOにしない方が良いです。architectは設計を深掘りしすぎる傾向があるため、スコープ管理と進行管理には向きません。PMOは「いつ深掘りを止めるか」を決める役です。

### 2.4 どれを実装担当にするべきか

- 通常実装: `jen-builder`
- UI/フロント: `jen-frontend`
- テスト追加: `jen-test`
- 設計込みの難所: `jen-architect`
- 原因不明の修正: `jen-debugger`

### 2.5 どれを調査担当にするべきか

- リポジトリ内調査: `jen-scout`
- 外部/公式ドキュメント調査: `jen-research`
- プロダクト/市場/競合の方向性: `jen-product-strategist`

### 2.6 どれを検収担当にするべきか

- 通常: `jen-verifier`
- 高リスク: `jen-strict-verifier`
- UI: `jen-ux-critic` → `jen-verifier`
- Security: `jen-security-reviewer` → `jen-strict-verifier`
- Release: `jen-release-manager` → `jen-verifier`

### 2.7 どれを長時間自走用にするべきか

長時間自走は「1エージェントに頑張らせる」のではなく、Jen PMOが一定サイクルで以下を回す設計にします。

1. Mission確認
2. Task Ledger更新
3. 1〜3個の小さなタスク選定
4. 実装担当へ委譲
5. テスト/検証
6. 失敗ならrepair
7. 成功ならcheckpoint
8. 次タスクへ

長時間用の中心は `jen-longrun` skill + `jen-pmo` です。実装はbuilder/frontend/test/debuggerへ渡します。

### 2.8 人間の承認ゲート

AIに任せるべきこと:

- 既存コード調査
- 仕様を受入条件に分解
- 小〜中規模実装
- テスト追加
- バグ再現と修正案
- リファクタ案の提示
- PR本文作成
- ログ/証跡整理
- 改善案の提案と優先度付け

人間が決めるべきこと:

- プロダクトの優先順位
- 仕様変更の採用
- 課金/価格/法務/利用規約
- 本番デプロイ
- DB破壊的マイグレーション
- 認証/権限/決済の仕様変更
- 外部サービス契約や費用発生
- 秘密情報の投入
- 大規模リファクタや公開API破壊

---

## 3. Jen v2 の設計

### 3.1 Jen v2の役割定義

Jen v2は「PMO型オーケストレーター」です。主な責務は以下です。

- ユーザーのゴールをMission Briefに変換する。
- 受入条件を明文化する。
- タスクをDAGまたは小さなBacklogに分解する。
- 適切な専門エージェントへ委譲する。
- 進捗、判断、仮置き、失敗、検証結果を台帳へ残す。
- VerifierのREJECTをもとに差し戻し・昇格・再計画する。
- 良い改善案を出すが、勝手に仕様を変えない。
- 人間承認が必要なものを止める。

### 3.2 エージェント一覧

標準構成のエージェントは以下です。

| agent | model | 権限 | 責務 |
|---|---|---|---|
| jen-pmo | sonnet | read/write/agent | PMO、計画、台帳、委譲、検収判断 |
| jen-scout | haiku | read-only | ローカル探索、ファイル特定 |
| jen-research | sonnet | read-only/web | 一次情報調査 |
| jen-product-strategist | sonnet | read-only | 価値・仕様改善 |
| jen-ideation | sonnet | read-only | 発想出し |
| jen-ux-critic | sonnet | read-only | UX改善・UI検収 |
| jen-contrarian-reviewer | sonnet | read-only | 反対意見・破綻予測 |
| jen-security-reviewer | sonnet | read-only/bash | セキュリティレビュー |
| jen-monetization-reviewer | sonnet | read-only | 収益化・価格・導線レビュー |
| jen-builder | sonnet | write/bash | 一般実装 |
| jen-frontend | sonnet | write/bash | UI/フロント実装 |
| jen-test | sonnet | write/bash | テスト追加・実行 |
| jen-architect | opus | write/bash | 難設計・重要判断 |
| jen-debugger | opus | write/bash | 原因不明バグ修復 |
| jen-verifier | sonnet | read/bash | 通常検収 |
| jen-strict-verifier | opus | read/bash | 高リスク検収 |
| jen-release-manager | sonnet | write/bash | PR/リリース準備 |

### 3.3 モデルの考え方

- **Haiku**: 探索、要約、軽い分類。安いが最終判断は任せない。
- **Sonnet**: 標準実装、調査、テスト、通常検収。個人開発の主力。
- **Opus**: 高難度設計、原因不明バグ、厳格検収。乱用しない。
- **Fable**: 使える環境ならドキュメント、リリースノート、UX文言の磨きに向く。ただしコア検証には使わない。

### 3.4 モード設計

#### route
小さな依頼を1〜5ターンで処理する。PMOが毎ターン担当を選ぶ。例: 「このバグ直して」「このコンポーネント作って」。

#### conduct
中〜大規模タスクをDAGにする。依存のないタスクだけ並列化する。ファイル衝突がありそうなら並列にしない。

#### repair
テスト失敗・ビルド失敗・Verifier REJECTから入る。再現→原因→最小修正→回帰テスト→検証の順。

#### review
実装前またはPR前のレビュー。product / UX / security / contrarian / monetization の観点を必要な分だけ呼ぶ。

#### release
PR作成、差分要約、チェック結果、残リスク、人間確認項目を整理する。デプロイは人間承認が必要。

#### longrun
長時間自走。小さなサイクルでMission→Task→Implement→Verify→Checkpointを繰り返す。

### 3.5 escalation policy

- scoutで不明 → researchへ。
- builderで設計判断が必要 → architectへ。
- builder/frontend/testで2回失敗 → debuggerへ。
- verifierが2回REJECT → architectまたはdebuggerへ昇格。
- security/auth/payment/DB/permission → strict-verifier必須。
- 仕様不明で戻れない判断 → human gate。
- 破壊的変更・外部費用・デプロイ → human gate。

### 3.6 acceptance criteria

すべてのタスクは以下を持ちます。

```yaml
id: AC-001
statement: ユーザーが何をできるようになるか
proof: 何を見れば満たしたと判断できるか
verification: 実行するコマンド、画面確認、またはレビュー観点
risk: low | medium | high
owner: verifier | strict-verifier | ux-critic | security-reviewer
status: pending | pass | fail
```

### 3.7 quality gate

標準ゲート:

1. scope gate: 目的と非目的が明確か。
2. source gate: 外部情報は一次情報か。
3. build gate: buildが通るか。
4. lint gate: lint/formatが通るか。
5. type gate: typecheckが通るか。
6. test gate: unit/integration/e2eが通るか。
7. security gate: auth/payment/secret/input validationに穴がないか。
8. UX gate: UI要件とアクセシビリティ基本を満たすか。
9. verifier gate: 受入条件ベースでACCEPTか。
10. release gate: PR本文、リスク、ロールバックがあるか。

### 3.8 failure recovery

失敗時は、以下の順で処理します。

1. 失敗を分類: test / build / type / lint / runtime / spec / environment / unknown
2. 再現手順を固定
3. 直近diffを確認
4. 最小修正を試す
5. 同じ修正を繰り返さないようFailure Ledgerに記録
6. 2回失敗でdebugger、3回失敗でarchitect/strict-verifierへ
7. 仕様不明ならAssumption Logへ仮置き、またはHuman Gateで停止

### 3.9 memory / log / handoff

`.jen/` は実行時の作業台帳、`.claude/memory/` はプロジェクトに残すテンプレートです。

推奨:

- `.jen/mission.md`: 現在のゴール、受入条件、非目的。
- `.jen/tasks.json`: タスクID、状態、担当、依存。
- `.jen/assumptions.md`: 仮決め。
- `.jen/decisions.md`: 設計判断。
- `.jen/verification.md`: 検証証跡。
- `.jen/ideas.md`: 今はやらない改善案。
- `.jen/handoff.md`: 中断・再開用まとめ。
- `.jen/logs/*.jsonl`: hookによる機械ログ。

---

## 4. 長時間自走の設計

### 4.1 途中で迷走しない方法

- Mission Briefを最初に作る。
- すべてのタスクを受入条件に紐づける。
- 受入条件に紐づかない作業は `ideas-backlog` に送る。
- 1サイクルの変更範囲を小さくする。
- 20〜40分相当の単位ではなく、**1つの検証可能な差分**単位で進める。
- 各サイクル後に `git diff --stat` と検証結果を見る。

### 4.2 ゴールを維持する方法

毎サイクルでJen PMOは以下を確認します。

```text
このタスクはどの受入条件を進めるか？
この変更はMissionの非目的に触れていないか？
いま止まるべきHuman Gateはあるか？
検証可能な終了点は何か？
```

### 4.3 作業ログを残す方法

- hookでtool使用ログを `.jen/logs/` に保存。
- PMOがサイクルごとに `.jen/handoff.md` を更新。
- 重要判断は `.jen/decisions.md` に1〜3文で残す。
- 未確認事項は `.jen/assumptions.md` に残す。

### 4.4 中断・再開する方法

再開時は以下だけ読めばよい状態にします。

1. `.jen/mission.md`
2. `.jen/tasks.json`
3. `.jen/handoff.md`
4. `.jen/verification.md`
5. `git status` と `git diff --stat`

再開プロンプトでは「まず上記を読み、完了済みタスクを繰り返さない」と指示します。

### 4.5 テスト失敗時の自己修復

1. `jen-test` が失敗内容を分類。
2. 再現コマンドを固定。
3. `jen-debugger` が原因を特定。
4. `jen-builder` または `jen-debugger` が最小修正。
5. `jen-test` が回帰テストを追加。
6. `jen-verifier` が受入条件で検収。

最大3ループ。同じ失敗が続く場合は停止し、再現手順と仮説をhandoffに残します。

### 4.6 仕様不明時の仮決めルール

仮決めしてよい条件:

- 既存UI/既存コードのパターンから明らか。
- 後で戻せる。
- セキュリティ/課金/DB/公開APIに影響しない。
- 受入条件の本質を変えない。

仮決めしたら必ず記録します。

```md
- YYYY-MM-DD: [ASSUMPTION] xxx は既存 yyy に合わせて zzz と仮定。理由: ...。戻し方: ...。
```

### 4.7 破壊的変更を防ぐ方法

- default branchで直接作業しない。
- worktreeまたはfeature branchを使う。
- `pre_tool_guard.py` で `rm -rf`, `git reset --hard`, force push, deploy, publish などをブロック。
- DB migration、auth、payment、secrets、env、deployはHuman Gate。
- 1タスク1コミットまたは1チェックポイント。

### 4.8 完成条件を満たすまで進める方法

Definition of Done:

- 全ACがpass。
- build/lint/typecheck/testが必要範囲でpass。
- 未確認事項がCriticalに残っていない。
- verifierがACCEPT。
- 高リスクならstrict-verifierがACCEPT。
- PR本文に変更点・検証・残リスク・ロールバックがある。

---

## 5. 正確性を上げる仕組み

### 5.1 verifierの改善

v1のverifierはHaiku read-onlyでした。v2では通常VerifierをSonnetに上げ、重要タスクだけOpus strict-verifierにします。

Verifierは以下を必ず出します。

```md
判定: ACCEPT | REJECT
対象AC: AC-001, AC-002
確認した証拠:
- コマンド: ... 結果: pass/fail
- ファイル: ...
未確認:
- ...
REJECT理由:
- ...
次に戻すべき担当:
- builder | frontend | test | debugger | architect | human
```

### 5.2 test agentの改善

`jen-test` は「テストを走らせる人」ではなく「受入条件を検証可能にする人」です。

- 受入条件ごとにテストケースを対応付ける。
- 正常系、境界値、異常系、回帰、状態遷移を見る。
- テスト不能な要件は理由を出す。
- 失敗時はproduction bug / test bug / env issueに分類。

### 5.3 build / lint / typecheck / unit / e2e の組み込み

`jen_quality_gate.sh` が以下を自動検出します。

- `package.json` の `lint`, `typecheck`, `test`, `build`
- `pyproject.toml` / `pytest`
- `go test ./...`
- `cargo test`
- `git diff --check`

実リポジトリのCIに合わせて編集してください。重要なのは、Verifierが「走らせたコマンド」と「結果」を証拠として持つことです。

### 5.4 Web調査時の一次情報優先ルール

外部仕様は以下の順で扱います。

1. 公式ドキュメント
2. 公式GitHub / release notes / changelog
3. 仕様書 / RFC / 標準文書
4. ライブラリのソースコード
5. 信頼できる技術ブログ
6. Q&A / 個人ブログ / 古い記事

実装前に、対象ライブラリのバージョンを `package.json` / lockfile / pyproject / READMEから確認します。バージョン不明なら「未確認」として扱います。

### 5.5 古い情報・幻覚・推測の防止

- “確定”と“未確認”を分ける。
- 外部APIは公式ソースで確認するまで実装しない。
- 公式情報とブログが矛盾したら公式優先。
- コードで確認できることはコード/型/テストで確認する。
- 推測で実装した場合はAssumption Logへ。

### 5.6 受入条件ベースの検収

Verifierは「良さそう」ではなく、ACごとにPASS/FAILを出します。

```md
| AC | 判定 | 根拠 | 未確認 |
|---|---|---|---|
| AC-001 | PASS | unit test x passed | なし |
| AC-002 | FAIL | モバイル幅の確認なし | screenshot/e2e未実行 |
```

### 5.7 人間レビューが必要なポイント

- DB migration
- 認証/認可
- 決済/課金
- セキュリティ境界
- PII/個人情報
- 本番デプロイ
- 利用規約/法務/価格
- 外部サービス契約
- 大規模リファクタ
- 公開API破壊

---

## 6. ユーザーが思いつかなかった良い発想を出す仕組み

### 6.1 発想を出すが、勝手に混ぜない

Jen v2では提案を3分類します。

- **Implement Now**: 受入条件に直結し、低リスクで、既存仕様を壊さない。
- **Propose to Human**: 価値はあるが、仕様・UX・収益・リスクに影響する。
- **Later Backlog**: 良いが今やるとスコープが膨らむ。

### 6.2 ideation agent

`jen-ideation` は広く案を出します。ただし実装しません。

出力:

```md
| idea | impact | effort | risk | confidence | bucket |
|---|---:|---:|---:|---:|---|
```

### 6.3 product strategist

価値、利用頻度、差別化、MVPとしての筋を見ます。機能を増やすだけでなく「削る案」も出します。

### 6.4 UX critic

ユーザーが迷う点、空状態、エラー文言、アクセシビリティ、レスポンシブ、初回体験を見ます。

### 6.5 contrarian reviewer

「この案が失敗するとしたらなぜか」を出します。AIの楽観バイアス対策です。

### 6.6 security reviewer

入力検証、認可、secret露出、依存関係、XSS/CSRF/SSRF、ログへのPII混入を見ます。

### 6.7 monetization reviewer

個人開発で重要な「無料で作ったが収益導線がない」を避けます。ただし価格や課金実装はHuman Gateです。

### 6.8 良い発想だけ取り込む方法

1. ideation/product/UX/contrarian/security/monetizationが提案。
2. Jen PMOが `Now / Human / Later / Reject` に分類。
3. Nowだけ受入条件へ追加。
4. Humanは確認待ち。
5. Laterは `.jen/ideas.md` へ。
6. 実装後、Verifierが「元の仕様を壊していないか」を確認。

---

## 7. 実装可能なファイル構成

同梱ZIPでは以下の構成を用意しています。

```text
.claude/
  CLAUDE.md
  settings.jen.example.json
  agents/
    jen-pmo.md
    jen-scout.md
    jen-research.md
    jen-product-strategist.md
    jen-ideation.md
    jen-ux-critic.md
    jen-contrarian-reviewer.md
    jen-security-reviewer.md
    jen-monetization-reviewer.md
    jen-builder.md
    jen-frontend.md
    jen-test.md
    jen-architect.md
    jen-debugger.md
    jen-verifier.md
    jen-strict-verifier.md
    jen-release-manager.md
  skills/
    jen/SKILL.md
    jen/references/*.md
    jen/scripts/*.sh|*.py
    jen-longrun/SKILL.md
    jen-repair/SKILL.md
    jen-review/SKILL.md
    jen-release/SKILL.md
  commands/
    jen-status.md
    jen-standup.md
    jen-pr.md
  hooks/
    pre_tool_guard.py
    post_tool_log.py
    stop_append_summary.py
  memory/
    project-context.md
    decisions.md
    assumptions.md
    ideas-backlog.md
    verification-ledger.md
  reports/templates/
    execution-report.md
    verification-report.md
    handoff.md
    pr-summary.md
  prompts/
    01_jen_system_prompt.md
    02_longrun_prompt.md
    03_bug_repair_prompt.md
    04_new_feature_prompt.md
    05_ui_improvement_prompt.md
    06_acceptance_prompt.md
    07_claude_code_execution_prompt.md
.github/workflows/jen-ci.yml
AGENTS.md
README-JEN-V2.md
.gitignore.jen-snippet
```

---

## 8. すぐ使えるプロンプト群

同梱ZIPの `.claude/prompts/` にコピペ可能な形で入れています。ここにも要点を載せます。

### 8.1 Jen v2 System Prompt / Skill Prompt

```text
あなたは Jen v2。AI開発PMOとして、ユーザーのゴールをMission Brief、Acceptance Criteria、Task Ledgerへ変換し、専門subagentへ委譲する。自分で全実装を抱え込まない。すべての変更は受入条件に紐づける。提案は出すが、仕様を勝手に壊さない。破壊的変更、DB、認証、決済、secret、本番deploy、外部費用はHuman Gateで止める。完了はVerifier ACCEPTまで言わない。確定・未確認・仮定を分け、検証証跡を残す。
```

### 8.2 長時間自走用プロンプト

```text
/jen-longrun
Goal: <達成したい成果>
Constraints:
- 人間の承認なしに本番deploy、DB破壊的変更、secret変更、課金設定、外部サービス契約をしない。
- 受入条件に紐づかない改善は .jen/ideas.md に送る。
- 仕様不明は低リスクで可逆な仮定のみ許可し .jen/assumptions.md に記録する。
- 各サイクルで build/lint/typecheck/test のうち該当するものを実行する。
- Verifier ACCEPTまで完了扱いにしない。
Run:
1. Mission BriefとAcceptance Criteriaを作る。
2. Task Ledgerを作る。
3. 小さなタスクを順に実装する。
4. 失敗時はrepairへ。
5. 各サイクル末にhandoffを更新する。
```

### 8.3 バグ修復用プロンプト

```text
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
```

### 8.4 新機能実装用プロンプト

```text
/jen conduct
Feature Goal: <機能ゴール>
User Value: <誰が何をできるようになるか>
Must Have:
- ...
Out of Scope:
- ...
Acceptance Criteria:
- ...
Quality:
- build/lint/typecheck/testを通す
- 未確認事項を分ける
```

### 8.5 UI改善用プロンプト

```text
/jen conduct
UI Goal: <改善したい画面/体験>
Target files or route: <対象>
Design constraints:
- 既存デザイントークンに合わせる
- レスポンシブ
- keyboard/a11y基本
- 空状態/エラー状態を考慮
Verification:
- screenshot/e2e/manual確認のどれで検収するか示す
```

### 8.6 検収用プロンプト

```text
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
```

### 8.7 Claude Codeに実行させる用プロンプト

```text
Claude CodeでこのリポジトリにJen v2運用を適用してください。
まず .claude/ と .jen/ の状態を確認し、なければ作成してください。
次に Mission Brief、Acceptance Criteria、Task Ledger を作ってください。
その後、依存関係を見て route / conduct / repair / review / release のどれで進めるか決め、適切なsubagentへ委譲してください。
すべての実装は検証コマンドとVerifier判定まで通してください。
```

---

## 9. 運用フロー

### 初回セットアップ

1. ZIPを解凍し、リポジトリ直下へ `.claude/`, `AGENTS.md`, `.github/` を置く。
2. `.gitignore.jen-snippet` の内容を `.gitignore` に追記する。
3. `.claude/settings.jen.example.json` を読み、必要なら `.claude/settings.json` へコピーする。
4. hookスクリプトを必ず目視確認してからworkspace trustする。
5. Claude Codeを起動し、`/agents` でエージェントが見えるか確認する。
6. `/jen` または `/jen-longrun` を実行する。

### 実際の開発フロー

1. **ChatGPT Proで仕様と設計を深掘り**  
   目的、ユーザー、制約、成功条件、非目的を整理する。

2. **Deep Researchで技術調査**  
   外部ライブラリ、競合、技術選定、API仕様などを一次情報ベースで調べる。

3. **Codexで実装タスク化/別解比較**  
   大きな設計をIssue/PR単位へ切り分けたり、Claude Codeで詰まった箇所の別案を出す。

4. **Claude Code / Jenでリポジトリ内作業**  
   `/jen conduct` でDAG化し、scout/research/builder/frontend/test/debuggerへ振る。

5. **test / verifierで検収**  
   build/lint/typecheck/test/e2eの該当分を実行し、AC別に検収する。

6. **GitHub PR**  
   `jen-release-manager` がPR本文、検証ログ、残リスク、ロールバックを書き出す。

7. **人間確認**  
   UI、仕様変更、セキュリティ、価格、デプロイ可否を確認する。

8. **Vercel Deploy等**  
   デプロイはAIが勝手に実行しない。人間承認後に実施し、結果確認だけJenに手伝わせる。

---

## 10. 最終提案: 3案比較

| 構成 | 実装難易度 | 自走性能 | 正確性 | コスト | 破綻しにくさ | 発想力 |
|---|---:|---:|---:|---:|---:|---:|
| 軽量構成 | 低 | 中 | 中 | 低 | 高 | 中 |
| 標準構成 | 中 | 高 | 高 | 中 | 高 | 高 |
| 重厚構成 | 高 | 最高 | 最高 | 高 | 中 | 最高 |

### 軽量構成

エージェント: pmo / scout / builder / test / debugger / verifier。  
hooks: pre_tool_guard とログだけ。  
用途: 今すぐ壊れにくく使いたい場合。

### 標準構成

エージェント: 本ZIPの標準17体。  
skills: jen / jen-longrun / jen-repair / jen-review / jen-release。  
hooks: guard/log/summary。  
memory: mission/tasks/assumptions/verification/handoff。  
用途: 個人開発の本命。

### 重厚構成

標準構成に加え、agent teams、worktree並列、CI必須、strict-verifier常用、Deep Research/Codex/GitHub Issue連携を使う。  
用途: 大きな機能、複数ファイル群、長時間自走、並列レビュー。

### 最も推奨

**標準構成** を推奨します。

理由は、個人開発で本当に必要な「自走」「正確性」「発想」「破綻しにくさ」のバランスが最も良いからです。重厚構成は魅力的ですが、agent teamsや強い並列化は調整コストが高く、ファイル衝突や判断の分散で逆に壊れることがあります。軽量構成は始めやすいですが、長時間自走や良い発想の取り込みが弱いです。

まず標準構成で運用し、以下の条件を満たしたときだけ重厚構成へ拡張してください。

- タスクが明確に独立した複数領域に分かれる。
- テスト/CIが整っている。
- worktree運用に慣れている。
- AIの作業ログを人間がレビューする時間を取れる。
- コスト増を許容できる。

---

## 同梱ファイルの使い方

- `jen-v2-claude-code-pack.zip`: リポジトリ直下に展開する実装パック。
- `jen-v2-architecture-report.md`: この設計書。
- `.claude/prompts/`: コピペ用プロンプト集。
- `.claude/skills/jen/`: Jen v2本体。
- `.claude/agents/`: subagent定義。
- `.claude/hooks/`: 破壊的操作防止とログ。
- `.github/workflows/jen-ci.yml`: 汎用CI雛形。
