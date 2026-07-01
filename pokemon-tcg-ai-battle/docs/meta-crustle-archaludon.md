# 実環境メタ分析：Buddy / Crustle / Archaludon（ブリジュラス）

ユーザ提供情報「現PTCG AI環境はブリジュラス（Archaludon）デッキ」、および Day-1 #1
「Crustle Bot」の再現を受けて、実環境の3デッキ＋自作エージェントで対戦検証した。

## 検証したデッキ／エージェント

| 略称 | 中身 | パイロット |
|---|---|---|
| Buddy | Mega Lucario ex（闘、弱点：超）＝サンプルエージェント | 専用（サンプル同梱）|
| Crustle | Dwebble→Crustle 壁（草、弱点：炎）＋回復＋特殊エネ | 忠実再現ボット |
| Archaludon | Duraludon→Archaludon ex（鋼300HP、弱点：炎、2枚サイド）| setup-then-attack ボット |
| Psy-champ | 単サイドPsychic（Iron Boulder等・全非ex）| psy_pilot（vs Buddy 0.70 の王者）|
| Fire | 単サイドFire（Volcanion/Ho-Oh等・全非ex）| typed_pilot(mad=120) |

## 勝率行列（ROW が COLUMN に勝つ率、先後入替）

```
ROW \ COL     Buddy    Crustle   Archaludon
Psy-champ     0.70     0.01      0.44
Fire          0.66     0.015     0.515
Crustle       0.83      ---      1.00
Archaludon    0.37     0.00       ---
Buddy          ---     0.17      0.63
```
（各セル N=100〜200・95%CI は本文。Buddy行のvsCrustle/Archaludonは列側の裏返し）

## 結論：これは「きれいな三すくみ」ではない — Crustle が支配的

ユーザ仮説「デッキ相性は三すくみになりがち」は方向として正しいが、**実際は Crustle が
ほぼ全てに勝つ一強の壁**だった。

1. **Crustle が Buddy(0.83)・Archaludon(1.00)・Psy-champ(0.99) を全て制圧。**
   - Archaludon ex には **0勝100敗（0.00）**。Crustleの特性
     「相手の {ex} ポケモンの技のダメージを全て無効」で、Archaludon ex の
     Metal Defender 220 が完全に通らない。ex主体デッキはCrustleに構造的に勝てない。

2. **Archaludon は Crustle と Buddy の両方に負ける最下位。**
   - vs Crustle 0.00（ex無効の直撃）、vs Buddy 0.37。
   - 「現環境＝Archaludon」だとしても、Archaludon 自体は上位2デッキに弱い。
     ラダー上位に Crustle が少ない前提で成立している環境と推測できる。

3. **炎の弱点を突いても Crustle は落ちない（Fire 0.015）。**
   - 理屈上は Volcanion 130→260（弱点×2）で Crustle 150 を一撃のはず。だが：
     - **Spiky Energy**：Crustleが殴られる度に攻撃側へ20ダメージ反射 → HP80のVictini等が自滅。
     - **Grow Grass Energy**（+20HP）＋ **Hero's Cape**（+100HP）で最大約270HP。
     - **Jumbo Ice Cream(回復80)／Cook(回復70)** で毎ターン回復。
   - 非exの炎でもダメージレースで削り切れず、Crustleの回復・反射・増HPが上回る。

## 実環境（Archaludon）への回答：Fire 単サイドが最有力

- **Fire は Buddy に 0.66、Archaludon に 0.515（ほぼ互角）** と、実環境相手に
  競争力のある唯一の自作デッキ。Archaludon ex(300HP鋼)は炎弱点×2で2発圏内、
  かつこちらは全非exの1サイドなのでサイドレースで有利に近い（＝互角）。
- Psy-champ は Archaludon に 0.44（弱点を突けないため）。**実環境では Fire の方が良い。**
- ただし **どちらも Crustle には勝てない**。Crustle がラダーに増えると環境が一変する。

## 一強 Crustle を崩す方向性（未実装・提案）

Crustleの弱点は「exダメージ無効・回復壁・Spiky反射」。破るには：
- **非exの高打点炎**（弱点×2で270HP超を一撃、かつSpiky反射20を耐えるHP）。
  炎の大型アタッカーは大半がex → Crustle特性で無効化される罠がある。非exで135+打点が鍵。
- **回復を上回る連続KO or ベンチ狙撃**（Boss's Orders で未成長Dwebbleを狙撃）。
- **特性・スタジアム・手札干渉**で回復エンジン（アイス/Cook）を止める。

## 再現方法

```bash
cd pokemon-tcg-ai-battle
# Fire pilot（typed_pilot）を実環境デッキにぶつける
python - <<'PY'
from eval.engine_driver import play_game
from eval.crustle_bot import ARCHALUDON_DECK, make_simple_bot
from eval.decks import DECKS
from eval.typed_pilot import make_typed_pilot
FIRE=DECKS["fire_single"]
fire=make_typed_pilot(FIRE, energy_id=2, attacker_priority=[663,318,1027,358,490], min_attack_dmg=120)
arch=make_simple_bot(ARCHALUDON_DECK)
w=sum(1 for g in range(50) if play_game(fire,arch,deck0=FIRE,deck1=ARCHALUDON_DECK)==0)
print("Fire vs Archaludon (先手50戦):", w/50)
PY
```
