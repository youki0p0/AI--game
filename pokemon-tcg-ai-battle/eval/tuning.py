"""Texel-style supervised tuning of the evaluation, using game outcomes as labels.

Chess-engine analogy:
  - Collect positions from self-play (here: buddy-vs-buddy, competent play).
  - Label each position by the game's final result (WDL) from player 0's view.
  - Fit P(P0 wins) = sigmoid(w . features) by minimising log-loss (Texel tuning).
  - The learned weights ARE the evaluation; sign of (pred - 0.5) is the eval sign.

This module is engine-light: it only uses the raw feature vector (not the
hand-tuned ``state_eval`` weights), so the linear model is free to learn them.
We then compare agreement-vs-outcome (by game progress) for the hand-tuned
``state_eval`` baseline vs the learned model.

Run:
    python -m eval.tuning --train-games 40 --val-games 20
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from typing import Any

import numpy as np

from .agents_buddy import load_buddy_agent
from .engine_driver import play_game
from .state_eval import (
    _active,
    _best_attack_damage,
    _energy_requirement,
    _g,
    _iter_pokemon,
    prize_value,
    state_eval,
)

# ---------------------------------------------------------------------------
# Raw feature extraction (player 0 perspective; positive favours P0)
# ---------------------------------------------------------------------------

_STATUS_KEYS = ("poisoned", "burned", "asleep", "paralyzed", "confused")


def _hand_size(player: Any) -> int:
    hand = _g(player, "hand")
    if isinstance(hand, list):
        return len(hand)
    return int(_g(player, "handCount", 0) or 0)


def _prize_remaining(player: Any) -> int:
    return len(_g(player, "prize", []) or [])


def _energy_total(player: Any) -> int:
    return sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(player))


def _in_play_count(player: Any) -> int:
    return sum(1 for _ in _iter_pokemon(player))


def _can_ko(attacker_player: Any, defender_player: Any) -> int:
    atk = _active(attacker_player)
    dfn = _active(defender_player)
    if atk is None or dfn is None:
        return 0
    dmg = _best_attack_damage(atk)
    hp = float(_g(dfn, "hp", 0) or 0)
    return 1 if dmg >= hp and hp > 0 else 0


def _status_count(player: Any) -> int:
    return sum(1 for k in _STATUS_KEYS if _g(player, k))


def _ex_risk(player: Any) -> int:
    """Sum of extra prizes the opponent would gain (ex/megaEx in play)."""
    return sum(max(0, prize_value(p) - 1) for p in _iter_pokemon(player))


def _attackers_ready(player: Any) -> int:
    n = 0
    for p in _iter_pokemon(player):
        req = _energy_requirement(p)
        have = len(_g(p, "energies", []) or [])
        if req is not None and have >= req:
            n += 1
    return n


FEATURE_NAMES = [
    "prize_diff",        # opp_remaining - my_remaining  (closer to win = positive)
    "inplay_diff",
    "active_hp_diff",
    "energy_diff",
    "ko_threat_diff",
    "status_diff",       # opp_status - my_status
    "ex_risk_diff",      # opp_ex_risk - my_ex_risk
    "attackers_ready_diff",
    "hand_diff",
    "deck_diff",
]


def feature_vector(current: Any, my_index: int = 0) -> "OrderedDict[str, float]":
    """Raw, un-weighted features from player ``my_index`` perspective."""
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return OrderedDict((k, 0.0) for k in FEATURE_NAMES)
    me = players[my_index]
    opp = players[1 - my_index]

    def hp_frac(player: Any) -> float:
        a = _active(player)
        if a is None:
            return 0.0
        mx = float(_g(a, "maxHp", 0) or 0)
        return (float(_g(a, "hp", 0) or 0) / mx) if mx > 0 else 0.0

    f = OrderedDict()
    f["prize_diff"] = float(_prize_remaining(opp) - _prize_remaining(me))
    f["inplay_diff"] = float(_in_play_count(me) - _in_play_count(opp))
    f["active_hp_diff"] = hp_frac(me) - hp_frac(opp)
    f["energy_diff"] = float(_energy_total(me) - _energy_total(opp))
    f["ko_threat_diff"] = float(_can_ko(me, opp) - _can_ko(opp, me))
    f["status_diff"] = float(_status_count(opp) - _status_count(me))
    f["ex_risk_diff"] = float(_ex_risk(opp) - _ex_risk(me))
    f["attackers_ready_diff"] = float(_attackers_ready(me) - _attackers_ready(opp))
    f["hand_diff"] = float(_hand_size(me) - _hand_size(opp))
    f["deck_diff"] = float(
        int(_g(me, "deckCount", 0) or 0) - int(_g(opp, "deckCount", 0) or 0)
    )
    return f


# ---------------------------------------------------------------------------
# Dataset generation (buddy vs buddy, one sample per turn)
# ---------------------------------------------------------------------------

def collect_dataset(n_games: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X[n,feat], y[n] in {1,0.5,0}, progress[n] in (0,1])."""
    X_rows: list[list[float]] = []
    y_rows: list[float] = []
    prog_rows: list[float] = []

    for _ in range(n_games):
        samples: list[tuple[float, list[float]]] = []  # (turn, features)
        seen_turns: set[int] = set()

        def observer(current: Any, _acting: int) -> None:
            turn = int(_g(current, "turn", -1) or -1)
            if turn in seen_turns:
                return
            seen_turns.add(turn)
            fv = feature_vector(current, my_index=0)
            samples.append((turn, list(fv.values())))

        a, b = load_buddy_agent(), load_buddy_agent()
        result = play_game(a, b, observer=observer)
        if not samples:
            continue
        label = 1.0 if result == 0 else (0.0 if result == 1 else 0.5)
        n = len(samples)
        for i, (_turn, feats) in enumerate(samples):
            X_rows.append(feats)
            y_rows.append(label)
            prog_rows.append((i + 1) / n)

    return np.array(X_rows, float), np.array(y_rows, float), np.array(prog_rows, float)


