"""Tests for the CABT evaluation harness.

NOTE ON ENGINE RANDOMNESS:
The CABT engine's internal RNG (coin flips, card shuffle, etc.) cannot be
seeded from Python.  Therefore tests verify:
  - Completion without exception
  - Return-value types and ranges
They do NOT assert specific win counts or exact game outcomes.
"""
from __future__ import annotations

import sys
import os

# Ensure the pokemon-tcg-ai-battle package root is on sys.path when running
# pytest from repo root or from the package directory.
_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from eval.engine_driver import play_game
from eval.baselines import make_random_agent, first_legal_agent
from eval.harness import evaluate


def test_play_game_random_vs_random_returns_int():
    """AC1: play_game(random, random) completes without exception and returns int in {0,1,2}."""
    random0 = make_random_agent(seed=1)
    random1 = make_random_agent(seed=2)
    result = play_game(random0, random1)
    assert isinstance(result, int), f"Expected int, got {type(result)}"
    assert result in (0, 1, 2), f"Result {result} not in {{0, 1, 2}}"


def test_evaluate_returns_correct_structure():
    """AC2: evaluate returns dict with required keys, winrate in [0,1], n == n_games."""
    n_games = 6
    random_agent = make_random_agent(seed=42)
    stats = evaluate(
        agent=random_agent,
        opponent=first_legal_agent,
        n_games=n_games,
        alternate_sides=True,
    )

    assert "n" in stats
    assert "wins" in stats
    assert "losses" in stats
    assert "draws" in stats
    assert "winrate" in stats

    assert stats["n"] == n_games, f"Expected n={n_games}, got {stats['n']}"
    assert 0.0 <= stats["winrate"] <= 1.0, f"winrate {stats['winrate']} out of [0,1]"

    # Counts must be non-negative and sum to n
    assert stats["wins"] >= 0
    assert stats["losses"] >= 0
    assert stats["draws"] >= 0
    assert stats["wins"] + stats["losses"] + stats["draws"] == n_games
