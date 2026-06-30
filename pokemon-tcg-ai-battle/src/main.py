"""kaggle-environments / CABT 提出エントリ。

CABT は observation(dict) を受け取り、選択した option の **インデックス配列** を返す
呼び出し可能オブジェクトを agent とする（例: env.run([agent1, agent2])）。
"""
from __future__ import annotations

from typing import Any

try:
    from .agent import choose_indices
except ImportError:
    from agent import choose_indices  # type: ignore


def agent(observation: dict, configuration: Any = None) -> list[int]:
    """1ターン分の選択を返す（list[int]）。"""
    return choose_indices(observation)
