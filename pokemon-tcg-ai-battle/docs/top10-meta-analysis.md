# トップ10 メタ分析（実データ20試合）

Kaggleラダー上位のリプレイ20試合（プレイヤー延べ40）を解析した実測メタ分布。

## アーキタイプ分布（使用回数 / 勝率）
| デッキ | 使用 | 勝率 | タイプ / 弱点 |
|---|---|---|---|
| Archaludon | 7 | 0.57 | 鋼 / 炎（Cinderace 炎を差し）|
| Alakazam(Abra線) | 7 | 0.57 | 超 / **悪** |
| Grimmsnarl | 7 | 0.43 | 悪 / **草** |
| Dunsparce系 control | 5 | 0.20 | 草系 |
| Dragapult | 3 | 0.67 | 竜 |
| Cinderace/Mega Starmie | 2 | 1.00 | 炎/水 |
| Gardevoir | 2 | 1.00 | 超 |

→ **3強（Archaludon鋼 / Alakazam超 / Grimmsnarl悪）が各7でほぼ拮抗**。単一支配は無い三つ巴。

## 型相性（三つ巴）
- 悪(Grimmsnarl) → 超(Alakazam) を弱点で叩く
- 炎(Cinderace/Archaludon差し) → 鋼(Archaludon) / 悪含む多くを叩く
- 草 → 悪(Grimmsnarl)

## 我々の Grimmsnarl の実測（対 実デッキ）
| 相手 | コピー版 | **精製版(採用)** |
|---|---|---|
| Alakazam(超) | 0.63–0.68 | **0.85–0.93** |
| Archaludon(鋼) | 0.25–0.38 | **0.38–0.53** |
| Cinderace | 0.18 | **0.43** |
| Grimmsnarl ミラー | 0.43 | **0.50** |
| Dragapult | 0.93 | 0.93 |
| Buddy | 0.40 | 0.45 |

→ **精製版（Dunsparce/Dudunsparce ドローエンジン＋Dawn）が全マッチで優位**。採用済み。
超(Alakazam)と Dragapult を圧倒、Archaludon に五分〜勝ち、ミラー五分。弱点は Cinderace/Buddy。

## 提出方針
- **Grimmsnarl(精製版)を提出**：三つ巴の1角を叩き(超)、他に五分。2エネ攻撃でブリックしない。
- 残課題：Cinderace(炎)/Buddy 対策。パイロットの mirror/Archaludon 詰め。

## 抽出した主要デッキリスト（cardId）
- Alakazam(超): 19/741/742/743(Abra線) + 305/66(Dunsparce) + 1081(ResetStamp) 等
- Archaludon(鋼): 169/190(Duraludon→Archaludon ex) + 666(Cinderace) + 1244(FullMetalLab) + 鋼13
- Grimmsnarl精製(悪): 646/647/648 + 112(Munkidori) + 305/66(Dunsparce線) + 1231(Dawn) + 1259(Spikemuth) + 悪10
