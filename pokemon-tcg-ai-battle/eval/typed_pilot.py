"""Type-generic dedicated pilot (generalized from psy_pilot).

psy_pilot's core is already type-agnostic: it attacks for max *effective* damage
(reading the attacker's real energyType and the defender's weakness/resistance
from card data), attaches its own basic energy to the active attacker, develops
bench / draws / searches otherwise, and goes second. Only three things were
Psychic-specific: the basic-energy card id, the attacker placement priority, and
the gust-target priority. This module parameterizes those so the SAME strong
logic can pilot a Fire deck (OHKO Crustle & Archaludon on weakness), a Metal
deck, etc.

Usage:
    pilot = make_typed_pilot(deck, energy_id=2)          # Fire
    pilot = make_typed_pilot(deck, energy_id=5,          # Psychic (== psy_pilot)
                             attacker_priority=[971,184,431,216,764],
                             gust_priority=[678,674,676,675,677,673])
"""
from __future__ import annotations

from typing import Any

from .state_eval import _card_data, _attack_data, _g

# OptionType / SelectType / SelectContext / AreaType ints (from cg.api)
T_NUMBER, T_YES, T_NO, T_CARD, T_TOOL_CARD, T_ENERGY_CARD, T_ENERGY = 0, 1, 2, 3, 4, 5, 6
T_PLAY, T_ATTACH, T_EVOLVE, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END, T_SKILL, T_SPECIAL = \
    7, 8, 9, 10, 11, 12, 13, 14, 15, 16
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
AREA_ACTIVE = 4


def _attack_damage(attack_id: Any) -> int:
    a = _attack_data(attack_id)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff_vs(attack_id: Any, attacker_type: Any, defender) -> int:
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


def make_typed_pilot(deck: list[int], energy_id: int,
                     attacker_priority: list[int] | None = None,
                     gust_priority: list[int] | None = None,
                     go_first: bool = False, trainers_first: bool = True,
                     min_attack_dmg: int = 1, hand_thin: int = 5):
    cfg = {
        "energy_id": energy_id,
        "attacker_priority": attacker_priority or [],
        "gust_priority": gust_priority or [],
        "go_first": go_first,
        "trainers_first": trainers_first,
        "min_attack_dmg": min_attack_dmg,
        "hand_thin": hand_thin,
        "deck": list(deck),
    }

    def piloted(obs: dict) -> list[int]:
        return _impl(obs, cfg)
    return piloted


def _impl(obs: dict, cfg: dict) -> list[int]:
    sel = obs.get("select")
    cur = obs.get("current")
    if sel is None:
        return list(cfg["deck"])  # deck-selection phase
    options = sel.get("option") or []
    n = len(options)
    if n == 0:
        return []
    stype = sel.get("type")
    sctx = sel.get("context")
    mc = int(sel.get("maxCount", 1) or 1)
    mn = int(sel.get("minCount", 0) or 0)
    energy_id = cfg["energy_id"]

    me = _g(cur, "yourIndex", 0) if cur is not None else 0
    players = _g(cur, "players", []) or [] if cur is not None else []
    opp_active = my_active = None
    if len(players) >= 2:
        oa = _g(players[1 - me], "active", []) or []
        opp_active = oa[0] if oa else None
        ma = _g(players[me], "active", []) or []
        my_active = ma[0] if ma else None

    def first_k() -> list[int]:
        k = min(max(mc, mn if mn > 0 else 1), n)
        return list(range(k))

    # --- first/second choice (aggro usually prefers second) ---
    if sctx == SC_IS_FIRST:
        want = T_YES if cfg.get("go_first") else T_NO
        for i, o in enumerate(options):
            if _g(o, "type") == want:
                return [i]
        return [0]
    if sctx == SC_MULLIGAN:
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]

    # --- choose attack: highest effective damage ---
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_d = 0, -1
        for i, o in enumerate(options):
            d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
            if d > best_d:
                best_d, best_i = d, i
        return [best_i]

    # --- MAIN phase: choose the macro action ---
    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        scores = []
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= int(cfg.get("hand_thin", 5))
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ATTACK:
                d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                if d >= int(cfg.get("min_attack_dmg", 1)):
                    s = 10000 + d + (50000 if (oh > 0 and d >= oh) else 0)
                else:
                    s = 200
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                in_active = _g(o, "inPlayArea") == AREA_ACTIVE
                s = 8000 + (300 if in_active else 0)
            elif t == T_PLAY:
                card = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    card = _card_data(_g(hand[idx], "id"))
                ct = _g(card, "cardType") if card else None
                boost = 3000 if (cfg.get("trainers_first") and thin) else 0
                if ct == 3:
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

    # --- placement: our best attacker, OR (gust) opponent's biggest prize target ---
    if sctx in SC_PLACEMENT:
        targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
        pri = cfg["gust_priority"] if targets_opp else cfg["attacker_priority"]
        rank = {cid: i for i, cid in enumerate(pri)}

        def keyf(i):
            cid = _g(options[i], "cardId")
            if cid in rank:
                return (0, rank[cid])
            # fallback: gust -> biggest prize (ex); place -> bulkiest
            cd = _card_data(cid)
            if targets_opp:
                pv = 3 if _g(cd, "megaEx") else (2 if _g(cd, "ex") else 1)
                return (1, -pv)
            return (1, -float(_g(cd, "hp", 0) or 0))
        scored = sorted(range(n), key=keyf)
        if mc <= 1:
            return [scored[0]]
        return sorted(scored[:max(mc, mn)])

    # --- target / card selection: prefer opponent active; own-type energy ---
    energy_choice = opp_active_choice = None
    for i, o in enumerate(options):
        if _g(o, "cardId") == energy_id and energy_choice is None:
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
        if _g(o, "cardId") == energy_id:
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
