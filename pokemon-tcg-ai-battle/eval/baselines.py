"""Baseline agents for CABT evaluation.

Each factory/function returns a callable with the signature:
    agent(obs: dict) -> list[int]

During the deck-selection phase obs["select"] is None; the agent must
return a list of 60 card-IDs (the deck).  During normal play the agent
returns option indices.
"""
from __future__ import annotations

import random as _random
from typing import Callable

from .engine_driver import load_default_deck


def make_random_agent(seed: int | None = None) -> Callable[[dict], list[int]]:
    """Return a random agent.

    Deck-selection phase: returns the default deck.
    Normal phase: randomly samples between minCount and maxCount (inclusive)
    indices from the available options.

    Args:
        seed: Seed for the random number generator.  Note that the engine's
              internal RNG (coin flips, shuffle) cannot be seeded externally,
              so strict game-level reproducibility is not guaranteed even when
              this seed is fixed.
    """
    rng = _random.Random(seed)

    def random_agent(obs: dict) -> list[int]:
        select = obs.get("select") if obs else None
        if select is None:
            # Deck-selection phase
            return load_default_deck()

        options = select.get("option", [])
        min_count = int(select.get("minCount", 0))
        max_count = int(select.get("maxCount", len(options)))
        # Clamp to valid range
        max_count = min(max_count, len(options))
        min_count = min(min_count, max_count)

        n = rng.randint(min_count, max_count) if min_count <= max_count else 0
        indices = list(range(len(options)))
        chosen = rng.sample(indices, k=n)
        return chosen

    return random_agent


def first_legal_agent(obs: dict) -> list[int]:
    """Deterministic agent that always picks the first maxCount options.

    Deck-selection phase: returns the default deck.
    Normal phase: returns indices [0, 1, ..., maxCount-1].
    """
    select = obs.get("select") if obs else None
    if select is None:
        return load_default_deck()

    options = select.get("option", [])
    max_count = int(select.get("maxCount", len(options)))
    max_count = min(max_count, len(options))
    return list(range(max_count))
