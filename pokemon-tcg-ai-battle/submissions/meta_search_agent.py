"""PTCG AI Battle 提出エージェント（本命・アーキタイプ検知型探索）。

中核アイデア: 相手デッキリストは不可視だが、相手 *盤面の固有ポケモン* から
アーキタイプ（buddy=メガルカリオ / Crustle=イワパレス壁 / Archaludon=ブリジュラス）は
特定できる。特定できたら「相手は既知の該当デッキ」と仮定して隠れ情報を復元し、cg.api の
search_begin による1手読み+ターン内rollout探索を回して最善手を選ぶ。未知の相手や復元失敗時は
軽量ヒューリスティックにフォールバックする。

＝ Crustle特攻(crustle_slayer)で実証した「盤面検知→既知デッキ仮定→探索インライン」を
全既知メタへ一般化したもの。探索の強さ(研究版 fire_slayer 総合0.73)を提出フォーマットの
まま引き出すのが狙い。自己完結（cg.api 以外を import しない・相手デッキ引数不要）。
"""
from __future__ import annotations

from collections import Counter

# --- 自分のデッキ: Fire非ex + Jamming Tower（対壁最適・全方位に競争力）------------
FIRE_DECK = (
    [663] * 4 + [358] * 4 + [1027] * 4 + [318] * 4
    + [1192] * 4 + [1224] * 4 + [1213] * 2 + [1152] * 4
    + [1102] * 4 + [1086] * 4 + [1123] * 2 + [1182] * 3
    + [1246] * 3
    + [2] * 14
)
assert len(FIRE_DECK) == 60

# --- 既知アーキタイプのデッキリスト（検知時に相手デッキとして仮定）----------------
CRUSTLE_DECK = (
    [344] * 4 + [345] * 4 + [1147] * 4 + [1159] * 1 + [1264] * 4 + [1212] * 4
    + [1224] * 4 + [18] * 4 + [11] * 4 + [1086] * 4 + [14] * 4 + [1] * 19
)
BUDDY_DECK = (
    [673] * 2 + [674] * 2 + [675] * 2 + [676] * 3 + [677] * 3 + [678] * 4
    + [1102] * 4 + [1123] * 2 + [1141] * 4 + [1142] * 4 + [1152] * 4 + [1159] * 1
    + [1182] * 2 + [1192] * 4 + [1227] * 4 + [1252] * 2 + [6] * 13
)
ARCHALUDON_DECK = (
    [992] * 4 + [190] * 4 + [57] * 2 + [1192] * 4 + [1227] * 4 + [1213] * 4
    + [1182] * 3 + [1097] * 4 + [1121] * 4 + [1152] * 4 + [1122] * 3 + [1123] * 2
    + [1159] * 1 + [1244] * 3 + [8] * 14
)
assert len(CRUSTLE_DECK) == 60 and len(BUDDY_DECK) == 60 and len(ARCHALUDON_DECK) == 60

# アーキタイプ判定シグナル（相手盤面/トラッシュの固有ポケモン等）
SIG_CRUSTLE = {344, 345, 18, 11, 14, 1159}          # Dwebble/Crustle/特殊エネ/HeroCape
SIG_BUDDY = {678, 677, 673, 674, 675, 676, 1141, 1142}  # MLucario/Riolu/Makuhita系/固有グッズ
SIG_ARCHALUDON = {992, 190, 57, 1244}               # Duraludon/Archaludon ex/Relicanth/FullMetalLab

ENERGY_ID = 2
JAMMING_TOWER = 1246
FIRE_TYPE = 2

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
        _CARD_TABLE, _ATTACK_TABLE = {}, {}


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


# ---------------------------------------------------------------------------
# アーキタイプ検知: 相手盤面/トラッシュの固有IDから既知デッキを推定
# ---------------------------------------------------------------------------
def _opp_visible_ids(op) -> set:
    ids = set()
    for area in ("active", "bench"):
        for p in (_g(op, area, []) or []):
            if p is None:
                continue
            ids.add(_g(p, "id"))
            for e in (_g(p, "energyCards", []) or []):
                ids.add(_g(e, "id"))
            for tl in (_g(p, "tools", []) or []):
                ids.add(_g(tl, "id"))
    for c in (_g(op, "discard", []) or []):
        ids.add(_g(c, "id"))
    return ids


def _detect_deck(cur, me):
    """検知できたら (assumed_opp_deck) を返す。未知なら None。"""
    players = _g(cur, "players", []) or []
    if len(players) < 2:
        return None
    ids = _opp_visible_ids(players[1 - me])
    # 固有性の高い順に判定（Archaludon/Crustle/Buddy はコア札が一意）
    if ids & {992, 190}:
        return ARCHALUDON_DECK
    if ids & {344, 345}:
        return CRUSTLE_DECK
    if ids & {678, 677}:
        return BUDDY_DECK
    # 補助シグナル（特殊エネ/固有グッズ）
    if ids & {18, 11, 14}:
        return CRUSTLE_DECK
    if ids & {1141, 1142}:
        return BUDDY_DECK
    if ids & {1244, 57}:
        return ARCHALUDON_DECK
    return None


