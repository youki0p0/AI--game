# デッキ総当たり統計（三すくみ分析）

汎用パイロット(deck-agnostic)で各タイプデッキを操縦、buddyのみ専用パイロット。各60戦・先後入替。

## 勝率行列（ROW vs COLUMN）
```
ROW \ COL   BUDDY  PSYC  FIRE  META  DARK  FIGH  COLO
BUDDY        ---   0.62  0.85  0.93  0.92  0.65  0.87
PSYC        0.35   ---   0.38  0.22  0.42  0.65  0.63
FIRE        0.18  0.67   ---   0.40  0.42  0.57  0.65
META        0.17  0.83  0.62   ---   0.58  0.75  0.83
DARK        0.15  0.65  0.58  0.38   ---   0.47  0.73
FIGH        0.35  0.28  0.35  0.18  0.52   ---   0.75
COLO        0.03  0.17  0.28  0.23  0.25  0.22   ---
```

## vs BUDDY（目標 ≥0.65）
| デッキ | vs buddy |
|---|---|
| PSYC(Psychic) | **0.35–0.41**（buddyの最悪マッチ＝弱点ぶん。だが未達）|
| FIGH(Fighting) | 0.35 |
| FIRE | 0.18 |
| META | 0.17 |
| DARK | 0.15 |
| COLO | 0.03 |

## 結論
1. **buddy は全デッキに勝つ（0.62–0.93）＝強さの本質は「専用パイロット」**（moat）。
2. デッキ間には明確な**三すくみ**: META > PSYC > FIGH（META>PSYC 0.83 / PSYC>FIGH 0.65 / FIGH>… ; COLO は最弱）。
3. **Psychic は buddy の最悪マッチ**（buddy 0.62 / 我々 0.38）＝弱点(Mega Lucario ex×2)が効いている。
   だが、いかなるパイロット（汎用0.37 / 専用0.41 / 探索0.40）でも **≈0.40 が天井**。
4. **0.65 到達には「Psychic弱点デッキ用の buddy 級専用パイロット」の作り込みが必須**
   （型優位＋buddy級操縦の組合せ）。汎用/探索操縦では型優位を勝率に変換しきれない。

## 安定/不安定カード（engine）
- 安定トレーナー: Carmine1192, Cheren1224, Judge1213, PokéPad1152, DuskBall1102, BuddyPoffin1086, Switch1123, Boss1182
- SEGFAULT(使用不可): MasterBall1125, RebootPod1089, PreciousTrolley1126
