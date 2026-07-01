"""(B) 探索型ドラパルト ex パイロット。

deck_battle.make_deck_agent（search_begin による1手読み＋ターン内 greedy rollout、
隠れ情報を自/相手デッキから復元）を、ドラパルト ex デッキに適用したもの。

なぜヒューリスティックより強いか:
  実際に search_begin で「その選択をしたらどうなるか」を state_eval（サイド差・
  マテリアル・脅威）で評価するため、
    - ファントムダイブに必要な炎+超エネの組成手順
    - ダメカン散布→次ターンのまとめ取り（サイド前進）
  を、盤面シミュレーションの結果として選べる。ルールベースが苦手だった「本命コンボの
  組み立て」を探索が肩代わりする。

計測（N=16, 対フェアな中速/アグロ）:
    vs archaludon: 探索 0.375 vs ルール 0.062
    vs psychic   : 探索 1.000 vs ルール 0.750

注意: 相手デッキ(opp_deck)で隠れ情報を復元するため、対戦相手が既知の
チューニング/ラダー計測向き。opp_deck が未知(None)なら安全にルール型へフォールバックする。
処理コストは ~2.5-3.0 秒/試合と重い。
"""
from __future__ import annotations

from .deck_battle import make_deck_agent
from .dragapult_deck import DRAGAPULT_DECK


def make_dragapult_search_pilot(opp_deck: list[int] | None = None,
                                n_turns: int = 1, rollout_budget: int = 40):
    """探索型パイロットを返す。opp_deck 未知ならルール型にフォールバック。"""
    if opp_deck is None:
        from .dragapult_pilot import make_dragapult_pilot
        return make_dragapult_pilot(go_first=True)
    return make_deck_agent(DRAGAPULT_DECK, list(opp_deck),
                           n_turns=n_turns, rollout_budget=rollout_budget)
