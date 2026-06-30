# Jen v2 Routing Policy

## 優先順位

1. Human Gateに該当するなら停止。
2. read-onlyで足りるならscout/research/reviewerを使う。
3. 通常実装はbuilder/frontend。
4. テストはtest。
5. 不明バグはdebugger。
6. 難設計はarchitect。
7. 完了候補はverifier。
8. 高リスクはstrict-verifier。

## 昇格

- scoutで不足 → research or builder
- builder失敗 → debugger or architect
- frontend失敗 → test/ux-critic/debugger
- test失敗 → debugger
- verifier REJECT 1回 → 該当担当へ差し戻し
- verifier REJECT 2回 → opus系へ昇格
- strict-verifier REJECT → Human Gateまたはarchitect

## 並列化してよい条件

- 依存がない。
- 同じファイルを触らない。
- 片方の出力がもう片方の仕様を変えない。
- 失敗しても安全に戻せる。

## 並列化しない条件

- 同じコンポーネント/型定義/APIを触る。
- DB schemaやauthに関係する。
- 仕様がまだ揺れている。
- テストが存在せず検証不能。
