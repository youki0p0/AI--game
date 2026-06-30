"""Engine driver: path setup, deck loading, and single-game execution.

The CABT engine uses a module-global battle_ptr (cg.sim.Battle.battle_ptr).
Therefore games MUST be executed sequentially -- do NOT parallelize.
"""
from __future__ import annotations

import os
import pickle
import sys
import warnings
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Engine path helpers
# ---------------------------------------------------------------------------

def _get_engine_dir() -> Path:
    """Return the absolute path to the engine/ directory.

    Searches candidate locations in priority order:
      1. Sibling of the package root (pokemon-tcg-ai-battle/engine/)
         -- handles the normal checkout case.
      2. Real path of this file's package root resolved through symlinks
         -- handles git-worktree scenarios where __file__ resolves to the
         worktree path but engine/ lives in the main working tree.
      3. CABT_ENGINE_PATH environment variable -- override for CI/custom layout.

    Layout assumed for case 1/2:
        <repo>/
            engine/          <- CABT engine (gitignored, placed locally)
            pokemon-tcg-ai-battle/
                eval/        <- this file
    """
    # Case 3: explicit env override
    env_path = os.environ.get("CABT_ENGINE_PATH")
    if env_path:
        p = Path(env_path)
        if (p / "cg").is_dir():
            return p

    here = Path(__file__).resolve().parent          # eval/
    project = here.parent                           # pokemon-tcg-ai-battle/

    # Case 1: engine/ next to the project directory
    candidates = [
        project / "engine",                        # worktree layout
        project.parent / "engine",                 # if eval/ is one level up
    ]

    # Case 2: walk up __file__ real path (resolves git-worktree symlinks)
    real_here = Path(os.path.realpath(__file__)).parent
    real_project = real_here.parent
    candidates += [
        real_project / "engine",
        real_project.parent / "engine",
    ]

    # Also search relative to the main repo location by resolving .git worktree link
    # Common pattern: /home/user/AI--game/.claude/worktrees/<id>/pokemon-tcg-ai-battle/
    # Main repo:      /home/user/AI--game/pokemon-tcg-ai-battle/
    main_repo_candidates = []

    # Walk up from worktree root looking for a .git file (worktree marker)
    wt_root = project
    for _ in range(8):
        git_file = wt_root / ".git"
        if git_file.is_file():
            # Parse "gitdir: /abs/path" to find the worktrees/<id> dir
            content = git_file.read_text().strip()
            if content.startswith("gitdir:"):
                wt_git_dir = Path(content.split(":", 1)[1].strip())
                # commondir contains the relative path to the main .git dir
                commondir_file = wt_git_dir / "commondir"
                if commondir_file.is_file():
                    commondir_rel = commondir_file.read_text().strip()
                    main_git_dir = (wt_git_dir / commondir_rel).resolve()
                    main_repo_root = main_git_dir.parent  # strip trailing ".git"
                    # project name inside main repo = same name as in worktree
                    proj_name = project.name
                    main_repo_candidates += [
                        main_repo_root / proj_name / "engine",
                        main_repo_root / "engine",
                    ]
            break
        wt_root = wt_root.parent

    candidates += main_repo_candidates

    for candidate in candidates:
        if (candidate / "cg").is_dir():
            return candidate

    raise FileNotFoundError(
        "engine/cg/ not found. Searched:\n"
        + "\n".join(f"  {c}" for c in candidates)
        + "\nSet CABT_ENGINE_PATH env var or place engine/ next to pokemon-tcg-ai-battle/."
    )


def _ensure_engine_on_path() -> None:
    """Add engine/ to sys.path if not already present."""
    engine_dir = str(_get_engine_dir())
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)


# ---------------------------------------------------------------------------
# Deck loading
# ---------------------------------------------------------------------------

def load_default_deck() -> list[int]:
    """Load the default deck (60 card-IDs) from engine/deck.pkl."""
    _ensure_engine_on_path()
    deck_path = _get_engine_dir() / "deck.pkl"
    with open(deck_path, "rb") as f:
        deck = pickle.load(f)
    if not isinstance(deck, list) or len(deck) != 60:
        raise ValueError(f"deck.pkl must be a list of 60 ints, got {type(deck)} len={len(deck)}")
    return deck


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def play_game(
    agent0: Callable[[dict], list[int]],
    agent1: Callable[[dict], list[int]],
    deck0: list[int] | None = None,
    deck1: list[int] | None = None,
    max_steps: int = 20000,
) -> int:
    """Play a single game between two agents and return the result.

    Args:
        agent0: Agent function for player 0.  Signature: (obs: dict) -> list[int].
                During the deck-selection phase (obs["select"] is None) the agent
                should return a list of 60 card-IDs.
        agent1: Agent function for player 1.  Same contract as agent0.
        deck0: 60-element list of card-IDs for player 0.  Uses default deck if None.
        deck1: 60-element list of card-IDs for player 1.  Uses default deck if None.
        max_steps: Safety limit on the number of battle_select calls.
                   If exceeded the game is treated as a draw (result=2).

    Returns:
        int: 0 = P0 wins, 1 = P1 wins, 2 = draw / timeout.

    Notes:
        - battle_finish() is always called (even on exception) via try/finally.
        - The engine uses a module-global battle_ptr; only one game at a time.
    """
    _ensure_engine_on_path()
    import cg.game as game  # noqa: PLC0415 -- intentional deferred import
    from cg.sim import Battle, lib  # noqa: PLC0415

    if deck0 is None:
        deck0 = load_default_deck()
    if deck1 is None:
        deck1 = load_default_deck()

    obs, _start_data = game.battle_start(deck0, deck1)

    try:
        steps = 0
        while True:
            # Check termination -------------------------------------------------
            current = obs.get("current") if obs else None
            if current is not None:
                result = current.get("result", -1)
                if result != -1:
                    return int(result)

            # Safety limit -------------------------------------------------------
            if steps >= max_steps:
                warnings.warn(
                    f"play_game: max_steps ({max_steps}) exceeded -- treating as draw",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return 2

            # Determine acting player -------------------------------------------
            serial_data = lib.GetBattleData(Battle.battle_ptr)
            acting_player = int(serial_data.selectPlayer)  # 0 or 1
            agent = agent0 if acting_player == 0 else agent1

            # Deck-selection phase: select is None and current is None ----------
            select = obs.get("select") if obs else None
            if select is None:
                # Agent must return a 60-card deck list
                action = agent(obs)
            else:
                # Normal selection phase
                action = agent(obs)

            obs = game.battle_select(action)
            steps += 1

    finally:
        game.battle_finish()
