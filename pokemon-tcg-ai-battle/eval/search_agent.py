"""Lookahead agent: pick options by evaluating the resulting position.

Chess analogy: at each decision we do a shallow search -- for every legal option
we apply it in the engine's *search* sandbox (search_begin / search_step, which
clones the state without touching the real game), evaluate the resulting
position with a static evaluation, and choose the best.  buddy itself does no
search, so a sound eval + 1-ply lookahead can outplay it.

Hidden information (both sides play the same known deck) is reconstructed from
the fixed 60-card decklist minus the visible cards, then handed to search_begin.

Single-select decisions  -> 1-ply greedy over options.
Multi-select decisions   -> greedy incremental set building.
Any failure              -> safe fallback (first legal / deck).
"""
from __future__ import annotations

import dataclasses
import enum
import pickle
from collections import Counter
from typing import Any, Callable

from .engine_driver import _ensure_engine_on_path, _get_engine_dir
from .state_eval import state_eval


def _to_plain(o: Any) -> Any:
    """Convert a search Observation dataclass (with IntEnums) to a JSON-like dict
    that buddy's ``to_observation_class`` can re-parse."""
    if isinstance(o, enum.Enum):
        return int(o)
    if dataclasses.is_dataclass(o):
        return {f.name: _to_plain(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, (list, tuple)):
        return [_to_plain(x) for x in o]
    return o

_DECK: list[int] | None = None
_CARD: dict | None = None


def _deck() -> list[int]:
    global _DECK
    if _DECK is None:
        _ensure_engine_on_path()
        with open(_get_engine_dir() / "deck.pkl", "rb") as f:
            _DECK = list(pickle.load(f))
    return _DECK


def _card_table() -> dict:
    global _CARD
    if _CARD is None:
        _ensure_engine_on_path()
        import cg.api as api  # noqa: PLC0415
        _CARD = {c.cardId: c for c in api.all_card_data()}
    return _CARD


# ---------------------------------------------------------------------------
# Hidden-information reconstruction
# ---------------------------------------------------------------------------

def _cards_in_play(pk: dict) -> list[int]:
    ids = [pk["id"]]
    for k in ("energyCards", "tools", "preEvolution"):
        for c in pk.get(k) or []:
            ids.append(c["id"])
    return ids


def _visible_used(player: dict) -> Counter:
    used: Counter = Counter()
    for c in player.get("hand") or []:
        used[c["id"]] += 1
    for area in ("active", "bench"):
        for pk in player.get(area) or []:
            if pk:
                for i in _cards_in_play(pk):
                    used[i] += 1
    for c in player.get("discard") or []:
        used[c["id"]] += 1
    return used


def _reconstruct(obs: dict) -> dict | None:
    cur = obs.get("current")
    if cur is None:
        return None
    me = cur["yourIndex"]
    opp = 1 - me
    full = Counter(_deck())

    mp, op = cur["players"][me], cur["players"][opp]
    my_unknown = list((full - _visible_used(mp)).elements())
    op_unknown = list((full - _visible_used(op)).elements())

    dc, pz = mp["deckCount"], len(mp["prize"])
    odc, opz, ohc = op["deckCount"], len(op["prize"]), op["handCount"]

    if len(my_unknown) < dc + pz or len(op_unknown) < odc + opz + ohc:
        return None  # counts do not reconcile -> skip search this decision

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
        tbl = _card_table()
        import cg.api as api  # noqa: PLC0415
        for cid in op_unknown:
            cd = tbl.get(cid)
            if cd and cd.basic and cd.cardType == api.CardType.POKEMON:
                rec["opp_active"] = [cid]
                break
        if not rec["opp_active"]:
            return None
    return rec


# ---------------------------------------------------------------------------
# Search-based agent
# ---------------------------------------------------------------------------

def make_search_agent(
    eval_fn: Callable[[Any, int], float] = state_eval,
    fallback: Callable[[dict], list[int]] | None = None,
    rollout: bool = True,
    rollout_budget: int = 30,
    n_turns: int = 2,
    leaf_eval: Callable[[Any, int], float] | None = None,
) -> Callable[[dict], list[int]]:
    """Return an agent(obs_dict) -> list[int].

    rollout=False : 1-ply greedy (evaluate state right after each option).
    rollout=True  : for each candidate option, greedily play out the next
                    ``n_turns`` turn-segments (each player optimising their own
                    eval), then evaluate.  n_turns=1 = end of our turn;
                    n_turns=2 = include the opponent's best reply (avoids leaving
                    a KO-able active).
    """

    def _fallback(obs: dict) -> list[int]:
        if fallback is not None:
            return fallback(obs)
        sel = obs.get("select")
        if sel is None:
            return _deck()
        n = len(sel["option"])
        k = min(sel.get("maxCount", 1) or 1, n)
        return list(range(max(k, sel.get("minCount", 0) or 0)))[:k] if n else []

    def agent(obs: dict) -> list[int]:
        sel = obs.get("select")
        if sel is None:
            return _deck()  # deck-selection phase
        options = sel.get("option") or []
        n = len(options)
        if n == 0:
            return []
        max_count = int(sel.get("maxCount", 1) or 1)
        min_count = int(sel.get("minCount", 0) or 0)
        cur = obs.get("current")
        if cur is None:
            return _fallback(obs)
        me = cur["yourIndex"]

        rec = _reconstruct(obs)
        if rec is None:
            return _fallback(obs)

        _ensure_engine_on_path()
        import cg.api as api  # noqa: PLC0415

        try:
            ob = api.to_observation_class(obs)
            root = api.search_begin(
                ob, rec["your_deck"], rec["your_prize"],
                rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"],
            )
        except Exception:
            return _fallback(obs)

        _leaf = leaf_eval if leaf_eval is not None else eval_fn

        def value_of(ns: Any) -> float:
            c = ns.observation.current
            if c is None:
                return 0.0
            res = getattr(c, "result", -1)
            if res != -1:
                return 1e9 if res == me else (-1e9 if res == (1 - me) else 0.0)
            return float(_leaf(c, me))

        def is_terminal(ns: Any) -> bool:
            c = ns.observation.current
            return c is None or getattr(c, "result", -1) != -1

        def play_turn(ns: Any) -> Any:
            """Greedily play out the current actor's whole turn (optimising that
            actor's own eval); return the node when the turn passes or ends."""
            c0 = ns.observation.current
            if c0 is None:
                return ns
            actor = getattr(c0, "yourIndex", me)
            for _ in range(rollout_budget):
                c = ns.observation.current
                if c is None or getattr(c, "result", -1) != -1:
                    return ns
                if getattr(c, "yourIndex", actor) != actor:
                    return ns  # turn passed to the other player
                sel = ns.observation.select
                if sel is None or not sel.option:
                    return ns
                mc = int(getattr(sel, "maxCount", 1) or 1)
                nopt = len(sel.option)
                if mc <= 1:
                    best_v, best_ns = float("-inf"), None
                    for i in range(nopt):
                        try:
                            nxt = api.search_step(ns.searchId, [i])
                        except Exception:
                            continue
                        v = _actor_value(nxt, actor)
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

        def _actor_value(ns: Any, actor: int) -> float:
            c = ns.observation.current
            if c is None:
                return 0.0
            res = getattr(c, "result", -1)
            if res != -1:
                return 1e9 if res == actor else (-1e9 if res == (1 - actor) else 0.0)
            return float(eval_fn(c, actor))

        def score_of(select_list: list[int]) -> float | None:
            try:
                ns = api.search_step(root.searchId, select_list)
            except Exception:
                return None
            if not rollout:
                return value_of(ns)
            for _ in range(n_turns):
                if is_terminal(ns):
                    break
                ns = play_turn(ns)
            return value_of(ns)

        try:
            if max_count <= 1:
                # ---- single-select: 1-ply greedy over options ----
                best_i, best_s = None, float("-inf")
                for i in range(n):
                    s = score_of([i])
                    if s is not None and s > best_s:
                        best_s, best_i = s, i
                result = [best_i] if best_i is not None else _fallback(obs)
            else:
                # ---- multi-select: greedy incremental set building ----
                chosen: list[int] = []
                remaining = set(range(n))
                cur_score = score_of([]) if min_count == 0 else None
                while len(chosen) < max_count and remaining:
                    best_i, best_s = None, float("-inf")
                    for i in list(remaining):
                        s = score_of(sorted(chosen + [i]))
                        if s is not None and s > best_s:
                            best_s, best_i = s, i
                    if best_i is None:
                        break
                    # stop early once minCount satisfied and no improvement
                    if (len(chosen) >= min_count and cur_score is not None
                            and best_s <= cur_score):
                        break
                    chosen.append(best_i)
                    remaining.discard(best_i)
                    cur_score = best_s
                if len(chosen) < min_count:  # must satisfy minimum
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

    return agent


if __name__ == "__main__":
    from .agents_buddy import load_buddy_agent
    from .harness import evaluate

    agent = make_search_agent()
    buddy = load_buddy_agent()
    res = evaluate(agent, buddy, n_games=6, seed=0)
    print("search_agent vs buddy:", res)


# ---------------------------------------------------------------------------
# Buddy-rollout agent: deviate at the root, then let BUDDY play both sides.
# Models the real opponent (buddy) accurately -> should exceed buddy.
# ---------------------------------------------------------------------------

def make_buddy_rollout_agent(
    leaf_eval: Callable[[Any, int], float] = state_eval,
    n_turns: int = 2,
    rollout_budget: int = 40,
) -> Callable[[dict], list[int]]:
    from .agents_buddy import load_buddy_agent

    roll_buddy = load_buddy_agent()

    def _reset_buddy() -> None:
        gl = roll_buddy.__globals__
        if "pre_turn" in gl:
            gl["pre_turn"] = -1

    def _buddy_on(observation: Any) -> list[int]:
        d = _to_plain(observation)
        d["search_begin_input"] = None
        try:
            return roll_buddy(d)
        except Exception:
            sel = observation.select
            n = len(sel.option) if sel else 0
            return [0] if n else []

    def _buddy_real(obs: dict) -> list[int]:
        _reset_buddy()
        try:
            return roll_buddy(obs)
        except Exception:
            sel = obs.get("select")
            if sel is None:
                return _deck()
            n = len(sel.get("option") or [])
            return [0] if n else []

    def agent(obs: dict) -> list[int]:
        sel = obs.get("select")
        if sel is None:
            return _deck()
        options = sel.get("option") or []
        n = len(options)
        if n == 0:
            return []
        cur = obs.get("current")
        if cur is None:
            return _buddy_real(obs)
        me = cur["yourIndex"]
        mc = int(sel.get("maxCount", 1) or 1)

        rec = _reconstruct(obs)
        if rec is None or mc > 1 or n == 1:
            return [0] if n == 1 else _buddy_real(obs)

        _ensure_engine_on_path()
        import cg.api as api  # noqa: PLC0415

        try:
            ob = api.to_observation_class(obs)
            root = api.search_begin(
                ob, rec["your_deck"], rec["your_prize"],
                rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"],
            )
        except Exception:
            return _buddy_real(obs)

        def leaf_value(ns: Any) -> float:
            c = ns.observation.current
            if c is None:
                return 0.0
            res = getattr(c, "result", -1)
            if res != -1:
                return 1e9 if res == me else (-1e9 if res == (1 - me) else 0.0)
            return float(leaf_eval(c, me))

        def play_actor_turn(ns: Any) -> Any:
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
                choice = _buddy_on(ns.observation)
                try:
                    ns = api.search_step(ns.searchId, choice)
                except Exception:
                    return ns
            return ns

        best_i, best_v = None, float("-inf")
        try:
            for i in range(n):
                try:
                    ns = api.search_step(root.searchId, [i])
                except Exception:
                    continue
                _reset_buddy()  # fresh plan for this candidate's rollout
                for _ in range(n_turns):
                    c = ns.observation.current
                    if c is None or getattr(c, "result", -1) != -1:
                        break
                    ns = play_actor_turn(ns)
                v = leaf_value(ns)
                if v > best_v:
                    best_v, best_i = v, i
        finally:
            try:
                api.search_end()
            except Exception:
                pass

        return [best_i] if best_i is not None else _buddy_real(obs)

    return agent
