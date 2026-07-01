# 提出パッケージ（PTCG AI Battle / Kaggle）

更新: 2026-07-01（Archaludon ex + **1手読み探索パイロット** へ差し替え）

## ★ 提出ファイル: `dist/submission.py`（= Archaludon ex / 鋼 ＋ 探索パイロット）
Kaggle「File Upload」に**ドラッグ&ドロップ**する単一 .py（= `submissions/archaludon_search_agent.py`）。

### Kaggle 形式適合
- ✅ 末尾の唯一の最終 def = `agent(observation, configuration=None)`
- ✅ **全例外を握り、空アクションで自滅しない**（探索失敗時も安全手にフォールバック）。370戦で例外0。
- ✅ `cg.api` のみ依存・デッキ埋め込み・相手デッキ非依存・end-to-end動作確認済み

### なぜこのデッキか（実メタ適合）
現 PTCG-AI ラダーの**最頻アーキタイプ**（上位10データで使用7＝最多タイ）。1進化
（Duraludon 169 → Archaludon ex 190）＋ Full Metal Lab / 鋼エネ厚めで攻撃到達が安定。

### 操縦（pilot）＝ 1手読み探索 ★今回の改良点
各決定で **全ての合法オプション** をエンジンの探索サンドボックス
(search_begin/search_step)へ適用し、結果盤面を静的評価 state_eval
（サイド差>>マテリアル>脅威>資源, 将棋流）で採点して最善手を選ぶ。
固定スコアの simple_bot から置き換え。相手手は 1ターン打ち切りで自盤面主体に評価するため
相手デッキ未知でも頑健（隠れ情報は自デッキ ARCH_DECK から再構成、発火率100%）。

### 実測（同一相手＝simple_bot操縦の実メタ, 先後入替）
**パイロット比較（N=50/相手・計250戦）: 探索 0.752 [0.698,0.806] > simple_bot 0.656 [0.597,0.715]（+0.10）**

| 相手 | simple_bot | **探索(採用)** |
|---|---|---|
| Grimmsnarl（悪）| 0.58 | **0.72** |
| Alakazam（超）| 0.46 | **0.70** |
| MegaStarmie（水）| 0.48 | **0.58** |
| Dragapult（竜）| 0.92 | 0.92 |
| Buddy | 0.84 | 0.84 |

→ **接戦マッチ（3柱）が全て改善**。楽勝マッチ（Dragapult/Buddy）は据え置き。
提出ファイル直接検証（N=40/相手・計120戦）でも **OVERALL 0.683・例外0** を再現。

### 残リスク
- 探索は per-option でエンジン模擬を行うが、1ターン打ち切り＋ロールアウト上限25で**1手の計算量は有界**。1戦<1sで完了、Kaggleの手番遅延は問題なし。
- Archaludon は**炎弱点**（Cinderace 666 差しで一部緩和）。
- 相手デッキ未知のため相手手番のロールアウトは近似。1手読み（自ターン主体）で影響を最小化。

## 代替（別提出枠 / 保険・メタ変動時の RPS）
- `../submissions/archaludon_agent.py`: 同デッキ・**simple_bot操縦**（探索なし＝最軽量・最安全のフォールバック）。
- `../submissions/grimmsnarl_agent.py`: 悪。Alakazam/Dragapult を圧倒するが MegaStarmie に弱い。
- `../submissions/megastarmie_agent.py`: 水。Grimmsnarl に強いが Archaludon に弱い。

## Human Gate
実提出（アップロード）は人間の操作。`dist/submission.py` を Kaggle にアップすれば提出完了。
**前回までの提出は壊れた/off-meta版なので、この Archaludon 版に必ず差し替えてください。**
