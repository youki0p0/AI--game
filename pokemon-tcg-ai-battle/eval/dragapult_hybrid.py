"""Dragapult ハイブリッドパイロット: 模倣プライア(手の絞り込み) + 深い探索(検証) + 専用eval。

構成（各部品は実測で効果確認済み）:
  1. MAIN: フィット済み模倣ランキング(dragapult_top_pilot.FITTED_MAIN)で有望手 top-K に絞り、
     各候補をエンジンsandboxで深さ3ロールアウトして専用evalで採点、最良を選ぶ。
     （模倣単体=勝率に変換されず / 汎用探索単体=0.135。絞り込み+検証で両者の弱点を打ち消す）
  2. 専用eval = state_eval + 散布ダメージ蓄積ボーナス(実測 0.113→0.200)
     + エネ型ボーナス（Phantom Dive のコストは [炎+超]。同色2枚の無駄付けを罰する）
  3. ctx14散布 = KO刈り取り(低HP優先) > 進化前狙撃(Duraludon等) > 大物に蓄積
  4. ctx21エネ選択 = [炎+超] ペアを完成させる型を選ぶ
  5. その他は dragapult_top_pilot と同じ（後攻/サーチ表/フォールバック）
"""
from __future__ import annotations

from .engine_driver import _ensure_engine_on_path
from .dragapult_top_pilot import (DRAG_DECK, FITTED_MAIN, SEARCH_PRIO,
                                  DRAGAPULT, DRAKLOAK, DREEPY, _g,
                                  _tables, _is_evolving_basic)
from .state_eval import state_eval

R_ENERGY, P_ENERGY = 2, 5


def _iter_my(pl):
    for x in (_g(pl, "active", []) or []):
        if x is not None:
            yield True, x
    for x in (_g(pl, "bench", []) or []):
        if x is not None:
            yield False, x


def make_drag_eval():
    """散布蓄積 + エネ型 を加味した Dragapult 専用局面評価。"""
    def ev(cur, me):
        base = state_eval(cur, me)
        pls = _g(cur, "players", []) or []
        if len(pls) < 2 or me not in (0, 1):
            return base
        mp_, op = pls[me], pls[1 - me]
        bonus = 0.0
        # 散布: 相手ボードに載ったダメージを高評価 + 瀕死ボーナス（実測で有効だった重み）
        for _, pk in _iter_my(op):
            hp = float(_g(pk, "hp", 0) or 0)
            mhp = float(_g(pk, "maxHp", 0) or 0)
            if mhp > 0:
                bonus += 4.0 * (mhp - hp)
                if 0 < hp <= 70:
                    bonus += 150.0
                if 0 < hp <= 30:
                    bonus += 150.0
        # エネ型: Dragapultライン上の [炎+超] ペア完成を評価、同色2枚は薄く
        for is_active, pk in _iter_my(mp_):
            if _g(pk, "id") not in (DRAGAPULT, DRAKLOAK, DREEPY):
                continue
            es = [_g(e, "id") for e in (_g(pk, "energyCards", []) or [])]
            r = es.count(R_ENERGY)
            p = es.count(P_ENERGY)
            if r >= 1 and p >= 1:
                bonus += 300.0 + (200.0 if (is_active and _g(pk, "id") == DRAGAPULT) else 0.0)
            elif r + p >= 2:
                bonus += 40.0   # 同色2枚 = Phantom Dive を撃てない無駄ペア
            elif r + p == 1:
                bonus += 60.0
        return base + bonus
    return ev


