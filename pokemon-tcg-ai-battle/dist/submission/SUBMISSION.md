# 提出パッケージ（PTCG AI Battle / Kaggle）

作成: 2026-07-01 ／ ブランチ: claude/kagura-makina-image-gen-rm1hd0

## ★ 提出ファイル（1モデル選択）: `dist/submission.py`
Kaggle「Submit to Competition → File Upload」に **ドラッグ&ドロップ**する単一 .py。

### Kaggle が要求する形式（アップロード画面より）
> Your submission should be a python file with **the last 'def' accepting an observation
> and returning an action.** You can also upload multiple files in a zip/gz/7z archive
> with a `main.py` at the top level.（受理: `.py` / `.zip` / `.gz` / `.7z`）

適合状況（`dist/submission.py`）:
- ✅ **ファイル末尾の `def` が `agent(observation, configuration=None) -> list[int]`**（＝Kaggleが呼ぶエントリ）
- ✅ observation を受け取り action（option インデックス配列 / デッキ選択時は60枚cardId）を返す
- ✅ 依存は `cg.api`（エンジン提供）のみ・デッキ埋め込み・外部成果物不要
- ✅ end-to-end 実対戦で動作確認済み

## 選択したモデル: meta_search（アーキタイプ検知型 探索）
理由: 現環境が Archaludon（ブリジュラス）主体という前提で、実測が最も強い。
相手盤面から buddy/Crustle/Archaludon を判定 → 該当既知デッキを仮定して `search_begin`
1手読み探索 → 未知/失敗は軽量ヒューリスティックにフォールバック。

### 実測（自作ガントレット・先後入替、CrustleはN=120）
| 相手 | 勝率 |
|---|---|
| Buddy（メガルカリオ）| 0.725 |
| Archaludon（現環境）| 0.525 |
| Fire | 0.500 |
| Crustle（イワパレス）| 0.375 [0.288,0.462] |
| Psychic（未検知→フォールバック）| 0.275 |
| **総合** | **0.480** |

速度: 検知時 ~1.15s/game（1手読み）、未検知 ~0.04s/game。

## 残リスク・限界
- **Crustle は 0.375 が上限**（回復壁は構造的天敵。「0.56」は高分散ノイズ、真値0.375）。
- **未検知の相手ではフォールバックが弱め**（psychic 0.275）。ラダー主流が環境デッキ前提で最適。
  非メタが多いと安定枠 `fire_single`（総合0.383/vs Buddy0.667）の方が堅い場面あり。
- 探索は 1手読み（速度と強さのトレードオフ）。

## 代替（安定枠・必要なら別提出に）
`fire_single/main.py`（`fire_single.tar.gz`）: 純ヒューリスティックで未知相手にも挙動が安定。
1日5提出可・最新2提出が集計対象なので、meta_search と併用も可能。

## Human Gate
実提出（アップロード）は人間の操作事項。`dist/submission.py` を Kaggle にアップロードすれば提出完了。
