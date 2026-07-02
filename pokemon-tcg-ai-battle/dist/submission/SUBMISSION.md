# 提出パッケージ（PTCG AI Battle / Kaggle）

更新: 2026-07-02（モデル2をユーザー選択の **Dragapult ハイブリッド** に変更）

## ★★ 2モデル分散（最新2提出を両方使う）

| 枠 | ファイル | デッキ/戦術 | 実測 |
|---|---|---|---|
| **モデル1** | `dist/submission.py` | Archaludon ex（鋼）＋探索(深さ3) | フィールド0.66〜0.75（主力・土台） |
| **モデル2** | `dist/submission2.py` | **Dragapult ex ハイブリッド**（模倣プライア＋探索） | フィールド0.20〜0.30（挑戦枠） |
| 代替 | `dist/submission2_megastarmie.py` | MegaStarmie（水）＋探索 | ペア下限保証0.62（統計的にはこちらが上） |

**モデル2の中身**: トップエージェント(勝率0.87)のリプレイ14試合から学習した模倣ランキングで
有望手を絞り、エンジンsandboxの深さ3ロールアウト＋Dragapult専用eval（散布蓄積・エネ型[炎+超]）で
検証して指す。散布=相手の進化前・エンジン狙撃。必ず後攻。全例外を握り空アクション自滅なし。

**正直な注記**: 統計的に強いモデル2は MegaStarmie（ペア下限0.62）。Dragapult は現状
フィールド0.2〜0.3で、トップ(探索型・2.4s/決定)との差は操縦の計画力。レートを最優先するなら
`submission2_megastarmie.py` を、Dragapultを使う意志を優先するなら `submission2.py` を。

**MegaStarmie（代替）の補完性データ**: vsDragapult 0.96 / vsCrustle 0.67〜0.92（Archaludonの唯一の穴=壁を
水の非ex打点で貫通）。Archaludon+MegaStarmie のペア下限保証 0.62。

→ **`dist/submission.py` と `dist/submission2.py` の両方をアップロード**（最新2つが有効カウント）。

---

## 提出ファイル1: `dist/submission.py`（= Archaludon ex / 鋼 ＋ 探索パイロット）
Kaggle「File Upload」に**ドラッグ&ドロップ**する単一 .py（= `submissions/archaludon_search_agent.py`）。

### Kaggle 形式適合
- ✅ 末尾の唯一の最終 def = `agent(observation, configuration=None)`
- ✅ **全例外を握り、空アクションで自滅しない**（探索失敗時も安全手にフォールバック）。370戦で例外0。
- ✅ `cg.api` のみ依存・デッキ埋め込み・相手デッキ非依存・end-to-end動作確認済み

### なぜこのデッキか（実メタ適合）
現 PTCG-AI ラダーの**最頻アーキタイプ**（上位10データで使用7＝最多タイ）。1進化
（Duraludon 169 → Archaludon ex 190）＋ Full Metal Lab / 鋼エネ厚めで攻撃到達が安定。

### 操縦（pilot）＝ 3手読み探索 ★今回の改良点
各決定で **全ての合法オプション** をエンジンの探索サンドボックス
(search_begin/search_step)へ適用し、結果盤面を静的評価 state_eval
（サイド差>>マテリアル>脅威>資源, 将棋流）で採点して最善手を選ぶ。
探索深さ **N_TURNS=3（自分→相手→自分）**。

**なぜ深さ3（奇数）か＝発見した勝ちパターン**:
深さを 1〜4 で実測すると 1:0.56 / **2:0.44** / **3:0.75** / 4:0.42 と
「**奇数=強い / 偶数=弱い**」。奇数深さは評価点が **自分のターン終了時**（実盤面）に来るのに対し、
偶数深さは **相手ターン終了時** の評価になり、相手の隠れ手札/山は自デッキから再構成した
"空想" なので誤差が乗る。深さ3は「相手の反撃(KO)を1回読んでから自分の立て直しを評価」する
最も費用対効果の高い点。→ これを **N_TURNS=奇数** としてアルゴリズム化。

### 実測（同一相手＝simple_bot操縦の実メタ, 先後入替）
**深さ比較（N=60/相手・計180戦）: 深さ3 0.739 [0.675,0.803] > 深さ1 0.633 [0.563,0.704]（+0.11）**

| 相手 | simple_bot | 探索 深さ1 | **探索 深さ3(採用)** |
|---|---|---|---|
| Grimmsnarl（悪）| 0.58 | 0.57 | **0.80** |
| Alakazam（超）| 0.46 | 0.65 | **0.72** |
| MegaStarmie（水）| 0.48 | 0.68 | **0.70** |

→ 全マッチで simple_bot・深さ1 を上回る。提出ファイル直接検証（深さ3・計90戦）でも
**OVERALL 0.711・例外0** を再現。合計270戦でブリック/例外なし。

### 残リスク
- 探索は per-option × 深さ3 でエンジン模擬。ロールアウト上限25で**1手の計算量は有界**。
  実測 約2.4s/戦（1手番あたり≈0.03〜0.06s）で Kaggle の手番遅延は問題なし。
- Archaludon は**炎弱点**（Cinderace 666 差しで一部緩和）。
- 相手デッキ未知のため相手手番のロールアウトは近似。奇数深さ（自ターンで評価）で影響を最小化。

## 代替（別提出枠 / 保険・メタ変動時の RPS）
- `../submissions/archaludon_agent.py`: 同デッキ・**simple_bot操縦**（探索なし＝最軽量・最安全のフォールバック）。
- `../submissions/grimmsnarl_agent.py`: 悪。Alakazam/Dragapult を圧倒するが MegaStarmie に弱い。
- `../submissions/megastarmie_agent.py`: 水。Grimmsnarl に強いが Archaludon に弱い。

## Human Gate
実提出（アップロード）は人間の操作。`dist/submission.py` を Kaggle にアップすれば提出完了。
**前回までの提出は壊れた/off-meta版なので、この Archaludon 版に必ず差し替えてください。**
