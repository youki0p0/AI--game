"""PTCG AI Battle 提出エージェント: Fire 単サイド（全非ex・弱点炎アグロ）。

方針（docs/meta-crustle-archaludon.md 参照）:
  - 全アタッカーが非ex＝KOされても相手に1サイドしか渡さない（サイドレース有利）。
  - 相手の弱点(炎)を突いて×2ダメージでKO。Archaludon ex(鋼300HP)/Crustle(草)/一般exに刺さる。
  - 実測: vs Buddy 0.66・vs Archaludon(現環境) 0.515（互角）。

自己完結（cg.api 以外を import しない）。Kaggle サンドボックスでそのまま動く単一ファイル。
observation(dict) を受け取り、select.option のインデックス配列(list[int]) を返す。
select が None（デッキ選択フェーズ）のときは 60 枚の cardId 配列を返す。
"""
from __future__ import annotations

# --- 60枚デッキ（Fire 単サイド。18 Pokémon / 30 Trainer / 12 Energy）---------
FIRE_DECK = (
    [490] * 4      # Victini      V-Force 120 (弱点×2=240)
    + [663] * 4    # Volcanion    Backfire 130 (弱点×2=260)
    + [318] * 4    # Ho-Oh        Shining Blaze 100
    + [1027] * 4   # Turtonator   Heat Breath 80
    + [358] * 2    # Hearthflame Mask Ogerpon
    # 安定トレーナー30枚（engine 安全なカードのみ）
    + [1192] * 4   # Carmine
    + [1224] * 4   # Cheren
    + [1213] * 4   # Judge
    + [1152] * 4   # Poké Pad
    + [1102] * 4   # Dusk Ball
    + [1086] * 4   # Buddy Poffin
    + [1123] * 4   # Switch
    + [1182] * 2   # Boss's Orders
    + [2] * 12     # Basic Fire Energy
)
assert len(FIRE_DECK) == 60, len(FIRE_DECK)

ENERGY_ID = 2          # 基本炎エネルギーの cardId（= energyType 炎）
MIN_ATTACK_DMG = 120   # これ未満の技はチップ扱いで避ける（意味あるKOを取りに行く）
# 配置優先: HP/打点の高いアタッカーを前へ
ATTACKER_PRIORITY = [663, 318, 1027, 358, 490]

# OptionType / SelectType / SelectContext / AreaType の int 値（cg.api 準拠）
T_YES, T_NO = 1, 2
T_PLAY, T_ATTACH, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END = 7, 8, 10, 11, 12, 13, 14
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
AREA_ACTIVE = 4

_CARD_TABLE = None
_ATTACK_TABLE = None


def _ensure_tables():
    global _CARD_TABLE, _ATTACK_TABLE
    if _CARD_TABLE is not None:
        return
    try:
        from cg.api import all_card_data, all_attack  # type: ignore
        _CARD_TABLE = {c.cardId: c for c in all_card_data()}
        _ATTACK_TABLE = {a.attackId: a for a in all_attack()}
    except Exception:
        _CARD_TABLE = {}
        _ATTACK_TABLE = {}


def _card_data(card_id):
    _ensure_tables()
    return None if card_id is None else _CARD_TABLE.get(card_id)


def _attack_data(attack_id):
    _ensure_tables()
    return None if attack_id is None else _ATTACK_TABLE.get(attack_id)


def _g(d, key, default=None):
    """dict からも dataclass からも安全に属性/キーを取り出す。"""
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _attack_damage(attack_id) -> int:
    a = _attack_data(attack_id)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff_vs(attack_id, attacker_type, defender) -> int:
    """弱点×2 / 抵抗力-30 を反映した実効ダメージ。"""
    dmg = _attack_damage(attack_id)
    if dmg <= 0 or defender is None:
        return dmg
    dd = _card_data(_g(defender, "id"))
    if dd is None:
        return dmg
    weak = _g(dd, "weakness")
    if weak is not None and attacker_type is not None and attacker_type == weak:
        return dmg * 2
    res = _g(dd, "resistance")
    if res is not None and attacker_type is not None and attacker_type == res:
        return max(0, dmg - 30)
    return dmg


