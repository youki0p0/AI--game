# 提出パッケージ（PTCG AI Battle / Kaggle）

更新: 2026-07-01（実ラダー環境デッキ **Archaludon ex / ブリジュラス（鋼）** へ差し替え）

## ★ 提出ファイル: `dist/submission.py`（= Archaludon ex / 鋼）
Kaggle「File Upload」に**ドラッグ&ドロップ**する単一 .py。

### Kaggle 形式適合
- ✅ 末尾の唯一の最終 def = `agent(observation, configuration=None)`
- ✅ **全例外を握り、空アクションで自滅しない**（実戦で空アクション自滅があったため根絶）
- ✅ `cg.api` のみ依存・デッキ埋め込み・相手デッキ非依存・end-to-end動作確認済み

### なぜこのデッキか（実メタ適合）
現 PTCG-AI ラダーの**最頻アーキタイプ**（上位10データで使用7＝最多タイ）。実メタ3柱
（Archaludon鋼 / Alakazam超 / Grimmsnarl悪）に対して、Grimmsnarl より**ポジションが良い**：
- **vs MegaStarmie 0.625**（Grimmsnarl はこれに 0.44 で負けるのが唯一の穴だった → Archaludon は勝ち越す）
- **vs Grimmsnarl ミラー 0.520**（H2H で我々の旧本命 Grimmsnarl を上回る）
- 1進化（Duraludon 169 → Archaludon ex 190）＋ Full Metal Lab / 鋼エネ厚めで**攻撃到達が安定**、ブリックしにくい。

### 操縦（pilot）
実測で最も安定して回った汎用 setup-then-attack ロジック（simple_bot）をインライン化。
※ 自作の専用パイロットは 0.44 と弱かったため、実測 0.58〜0.60 の simple_bot を採用。

### 実測（自己完結・先後入替・N=200/相手＝計1200戦）
**OVERALL 0.580  95%CI[0.552, 0.608]**（Grimmsnarl 0.581 と統計的に同等、メタ位置は上）

| 相手 | 勝率 |
|---|---|
| Dragapult（竜）| **0.920** |
| MegaStarmie（水）| **0.625**（Grimmsnarl の穴を埋める）|
| Alakazam（超）| 0.580 |
| Grimmsnarl ミラー | 0.520 |
| Archaludon ミラー | 0.515 |
| Buddy（メガルカリオ）| 0.320 |

### 残リスク
- **vs Buddy 0.320 が最弱**。ただし Buddy は上位10ラダーデータに出現せず、実メタ優先度は低い。**ブリックはせず殴り合う**。
- Archaludon は**炎弱点**。Cinderace/炎の高打点には弱い（デッキに Cinderace 666 を差して一部緩和）。
- パイロットは汎用ロジック。トップ層の人間には及ばないが「機能停止しない実環境デッキ」が最重要目的。

## 代替（別提出枠 / メタ変動時の RPS）
- `../submissions/grimmsnarl_agent.py`: 悪。Alakazam/Dragapult を圧倒するが MegaStarmie に弱い。
- `../submissions/megastarmie_agent.py`: 水。Grimmsnarl に強いが Archaludon に弱い。

## Human Gate
実提出（アップロード）は人間の操作。`dist/submission.py` を Kaggle にアップすれば提出完了。
**前回までの提出は壊れた/off-meta版なので、この Archaludon 版に必ず差し替えてください。**
