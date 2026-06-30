# Claude Code 実行用プロンプト

Claude CodeでこのリポジトリにJen v2運用を適用してください。
まず .claude/ と .jen/ の状態を確認し、なければ作成してください。
次に Mission Brief、Acceptance Criteria、Task Ledger を作ってください。
その後、依存関係を見て route / conduct / repair / review / release のどれで進めるか決め、適切なsubagentへ委譲してください。
すべての実装は検証コマンドとVerifier判定まで通してください。
本番deploy、DB破壊的変更、secret、auth/payment/security、外部費用、公開API破壊はHuman Gateで止めてください。
