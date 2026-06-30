"""Robust, deck-agnostic heuristic pilot.

Goal: pilot ANY legal deck reasonably and NEVER return an invalid selection
(so games never crash). Used to compare decks fairly in a round-robin so the
matchup reflects the DECK, not bespoke piloting.

Heuristic (per decision):
  * deck-selection phase -> return the deck
  * MAIN  -> ATTACK (max effective dmg, KO first) > ABILITY > ATTACH to active
             > PLAY draw/search/develop > RETREAT > END
  * ATTACK select -> highest effective damage (weakness x2)
  * placement of OUR Pokémon -> highest max-HP (bulk); of OPPONENT (gust) -> highest prize value
  * energy/target/card select -> sensible pick (opp active for damage; any energy)
  * first/second -> go second (aggro attacks first)
All selections are validated against minCount/maxCount/range/duplicates.
"""
from __future__ import annotations

from typing import Any

from .state_eval import _attack_data, _card_data, _g

T_YES, T_NO = 1, 2
T_PLAY, T_ATTACH, T_ABILITY, T_RETREAT, T_ATTACK, T_END = 7, 8, 10, 12, 13, 14
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
AREA_ACTIVE = 4


def _validate(sel: dict, idxs: list[int]) -> list[int]:
    """Clamp an index list to a valid selection for this select."""
    n = len(sel.get("option") or [])
    mc = int(sel.get("maxCount", 1) or 1)
    mn = int(sel.get("minCount", 0) or 0)
    seen, out = set(), []
    for i in idxs:
        if isinstance(i, int) and 0 <= i < n and i not in seen:
            seen.add(i)
            out.append(i)
        if len(out) >= mc:
            break
    if len(out) < mn:  # pad up to minCount with first unused legal indices
        for i in range(n):
            if i not in seen:
                out.append(i)
                seen.add(i)
            if len(out) >= mn:
                break
    return out


def _prize_value(card_data: Any) -> int:
    if card_data is None:
        return 1
    if _g(card_data, "megaEx"):
        return 3
    if _g(card_data, "ex"):
        return 2
    return 1


def _eff_dmg(attack_id: Any, attacker: Any, defender: Any) -> int:
    a = _attack_data(attack_id)
    dmg = int(_g(a, "damage", 0) or 0) if a else 0
    if dmg <= 0 or defender is None:
        return dmg
    ad = _card_data(_g(attacker, "id")) if attacker is not None else None
    dd = _card_data(_g(defender, "id"))
    at = _g(ad, "energyType") if ad else None
    if dd is not None and at is not None:
        if _g(dd, "weakness") == at:
            return dmg * 2
        if _g(dd, "resistance") == at:
            return max(0, dmg - 30)
    return dmg


def make_generic_pilot(deck: list[int]):
    def agent(obs: dict) -> list[int]:
        sel = obs.get("select")
        if sel is None:
            return list(deck)
        options = sel.get("option") or []
        n = len(options)
        if n == 0:
            return []
        cur = obs.get("current")
        stype = sel.get("type")
        sctx = sel.get("context")
        mc = int(sel.get("maxCount", 1) or 1)
        me = _g(cur, "yourIndex", 0) if cur is not None else 0
        players = (_g(cur, "players", []) or []) if cur is not None else []
        my_active = opp_active = None
        if len(players) >= 2:
            ma = _g(players[me], "active", []) or []
            my_active = ma[0] if ma else None
            oa = _g(players[1 - me], "active", []) or []
            opp_active = oa[0] if oa else None

        def V(idxs):
            return _validate(sel, idxs)

        # first/second -> go second
        if sctx == SC_IS_FIRST:
            for i, o in enumerate(options):
                if _g(o, "type") == T_NO:
                    return V([i])
            return V([0])
        if sctx == SC_MULLIGAN:
            for i, o in enumerate(options):
                if _g(o, "type") == T_NO:
                    return V([i])
            return V([0])

        # choose attack: max effective damage
        if stype == ST_ATTACK:
            best_i, best_d = 0, -1
            for i, o in enumerate(options):
                d = _eff_dmg(_g(o, "attackId"), my_active, opp_active)
                if d > best_d:
                    best_d, best_i = d, i
            return V([best_i])

        # MAIN macro action
        if stype == ST_MAIN:
            scores = []
            for o in options:
                t = _g(o, "type")
                s = 50.0
                if t == T_ATTACK:
                    d = _eff_dmg(_g(o, "attackId"), my_active, opp_active)
                    oh = float(_g(opp_active, "hp", 0) or 0)
                    s = (10000 + d + (50000 if (oh > 0 and d >= oh) else 0)) if d >= 1 else 150
                elif t == T_ABILITY:
                    s = 9000
                elif t == T_ATTACH:
                    s = 8000 + (300 if _g(o, "inPlayArea") == AREA_ACTIVE else 0)
                elif t == T_PLAY:
                    s = 5500
                elif t == T_RETREAT:
                    s = 1200
                elif t == T_END:
                    s = 100
                scores.append(s)
            return V([max(range(n), key=lambda i: scores[i])])

        # placement: our Pokémon -> bulkiest; opponent (gust) -> biggest prize
        if sctx in SC_PLACEMENT:
            targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
            def keyf(i):
                cd = _card_data(_g(options[i], "cardId"))
                if targets_opp:
                    return -_prize_value(cd)          # gust the biggest prize
                return -float(_g(cd, "hp", 0) or 0)   # promote bulkiest attacker
            order = sorted(range(n), key=keyf)
            return V(order[:max(1, mc)]) if mc <= 1 else V(order[:mc])

        # generic single/multi: prefer opponent active (damage target); else first legal
        opp_active_idx = None
        for i, o in enumerate(options):
            if _g(o, "playerIndex") == (1 - me) and (
                    _g(o, "area") == AREA_ACTIVE or _g(o, "inPlayArea") == AREA_ACTIVE):
                opp_active_idx = i
                break
        if mc <= 1:
            return V([opp_active_idx if opp_active_idx is not None else 0])
        return V(list(range(n)))

    return agent