def agent(obs_dict: dict, configuration=None) -> list[int]:
    sel = obs_dict.get("select") if isinstance(obs_dict, dict) else _g(obs_dict, "select")
    cur = obs_dict.get("current") if isinstance(obs_dict, dict) else _g(obs_dict, "current")
    if sel is None:
        return list(FIRE_DECK)  # デッキ選択フェーズ
    options = _g(sel, "option", []) or []
    n = len(options)
    if n == 0:
        return []
    stype = _g(sel, "type")
    sctx = _g(sel, "context")
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)

    me = _g(cur, "yourIndex", 0) if cur is not None else 0
    players = (_g(cur, "players", []) or []) if cur is not None else []
    opp_active = my_active = None
    if len(players) >= 2:
        oa = _g(players[1 - me], "active", []) or []
        opp_active = oa[0] if oa else None
        ma = _g(players[me], "active", []) or []
        my_active = ma[0] if ma else None

    def first_k() -> list[int]:
        k = min(max(mc, mn if mn > 0 else 1), n)
        return list(range(k))

    # --- 先攻/後攻: アグロなので後攻を選ぶ ---
    if sctx == SC_IS_FIRST:
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]
    if sctx == SC_MULLIGAN:
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]

    # --- 技選択: 実効ダメージ最大 ---
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_d = 0, -1
        for i, o in enumerate(options):
            d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
            if d > best_d:
                best_d, best_i = d, i
        return [best_i]

    # --- MAIN: マクロ行動を選ぶ（攻撃>特性>エネ付け>展開/ドロー>後退>終了）---
    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= 5
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ATTACK:
                d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                if d >= MIN_ATTACK_DMG:
                    s = 10000 + d + (50000 if (oh > 0 and d >= oh) else 0)
                else:
                    s = 200
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                s = 8000 + (300 if _g(o, "inPlayArea") == AREA_ACTIVE else 0)
            elif t == T_PLAY:
                card = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    card = _card_data(_g(hand[idx], "id"))
                ct = _g(card, "cardType") if card else None
                boost = 3000 if thin else 0
                if ct == 3:        # SUPPORTER
                    s = 6500 + boost
                elif ct in (1, 2):  # ITEM / TOOL
                    s = 5500 + boost
                else:               # basic Pokémon
                    s = 5000
            elif t == T_RETREAT:
                s = 1500
            elif t == T_DISCARD:
                s = 800
            elif t == T_END:
                s = 100
            else:
                s = 50
            scores.append(s)
        return [max(range(n), key=lambda i: scores[i])]

    # --- 配置: 自軍はアタッカー優先/敵はサイドの大きい的（gust）---
    if sctx in SC_PLACEMENT:
        targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
        rank = {cid: i for i, cid in enumerate(ATTACKER_PRIORITY)}

        def keyf(i):
            cid = _g(options[i], "cardId")
            if not targets_opp and cid in rank:
                return (0, rank[cid])
            cd = _card_data(cid)
            if targets_opp:
                pv = 3 if _g(cd, "megaEx") else (2 if _g(cd, "ex") else 1)
                return (1, -pv)
            return (1, -float(_g(cd, "hp", 0) or 0))
        scored = sorted(range(n), key=keyf)
        if mc <= 1:
            return [scored[0]]
        return sorted(scored[:max(mc, mn)])

    # --- 汎用の的/カード選択: 敵アクティブ優先、次いで自軍炎エネルギー ---
    energy_choice = opp_active_choice = None
    for i, o in enumerate(options):
        if _g(o, "cardId") == ENERGY_ID and energy_choice is None:
            energy_choice = i
        if _g(o, "playerIndex") == (1 - me) and _g(o, "area") == AREA_ACTIVE and opp_active_choice is None:
            opp_active_choice = i
        if _g(o, "inPlayArea") == AREA_ACTIVE and _g(o, "playerIndex") == (1 - me) and opp_active_choice is None:
            opp_active_choice = i

    if mc <= 1:
        if opp_active_choice is not None:
            return [opp_active_choice]
        if energy_choice is not None:
            return [energy_choice]
        return [0]

    chosen = []
    for i, o in enumerate(options):
        if _g(o, "cardId") == ENERGY_ID:
            chosen.append(i)
        if len(chosen) >= mc:
            break
    if len(chosen) < (mn or mc):
        for i in range(n):
            if i not in chosen:
                chosen.append(i)
            if len(chosen) >= max(mn, mc):
                break
    return sorted(chosen[:max(mc, mn)]) if chosen else first_k()
