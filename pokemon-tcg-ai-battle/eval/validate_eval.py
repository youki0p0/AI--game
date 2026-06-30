"""Validate the static evaluation function against real games.

Idea (shogi-style): a good evaluation value should predict the eventual
winner -- and the agreement should grow as the game approaches its end.

We use **buddy-vs-buddy** games (the bundled competent sample agent against
itself) because they produce realistically played positions; random games give
a much weaker signal.

For every decision point we record ``state_eval(current, my_index=0)`` (player 0's
perspective) together with the game's final result.  We then bucket the records
by game-progress fraction and report, per bucket:

  agreement = P( sign(eval favoring P0) matches "did P0 win?" )

A sound evaluation shows agreement near 0.5 early and rising toward ~1.0 late.

Usage:
    python -m eval.validate_eval --n-games 30 --buckets 5
"""
from __future__ import annotations

import argparse

from .agents_buddy import load_buddy_agent
from .engine_driver import play_game
from .state_eval import state_eval


def _run_one_game() -> list[tuple[float, float]]:
    """Play one buddy-vs-buddy game.

    Returns a list of (progress_fraction, eval_p0) for every decision point,
    with the game's outcome encoded via the sign convention applied by the
    caller.  We return raw (turn_index, eval) and normalise progress later.
    """
    records: list[tuple[int, float]] = []

    def observer(current: dict, _acting_player: int) -> None:
        # Always evaluate from player 0's fixed perspective.
        ev = state_eval(current, my_index=0)
        turn = current.get("turn", len(records)) if isinstance(current, dict) else len(records)
        records.append((int(turn), float(ev)))

    a = load_buddy_agent()
    b = load_buddy_agent()
    result = play_game(a, b, observer=observer)

    if not records:
        return []

    # P0 outcome: +1 win, -1 loss, 0 draw
    p0_outcome = 1.0 if result == 0 else (-1.0 if result == 1 else 0.0)

    n = len(records)
    out: list[tuple[float, float]] = []
    for i, (_turn, ev) in enumerate(records):
        progress = (i + 1) / n  # 0..1 across the game
        # store (progress, signed agreement contribution)
        out.append((progress, ev * p0_outcome))  # >0 means eval agreed with outcome
    return out


def validate(n_games: int, buckets: int) -> dict:
    """Run n_games and return agreement statistics by progress bucket."""
    bucket_hit = [0] * buckets
    bucket_total = [0] * buckets
    decisive_games = 0

    for g in range(n_games):
        recs = _run_one_game()
        if not recs:
            continue
        # Skip draws (no directional signal): detect via all contributions ~0?
        # Draw encodes p0_outcome=0 so every product is 0; treat as non-decisive.
        if all(abs(c) < 1e-12 for _p, c in recs):
            continue
        decisive_games += 1
        for progress, agree in recs:
            bi = min(buckets - 1, int(progress * buckets))
            bucket_total[bi] += 1
            if agree > 0:  # eval sign matched the eventual winner
                bucket_hit[bi] += 1

    rows = []
    for i in range(buckets):
        lo, hi = i / buckets, (i + 1) / buckets
        tot = bucket_total[i]
        rate = (bucket_hit[i] / tot) if tot else float("nan")
        rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": tot, "agreement": rate})

    return {"n_games": n_games, "decisive_games": decisive_games, "buckets": rows}


def main() -> None:
    p = argparse.ArgumentParser(description="Validate state_eval via buddy-vs-buddy games")
    p.add_argument("--n-games", type=int, default=30, help="number of buddy-vs-buddy games")
    p.add_argument("--buckets", type=int, default=5, help="game-progress buckets")
    args = p.parse_args()

    print(f"Validating state_eval on {args.n_games} buddy-vs-buddy games...")
    stats = validate(args.n_games, args.buckets)
    print(f"decisive (non-draw) games: {stats['decisive_games']}/{stats['n_games']}")
    print("-" * 46)
    print(f"{'progress':>10} | {'n':>7} | {'agreement':>10}")
    print("-" * 46)
    for r in stats["buckets"]:
        print(f"{r['bucket']:>10} | {r['n']:>7} | {r['agreement']:>10.3f}")
    print("-" * 46)
    print("期待: 終盤(下の行)ほど一致率が1.0へ上がれば評価値は妥当")


if __name__ == "__main__":
    main()
