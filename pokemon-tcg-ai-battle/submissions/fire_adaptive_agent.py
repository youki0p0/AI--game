"""PTCG AI Battle 提出エージェント（適応型）: Fire 単サイド + 対イワパレス警戒モード。

相手デッキは見えないが、対戦中は *相手の盤面* は見える。そこで相手の場に
イワパレス(Crustle)系のシグナル（Crustle/Dwebble本体、または壁が必要とする特殊エネ
グロウグラス/ミスト/スパイキー、ヒーローマント）を検知したら「壁警戒モード」に切替える:

  1. ジャミングタワー(1246)を優先して貼る → ヒーローマント(Tool)を無効化し Crustle を素150へ。
  2. **チップ攻撃で消耗しない**（KOできない攻撃は打たず、炎アタッカーに集中してエネを積む）。
  3. 弱点(炎)×2で OHKO できる時だけ攻撃（Victini V-Force 120→240 は2エネで到達可能）。

通常時は Fire 単サイドのアグロ挙動（vs Buddy 0.65+）そのまま。壁検知時のみ挙動が変わる。
自己完結（cg.api 以外を import しない）・相手デッキ非依存。observation(dict)→list[int]。

★実測結果（自己完結・N=60〜80）と位置づけ:
  vs Buddy 0.717（ヒーローマント無効化で本命 fire_single 0.667 から改善）
  vs Archaludon 0.333 / vs Psychic 0.383 / vs Crustle **0.013**（改善せず）
  → 壁検知は機能し、ジャミングタワーも貼れる。だが **vs Crustle は依然勝てない**:
    炎の弱点OHKO（Victini V-Force 2エネ240 / Volcanion 3エネ260）を、回復壁を相手に
    ヒューリスティックでは組成しきれない（＝探索型パイロットが必要だった理由と同じ）。
  結論: 「検知」は簡単だが「実行(OHKO組成)」が難しく、壁攻略は rule-based では不可。
  本ファイルは “相手盤面からメタ判断して挙動を変える” 実験例。実提出は相手デッキ非依存で
  最も安定する fire_single_agent.py を採用（Archaludon 0.433 との兼ね合いで総合が上）。
"""
from __future__ import annotations

# --- 60枚デッキ: Fire単サイド + Jamming Tower3（ヒーローマント剥がし用）---------
FIRE_DECK = (
    [490] * 4      # Victini      V-Force 120 (弱点×2=240, 2エネ) ← 壁への主OHKO
    + [663] * 4    # Volcanion    Backfire 130 (弱点×2=260, 3エネ)
    + [318] * 4    # Ho-Oh        Shining Blaze 100
    + [1027] * 4   # Turtonator   Heat Breath 80
    + [358] * 2    # Hearthflame Mask Ogerpon (Fire Kagura=エネ加速)
    # トレーナー30（安定枠 + Jamming Tower3）
    + [1192] * 4   # Carmine
    + [1224] * 4   # Cheren
    + [1213] * 3   # Judge
    + [1152] * 4   # Poké Pad
    + [1102] * 2   # Dusk Ball
    + [1086] * 4   # Buddy Poffin
    + [1123] * 4   # Switch
    + [1182] * 2   # Boss's Orders
    + [1246] * 3   # Jamming Tower (対壁: ヒーローマント無効化)
    + [2] * 12     # Basic Fire Energy
)
assert len(FIRE_DECK) == 60, len(FIRE_DECK)

ENERGY_ID = 2
MIN_ATTACK_DMG = 120
ATTACKER_PRIORITY = [663, 318, 1027, 358, 490]
JAMMING_TOWER = 1246

# イワパレス系シグナル
CRUSTLE_POKEMON = {344, 345}            # Dwebble / Crustle
CRUSTLE_SP_ENERGY = {18, 11, 14}        # Grow Grass / Mist / Spiky
HERO_CAPE = 1159

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


def _card_data(cid):
    _ensure_tables()
    return None if cid is None else _CARD_TABLE.get(cid)


def _attack_data(aid):
    _ensure_tables()
    return None if aid is None else _ATTACK_TABLE.get(aid)