# ---------------------------------------------------------------------------
# 隠れ情報復元（自分=FIRE_DECK, 相手=推定デッキ）
# ---------------------------------------------------------------------------
def _cards_in_play(pk) -> list:
    ids = [_g(pk, "id")]
    for k in ("energyCards", "tools", "preEvolution"):
        for c in (_g(pk, k, []) or []):
            ids.append(_g(c, "id"))
    return ids


def _visible_used(player) -> Counter:
    used: Counter = Counter()
    for c in (_g(player, "hand", []) or []):
        used[_g(c, "id")] += 1
    for area in ("active", "bench"):
        for pk in (_g(player, area, []) or []):
            if pk:
                for i in _cards_in_play(pk):
                    used[i] += 1
    for c in (_g(player, "discard", []) or []):
        used[_g(c, "id")] += 1
    return used


def _reconstruct(obs, opp_deck):
    cur = obs.get("current")
    if cur is None:
        return None
    me = cur["yourIndex"]
    opp = 1 - me
    mp, op = cur["players"][me], cur["players"][opp]
    my_unknown = list((Counter(FIRE_DECK) - _visible_used(mp)).elements())
    op_unknown = list((Counter(opp_deck) - _visible_used(op)).elements())
    dc, pz = mp["deckCount"], len(mp["prize"])
    odc, opz, ohc = op["deckCount"], len(op["prize"]), op["handCount"]
    if len(my_unknown) < dc + pz or len(op_unknown) < odc + opz + ohc:
        return None
    rec = {
        "your_deck": my_unknown[:dc], "your_prize": my_unknown[dc:dc + pz],
        "opp_deck": op_unknown[:odc], "opp_prize": op_unknown[odc:odc + opz],
        "opp_hand": op_unknown[odc + opz:odc + opz + ohc], "opp_active": [],
    }
    oa = op.get("active") or []
    if len(oa) > 0 and oa[0] is None:
        _ensure_tables()
        import cg.api as api  # noqa: PLC0415
        for cid in op_unknown:
            cd = _CARD_TABLE.get(cid)
            if cd and _g(cd, "basic") and _g(cd, "cardType") == api.CardType.POKEMON:
                rec["opp_active"] = [cid]
                break
        if not rec["opp_active"]:
            return None
    return rec


# ---------------------------------------------------------------------------
# 評価関数（サイド差 >> 相手削り + 自炎エネ組成 + Jamming）
# ---------------------------------------------------------------------------
def _eff_vs(aid, atk_type, defender) -> int:
    a = _attack_data(aid)
    dmg = int(_g(a, "damage", 0) or 0) if a is not None else 0
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


# 重み（研究版 state_eval と一致。この評価で fire_slayer は vs Crustle 0.56 を出した）
_W = {
    "prize_diff": 1000.0, "prize_value": 300.0, "hp_ratio": 120.0,
    "energy_ready": 90.0, "energy_extra": 15.0, "stage2": 60.0, "stage1": 30.0, "tool": 25.0,
    "can_ko": 250.0, "will_be_koed": 200.0, "damage_ratio": 80.0,
    "sc_poison": 40.0, "sc_burn": 30.0, "sc_sleep": 70.0, "sc_paralyze": 70.0, "sc_confuse": 35.0,
    "hand": 8.0, "deck": 1.5, "bench": 25.0, "total_energy": 6.0, "terminal": 100000.0,
    "fire_energy": 45.0, "jam": 120.0,
}


def _prize_value(p) -> int:
    cd = _card_data(_g(p, "id"))
    if cd is None:
        return 1
    return 3 if _g(cd, "megaEx") else (2 if _g(cd, "ex") else 1)


def _energy_req(p):
    cd = _card_data(_g(p, "id"))
    if cd is None:
        return None
    costs = [len(_g(a, "energies", []) or []) for a in
             (_attack_data(aid) for aid in (_g(cd, "attacks", []) or [])) if a is not None]
    return min(costs) if costs else None


def _best_dmg(p) -> int:
    cd = _card_data(_g(p, "id"))
    if cd is None:
        return 0
    have = len(_g(p, "energies", []) or [])
    best = 0
    for aid in (_g(cd, "attacks", []) or []):
        a = _attack_data(aid)
        if a is not None and have >= len(_g(a, "energies", []) or []):
            best = max(best, int(_g(a, "damage", 0) or 0))
    return best


