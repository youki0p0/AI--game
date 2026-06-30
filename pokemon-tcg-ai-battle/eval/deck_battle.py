"""Deck advantage: pilot a custom Psychic deck (exploits buddy's Fighting
weakness) with our generic lookahead agent, and measure win-rate vs buddy.

buddy's key attacker Mega Lucario ex (HP340) is weak to Psychic (x2).
Iron Boulder (basic, 170 dmg for 1 PSY + 1 any) deals 340 with weakness -> OHKO.

This module reconstructs hidden info per side from the *correct* deck (ours vs
buddy's) and runs a 1-ply turn-rollout agent (our best config) on the Psychic deck.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from .engine_driver import _ensure_engine_on_path, _get_engine_dir, play_game
from .search_agent import _to_plain, _cards_in_play, _visible_used
from .state_eval import state_eval

# --- Psychic anti-Fighting deck (60 cards) ---------------------------------
PSY_ENERGY = 5
PSY_DECK: list[int] = (
    # v6: COMPETITIVE RATIOS (real-meta stats): ~18 Pokémon / ~30 Trainers / ~12 Energy.
    # Prior homebrews ran 20-24 energy + ~16 trainers (opposite of meta) -> too slow.
    # Pokémon (18)
    [971] * 4      # Iron Boulder   : 170/{P}{C}, HP140, 1-prize, OHKOs Lucario 340 (Future)
    + [184] * 4    # Latias ex      : 200/{P}{P}{C}, HP210 OHKO
    + [216] * 4    # Mesprit        : 160/{P}{P}, HP70 cheap 2-energy hitter
    + [431] * 4    # TR's Mewtwo ex : 160/{P}{P}{C}, HP280 tank
    + [764] * 2    # Cresselia      : backup
    # Trainers (30): heavy draw + search (meta-style consistency)
    + [1224] * 4   # Cheren         : draw 3
    + [1192] * 4   # Carmine        : draw
    + [1213] * 4   # Judge          : draw 4 / disrupt
    + [1125] * 4   # Master Ball    : search ANY Pokémon -> hand
    + [1152] * 4   # Poké Pad       : search non-ex Pokémon (Iron Boulder)
    + [1102] * 4   # Dusk Ball      : search Pokémon
    + [1123] * 4   # Switch         : mobility (promote Iron Boulder)
    + [1182] * 2   # Boss's Orders  : gust Lucario for OHKO
    # Energy (12)
    + [PSY_ENERGY] * 12
)
ATTACKER_PRIORITY = [971, 184, 431, 216, 764, 765]
# Opponent gust priority (unused in stable build; kept for future Boss's Orders)
GUST_TARGET_PRIORITY = [678, 674, 676, 675, 677, 673]
assert len(PSY_DECK) == 60, len(PSY_DECK)


def _reconstruct(obs: dict, my_deck: list[int], opp_deck: list[int]) -> dict | None:
    cur = obs.get("current")
    if cur is None:
        return None
    me = cur["yourIndex"]
    opp = 1 - me
    mp, op = cur["players"][me], cur["players"][opp]
    my_unknown = list((Counter(my_deck) - _visible_used(mp)).elements())
    op_unknown = list((Counter(opp_deck) - _visible_used(op)).elements())
    dc, pz = mp["deckCount"], len(mp["prize"])
    odc, opz, ohc = op["deckCount"], len(op["prize"]), op["handCount"]
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
    oa = op.get("active") or []
    if len(oa) > 0 and oa[0] is None:
        _ensure_engine_on_path()
        import cg.api as api  # noqa: PLC0415
        tbl = {c.cardId: c for c in api.all_card_data()}
        for cid in op_unknown:
            cd = tbl.get(cid)
            if cd and cd.basic and cd.cardType == api.CardType.POKEMON:
                rec["opp_active"] = [cid]
                break
        if not rec["opp_active"]:
            return None
    return rec


def make_deck_agent(my_deck: list[int], opp_deck: list[int],
                    eval_fn: Callable[[Any, int], float] = state_eval,
                    n_turns: int = 1, rollout_budget: int = 40) -> Callable[[dict], list[int]]:
    """1-ply turn-rollout agent that pilots ``my_deck`` (deck-aware hidden info)."""

    def _fallback(obs: dict) -> list[int]:
        sel = obs.get("select")
        if sel is None:
            return list(my_deck)
        n = len(sel["option"])
        k = min(sel.get("maxCount", 1) or 1, n)
        return list(range(k)) if n else []

    def agent(obs: dict) -> list[int]:
        sel = obs.get("select")
        if sel is None:
            return list(my_deck)
        options = sel.get("option") or []
        n = len(options)
        if n == 0:
            return []
        cur = obs.get("current")
        if cur is None:
            return _fallback(obs)
        me = cur["yourIndex"]
        mc = int(sel.get("maxCount", 1) or 1)
        rec = _reconstruct(obs, my_deck, opp_deck)
        if rec is None:
            return _fallback(obs)
        _ensure_engine_on_path()
        import cg.api as api  # noqa: PLC0415
        try:
            ob = api.to_observation_class(obs)
            root = api.search_begin(ob, rec["your_deck"], rec["your_prize"],
                                    rec["opp_deck"], rec["opp_prize"],
                                    rec["opp_hand"], rec["opp_active"])
        except Exception:
            return _fallback(obs)

        def value_of(ns: Any) -> float:
            c = ns.observation.current
            if c is None:
                return 0.0
            res = getattr(c, "result", -1)
            if res != -1:
                return 1e9 if res == me else (-1e9 if res == (1 - me) else 0.0)
            return float(eval_fn(c, me))

        def play_turn(ns: Any) -> Any:
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
                        rr = getattr(cc, "result", -1) if cc else -1
                        v = (1e9 if rr == actor else (-1e9 if rr == (1 - actor) else
                             float(eval_fn(cc, actor)))) if cc else 0.0
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

        def score(sel_list: list[int]) -> float | None:
            try:
                ns = api.search_step(root.searchId, sel_list)
            except Exception:
                return None
            for _ in range(n_turns):
                c = ns.observation.current
                if c is None or getattr(c, "result", -1) != -1:
                    break
                ns = play_turn(ns)
            return value_of(ns)

        try:
            if mc <= 1:
                best_i, best_s = None, float("-inf")
                for i in range(n):
                    s = score([i])
                    if s is not None and s > best_s:
                        best_s, best_i = s, i
                out = [best_i] if best_i is not None else _fallback(obs)
            else:
                chosen: list[int] = []
                remaining = set(range(n))
                while len(chosen) < mc and remaining:
                    bi, bs = None, float("-inf")
                    for i in list(remaining):
                        s = score(sorted(chosen + [i]))
                        if s is not None and s > bs:
                            bs, bi = s, i
                    if bi is None:
                        break
                    chosen.append(bi)
                    remaining.discard(bi)
                out = sorted(chosen) if chosen else _fallback(obs)
        finally:
            try:
                api.search_end()
            except Exception:
                pass
        return out

    return agent


def evaluate_decks(my_deck: list[int], opp_deck: list[int], opponent: Callable,
                   n_games: int = 20, **agent_kw) -> dict:
    """Our deck_agent (piloting my_deck) vs opponent (piloting opp_deck),
    alternating which side starts."""
    agent = make_deck_agent(my_deck, opp_deck, **agent_kw)
    wins = losses = draws = 0
    for g in range(n_games):
        if g % 2 == 0:
            r = play_game(agent, opponent, deck0=my_deck, deck1=opp_deck)
            me = 0
        else:
            r = play_game(opponent, agent, deck0=opp_deck, deck1=my_deck)
            me = 1
        if r == me:
            wins += 1
        elif r == (1 - me):
            losses += 1
        else:
            draws += 1
    return {"n": n_games, "wins": wins, "losses": losses, "draws": draws,
            "winrate": wins / n_games if n_games else 0.0}


if __name__ == "__main__":
    import pickle
    from .agents_buddy import load_buddy_agent
    buddy_deck = list(pickle.load(open(_get_engine_dir() / "deck.pkl", "rb")))
    buddy = load_buddy_agent()
    res = evaluate_decks(PSY_DECK, buddy_deck, buddy, n_games=16)
    print("Psychic deck (our search agent) vs buddy:", res)
