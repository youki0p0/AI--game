"""Load the bundled CABT sample agent ("buddy") as isolated callables.

The sample agent (``engine/sample_agent_buddy.py``) keeps mutable module-level
globals (``plan`` / ``pre_turn`` / ``ability_used``) and loads ``deck.pkl`` at
import time.  To run buddy-vs-buddy inside a single process each side needs its
OWN globals, so we import the source file as a *fresh* module instance per call.

buddy is a competent rule-based agent, so buddy-vs-buddy games produce
realistically played positions -- the right dataset for validating/tuning the
state evaluation function (much higher signal than random-vs-random).
"""
from __future__ import annotations

import importlib.util
import os
from typing import Callable

from .engine_driver import _ensure_engine_on_path, _get_engine_dir

_instance_counter = 0


def load_buddy_agent() -> Callable[[dict], list[int]]:
    """Return a fresh, independent buddy ``agent(obs_dict) -> list[int]``.

    Each call yields a separate module instance with its own mutable globals,
    so two buddy agents can play each other without trampling shared state.
    """
    global _instance_counter
    engine_dir = _get_engine_dir()
    _ensure_engine_on_path()  # so the sample's ``from cg.api import ...`` resolves

    sample = engine_dir / "sample_agent_buddy.py"
    if not sample.is_file():
        raise FileNotFoundError(
            f"sample agent not found: {sample}. Place the CABT package under engine/."
        )

    _instance_counter += 1
    mod_name = f"_buddy_agent_instance_{_instance_counter}"
    spec = importlib.util.spec_from_file_location(mod_name, sample)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load sample agent from {sample}")
    module = importlib.util.module_from_spec(spec)

    # The sample opens "deck.pkl" relative to cwd; run its import with cwd=engine_dir.
    prev_cwd = os.getcwd()
    os.chdir(engine_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(prev_cwd)

    agent = getattr(module, "agent", None)
    if not callable(agent):
        raise AttributeError("sample agent module has no callable 'agent'")
    return agent


if __name__ == "__main__":
    # Minimal self-check: buddy vs buddy should finish with a valid result.
    from .engine_driver import play_game

    a = load_buddy_agent()
    b = load_buddy_agent()
    result = play_game(a, b)
    print(f"buddy vs buddy result: {result} (0=P0 win, 1=P1 win, 2=draw)")
