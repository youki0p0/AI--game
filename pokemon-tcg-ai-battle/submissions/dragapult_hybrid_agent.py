"""PTCG AI Battle 提出エージェント(モデル2): Dragapult ex ハイブリッド（模倣プライア+探索）。

トップエージェント(勝率0.87)のリプレイ14試合から学習した模倣ランキング(FITTED_MAIN)で有望手を
絞り込み、エンジンsandboxの深さ3ロールアウト+Dragapult専用eval(散布蓄積/エネ型[炎+超])で検証して
指す。散布(ctx14)は相手の進化前・エンジン狙撃、エネ選択(ctx21)は[炎+超]ペア完成、山サーチは
トップの優先表。未対応コンテキストは汎用探索にフォールバック。

★ 提出安全化: 末尾の唯一の最終 def が agent(observation, ...)。全例外を握り空アクション自滅を根絶。
"""
from __future__ import annotations

import dataclasses
import enum
from collections import Counter
from typing import Any

# --- Archaludon ex デッキ（archaludon_agent.py と同一）-----------------------------
DRAG_DECK = ([2]*4+[5]*4+[119]*4+[120]*4+[121]*3+[140]*1+[184]*1+[235]*2+[1071]*1
             +[1079]*2+[1080]*1+[1086]*4+[1097]*2+[1120]*4+[1121]*4+[1152]*3+[1156]*1
             +[1182]*3+[1198]*4+[1210]*2+[1227]*4+[1256]*2)
assert len(DRAG_DECK) == 60, len(DRAG_DECK)

# 探索パラメータ
N_TURNS = 3            # 3手読み(自分→相手→自分)。奇数深さ=自ターンで評価=空想相手誤差に頑健。
ROLLOUT_BUDGET = 25    # 1ターン内で貪欲に進める最大ステップ数

# ---------------------------------------------------------------------------
# カード/技テーブル（cg.api から一度だけロード、失敗しても動く）
# ---------------------------------------------------------------------------
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
# 静的評価 state_eval（将棋流: サイド差 >> マテリアル > 脅威 > 資源）
# ---------------------------------------------------------------------------
W_PRIZE_DIFF = 1000.0
W_PRIZE_VALUE = 300.0
W_HP_RATIO = 120.0
W_ENERGY_READY = 90.0
W_ENERGY_EXTRA = 15.0
W_STAGE2 = 60.0
W_STAGE1 = 30.0
W_TOOL = 25.0
W_CAN_KO = 250.0
W_WILL_BE_KOED = 200.0
W_DAMAGE_RATIO = 80.0
W_SC = {"poisoned": 40.0, "burned": 30.0, "asleep": 70.0, "paralyzed": 70.0, "confused": 35.0}
W_HAND = 8.0
W_DECK = 1.5
W_BENCH = 25.0
W_TOTAL_ENERGY = 6.0
TERMINAL = 100000.0


def _iter_pokemon(player):
    if player is None:
        return
    for p in (_g(player, "active", []) or []):
        if p is not None:
            yield p
    for p in (_g(player, "bench", []) or []):
        if p is not None:
            yield p


def _active(player):
    arr = _g(player, "active", []) or []
    return arr[0] if len(arr) > 0 else None


