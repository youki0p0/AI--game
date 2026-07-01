"""PTCG AI Battle 提出エージェント（イワパレス特攻）: Fire非ex + 探索でCrustleを割る。

狙い: 天敵イワパレス(Crustle, 特性しんぴのいしやど=exの技ダメージ無効)を *提出可能な
自己完結フォーマット* で倒す。相手デッキは不可視だが、相手 *盤面* から Crustle を
認識できるので「相手はCrustleデッキ」と仮定して隠れ情報を復元し、その場で1手読み探索を
回してOHKOライン（Volcanion Backfire 130→弱点x2=260 等）を組み立てる。

なぜ探索か: ルールベースでは「3エネの弱点OHKO」を回復壁相手に組成できず vs Crustle 0.0x。
盤面シミュレーションする探索なら組成でき、実測 vs Crustle 0.5+ を達成した（研究成果）。
本ファイルはその探索を cg.api だけで自己完結させ、提出できる形にしたもの。

構成:
  - デッキ = Fire非ex + Jamming Tower3（ヒーローマント無効化）。
  - 相手盤面に Crustle系シグナルを検知したら「特攻モード」= 相手をCRUSTLE_DECKと仮定して
    search_begin による1手読み+ターン内rolloutを実行。
  - 非検知/復元失敗/例外時は 軽量な炎ヒューリスティックにフォールバック（安全策）。

自己完結（cg.api 以外を import しない）。observation(dict) → list[int]。
"""
from __future__ import annotations

from collections import Counter

# --- デッキ: Fire非ex + Jamming Tower（対Crustle最適化, fire_slayer と同構成）--------
FIRE_DECK = (
    [663] * 4 + [358] * 4 + [1027] * 4 + [318] * 4          # Volcanion/Ogerpon/Turtonator/Ho-Oh
    + [1192] * 4 + [1224] * 4 + [1213] * 2 + [1152] * 4     # Carmine/Cheren/Judge/PokéPad
    + [1102] * 4 + [1086] * 4 + [1123] * 2 + [1182] * 3     # DuskBall/BuddyPoffin/Switch/Boss
    + [1246] * 3                                            # Jamming Tower
    + [2] * 14                                              # Fire energy
)
assert len(FIRE_DECK) == 60

# 特攻の仮想敵: Day-1 Crustle 壁デッキ（検知時に相手デッキとして仮定→隠れ情報復元）
CRUSTLE_DECK = (
    [344] * 4 + [345] * 4 + [1147] * 4 + [1159] * 1 + [1264] * 4 + [1212] * 4
    + [1224] * 4 + [18] * 4 + [11] * 4 + [1086] * 4 + [14] * 4 + [1] * 19
)
assert len(CRUSTLE_DECK) == 60

ENERGY_ID = 2
JAMMING_TOWER = 1246
CRUSTLE_POKEMON = {344, 345}
CRUSTLE_SP_ENERGY = {18, 11, 14}
HERO_CAPE = 1159
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
# Crustle 検知
# ---------------------------------------------------------------------------
def _detect_wall(cur, me) -> bool:
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


# ---------------------------------------------------------------------------
# 隠れ情報の復元（自分=FIRE_DECK, 相手=CRUSTLE_DECK と仮定）
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


def _reconstruct(obs):
    cur = obs.get("current")
    if cur is None:
        return None
    me = cur["yourIndex"]
    opp = 1 - me
    mp, op = cur["players"][me], cur["players"][opp]
    my_unknown = list((Counter(FIRE_DECK) - _visible_used(mp)).elements())
    op_unknown = list((Counter(CRUSTLE_DECK) - _visible_used(op)).elements())
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
# コンパクト評価関数（Crustle戦向け: サイド差 >> 相手削り + 自炎エネ組成 + Jamming）
# ---------------------------------------------------------------------------
def _eval(current, me) -> float:
    if current is None:
        return 0.0
    res = _g(current, "result", -1)
    if res is not None and res != -1:
        return 1e9 if res == me else (-1e9 if res == (1 - me) else 0.0)
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    mp, op = players[me], players[1 - me]
    s = 0.0
    # サイド差（支配項）: 残サイドが少ない方が勝ち
    my_rem = len(_g(mp, "prize", []) or [])
    op_rem = len(_g(op, "prize", []) or [])
    s += 2000.0 * (op_rem - my_rem)

    def act(pl):
        a = _g(pl, "active", []) or []
        return a[0] if a else None
    oa, ma = act(op), act(mp)
    # 相手アクティブへの削り進捗（回復で見えなくなるのを補助）
    if oa is not None:
        hp = float(_g(oa, "hp", 0) or 0)
        mx = float(_g(oa, "maxHp", 0) or 0)
        if mx > 0:
            s += 3.0 * max(0.0, mx - hp)
    # 自軍: サイド価値 + 炎アタッカーのエネ組成(OHKO到達) + HP
    for area in ("active", "bench"):
        for p in (_g(mp, area, []) or []):
            if p is None:
                continue
            cd = _card_data(_g(p, "id"))
            s += 120.0  # 盤面存在
            if cd is not None and _g(cd, "energyType") == FIRE_TYPE:
                s += 45.0 * min(len(_g(p, "energies", []) or []), 3)
        for p in (_g(op, area, []) or []):
            if p is not None:
                s -= 100.0
    # Jamming Tower（ヒーローマント無効化）
    for st in (_g(current, "stadium", []) or []):
        if _g(st, "id") == JAMMING_TOWER:
            s += 120.0
            break
    return s


# ---------------------------------------------------------------------------
# 特攻モード: 相手をCrustleと仮定して1手読み+ターン内rollout
# ---------------------------------------------------------------------------
def _search_action(obs, rollout_budget: int = 40):
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
    rec = _reconstruct(obs)
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
# フォールバック: 軽量な炎ヒューリスティック（非Crustle/探索失敗時）
# ---------------------------------------------------------------------------
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
    # Crustle 検知時のみ探索（特攻）。失敗時はヒューリスティックへ。
    if cur is not None and _detect_wall(cur, me):
        try:
            out = _search_action(obs_dict)
        except Exception:
            out = None
        if out:
            return out
    return _heuristic_action(obs_dict)
