# 提出パッケージ（PTCG AI Battle / Kaggle）

更新: 2026-07-01（実戦の完封負けを受け、堅牢な psy_champion へ差し替え）

## ★ 提出ファイル（1モデル）: `dist/submission.py`
Kaggle「Submit to Competition → File Upload」に**ドラッグ&ドロップ**する単一 .py。

### Kaggle 形式への適合（アップロード画面の指示）
> the last 'def' accepting an observation and returning an action（.py/.zip/.gz/.7z 可）
- ✅ **ファイル末尾の唯一の最終 def = `agent(observation, configuration=None)`**（入れ子defなし・AST検証済み）
- ✅ observation → action（デッキ選択時は60枚cardId）
- ✅ `cg.api` のみ依存・デッキ埋め込み・相手デッキ非依存・end-to-end動作確認済み

## 選択モデル: psy_champion（Psychic単サイド・堅牢ヒューリスティック）
### 差し替えの理由（実戦ログ 83005093 の教訓）
前提出 meta_search は実戦で **Archaludon に 0–6 完封負け**。原因は
**炎デッキ(3エネ技依存)が2エネで止まりブリック**＋**相手がバリアント構築で探索の隠れ情報
復元が破綻→弱いフォールバック**だった。そこで:
- **2エネ主体**（Iron Boulder 170/{P}{C}, Mesprit 160/{P}{P}）で**確実に立ち上がる**＝ブリックしない
- **相手デッキ復元に非依存の純ルールベース**＝相手が何の構築でも挙動が安定（バリアント耐性）

### 実測（自己完結・先後入替、N=60〜80）
| 相手 | 勝率 |
|---|---|
| Buddy（メガルカリオ）| 0.66〜0.74 |
| Archaludon（現環境）| 0.40 |
| Crustle（イワパレス）| 0.03 |

## 残リスク・限界（正直に）
- **Archaludon には超で弱点を突けず不利（0.40）**。ただし前提出のように0–6で機能停止はせず、
  ちゃんと殴り合って競る（ブリック回避が最優先の目的）。
- **Crustle には弱い（0.03）**。回復壁は構造的天敵。
- ガントレット相手（buddy/simple_bot）は実ラダーの強豪より弱い。実測値は上振れ気味に見ておく。

## 代替案（必要なら別提出枠に）
- `fire_single/main.py`: 炎単サイド。Archaludon 0.43 と超より良い（弱点を突ける）が、
  3エネ技を含むためブリック耐性は champion に劣る。1日5提出・最新2提出集計なので併用も可。

## Human Gate
実提出（アップロード）は人間の操作事項。`dist/submission.py` を Kaggle にアップすれば提出完了。