def _eff_dmg_pk(attacker, defender) -> float:
    dmg = float(_best_dmg(attacker))
    if dmg <= 0 or defender is None:
        return dmg
    ad = _card_data(_g(attacker, "id"))
    dd = _card_data(_g(defender, "id"))
    if ad is None or dd is None:
        return dmg
    at = _g(ad, "energyType")
    if _g(dd, "weakness") is not None and at is not None and at == _g(dd, "weakness"):
        return dmg * 2.0
    if _g(dd, "resistance") is not None and at is not None and at == _g(dd, "resistance"):
        return max(0.0, dmg - 30.0)
    return dmg


def _pokemon_value(p) -> float:
    if p is None:
        return 0.0
    v = _W["prize_value"] * _prize_value(p)
    hp = float(_g(p, "hp", 0) or 0)
    mx = float(_g(p, "maxHp", 0) or 0)
    if mx > 0:
        v += _W["hp_ratio"] * max(0.0, min(1.0, hp / mx))
    have = len(_g(p, "energies", []) or [])
    req = _energy_req(p)
    if req is None:
        v += _W["energy_extra"] * have
    else:
        v += _W["energy_ready"] * min(have, req) + _W["energy_extra"] * max(0, have - req)
    cd = _card_data(_g(p, "id"))
    if cd is not None:
        if _g(cd, "stage2"):
            v += _W["stage2"]
        elif _g(cd, "stage1"):
            v += _W["stage1"]
    v += _W["tool"] * len(_g(p, "tools", []) or [])
    return v


def _sc_score(pl) -> float:
    s = 0.0
    for k, w in (("poisoned", "sc_poison"), ("burned", "sc_burn"), ("asleep", "sc_sleep"),
                 ("paralyzed", "sc_paralyze"), ("confused", "sc_confuse")):
        if _g(pl, k):
            s += _W[w]
    return s


def _iter_pk(pl):
    for area in ("active", "bench"):
        for p in (_g(pl, area, []) or []):
            if p is not None:
                yield p


def _eval(current, me) -> float:
    """研究版 state_eval + fire_slayer_eval を忠実にインライン。"""
    if current is None:
        return 0.0
    res = _g(current, "result", -1)
    if res is not None and res != -1:
        return _W["terminal"] if res == me else (-_W["terminal"] if res == (1 - me) else 0.0)
    players = _g(current, "players", []) or []
    if len(players) < 2 or me not in (0, 1):
        return 0.0
    mp, op = players[me], players[1 - me]
    s = 0.0
    # サイド差（支配項）
    s += _W["prize_diff"] * (len(_g(op, "prize", []) or []) - len(_g(mp, "prize", []) or []))
    # マテリアル差
    s += sum(_pokemon_value(p) for p in _iter_pk(mp)) - sum(_pokemon_value(p) for p in _iter_pk(op))

    def act(pl):
        a = _g(pl, "active", []) or []
        return a[0] if a else None
    ma, oa = act(mp), act(op)
    # 脅威/テンポ
    if ma is not None and oa is not None:
        d = _eff_dmg_pk(ma, oa)
        oh = float(_g(oa, "hp", 0) or 0)
        if oh > 0:
            s += (_W["can_ko"] + _W["damage_ratio"]) if d >= oh else _W["damage_ratio"] * (d / oh)
    if oa is not None and ma is not None:
        d = _eff_dmg_pk(oa, ma)
        mh = float(_g(ma, "hp", 0) or 0)
        if mh > 0:
            s -= (_W["will_be_koed"] + _W["damage_ratio"]) if d >= mh else _W["damage_ratio"] * (d / mh)
    s -= _sc_score(mp)
    s += _sc_score(op)
    # 資源
    s += _W["hand"] * (float(_g(mp, "handCount", 0) or 0) - float(_g(op, "handCount", 0) or 0))
    s += _W["deck"] * (float(_g(mp, "deckCount", 0) or 0) - float(_g(op, "deckCount", 0) or 0))
    s += _W["bench"] * (len(_g(mp, "bench", []) or []) - len(_g(op, "bench", []) or []))
    my_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pk(mp))
    op_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pk(op))
    s += _W["total_energy"] * (my_e - op_e)
    # 炎スレイヤー補正: 炎アタッカーのエネ組成 + Jamming Tower
    for p in _iter_pk(mp):
        cd = _card_data(_g(p, "id"))
        if cd is not None and _g(cd, "energyType") == FIRE_TYPE:
            s += _W["fire_energy"] * min(len(_g(p, "energies", []) or []), 3)
    for st in (_g(current, "stadium", []) or []):
        if _g(st, "id") == JAMMING_TOWER:
            s += _W["jam"]
            break
    return s


