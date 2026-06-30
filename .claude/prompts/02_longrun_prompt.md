# 長時間自走用プロンプト

/jen-longrun
Goal: <ここに達成したい成果を書く>
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
