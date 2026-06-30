"""Dedicated heuristic pilot for the Psychic anti-Fighting deck.

The deck is all basics (no evolutions), so piloting is simple:
  1. If we can attack, attack for max effective damage (weakness x2 -> OHKO Lucario).
  2. Otherwise attach Psychic energy to the active attacker (build toward an attack).
  3. Otherwise develop bench / draw (Carmine) / search (Dusk Ball).
  4. Choose to go SECOND (aggro attacks first).
  5. Target the opponent's Active; attach Psychic energy; pick highest-damage attack.

Returns option indices like any CABT agent.
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
# placement contexts where we pick one of OUR Pokémon
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}  # SETUP_ACTIVE/BENCH, SWITCH, TO_ACTIVE/BENCH/FIELD
AREA_ACTIVE = 4
ENERGY_PSY = 5
IRON_BOULDER = 971
ATTACKER_PRIORITY = [971, 431, 184, 216, 764, 765]
GUST_TARGET_PRIORITY = [678, 674, 676, 675, 677, 673]  # pull Lucario (3 prizes) first


def _opt(o: Any, k: str, default=None):
    return _g(o, k, default)


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


# Tunable strategy flags (set by make_psy_pilot; defaults give the original agent)
CFG = {"go_first": False, "trainers_first": True, "min_attack_dmg": 1, "hand_thin": 5}


def make_psy_pilot(**flags):
    cfg = dict(CFG)
    cfg.update(flags)

    def piloted(obs: dict) -> list[int]:
        return _agent_impl(obs, cfg)
    return piloted


def agent(obs: dict) -> list[int]:
    return _agent_impl(obs, CFG)


def _agent_impl(obs: dict, cfg: dict) -> list[int]:
    sel = obs.get("select")
    cur = obs.get("current")
    if sel is None:
        from .deck_battle import PSY_DECK
        return list(PSY_DECK)  # deck-selection phase
    options = sel.get("option") or []
    n = len(options)
    if n == 0:
        return []
    stype = sel.get("type")
    sctx = sel.get("context")
    mc = int(sel.get("maxCount", 1) or 1)
    mn = int(sel.get("minCount", 0) or 0)

    me = _g(cur, "yourIndex", 0) if cur is not None else 0
    players = _g(cur, "players", []) or [] if cur is not None else []
    opp_active = None
    my_active = None
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
            if _opt(o, "type") == want:
                return [i]
        return [0]
    if sctx == SC_MULLIGAN:
        for i, o in enumerate(options):
            if _opt(o, "type") == T_NO:
                return [i]
        return [0]

    # --- choose attack: highest effective damage ---
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_d = 0, -1
        for i, o in enumerate(options):
            d = _eff_vs(_opt(o, "attackId"), atk_type, opp_active)
            if d > best_d:
                best_d, best_i = d, i
        return [best_i]

    # --- MAIN phase: choose the macro action ---
    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        scores = []
        for o in options:
            t = _opt(o, "type")
            s = 0.0
            hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
            thin = hand_ct <= int(cfg.get("hand_thin", 5))
            if t == T_ATTACK:
                d = _eff_vs(_opt(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                if d >= int(cfg.get("min_attack_dmg", 1)):
                    s = 10000 + d + (50000 if (oh > 0 and d >= oh) else 0)
                else:
                    s = 200  # weak/no-damage attack: avoid unless nothing else
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                in_active = _opt(o, "inPlayArea") == AREA_ACTIVE
                s = 8000 + (300 if in_active else 0)
            elif t == T_PLAY:
                card = None
                idx = _opt(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    card = _card_data(_g(hand[idx], "id"))
                ct = _g(card, "cardType") if card else None
                boost = 3000 if (cfg.get("trainers_first") and thin) else 0
                if ct == 3:        # SUPPORTER (draw)
                    s = 6500 + boost
                elif ct in (1, 2):  # ITEM / TOOL (search/draw)
                    s = 5500 + boost
                else:               # basic Pokémon -> develop bench
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

    # --- placement: pick our best attacker, OR (for gust) the opponent's biggest target ---
    if sctx in SC_PLACEMENT:
        targets_opp = any(_opt(o, "playerIndex") == (1 - me) for o in options)
        pri = GUST_TARGET_PRIORITY if targets_opp else ATTACKER_PRIORITY
        rank = {cid: i for i, cid in enumerate(pri)}
        scored = sorted(range(n), key=lambda i: rank.get(_opt(options[i], "cardId"), 99))
        if mc <= 1:
            return [scored[0]]
        return sorted(scored[:max(mc, mn)])

    # --- target / card selection: prefer opponent active; psychic energy; Iron Boulder ---
    # energy selection: pick a Psychic energy if available
    psy_choice = None
    iron_choice = None
    opp_active_choice = None
    for i, o in enumerate(options):
        if _opt(o, "cardId") == ENERGY_PSY:
            psy_choice = psy_choice if psy_choice is not None else i
        if _opt(o, "cardId") == IRON_BOULDER:
            iron_choice = iron_choice if iron_choice is not None else i
        # option referencing opponent active
        if _opt(o, "playerIndex") == (1 - me) and _opt(o, "area") == AREA_ACTIVE:
            opp_active_choice = opp_active_choice if opp_active_choice is not None else i
        if _opt(o, "inPlayArea") == AREA_ACTIVE and _opt(o, "playerIndex") == (1 - me):
            opp_active_choice = opp_active_choice if opp_active_choice is not None else i

    if mc <= 1:
        if opp_active_choice is not None:  # damage/effect target -> opponent active
            return [opp_active_choice]
        if psy_choice is not None:
            return [psy_choice]
        if iron_choice is not None:
            return [iron_choice]
        return [0]

    # multi-select: prefer psychic energies / first legal
    chosen = []
    for i, o in enumerate(options):
        if _opt(o, "cardId") == ENERGY_PSY:
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


if __name__ == "__main__":
    import pickle
    from .deck_battle import PSY_DECK, evaluate_decks
    from .engine_driver import _get_engine_dir
    from .agents_buddy import load_buddy_agent
    buddy_deck = list(pickle.load(open(_get_engine_dir() / "deck.pkl", "rb")))
    buddy = load_buddy_agent()

    # custom eval: our heuristic pilot on PSY_DECK vs buddy (alternate sides)
    from .engine_driver import play_game
    wins = 0
    N = 20
    for gi in range(N):
        if gi % 2 == 0:
            r = play_game(agent, buddy, deck0=PSY_DECK, deck1=buddy_deck); mei = 0
        else:
            r = play_game(buddy, agent, deck0=buddy_deck, deck1=PSY_DECK); mei = 1
        wins += 1 if r == mei else 0
    print(f"psy_pilot vs buddy: {wins}/{N} = {wins/N:.3f}")