def _g(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _attack_damage(aid) -> int:
    a = _attack_data(aid)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff_vs(aid, atk_type, defender) -> int:
    dmg = _attack_damage(aid)
    if dmg <= 0 or defender is None:
        return dmg
    dd = _card_data(_g(defender, "id"))
    if dd is None:
        return dmg
    weak = _g(dd, "weakness")
    if weak is not None and atk_type is not None and atk_type == weak:
        return dmg * 2
    res = _g(dd, "resistance")
    if res is not None and atk_type is not None and atk_type == res:
        return max(0, dmg - 30)
    return dmg


def _detect_wall(cur, me) -> bool:
    """相手の盤面/トラッシュ/スタジアムから イワパレス系シグナルを検知。"""
    players = _g(cur, "players", []) or []
    if len(players) < 2:
        return False
    op = players[1 - me]
    for area in ("active", "bench"):
        for p in (_g(op, area, []) or []):
            if p is None:
                continue
            if _g(p, "id") in CRUSTLE_POKEMON:
                return True
            for e in (_g(p, "energyCards", []) or []):
                if _g(e, "id") in CRUSTLE_SP_ENERGY:
                    return True
            for tl in (_g(p, "tools", []) or []):
                if _g(tl, "id") == HERO_CAPE:
                    return True
    for c in (_g(op, "discard", []) or []):
        cid = _g(c, "id")
        if cid in CRUSTLE_POKEMON or cid in CRUSTLE_SP_ENERGY or cid == HERO_CAPE:
            return True
    return False


def _jamming_in_play(cur) -> bool:
    for s in (_g(cur, "stadium", []) or []):
        if _g(s, "id") == JAMMING_TOWER:
            return True
    return False


def agent(obs_dict: dict, configuration=None) -> list[int]:
    sel = obs_dict.get("select") if isinstance(obs_dict, dict) else _g(obs_dict, "select")
    cur = obs_dict.get("current") if isinstance(obs_dict, dict) else _g(obs_dict, "current")
    if sel is None:
        return list(FIRE_DECK)
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

    wall = _detect_wall(cur, me)  # ★イワパレス警戒フラグ

    def first_k():
        k = min(max(mc, mn if mn > 0 else 1), n)
        return list(range(k))

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

    # 技選択: 実効ダメージ最大（弱点×2）
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_d = 0, -1
        for i, o in enumerate(options):
            d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
            if d > best_d:
                best_d, best_i = d, i
        return [best_i]

    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= 5
        jam_down = _jamming_in_play(cur)
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ATTACK:
                d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                ko = oh > 0 and d >= oh
                if wall:
                    # 壁警戒: KOできる時だけ攻撃。チップ攻撃はせず消耗を避ける。
                    s = (60000 + d) if ko else 150
                elif d >= MIN_ATTACK_DMG:
                    s = 10000 + d + (50000 if ko else 0)
                else:
                    s = 200
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                s = 8000 + (300 if _g(o, "inPlayArea") == AREA_ACTIVE else 0)
            elif t == T_PLAY:
                card = None
                cid = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    cid = _g(hand[idx], "id")
                    card = _card_data(cid)
                ct = _g(card, "cardType") if card else None
                boost = 3000 if thin else 0
                if wall and cid == JAMMING_TOWER and not jam_down:
                    s = 9500  # 壁警戒: 最優先でジャミングタワー（ヒーローマント剥がし）
                elif cid == JAMMING_TOWER:
                    s = 400 if jam_down else 3000  # 通常時は控えめ（重複貼りしない）
                elif ct == 3:
                    s = 6500 + boost
                elif ct in (1, 2):
                    s = 5500 + boost
                else:
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

    if sctx in SC_PLACEMENT:
        targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
        # 壁警戒時は Victini(490, V-Force 240 が2エネで到達=最速OHKO)を前線に。
        pri = [490, 663, 1027, 358, 318] if wall else ATTACKER_PRIORITY
        rank = {cid: i for i, cid in enumerate(pri)}

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
