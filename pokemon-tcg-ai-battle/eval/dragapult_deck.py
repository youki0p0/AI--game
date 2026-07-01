"""実世界メタのトップデッキ「ドラパルト ex（Dragapult ex）」の CABT 再現。

pokemon-card.com 公式デッキ（deckID: UXUSpp-g9Dg7P-R3pSMy, 60枚）を engine の
cardId にマッピングしたもの。27種中26種が engine のカードプールに存在する。
唯一「スペシャルレッドカード」だけ engine に無いため、同じ手札干渉役の Judge(1213)
で 1 枚代替している。

デッキタイプ: 2進化トキシック・トゥールボックス（炎/超/悪の3エネ）
  - ドラパルト ex(121): 2進化・HP320・Dragon。技 Phantom Dive でベンチにダメカン散布。
    ドラメシヤ(119)→ドロンチ(120)→ドラパルト ex、またはふしぎなアメ(1079)で直接進化。
  - ヨノワール(133)ライン: サマヨール(132)/ヨマワル(131)。特性でダメカン移動/狙撃補助。
  - マシマシラ(112)/キチキギス ex=Fezandipiti ex(140): ダメカン操作・KO時ドロー。
  - ニャース ex=Meowth ex(1071): 特性でグッズ回収。スボミー(235): 序盤妨害。

注意: これは2進化を含む高難度の操縦を要するデッキ。ベースの simple_bot では
ほぼ機能しない（vs buddy 1/20）。専用パイロット（進化順序・アメ・トゥールボックス
判断）を実装しないと勝率は出ない。デッキ「構築」は可能だが「操縦」は別課題。
"""
from __future__ import annotations

# (cardId, 枚数, 和名, 英名/engine名) — 監査用の対応表
DRAGAPULT_CARDS = [
    # --- Pokémon (21) ---
    (121, 3, "ドラパルト ex", "Dragapult ex"),
    (120, 4, "ドロンチ", "Drakloak"),
    (119, 4, "ドラメシヤ", "Dreepy"),
    (133, 1, "ヨノワール", "Dusknoir"),
    (132, 1, "サマヨール", "Dusclops"),
    (131, 2, "ヨマワル", "Duskull"),
    (235, 2, "スボミー", "Budew"),
    (112, 1, "マシマシラ", "Munkidori"),
    (140, 1, "キチキギス ex", "Fezandipiti ex"),
    (1071, 2, "ニャース ex", "Meowth ex"),
    # --- Trainers (31) ---
    (1086, 4, "なかよしポフィン", "Buddy-Buddy Poffin"),
    (1152, 4, "ポケパッド", "Poké Pad"),
    (1121, 4, "ハイパーボール", "Ultra Ball"),
    (1079, 2, "ふしぎなアメ", "Rare Candy"),
    (1097, 2, "夜のタンカ", "Night Stretcher"),
    (1213, 1, "スペシャルレッドカード(代替:ジャッジマン)", "Judge (subst.)"),
    (1080, 1, "アンフェアスタンプ", "Unfair Stamp"),
    (1227, 4, "リーリエの決心", "Lillie's Determination"),
    (1182, 3, "ボスの指令", "Boss's Orders"),
    (1198, 2, "アカマツ", "Crispin"),
    (1240, 1, "メイのはげまし", "Rosa's Encouragement"),
    (1246, 1, "ジャミングタワー", "Jamming Tower"),
    (1256, 1, "ロケット団の監視塔", "Team Rocket's Watchtower"),
    (1260, 1, "危ない廃墟", "Risky Ruins"),
    # --- Energy (8) ---
    (2, 3, "基本炎エネルギー", "Basic Fire Energy"),
    (5, 3, "基本超エネルギー", "Basic Psychic Energy"),
    (7, 2, "基本悪エネルギー", "Basic Darkness Energy"),
]

DRAGAPULT_DECK: list[int] = [cid for cid, n, *_ in DRAGAPULT_CARDS for _ in range(n)]
assert len(DRAGAPULT_DECK) == 60, len(DRAGAPULT_DECK)
