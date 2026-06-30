"""Win-rate-driven weight optimisation of the lookahead agent vs buddy.

Hill-climbing over a few high-impact evaluation weights.  The objective is the
actual win-rate vs buddy (the thing we care about), estimated over N games.
Promising candidates are re-confirmed on more games before being accepted.
Best weights persist to ``eval/best_weights.json`` so progress accumulates
across runs.

    python -m eval.optimize --candidates 6 --quick 40 --confirm 80
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from dataclasses import replace

from .agents_buddy import load_buddy_agent
from .harness import evaluate
from .search_agent import make_search_agent
from .state_eval import DEFAULT_WEIGHTS, state_eval

# High-impact weights to tune (multiplicative search around the base values).
PARAMS = [
    "prize_diff", "w_prize_value", "w_can_ko", "w_will_be_koed",
    "w_damage_ratio", "w_hp_ratio", "w_energy_ready", "w_bench",
]

BEST_PATH = os.path.join(os.path.dirname(__file__), "best_weights.json")


def _weights_from(mults: dict) -> object:
    kw = {p: getattr(DEFAULT_WEIGHTS, p) * mults.get(p, 1.0) for p in PARAMS}
    return replace(DEFAULT_WEIGHTS, **kw)


def _winrate(mults: dict, n_games: int, seed: int, buddy) -> float:
    W = _weights_from(mults)
    ef = lambda c, mi: state_eval(c, mi, W)  # noqa: E731
    ag = make_search_agent(rollout=True, n_turns=1, rollout_budget=40, eval_fn=ef)
    return evaluate(ag, buddy, n_games=n_games, seed=seed)["winrate"]


def _load_best() -> tuple[dict, float]:
    if os.path.exists(BEST_PATH):
        with open(BEST_PATH) as f:
            d = json.load(f)
        return d.get("mults", {}), float(d.get("winrate", 0.0))
    return {p: 1.0 for p in PARAMS}, -1.0


def _save_best(mults: dict, wr: float) -> None:
    with open(BEST_PATH, "w") as f:
        json.dump({"mults": mults, "winrate": wr, "params": PARAMS}, f, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=6)
    ap.add_argument("--quick", type=int, default=40)
    ap.add_argument("--confirm", type=int, default=80)
    ap.add_argument("--sigma", type=float, default=0.35)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    buddy = load_buddy_agent()
    best_mults, best_wr = _load_best()

    if best_wr < 0:  # establish baseline once
        best_wr = _winrate(best_mults, args.confirm, 9001, buddy)
        _save_best(best_mults, best_wr)
        print(f"[baseline] winrate={best_wr:.3f}")

    print(f"[start] best winrate={best_wr:.3f}  mults={best_mults}")
    for c in range(args.candidates):
        cand = dict(best_mults)
        # perturb a random subset of params
        for p in rng.sample(PARAMS, k=rng.randint(1, 3)):
            cand[p] = max(0.2, min(4.0, cand[p] * math.exp(rng.gauss(0, args.sigma))))
        qseed = rng.randint(1, 10_000)
        qwr = _winrate(cand, args.quick, qseed, buddy)
        tag = ""
        if qwr >= best_wr - 0.02:
            cwr = _winrate(cand, args.confirm, qseed + 1, buddy)
            if cwr > best_wr:
                best_wr, best_mults = cwr, cand
                _save_best(best_mults, best_wr)
                tag = f"  ACCEPT confirm={cwr:.3f} <== NEW BEST"
            else:
                tag = f"  confirm={cwr:.3f} (reject)"
        print(f"[cand {c+1}/{args.candidates}] quick={qwr:.3f}{tag}")

    print(f"[done] best winrate={best_wr:.3f}")
    print(f"       mults={json.dumps(best_mults)}")


if __name__ == "__main__":
    main()