# ---------------------------------------------------------------------------
# 探索本体
# ---------------------------------------------------------------------------
def _search_action(obs, opp_deck, rollout_budget: int = 40):
    sel = obs.get("select")
    if sel is None:
        return None
    options = sel.get("option") or []
    n = len(options)
    if n == 0:
        return []
    cur = obs.get("current")
    if cur is None:
        return None
    me = cur["yourIndex"]
    mc = int(sel.get("maxCount", 1) or 1)
    rec = _reconstruct(obs, opp_deck)
    if rec is None:
        return None
    import cg.api as api  # noqa: PLC0415
    try:
        ob = api.to_observation_class(obs)
        root = api.search_begin(ob, rec["your_deck"], rec["your_prize"],
                                rec["opp_deck"], rec["opp_prize"],
                                rec["opp_hand"], rec["opp_active"])
    except Exception:
        return None

    def value_of(ns):
        c = ns.observation.current
        return _eval(c, me) if c is not None else 0.0

    def play_turn(ns):
        c0 = ns.observation.current
        if c0 is None:
            return ns
        actor = getattr(c0, "yourIndex", me)
        for _ in range(rollout_budget):
            c = ns.observation.current
            if c is None or getattr(c, "result", -1) != -1:
                return ns
            if getattr(c, "yourIndex", actor) != actor:
                return ns
            s = ns.observation.select
            if s is None or not s.option:
                return ns
            mc2 = int(getattr(s, "maxCount", 1) or 1)
            nopt = len(s.option)
            if mc2 <= 1:
                bv, bns = float("-inf"), None
                for i in range(nopt):
                    try:
                        nx = api.search_step(ns.searchId, [i])
                    except Exception:
                        continue
                    cc = nx.observation.current
                    v = _eval(cc, actor) if cc else 0.0
                    if v > bv:
                        bv, bns = v, nx
                if bns is None:
                    return ns
                ns = bns
            else:
                try:
                    ns = api.search_step(ns.searchId, list(range(min(mc2, nopt))))
                except Exception:
                    return ns
        return ns

    def score(sel_list):
        try:
            ns = api.search_step(root.searchId, sel_list)
        except Exception:
            return None
        c = ns.observation.current
        if c is not None and getattr(c, "result", -1) == -1:
            ns = play_turn(ns)
        return value_of(ns)

    try:
        if mc <= 1:
            best_i, best_s = None, float("-inf")
            for i in range(n):
                sc = score([i])
                if sc is not None and sc > best_s:
                    best_s, best_i = sc, i
            out = [best_i] if best_i is not None else None
        else:
            chosen, remaining = [], set(range(n))
            while len(chosen) < mc and remaining:
                bi, bs = None, float("-inf")
                for i in list(remaining):
                    sc = score(sorted(chosen + [i]))
                    if sc is not None and sc > bs:
                        bs, bi = sc, i
                if bi is None:
                    break
                chosen.append(bi)
                remaining.discard(bi)
            out = sorted(chosen) if chosen else None
    finally:
        try:
            api.search_end()
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# フォールバック: 軽量炎ヒューリスティック
# ---------------------------------------------------------------------------
def _heuristic_action(obs):
    sel = obs.get("select")
    cur = obs.get("current")
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
    if sctx in (SC_IS_FIRST, SC_MULLIGAN):
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]
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
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ATTACK:
                d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                s = (10000 + d + (50000 if (oh > 0 and d >= oh) else 0)) if d >= 120 else 200
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                s = 8000 + (300 if _g(o, "inPlayArea") == AREA_ACTIVE else 0)
            elif t == T_PLAY:
                s = 5500
            elif t == T_RETREAT:
                s = 1500
            elif t == T_END:
                s = 100
            else:
                s = 50
            scores.append(s)
        return [max(range(n), key=lambda i: scores[i])]
    if sctx in SC_PLACEMENT:
        targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
        pri = [663, 1027, 358, 318]
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
        return [scored[0]] if mc <= 1 else sorted(scored[:max(mc, mn)])
    for i, o in enumerate(options):
        if _g(o, "playerIndex") == (1 - me) and _g(o, "area") == AREA_ACTIVE:
            return [i]
        if _g(o, "cardId") == ENERGY_ID:
            return [i]
    if mc <= 1:
        return [0]
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


# ---------------------------------------------------------------------------
# エントリ
# ---------------------------------------------------------------------------
def agent(obs_dict: dict, configuration=None) -> list[int]:
    sel = obs_dict.get("select") if isinstance(obs_dict, dict) else _g(obs_dict, "select")
    cur = obs_dict.get("current") if isinstance(obs_dict, dict) else _g(obs_dict, "current")
    if sel is None:
        return list(FIRE_DECK)
    me = _g(cur, "yourIndex", 0) if cur is not None else 0
    if cur is not None:
        opp_deck = _detect_deck(cur, me)
        if opp_deck is not None:
            try:
                out = _search_action(obs_dict, opp_deck)
            except Exception:
                out = None
            if out:
                return out
    return _heuristic_action(obs_dict)
