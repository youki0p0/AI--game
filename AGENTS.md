# Agent Instructions for This Repository

このリポジトリでは Jen v2 PMO 運用を標準にする。

## 基本ルール

- 目的、非目的、受入条件を確認してから実装する。
- 変更は小さく、検証可能な単位に分ける。
- 受入条件に紐づかない改善は実装せず、提案として記録する。
- 確定情報、未確認情報、仮定を分ける。
- 破壊的変更、DB migration、auth/payment/security、secret、deploy、外部費用は人間承認を要求する。
- 実装者と検証者を分ける。自分の変更を自分だけで完了扱いにしない。

## 推奨コマンド

- `/jen`: 通常のPMOオーケストレーション
- `/jen-longrun`: 長時間自走
- `/jen-repair`: バグ修復
- `/jen-review`: 検収
- `/jen-release`: PR/リリース準備

## Definition of Done

- Acceptance Criteria がすべてPASS。
- build/lint/typecheck/test の該当コマンドがPASS。
- 未確認事項がCriticalに残っていない。
- VerifierがACCEPT。
- 高リスク変更はStrict Verifierと人間確認を通す。
