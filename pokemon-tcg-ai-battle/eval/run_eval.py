"""CLI entry point for CABT evaluation harness.

Usage:
    python -m eval.run_eval [--n-games N] [--seed S]

Run from the pokemon-tcg-ai-battle/ directory so that the eval package is on
the Python path.  Example:

    cd pokemon-tcg-ai-battle
    python -m eval.run_eval --n-games 10 --seed 42
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CABT local battle evaluation: random vs first_legal agents"
    )
    parser.add_argument(
        "--n-games",
        type=int,
        default=50,
        help="Number of games to play per matchup (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for random agent (default: 0)",
    )
    args = parser.parse_args()

    from eval.baselines import make_random_agent, first_legal_agent  # noqa: PLC0415
    from eval.harness import evaluate  # noqa: PLC0415

    random_agent = make_random_agent(seed=args.seed)

    print(f"Evaluating: random_agent (seed={args.seed}) vs first_legal_agent")
    print(f"Games: {args.n_games}  |  alternate_sides=True")
    print("-" * 50)

    stats = evaluate(
        agent=random_agent,
        opponent=first_legal_agent,
        n_games=args.n_games,
        alternate_sides=True,
        seed=args.seed,
    )

    print(f"n       : {stats['n']}")
    print(f"wins    : {stats['wins']}")
    print(f"losses  : {stats['losses']}")
    print(f"draws   : {stats['draws']}")
    print(f"winrate : {stats['winrate']:.3f}")


if __name__ == "__main__":
    main()
