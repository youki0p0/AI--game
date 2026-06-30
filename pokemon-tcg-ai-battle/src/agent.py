"""PTCG AI Battle 用エージェントの方策ロジック。

CABT エンジン仕様（https://matsuoinstitute.github.io/cabt/）:
  observation = {
    "logs":    過去のアクション/イベントのログ,
    "current": 盤面状態(デッキ選択中などは None),
    "select":  {"option": [...選択肢...], "maxCount": int, ...},
  }
  エージェントは select.option のインデックスを `maxCount` 個選び、
  **int の配列 (list[int])** で返す。エンジンは合法な選択肢のみ提示する。

board state (current) 主要フィールド:
  players[*]: active(0-1体), bench(最大5), hand, prize, deckCount, discard,
              handCount, benchMax, 状態異常(poisoned/burned/asleep/paralyzed/confused)
  stadium, ターン数, 先攻/後攻, サポート/スタジアム/エネルギー使用状況 など

まずは「先頭から maxCount 個選ぶ」決定論ベースラインを置く。
後で current(盤面) を読んでルールベース→探索→学習へ発展させる。
"""
from __future__ import annotations

import random
from typing import Any


def _select(observation: dict) -> tuple[list, int]:
    sel = observation.get("select") or {}
    options = sel.get("option") or []
    max_count = sel.get("maxCount") or (1 if options else 0)
    return options, max_count


def choose_indices(observation: dict) -> list[int]:
    """選択する option のインデックス配列を返す（ベースライン: 先頭から maxCount 個）。

    置き換えポイント:
      - ルールベース: option/current を見て最大ダメージ手・有利な選択を採る
      - 探索: 各 option を評価して最良の組を選ぶ
    """
    options, max_count = _select(observation)
    n = len(options)
    if n == 0 or max_count <= 0:
        return []
    return list(range(min(max_count, n)))


def choose_indices_random(observation: dict, rng: random.Random | None = None) -> list[int]:
    """ランダム・ベースライン（CABTドキュメントの例と同等）。"""
    options, max_count = _select(observation)
    n = len(options)
    if n == 0 or max_count <= 0:
        return []
    rng = rng or random
    return rng.sample(range(n), min(max_count, n))


class Agent:
    """状態を持つ方策の入れ物（学習方策・先読みキャッシュ等）。"""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def reset(self) -> None:
        """対戦開始時の初期化フック。"""

    def act(self, observation: dict) -> list[int]:
        return choose_indices(observation)


if __name__ == "__main__":
    demo = {"logs": [], "current": None,
            "select": {"option": ["deckA", "deckB", "deckC"], "maxCount": 1}}
    print("deterministic:", choose_indices(demo))
    print("random:       ", choose_indices_random(demo, random.Random(0)))
