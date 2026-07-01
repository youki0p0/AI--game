"""対Crustle 用の炎スレイヤー評価関数（planning強化）。

plain state_eval に、対壁で効く2項を加える:
  1) 炎アタッカーの 3エネ組成（OHKO到達）を強く報酬化 → 最速で弱点OHKOを撃てる形へ。
  2) Jamming Tower が自分の場に出ている（ヒーローマント無効化→Crustleを素150へ）を報酬化。
非壁マッチでもほぼ無害（炎エネ組成/スタジアムは常に軽い加点）。
"""
from __future__ import annotations

from typing import Any, Optional

from .state_eval import (
    DEFAULT_WEIGHTS, Weights, _card_data, _g, _iter_pokemon, state_eval,
)

FIRE_TYPE = 2
JAMMING_TOWER = 1246
W_FIRE_ENERGY = 45.0   # 炎アタッカーに乗った(最大3までの)エネ1個あたり
W_JAM = 120.0          # Jamming Tower が自分の場に出ている


def fire_slayer_eval(current: Any, my_index: int,
                     weights: Optional[Weights] = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    base = state_eval(current, my_index, w)
    if current is None:
        return base
    result = _g(current, "result", -1)
    if result is not None and result != -1:
        return base  # 終局はそのまま
    players = _g(current, "players", []) or []
    if len(players) < 2 or my_index not in (0, 1):
        return base
    me = players[my_index]
    bonus = 0.0
    # (1) 炎アタッカーの3エネ組成（OHKO到達度）
    for p in _iter_pokemon(me):
        cd = _card_data(_g(p, "id"))
        if cd is not None and _g(cd, "energyType") == FIRE_TYPE:
            have = len(_g(p, "energies", []) or [])
            bonus += W_FIRE_ENERGY * min(have, 3)
    # (2) Jamming Tower が自分の場に出ているか（ヒーローマント剥がし）
    for s in (_g(current, "stadium", []) or []):
        if _g(s, "id") == JAMMING_TOWER:
            bonus += W_JAM
            break
    return base + bonus
