# 提出パッケージ（PTCG AI Battle / Kaggle）

更新: 2026-07-01（トップ層のコピー Grimmsnarl ex へ差し替え・A案）

## ★ 提出ファイル: `dist/submission.py`（= Marnie's Grimmsnarl ex / 悪）
Kaggle「File Upload」に**ドラッグ&ドロップ**する単一 .py。

### Kaggle 形式適合
- ✅ 末尾の唯一の最終 def = `agent(observation, configuration=None)`
- ✅ **全例外を握り、空アクションで自滅しない**（実戦で空69/136の自滅があったため根絶）
- ✅ `cg.api` のみ依存・デッキ埋め込み・相手デッキ非依存・end-to-end動作確認済み

### なぜこのデッキか
トップ層の決勝級ログ(83010255)で**両者が使っていた環境No.1デッキ**をそのままコピー。
- **Shadow Bullet 180＋ベンチ30 を たった2エネ**／HP320／Punk Up(進化加速)
- **2エネ攻撃なのでブリックしない**（我々の炎デッキが3エネ待ちで倒され0-6完封した欠点を構造的に回避）。
  実測で最大8エネ・Grimmsnarl 到達率も高く、確実に機能する。

### 実測（自己完結・先後入替・N=50）
| 相手 | 勝率 |
|---|---|
| Psychic（自作champion）| **0.76**（悪が超の弱点を突く）|
| Archaludon（現環境）| 0.50 |
| Grimmsnarl ミラー | 0.48 |
| Buddy（メガルカリオ）| 0.40 |

### 残リスク
- vs Buddy 0.40 が最弱（未調整パイロット）。ただし**ブリックはせず殴り合う**。
- Grimmsnarl は**草弱点**。草の高打点デッキには弱い（現環境での草採用率は低め）。
- パイロットは未成熟。トップ層の人間には及ばないが「機能停止しない環境デッキ」が最重要目的。

## 代替（別提出枠）
- `../submissions/psy_champion_agent.py`: 単サイド超。Buddy に強いが**悪トップに弱点**。
- `../submissions/fire_single_agent.py`: 炎。実戦で3エネ待ちブリックの傾向。

## Human Gate
実提出（アップロード）は人間の操作。`dist/submission.py` を Kaggle にアップすれば提出完了。
**前回までの提出は壊れた/off-meta版なので、この Grimmsnarl 版に必ず差し替えてください。**
