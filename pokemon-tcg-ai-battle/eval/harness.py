"""Evaluation harness: run N games and aggregate win/loss/draw statistics.

Sequential execution is mandatory because the CABT engine uses a module-global
battle_ptr (cg.sim.Battle.battle_ptr) -- only one game can run at a time.
"""
from __future__ import annotations

from typing import Callable

from .engine_driver import play_game


def evaluate(
    agent: Callable[[dict], list[int]],
    opponent: Callable[[dict], list[int]],
    n_games: int = 50,
    alternate_sides: bool = True,
    seed: int = 0,
) -> dict:
    """Evaluate *agent* against *opponent* over n_games sequential games.

    Args:
        agent: The agent under evaluation.  Signature: (obs: dict) -> list[int].
        opponent: The opponent agent.  Same signature.
        n_games: Total number of games to play.
        alternate_sides: If True, alternate which player slot the agent occupies
                         each game (half as P0, half as P1) to eliminate
                         first-player bias.  When n_games is odd the extra game
                         has the agent as P0.
        seed: Base seed forwarded to play_game is not used directly here (engine
              RNG is not externally seedable), but kept for API consistency.

    Returns:
        dict with keys:
            n       -- total games played
            wins    -- games agent won
            losses  -- games agent lost
            draws   -- games that were draws
            winrate -- wins / n  (float in [0.0, 1.0])
    """
    wins = 0
    losses = 0
    draws = 0

    for i in range(n_games):
        # Determine which slot the agent occupies this game
        if alternate_sides:
            agent_is_p0 = (i % 2 == 0)
        else:
            agent_is_p0 = True

        if agent_is_p0:
            agent0, agent1 = agent, opponent
        else:
            agent0, agent1 = opponent, agent

        result = play_game(agent0, agent1)  # 0=P0 wins, 1=P1 wins, 2=draw

        if result == 2:
            draws += 1
        elif (result == 0 and agent_is_p0) or (result == 1 and not agent_is_p0):
            wins += 1
        else:
            losses += 1

    n = wins + losses + draws
    winrate = wins / n if n > 0 else 0.0

    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "winrate": winrate,
    }