# ---------------------------------------------------------------------------
# Logistic regression (Texel tuning) -- plain numpy, no sklearn dependency
# ---------------------------------------------------------------------------

class LearnedModel:
    def __init__(self, w: np.ndarray, b: float, mean: np.ndarray, std: np.ndarray):
        self.w, self.b, self.mean, self.std = w, b, mean, std

    def prob(self, X: np.ndarray) -> np.ndarray:
        z = (X - self.mean) / self.std
        return 1.0 / (1.0 + np.exp(-(z @ self.w + self.b)))

    def eval_position(self, current: Any, my_index: int = 0) -> float:
        fv = np.array([list(feature_vector(current, my_index).values())], float)
        return float(self.prob(fv)[0] - 0.5)  # >0 favours my_index


def fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 4000,
                 lr: float = 0.3, l2: float = 1e-3) -> LearnedModel:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    n, d = Z.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Z @ w + b)))
        err = p - y
        gw = Z.T @ err / n + l2 * w
        gb = err.mean()
        w -= lr * gw
        b -= lr * gb
    return LearnedModel(w, b, mean, std)


# ---------------------------------------------------------------------------
# Agreement-by-progress evaluation (baseline vs learned)
# ---------------------------------------------------------------------------

def agreement_by_progress(scores: np.ndarray, y: np.ndarray, prog: np.ndarray,
                          buckets: int = 5) -> list[dict]:
    """scores>0 predicts P0 win. Skip draws (y==0.5)."""
    rows = []
    decisive = y != 0.5
    outcome = np.where(y[decisive] == 1.0, 1.0, -1.0)
    s = scores[decisive]
    pr = prog[decisive]
    for i in range(buckets):
        lo, hi = i / buckets, (i + 1) / buckets
        m = (pr >= lo) & (pr < hi if i < buckets - 1 else pr <= hi)
        tot = int(m.sum())
        if tot == 0:
            rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": 0, "agreement": float("nan")})
            continue
        agree = float((np.sign(s[m]) == np.sign(outcome[m])).mean())
        rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": tot, "agreement": agree})
    return rows


def _baseline_scores(X_like_currents: list[Any]) -> np.ndarray:  # pragma: no cover
    raise NotImplementedError  # baseline needs raw currents; handled in main()


def main() -> None:
    p = argparse.ArgumentParser(description="Texel tuning of PTCG evaluation")
    p.add_argument("--train-games", type=int, default=40)
    p.add_argument("--val-games", type=int, default=20)
    p.add_argument("--buckets", type=int, default=5)
    args = p.parse_args()

    print(f"[1/3] collecting train data ({args.train_games} buddy-vs-buddy games)...")
    Xtr, ytr, _ = collect_dataset(args.train_games)
    print(f"      train samples: {len(ytr)}  (win={int((ytr==1).sum())} "
          f"loss={int((ytr==0).sum())} draw={int((ytr==0.5).sum())})")

    print("[2/3] fitting logistic model (Texel)...")
    model = fit_logistic(Xtr, ytr)
    print("      learned weights (standardised):")
    for name, wv in zip(FEATURE_NAMES, model.w):
        print(f"        {name:>22}: {wv:+.3f}")

    print(f"[3/3] validating on {args.val_games} fresh games (baseline vs learned)...")
    # Re-play val games, scoring each sampled position with BOTH evaluators.
    base_scores, learn_scores, ys, progs = [], [], [], []
    for _ in range(args.val_games):
        rows: list[tuple[int, Any]] = []
        seen: set[int] = set()

        def observer(current: Any, _a: int) -> None:
            t = int(_g(current, "turn", -1) or -1)
            if t in seen:
                return
            seen.add(t)
            rows.append((t, current))

        a, b = load_buddy_agent(), load_buddy_agent()
        result = play_game(a, b, observer=observer)
        if not rows:
            continue
        label = 1.0 if result == 0 else (0.0 if result == 1 else 0.5)
        n = len(rows)
        for i, (_t, cur) in enumerate(rows):
            base_scores.append(state_eval(cur, my_index=0))
            learn_scores.append(model.eval_position(cur, my_index=0))
            ys.append(label)
            progs.append((i + 1) / n)

    base_scores = np.array(base_scores); learn_scores = np.array(learn_scores)
    ys = np.array(ys); progs = np.array(progs)

    base_rows = agreement_by_progress(base_scores, ys, progs, args.buckets)
    learn_rows = agreement_by_progress(learn_scores, ys, progs, args.buckets)

    print("\n=== agreement (eval sign vs eventual winner) by game progress ===")
    print(f"{'progress':>10} | {'n':>6} | {'baseline':>9} | {'learned':>9}")
    print("-" * 46)
    for br, lr_ in zip(base_rows, learn_rows):
        print(f"{br['bucket']:>10} | {br['n']:>6} | {br['agreement']:>9.3f} | {lr_['agreement']:>9.3f}")
    # overall
    dec = ys != 0.5
    out = np.where(ys[dec] == 1.0, 1.0, -1.0)
    base_acc = (np.sign(base_scores[dec]) == np.sign(out)).mean()
    learn_acc = (np.sign(learn_scores[dec]) == np.sign(out)).mean()
    print("-" * 46)
    print(f"{'overall':>10} | {int(dec.sum()):>6} | {base_acc:>9.3f} | {learn_acc:>9.3f}")
    print("\n注: learned が baseline を上回れば Texel チューニングが有効。")


if __name__ == "__main__":
    main()
