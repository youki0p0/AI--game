"""並行ガントレット: 1つのエージェントを複数の相手デッキと *同時並行* で対戦させ、
勝率を集計する。パイロット改善(チューニング)の計測を高速化するためのハーネス。

CABT エンジンはプロセスグローバルな battle_ptr を使い「1プロセス1試合」しか回せない。
そこで相手ごとに **別プロセス** を割り当てて並列化する（= ユーザの言う「複数パネル」）。
multiprocessing.Pool で opponent 数だけワーカーを立て、各ワーカーが N 戦を回す。

使い方:
    python -m eval.gauntlet dragapult --games 100 --opponents buddy,crustle,archaludon,fire
"""
from __future__ import annotations

import math
import multiprocessing as mp
import pickle
from typing import Callable


# --- コンテスタント(自分/相手)の構築: 名前 -> (agent_factory, deck) -------------
def build_contestant(name: str, opp_deck: list[int] | None = None
                     ) -> tuple[Callable[[], Callable], list[int]]:
    """名前から (agentを返すfactory, 60枚デッキ) を作る。プロセス内で呼ぶ。

    opp_deck: 探索型パイロット(相手デッキで隠れ情報を復元)に渡す。他は無視。
    """
    from .engine_driver import _ensure_engine_on_path, _get_engine_dir
    _ensure_engine_on_path()

    if name == "buddy":
        from .agents_buddy import load_buddy_agent
        deck = list(pickle.load(open(_get_engine_dir() / "deck.pkl", "rb")))
        return (load_buddy_agent, deck)
    if name == "crustle":
        from .crustle_bot import CRUSTLE_DECK, crustle_agent
        return ((lambda: crustle_agent), list(CRUSTLE_DECK))
    if name == "archaludon":
        from .crustle_bot import ARCHALUDON_DECK, make_simple_bot
        return ((lambda: make_simple_bot(ARCHALUDON_DECK)), list(ARCHALUDON_DECK))
    if name == "fire":
        from .decks import DECKS
        from .typed_pilot import make_typed_pilot
        d = DECKS["fire_single"]
        return ((lambda: make_typed_pilot(d, energy_id=2,
                                          attacker_priority=[663, 318, 1027, 358, 490],
                                          min_attack_dmg=120)), list(d))
    if name == "psychic":
        from .champion import CHAMPION_DECK, champion_agent
        return (champion_agent, list(CHAMPION_DECK))
    if name == "dragapult":
        from .dragapult_deck import DRAGAPULT_DECK
        from .dragapult_pilot import make_dragapult_pilot
        return ((lambda: make_dragapult_pilot(go_first=True)), list(DRAGAPULT_DECK))
    if name == "dragapult_search":
        from .dragapult_deck import DRAGAPULT_DECK
        from .dragapult_search import make_dragapult_search_pilot
        return ((lambda: make_dragapult_search_pilot(opp_deck)), list(DRAGAPULT_DECK))
    if name == "fire_slayer":
        # WEB調査ベースの対Crustle炎デッキ。探索型で3エネOHKOを組む(opp_deck既知時)。
        from .decks import DECKS
        d = DECKS["fire_slayer"]
        if opp_deck is None:
            from .typed_pilot import make_typed_pilot
            return ((lambda: make_typed_pilot(d, energy_id=2,
                                              attacker_priority=[663, 1027, 358, 490],
                                              min_attack_dmg=150)), list(d))
        from .deck_battle import make_deck_agent
        return ((lambda: make_deck_agent(d, list(opp_deck), n_turns=1, rollout_budget=40)), list(d))
    # 汎用: DECKS の型デッキ + generic_pilot
    from .decks import DECKS
    from .generic_pilot import make_generic_pilot
    if name in DECKS:
        d = DECKS[name]
        return ((lambda: make_generic_pilot(d)), list(d))
    raise ValueError(f"unknown contestant: {name}")


def _run_matchup(args: tuple) -> dict:
    """1つの相手に対して N 戦（先後入替）。別プロセスで実行される。"""
    hero_name, opp_name, n_games = args
    from .engine_driver import play_game
    opp_factory, opp_deck = build_contestant(opp_name)
    # 探索型 hero は相手デッキで隠れ情報を復元するため opp_deck を渡す
    hero_factory, hero_deck = build_contestant(hero_name, opp_deck=opp_deck)
    w = l = d = 0
    for gi in range(n_games):
        if gi % 2 == 0:
            r = play_game(hero_factory(), opp_factory(), deck0=hero_deck, deck1=opp_deck)
            me = 0
        else:
            r = play_game(opp_factory(), hero_factory(), deck0=opp_deck, deck1=hero_deck)
            me = 1
        if r == me:
            w += 1
        elif r == (1 - me):
            l += 1
        else:
            d += 1
    rate = w / n_games if n_games else 0.0
    se = math.sqrt(rate * (1 - rate) / n_games) if n_games else 0.0
    return {"opponent": opp_name, "n": n_games, "w": w, "l": l, "d": d,
            "winrate": rate, "ci_lo": rate - 1.96 * se, "ci_hi": rate + 1.96 * se}


def run_gauntlet(hero: str, opponents: list[str], games: int = 100,
                 workers: int | None = None) -> list[dict]:
    """hero を各 opponent と *並行* に対戦させ、結果リストを返す。"""
    tasks = [(hero, opp, games) for opp in opponents]
    workers = workers or min(len(tasks), max(1, (mp.cpu_count() or 2)))
    ctx = mp.get_context("spawn")  # engine のグローバル状態をプロセス間で汚さない
    with ctx.Pool(processes=workers) as pool:
        results = pool.map(_run_matchup, tasks)
    return results


def _print(hero: str, results: list[dict]) -> None:
    print(f"=== GAUNTLET: {hero} vs {len(results)} decks (並行) ===")
    tot_w = tot_n = 0
    for r in sorted(results, key=lambda x: -x["winrate"]):
        tot_w += r["w"]; tot_n += r["n"]
        print(f"  vs {r['opponent']:16} {r['winrate']:.3f} "
              f"[{r['ci_lo']:.3f},{r['ci_hi']:.3f}]  W{r['w']} L{r['l']} D{r['d']}")
    if tot_n:
        print(f"  {'OVERALL':19} {tot_w/tot_n:.3f}  ({tot_w}/{tot_n})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("hero")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--opponents", default="buddy,crustle,archaludon,fire,psychic")
    ap.add_argument("--workers", type=int, default=0)
    a = ap.parse_args()
    opps = [x.strip() for x in a.opponents.split(",") if x.strip()]
    res = run_gauntlet(a.hero, opps, games=a.games, workers=a.workers or None)
    _print(a.hero, res)