def _prize_value(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return 1
    if _g(d, "megaEx"):
        return 3
    if _g(d, "ex"):
        return 2
    return 1


def _energy_requirement(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return None
    costs = []
    for aid in (_g(d, "attacks", []) or []):
        a = _attack_data(aid)
        if a is None:
            continue
        costs.append(len(_g(a, "energies", []) or []))
    return min(costs) if costs else None


def _best_attack_damage(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return 0
    have = len(_g(pk, "energies", []) or [])
    best = 0
    for aid in (_g(d, "attacks", []) or []):
        a = _attack_data(aid)
        if a is None:
            continue
        if have >= len(_g(a, "energies", []) or []):
            best = max(best, int(_g(a, "damage", 0) or 0))
    return best


def _pokemon_value(pk):
    if pk is None:
        return 0.0
    s = W_PRIZE_VALUE * _prize_value(pk)
    hp = float(_g(pk, "hp", 0) or 0)
    mhp = float(_g(pk, "maxHp", 0) or 0)
    if mhp > 0:
        s += W_HP_RATIO * max(0.0, min(1.0, hp / mhp))
    have = len(_g(pk, "energies", []) or [])
    req = _energy_requirement(pk)
    if req is None:
        s += W_ENERGY_EXTRA * have
    else:
        s += W_ENERGY_READY * min(have, req) + W_ENERGY_EXTRA * max(0, have - req)
    d = _card_data(_g(pk, "id"))
    if d is not None:
        if _g(d, "stage2"):
            s += W_STAGE2
        elif _g(d, "stage1"):
            s += W_STAGE1
    s += W_TOOL * len(_g(pk, "tools", []) or [])
    return s


def _effective_damage(attacker, defender):
    dmg = float(_best_attack_damage(attacker))
    if dmg <= 0:
        return dmg
    ad = _card_data(_g(attacker, "id"))
    dd = _card_data(_g(defender, "id"))
    if ad is None or dd is None:
        return dmg
    at = _g(ad, "energyType")
    weak = _g(dd, "weakness")
    resist = _g(dd, "resistance")
    if weak is not None and at is not None and at == weak:
        return dmg * 2.0
    if resist is not None and at is not None and at == resist:
        return max(0.0, dmg - 30.0)
    return dmg


def _sc_score(player):
    s = 0.0
    for k, v in W_SC.items():
        if _g(player, k):
            s += v
    return s


def state_eval(current, me):
    if current is None:
        return 0.0
    res = _g(current, "result", -1)
    if res is not None and res != -1:
        if res == 2:
            return 0.0
        return TERMINAL if res == me else -TERMINAL
    players = _g(current, "players", []) or []
    if len(players) < 2 or me not in (0, 1):
        return 0.0
    mp, op = players[me], players[1 - me]

    score = 0.0
    # サイド差（支配項）
    score += W_PRIZE_DIFF * (len(_g(op, "prize", []) or []) - len(_g(mp, "prize", []) or []))
    # マテリアル差
    score += sum(_pokemon_value(p) for p in _iter_pokemon(mp)) \
        - sum(_pokemon_value(p) for p in _iter_pokemon(op))
    # 脅威/テンポ
    ma, oa = _active(mp), _active(op)
    if ma is not None and oa is not None:
        dmg = _effective_damage(ma, oa)
        ohp = float(_g(oa, "hp", 0) or 0)
        if ohp > 0:
            if dmg >= ohp:
                score += W_CAN_KO + W_DAMAGE_RATIO
            else:
                score += W_DAMAGE_RATIO * (dmg / ohp)
        dmg2 = _effective_damage(oa, ma)
        mhp = float(_g(ma, "hp", 0) or 0)
        if mhp > 0:
            if dmg2 >= mhp:
                score -= W_WILL_BE_KOED + W_DAMAGE_RATIO
            else:
                score -= W_DAMAGE_RATIO * (dmg2 / mhp)
    score -= _sc_score(mp)
    score += _sc_score(op)
    # 資源差
    score += W_HAND * (float(_g(mp, "handCount", 0) or 0) - float(_g(op, "handCount", 0) or 0))
    score += W_DECK * (float(_g(mp, "deckCount", 0) or 0) - float(_g(op, "deckCount", 0) or 0))
    score += W_BENCH * (len(_g(mp, "bench", []) or []) - len(_g(op, "bench", []) or []))
    me_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(mp))
    op_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(op))
    score += W_TOTAL_ENERGY * (me_e - op_e)
    # --- Dragapult 専用ボーナス: 散布蓄積 + エネ型[炎(2)+超(5)]ペア ---
    for pk in _iter_pokemon(op):
        hp2 = float(_g(pk, "hp", 0) or 0); mhp2 = float(_g(pk, "maxHp", 0) or 0)
        if mhp2 > 0:
            score += 4.0 * (mhp2 - hp2)
            if 0 < hp2 <= 70:
                score += 150.0
            if 0 < hp2 <= 30:
                score += 150.0
    actv = _active(mp)
    for pk in _iter_pokemon(mp):
        if _g(pk, "id") not in (121, 120, 119):
            continue
        es = [_g(e, "id") for e in (_g(pk, "energyCards", []) or [])]
        r_, p_ = es.count(2), es.count(5)
        if r_ >= 1 and p_ >= 1:
            score += 300.0 + (200.0 if (pk is actv and _g(pk, "id") == 121) else 0.0)
        elif r_ + p_ >= 2:
            score += 40.0
        elif r_ + p_ == 1:
            score += 60.0
    return score


# ---------------------------------------------------------------------------
# 隠れ情報の再構成（自デッキ=DRAG_DECK から）
# ---------------------------------------------------------------------------
def _cards_in_play(pk):
    ids = [pk["id"]] if isinstance(pk, dict) else [_g(pk, "id")]
    for k in ("energyCards", "tools", "preEvolution"):
        for c in (_g(pk, k) or []):
            ids.append(_g(c, "id"))
    return [i for i in ids if i is not None]


def _visible_used(player):
    used = Counter()
    for c in (_g(player, "hand") or []):
        used[_g(c, "id")] += 1
    for area in ("active", "bench"):
        for pk in (_g(player, area) or []):
            if pk:
                for i in _cards_in_play(pk):
                    used[i] += 1
    for c in (_g(player, "discard") or []):
        used[_g(c, "id")] += 1
    return used


def _reconstruct(obs):
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    if cur is None:
        return None
    me = _g(cur, "yourIndex", 0)
    opp = 1 - me
    players = _g(cur, "players", []) or []
    if len(players) < 2:
        return None
    full = Counter(DRAG_DECK)
    mp, op = players[me], players[opp]
    my_unknown = list((full - _visible_used(mp)).elements())
    op_unknown = list((full - _visible_used(op)).elements())
    dc, pz = _g(mp, "deckCount", 0), len(_g(mp, "prize", []) or [])
    odc, opz, ohc = _g(op, "deckCount", 0), len(_g(op, "prize", []) or []), _g(op, "handCount", 0)
    if len(my_unknown) < dc + pz or len(op_unknown) < odc + opz + ohc:
        return None
    rec = {
        "your_deck": my_unknown[:dc],
        "your_prize": my_unknown[dc:dc + pz],
        "opp_deck": op_unknown[:odc],
        "opp_prize": op_unknown[odc:odc + opz],
        "opp_hand": op_unknown[odc + opz:odc + opz + ohc],
        "opp_active": [],
    }
    oa = _g(op, "active") or []
    if len(oa) > 0 and oa[0] is None:
        import cg.api as api  # noqa: PLC0415
        _ensure_tables()
        picked = None
        for cid in op_unknown:
            cd = _CARD_TABLE.get(cid)
            if cd and _g(cd, "basic") and _g(cd, "cardType") == api.CardType.POKEMON:
                picked = cid
                break
        if picked is None:
            return None
        rec["opp_active"] = [picked]
    return rec


# ---------------------------------------------------------------------------
# 1手読み探索パイロット
# ---------------------------------------------------------------------------
def _fallback(obs):
    """探索不能時の安全手（簡易 setup-then-attack 相当）。空アクションにしない。"""
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    if sel is None:
        return list(DRAG_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


FITTED_MAIN = {"PLAY:1079": 5.82, "PLAY:119": 4.19, "ATTACH:A:1071": 3.55, "ABILITY": 3.24, "PLAY:1120": 3.17, "EVOLVE:121": 2.56, "PLAY:140": 2.28, "EVOLVE:120": 1.74, "ATTACK:Phantom Dive": 1.39, "PLAY:235": 1.33, "PLAY:1256": 1.27, "PLAY:184": 1.18, "PLAY:1152": 1.05, "PLAY:1086": 0.91, "PLAY:1227": 0.87, "ATTACH:B:121": 0.82, "ATTACH:A:121": 0.76, "PLAY:1080": 0.74, "ATTACH:A:140": 0.73, "ATTACH:B:119": 0.70, "PLAY:1198": 0.60, "PLAY:1182": 0.45, "PLAY:1210": 0.38, "PLAY:1121": 0.37, "ATTACH:A:235": 0.31, "ATTACH:B:120": -0.12, "PLAY:1071": -0.15, "PLAY:1097": -0.23, "ATTACH:A:119": -0.36, "ATTACH:A:120": -0.48, "ATTACH:A:184": -0.54, "ATTACK:Itchy Pollen": -0.86, "ATTACK:Jet Headbutt": -0.87, "ATTACK:Bite": -1.09, "RETREAT": -1.45, "ATTACK:Petty Grudge": -2.05, "END": -2.23, "ATTACK:Dragon Headbutt": -4.12, "ATTACH:B:1071": -6.13, "ATTACH:B:184": -6.47, "ATTACH:B:235": -6.49, "ATTACH:B:140": -6.80}
SEARCH_PRIO_D = [120, 5, 121, 119, 184, 235, 140, 2, 1071, 1079, 1227, 1182, 1086, 1121]
_EVO_SET_D = None


def _evolving_basic(cid):
    global _EVO_SET_D
    _ensure_tables()
    if _EVO_SET_D is None:
        _EVO_SET_D = {(_g(c, "evolvesFrom") or "") for c in _CARD_TABLE.values()} - {""}
    c = _CARD_TABLE.get(cid)
    return bool(c) and bool(_g(c, "basic")) and _g(c, "name", "") in _EVO_SET_D


def _hybrid_impl(obs):
    """模倣プライア+ロールアウト検証のメインロジック。未対応ctxは None を返し汎用探索へ。"""
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    if sel is None:
        return list(DRAG_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    ctx = _g(sel, "context")
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    me = _g(cur, "yourIndex", 0) if cur else 0
    pls = (_g(cur, "players", []) or []) if cur else []
    mp_ = pls[me] if len(pls) > me else {}
    _ensure_tables()

    if ctx == 41:  # 必ず後攻
        for i, o in enumerate(opts):
            if _g(o, "type") == 2:
                return [i]
        return [0]

    def hand_cid(idx):
        hand = _g(mp_, "hand", []) or []
        return _g(hand[idx], "id") if (idx is not None and 0 <= idx < len(hand)) else None

    def inplay(pl, area, idx):
        if pl is None or len(pls) <= pl:
            return None
        arr = _g(pls[pl], "active") if area == 4 else (_g(pls[pl], "bench") if area == 5 else None)
        if isinstance(arr, list) and idx is not None and 0 <= idx < len(arr):
            return arr[idx]
        return None

    if ctx == 0 and mc <= 1 and cur is not None:
        def lab(o):
            t = _g(o, "type")
            if t == 7:
                return "PLAY:%s" % hand_cid(_g(o, "index"))
            if t == 9:
                return "EVOLVE:%s" % hand_cid(_g(o, "index"))
            if t == 8:
                tgt = inplay(me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
                return "ATTACH:%s:%s" % ("A" if _g(o, "inPlayArea") == 4 else "B", _g(tgt, "id"))
            if t == 13:
                a = _attack_data(_g(o, "attackId"))
                return "ATTACK:%s" % (_g(a, "name", "?") if a else "?")
            return {10: "ABILITY", 12: "RETREAT", 14: "END", 11: "DISCARD"}.get(t, "t%s" % t)
        labels = [lab(o) for o in opts]
        pri = sorted(((FITTED_MAIN.get(labels[i], -3.0), i) for i in range(n)), reverse=True)
        cands = [i for _, i in pri[:4]]
        atk = max((i for i in range(n) if labels[i].startswith("ATTACK:")),
                  key=lambda i: FITTED_MAIN.get(labels[i], -3.0), default=None)
        att = max((i for i in range(n) if labels[i].startswith("ATTACH:")
                   and labels[i].split(":")[-1] in ("121", "120", "119")),
                  key=lambda i: FITTED_MAIN.get(labels[i], -3.0), default=None)
        for e_ in (atk, att):
            if e_ is not None and e_ not in cands:
                cands.append(e_)
        if len(cands) == 1:
            return [cands[0]]
        rec = _reconstruct(obs)
        if rec is None:
            return [cands[0]]
        import cg.api as api  # noqa: PLC0415
        try:
            ob = api.to_observation_class(obs)
            root = api.search_begin(ob, rec["your_deck"], rec["your_prize"],
                                    rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"])
        except Exception:
            return [cands[0]]

        def leafv(ns):
            c = ns.observation.current
            if c is None:
                return 0.0
            r = getattr(c, "result", -1)
            if r != -1:
                return 1e9 if r == me else (-1e9 if r == (1 - me) else 0.0)
            return float(state_eval(c, me))

        def play_turn(ns):
            c0 = ns.observation.current
            if c0 is None:
                return ns
            actor = getattr(c0, "yourIndex", me)
            for _ in range(30):
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
                    bv, bn = float("-inf"), None
                    for j in range(nopt):
                        try:
                            nx = api.search_step(ns.searchId, [j])
                        except Exception:
                            continue
                        cc = nx.observation.current
                        rr = getattr(cc, "result", -1) if cc else -1
                        v = (1e9 if rr == actor else -1e9 if rr == (1 - actor)
                             else (state_eval(cc, actor) if cc else 0.0))
                        if v > bv:
                            bv, bn = v, nx
                    if bn is None:
                        return ns
                    ns = bn
                else:
                    try:
                        ns = api.search_step(ns.searchId, list(range(min(mc2, nopt))))
                    except Exception:
                        return ns
            return ns
        best_i, best_v = cands[0], float("-inf")
        try:
            for i in cands:
                try:
                    ns = api.search_step(root.searchId, [i])
                except Exception:
                    continue
                for _ in range(3):
                    c = ns.observation.current
                    if c is None or getattr(c, "result", -1) != -1:
                        break
                    ns = play_turn(ns)
                v = leafv(ns)
                if v > best_v:
                    best_v, best_i = v, i
        finally:
            try:
                api.search_end()
            except Exception:
                pass
        return [best_i]

    if ctx == 14:  # 散布
        rem = int(_g(sel, "remainDamageCounter", 0) or 0)
        def sc(i):
            o = opts[i]
            pl = _g(o, "playerIndex")
            pk = inplay(pl, _g(o, "area"), _g(o, "index"))
            if pk is None:
                return -1e18
            if pl is None or pl == me:
                return -1e9
            hp = float(_g(pk, "hp", 0) or 0)
            cid = _g(pk, "id")
            cd = _CARD_TABLE.get(cid)
            if rem > 0 and hp <= rem * 10:
                return 100000 + (2000 if (_g(cd, "ex") or _g(cd, "megaEx")) else 0) - hp * 10
            if _evolving_basic(cid):
                return 5000 - hp
            return 1000 - hp * 0.5
        order = sorted(range(n), key=sc, reverse=True)
        if mc <= 1:
            return [order[0]]
        return sorted(order[:max(mn, min(mc, n))])

    if ctx == 21:  # エネ型: [炎+超] ペア完成
        need = None
        for pk in list(_g(mp_, "active", []) or []) + list(_g(mp_, "bench", []) or []):
            if pk is None or _g(pk, "id") not in (121, 120, 119):
                continue
            es = [_g(e, "id") for e in (_g(pk, "energyCards", []) or [])]
            if 2 in es and 5 not in es:
                need = 5
                break
            if 5 in es and 2 not in es:
                need = 2
                break
        if need is None:
            need = 5
        for i, o in enumerate(opts):
            if _g(o, "cardId") == need:
                return [i]
        return [0]

    if ctx in (7, 8):  # 山サーチ
        deck = _g(sel, "deck")
        def cid_of(o):
            c = _g(o, "cardId")
            if c is None and deck is not None:
                idx = _g(o, "index")
                if idx is not None and 0 <= idx < len(deck):
                    c = _g(deck[idx], "id")
            return c
        rank = {cid: r for r, cid in enumerate(SEARCH_PRIO_D)}
        order = sorted(range(n), key=lambda i: rank.get(cid_of(opts[i]), 999))
        if mc <= 1:
            return [order[0]]
        return sorted(order[:max(mn, min(mc, n))])

    return None  # 未対応 → 汎用探索へ


def _search_impl(obs):
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    if sel is None:
        return list(DRAG_DECK)  # デッキ選択フェーズ
    options = _g(sel, "option", []) or []
    n = len(options)
    if n == 0:
        return []
    max_count = int(_g(sel, "maxCount", 1) or 1)
    min_count = int(_g(sel, "minCount", 0) or 0)
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    if cur is None:
        return _fallback(obs)
    me = _g(cur, "yourIndex", 0)

    rec = _reconstruct(obs)
    if rec is None:
        return _fallback(obs)

    import cg.api as api  # noqa: PLC0415
    try:
        ob = api.to_observation_class(obs)
        root = api.search_begin(
            ob, rec["your_deck"], rec["your_prize"],
            rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"],
        )
    except Exception:
        return _fallback(obs)

    def value_of(ns):
        c = ns.observation.current
        if c is None:
            return 0.0
        r = getattr(c, "result", -1)
        if r != -1:
            return 1e9 if r == me else (-1e9 if r == (1 - me) else 0.0)
        return float(state_eval(c, me))

    def actor_value(ns, actor):
        c = ns.observation.current
        if c is None:
            return 0.0
        r = getattr(c, "result", -1)
        if r != -1:
            return 1e9 if r == actor else (-1e9 if r == (1 - actor) else 0.0)
        return float(state_eval(c, actor))

    def play_turn(ns):
        c0 = ns.observation.current
        if c0 is None:
            return ns
        actor = getattr(c0, "yourIndex", me)
        for _ in range(ROLLOUT_BUDGET):
            c = ns.observation.current
            if c is None or getattr(c, "result", -1) != -1:
                return ns
            if getattr(c, "yourIndex", actor) != actor:
                return ns
            s = ns.observation.select
            if s is None or not s.option:
                return ns
            mc = int(getattr(s, "maxCount", 1) or 1)
            nopt = len(s.option)
            if mc <= 1:
                best_v, best_ns = float("-inf"), None
                for i in range(nopt):
                    try:
                        nxt = api.search_step(ns.searchId, [i])
                    except Exception:
                        continue
                    v = actor_value(nxt, actor)
                    if v > best_v:
                        best_v, best_ns = v, nxt
                if best_ns is None:
                    return ns
                ns = best_ns
            else:
                try:
                    ns = api.search_step(ns.searchId, list(range(min(mc, nopt))))
                except Exception:
                    return ns
        return ns

    def score_of(select_list):
        try:
            ns = api.search_step(root.searchId, select_list)
        except Exception:
            return None
        for _ in range(N_TURNS):
            c = ns.observation.current
            if c is None or getattr(c, "result", -1) != -1:
                break
            ns = play_turn(ns)
        return value_of(ns)

    try:
        if max_count <= 1:
            best_i, best_s = None, float("-inf")
            for i in range(n):
                s = score_of([i])
                if s is not None and s > best_s:
                    best_s, best_i = s, i
            result = [best_i] if best_i is not None else _fallback(obs)
        else:
            chosen, remaining = [], set(range(n))
            cur_score = score_of([]) if min_count == 0 else None
            while len(chosen) < max_count and remaining:
                best_i, best_s = None, float("-inf")
                for i in list(remaining):
                    s = score_of(sorted(chosen + [i]))
                    if s is not None and s > best_s:
                        best_s, best_i = s, i
                if best_i is None:
                    break
                if len(chosen) >= min_count and cur_score is not None and best_s <= cur_score:
                    break
                chosen.append(best_i)
                remaining.discard(best_i)
                cur_score = best_s
            if len(chosen) < min_count:
                for i in range(n):
                    if i not in chosen:
                        chosen.append(i)
                    if len(chosen) >= min_count:
                        break
            result = sorted(chosen) if chosen else _fallback(obs)
    finally:
        try:
            api.search_end()
        except Exception:
            pass
    return result


def _safe_default(observation):
    """絶対にブリックしない保険手。空アクション自滅を根絶する。"""
    sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
    if sel is None:
        return list(DRAG_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


# Kaggle エントリ: 末尾の唯一の最終 def。全例外を握り *空アクション自滅を根絶*。
def agent(observation, configuration=None):
    try:
        out = _hybrid_impl(observation)
        if out is None:
            out = _search_impl(observation)
    except Exception:
        return _safe_default(observation)
    try:
        sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
        if sel is None:
            return out if (isinstance(out, list) and len(out) == 60) else list(DRAG_DECK)
        opts = _g(sel, "option", []) or []
        n = len(opts)
        if n == 0:
            return []
        mc = int(_g(sel, "maxCount", 1) or 1)
        mn = int(_g(sel, "minCount", 0) or 0)
        ok = (isinstance(out, list) and len(out) >= max(1, mn) and len(out) <= mc
              and len(set(out)) == len(out)
              and all(isinstance(i, int) and 0 <= i < n for i in out))
        return out if ok else _safe_default(observation)
    except Exception:
        return _safe_default(observation)
