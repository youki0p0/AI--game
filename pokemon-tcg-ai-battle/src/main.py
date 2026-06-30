"""kaggle-environments 提出エントリ。

提出時はこのファイル（または同等の関数）を agent として登録する。
kaggle-environments の慣例に合わせて `act(observation, configuration)` を公開。
返り値は「選択する合法手のインデックス」。複数選択が必要な仕様なら配列を返すよう調整する。
"""
from __future__ import annotations

from typing import Any

try:
    from .agent import choose_index
except ImportError:  # 提出環境で単体ファイルとして読まれる場合のフォールバック
    from agent import choose_index  # type: ignore


def act(observation: Any, configuration: Any = None) -> int:
    """1ターン分の行動を返す。"""
    return choose_index(observation)


# kaggle-environments は呼び出し可能オブジェクトを agent として受け取る
agent = act
