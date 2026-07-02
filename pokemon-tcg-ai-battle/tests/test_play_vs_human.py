"""Tests for eval.play_vs_human -- the interactive human-vs-AI CLI.

These exercise only the engine-independent parts (option/board rendering,
input parsing, opponent-deck resolution) with synthetic ``obs`` dicts, since
the real CABT engine (``engine/cg``) is not distributed in this repo and may
not be present in every environment.
"""
from __future__ import annotations

import sys
import os

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import pytest

from eval.play_vs_human import (
    HumanResign,
    T_ATTACK,
    T_END,
    T_PLAY,
    describe_option,
    list_opponents,
    make_human_agent,
    render_board,
    resolve_opponent,
)

CURRENT = {
    "turn": 3,
    "players": [
        {"active": [{"id": 971, "hp": 90, "maxHp": 140, "energy": [1, 2]}],
         "bench": [{"id": 216, "hp": 70, "maxHp": 70, "energy": []}],
         "prize": [None] * 4, "handCount": 5, "deckCount": 40, "discard": [1, 2]},
        {"active": [{"id": 678, "hp": 200, "maxHp": 340, "poisoned": True}],
         "bench": [], "prize": [None] * 5, "handCount": 4, "deckCount": 38, "discard": []},
    ],
}

OPTIONS = [
    {"type": T_ATTACK, "attackId": 12345},
    {"type": T_PLAY, "index": 0},
    {"type": T_END},
]


def test_render_board_does_not_raise():
    render_board(CURRENT, me=0)
    render_board(None, me=0)  # no-op guard


def test_describe_option_labels_are_japanese_and_non_empty():
    labels = [describe_option(o, CURRENT, 0) for o in OPTIONS]
    assert labels[0].startswith("こうげき")
    assert labels[2] == "ターン終了"
    assert all(labels)


def test_human_agent_deck_submission_phase_returns_deck():
    deck = list(range(60))
    agent = make_human_agent(deck, me=0, input_fn=lambda p: pytest.fail("should not prompt"))
    obs = {"select": None, "current": None}
    assert agent(obs) == deck


def test_human_agent_rejects_out_of_range_then_accepts():
    inputs = iter(["99", "0"])
    agent = make_human_agent([0] * 60, me=0, input_fn=lambda p: next(inputs))
    sel = {"option": OPTIONS, "maxCount": 1, "minCount": 0}
    obs = {"select": sel, "current": CURRENT}
    assert agent(obs) == [0]


def test_human_agent_empty_input_allowed_when_min_count_zero():
    agent = make_human_agent([0] * 60, me=0, input_fn=lambda p: "")
    sel = {"option": OPTIONS, "maxCount": 1, "minCount": 0}
    obs = {"select": sel, "current": CURRENT}
    assert agent(obs) == []


def test_human_agent_multi_select_within_max_count():
    agent = make_human_agent([0] * 60, me=0, input_fn=lambda p: "0,1")
    sel = {"option": OPTIONS, "maxCount": 2, "minCount": 1}
    obs = {"select": sel, "current": CURRENT}
    assert agent(obs) == [0, 1]


def test_human_agent_resign_raises():
    agent = make_human_agent([0] * 60, me=0, input_fn=lambda p: "q")
    sel = {"option": OPTIONS, "maxCount": 1, "minCount": 0}
    obs = {"select": sel, "current": CURRENT}
    with pytest.raises(HumanResign):
        agent(obs)


def test_resolve_opponent_unknown_name_raises_value_error():
    with pytest.raises(ValueError):
        resolve_opponent("no-such-opponent")


@pytest.mark.parametrize("name", [n for n in list_opponents() if n != "buddy"])
def test_resolve_opponent_builds_callable_and_60_card_deck(name):
    # "buddy" needs engine/sample_agent_buddy.py, so it is excluded here.
    agent, deck = resolve_opponent(name)
    assert callable(agent)
    assert len(deck) == 60


def test_resolve_opponent_path_form_autodetects_deck():
    agent, deck = resolve_opponent("submissions/grimmsnarl_agent.py")
    assert callable(agent)
    assert len(deck) == 60