def make_hybrid_dragapult_pilot(topk=4, n_turns=3, rollout_budget=30):
    cards, atks = _tables()
    _ensure_engine_on_path()
    import cg.api as api
    from . import search_agent as SA
    SA._DECK = list(DRAG_DECK)
    drag_eval = make_drag_eval()
    fallback = SA.make_search_agent(eval_fn=drag_eval, rollout=True, n_turns=3, rollout_budget=25)

    def hand_card(mp_, idx):
        hand = _g(mp_, "hand", []) or []
        if idx is not None and 0 <= idx < len(hand):
            return _g(hand[idx], "id")
        return None

    def inplay(pls, pl, area, idx):
        if pl is None or len(pls) <= pl:
            return None
        arr = _g(pls[pl], "active") if area == 4 else (_g(pls[pl], "bench") if area == 5 else None)
        if isinstance(arr, list) and idx is not None and 0 <= idx < len(arr):
            return arr[idx]
        return None

    def main_label(o, mp_, pls, me):
        t = _g(o, "type")
        if t == 7:
            return f"PLAY:{hand_card(mp_, _g(o, 'index'))}"
        if t == 9:
            return f"EVOLVE:{hand_card(mp_, _g(o, 'index'))}"
        if t == 8:
            tgt = inplay(pls, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
            ab = "A" if _g(o, "inPlayArea") == 4 else "B"
            return f"ATTACH:{ab}:{_g(tgt, 'id')}"
        if t == 13:
            a = atks.get(_g(o, "attackId"))
            return f"ATTACK:{_g(a, 'name', '?') if a else '?'}"
        return {10: "ABILITY", 12: "RETREAT", 14: "END", 11: "DISCARD"}.get(t, f"t{t}")

    # --- sandbox ロールアウト（貪欲、両者 drag_eval 最大化） ---
    def leaf(ns, me):
        c = ns.observation.current
        if c is None:
            return 0.0
        r = getattr(c, "result", -1)
        if r != -1:
            return 1e9 if r == me else (-1e9 if r == (1 - me) else 0.0)
        return float(drag_eval(c, me))

    def play_turn(ns, me):
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
                bv, bn = float("-inf"), None
                for j in range(nopt):
                    try:
                        nx = api.search_step(ns.searchId, [j])
                    except Exception:
                        continue
                    cc = nx.observation.current
                    rr = getattr(cc, "result", -1) if cc else -1
                    v = (1e9 if rr == actor else -1e9 if rr == (1 - actor)
                         else (drag_eval(cc, actor) if cc else 0.0))
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

    def agent(obs):
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

        # 後攻選択
        if ctx == 41:
            for i, o in enumerate(opts):
                if _g(o, "type") == 2:
                    return [i]
            return [0]

        # --- MAIN: 模倣プライアで top-K に絞り、sandboxロールアウトで検証 ---
        if ctx == 0 and mc <= 1 and cur is not None:
            labels = [main_label(o, mp_, pls, me) for o in opts]
            prior = [(FITTED_MAIN.get(labels[i], -3.0), i) for i in range(n)]
            prior.sort(reverse=True)
            cands = [i for _, i in prior[:max(1, topk)]]
            # 攻撃とドララインへのエネ付けは必ず候補に含める（トレースで判明した"遅さ"の対策:
            # プライア値が低く top-K から漏れ、初攻撃がT12まで遅延して負けていた）
            atk_best = max((i for i in range(n) if labels[i].startswith("ATTACK:")),
                           key=lambda i: FITTED_MAIN.get(labels[i], -3.0), default=None)
            att_best = max((i for i in range(n) if labels[i].startswith("ATTACH:")
                            and labels[i].split(":")[-1] in ("121", "120", "119")),
                           key=lambda i: FITTED_MAIN.get(labels[i], -3.0), default=None)
            for extra in (atk_best, att_best):
                if extra is not None and extra not in cands:
                    cands.append(extra)
            if len(cands) == 1 or n == 1:
                return [cands[0]]
            rec = SA._reconstruct(obs)
            if rec is None:
                return [cands[0]]  # 探索不能→プライア最善
            try:
                ob = api.to_observation_class(obs)
                root = api.search_begin(ob, rec["your_deck"], rec["your_prize"],
                                        rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"])
            except Exception:
                return [cands[0]]
            best_i, best_v = cands[0], float("-inf")
            try:
                for i in cands:
                    try:
                        ns = api.search_step(root.searchId, [i])
                    except Exception:
                        continue
                    for _ in range(n_turns):
                        c = ns.observation.current
                        if c is None or getattr(c, "result", -1) != -1:
                            break
                        ns = play_turn(ns, me)
                    v = leaf(ns, me)
                    if v > best_v:
                        best_v, best_i = v, i
            finally:
                try:
                    api.search_end()
                except Exception:
                    pass
            return [best_i]

        # --- ctx14: 散布（KO刈り取り>進化前狙撃>大物蓄積） ---
        if ctx == 14:
            rem = int(_g(sel, "remainDamageCounter", 0) or 0)
            def score(i):
                o = opts[i]
                pl = _g(o, "playerIndex")
                pk = inplay(pls, pl, _g(o, "area"), _g(o, "index"))
                if pk is None:
                    return -1e18
                if pl is None or pl == me:
                    return -1e9
                hp = float(_g(pk, "hp", 0) or 0)
                cid = _g(pk, "id")
                cd = cards.get(cid)
                if rem > 0 and hp <= rem * 10:
                    # KO可能: 低HP優先(少ないカウンタで刈る) + サイド価値
                    return 100000 + (2000 if (_g(cd, "ex") or _g(cd, "megaEx")) else 0) - hp * 10
                if _is_evolving_basic(cards, cid):
                    return 5000 - hp
                return 1000 - hp * 0.5
            order = sorted(range(n), key=score, reverse=True)
            if mc <= 1:
                return [order[0]]
            return sorted(order[:max(mn, min(mc, n))])

        # --- ctx21: エネ選択は [炎+超] ペアを完成させる型 ---
        if ctx == 21:
            need = None
            for _, pk in _iter_my(mp_):
                if _g(pk, "id") in (DRAGAPULT, DRAKLOAK, DREEPY):
                    es = [_g(e, "id") for e in (_g(pk, "energyCards", []) or [])]
                    if R_ENERGY in es and P_ENERGY not in es:
                        need = P_ENERGY
                        break
                    if P_ENERGY in es and R_ENERGY not in es:
                        need = R_ENERGY
                        break
            if need is None:
                need = P_ENERGY
            for i, o in enumerate(opts):
                if _g(o, "cardId") == need:
                    return [i]
            return [0]

        # --- ctx7/8: 山サーチ（v4のテーブル） ---
        if ctx in (7, 8):
            deck = _g(sel, "deck")
            def cid_of(o):
                c = _g(o, "cardId")
                if c is None and deck is not None:
                    idx = _g(o, "index")
                    if idx is not None and 0 <= idx < len(deck):
                        c = _g(deck[idx], "id")
                return c
            rank = {cid: r for r, cid in enumerate(SEARCH_PRIO)}
            order = sorted(range(n), key=lambda i: rank.get(cid_of(opts[i]), 999))
            if mc <= 1:
                return [order[0]]
            return sorted(order[:max(mn, min(mc, n))])

        return fallback(obs)

    return agent
