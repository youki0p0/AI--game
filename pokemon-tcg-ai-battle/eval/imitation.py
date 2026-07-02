"""模倣検証ハーネス: リプレイの全決定点で「候補パイロットの出力 == 実際の指し手」の一致率を測る。

リプレイ(Kaggleエピソード)には各決定点の観測(observation)と実際の行動(action)が両方あるため、
試合を再現走行せず、記録観測を候補エージェントに与えて指し手を照合する（オフライン検証）。
→ 相手も味方も文脈は記録どおり＝「ログがほぼ一致するか」を決定点単位で定量化できる。

使い方:
  python -m eval.imitation --dir /tmp/topwin --player Huangxiayiluo --pilot search
出力: 全体一致率 / 決定種類(context, optionタイプ)別の一致率と不一致トップ。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter, defaultdict

from .engine_driver import _ensure_engine_on_path

CTX_NAME = {0: "MAIN", 1: "置く(初期)", 2: "置く", 3: "ベンチへ", 4: "配置", 5: "配置", 6: "攻撃選択",
            7: "山→手札", 8: "山→ベンチ", 21: "エネ選択", 22: "対象選択", 30: "並べ替え",
            38: "マリガン確認", 41: "先攻選択", 42: "マリガン"}
OPT_NAME = {1: "YES", 2: "NO", 3: "CARD", 4: "NUMBER", 7: "PLAY", 8: "ATTACH", 9: "EVOLVE",
            10: "ABILITY", 11: "DISCARD", 12: "RETREAT", 13: "ATTACK", 14: "END"}


def extract_decisions(path: str, player_name: str):
    """(observation, action) 対を対象プレイヤーの決定点だけ抽出する。"""
    d = json.load(open(path))
    steps = d.get("steps") or []
    info = d.get("info") or {}
    names = info.get("TeamNames") or []
    if player_name not in names:
        return None
    pi = names.index(player_name)
    out = []
    # Kaggleリプレイは「step t の観測への応答が step t+1 の action に記録」される(実測66/66で妥当)。
    for t in range(len(steps) - 1):
        e = steps[t][pi]
        obs = e.get("observation") or {}
        sel = obs.get("select")
        if e.get("status") != "ACTIVE" or sel is None:
            continue
        opts = sel.get("option") or []
        if len(opts) == 0:
            continue
        act = steps[t + 1][pi].get("action")
        if not act or len(act) == 60:  # 空/デッキ選択は対象外
            continue
        if not all(isinstance(i, int) and 0 <= i < len(opts) for i in act):
            continue  # 稀な不整合はスキップ
        out.append((obs, list(act)))
    return {"player_index": pi, "decisions": out, "rewards": d.get("rewards"),
            "file": os.path.basename(path)}


def choice_kind(obs, act):
    """決定の種類ラベル（不一致分析用）。"""
    sel = obs.get("select") or {}
    ctx = sel.get("context")
    opts = sel.get("option") or []
    t = None
    if act and 0 <= act[0] < len(opts):
        t = opts[act[0]].get("type")
    return f"{CTX_NAME.get(ctx, f'ctx{ctx}')}/{OPT_NAME.get(t, f'op{t}')}"


def evaluate_pilot(agent_fn, games, max_per_game=None):
    """全決定点で agent_fn(obs) と記録手を照合。(一致数, 総数, 種類別集計, 不一致例)"""
    total = hit = 0
    by_kind = defaultdict(lambda: [0, 0])  # kind -> [hit, total]
    misses = Counter()
    for g in games:
        n = 0
        for obs, act in g["decisions"]:
            if max_per_game and n >= max_per_game:
                break
            n += 1
            try:
                pred = agent_fn(obs)
            except Exception:
                pred = None
            kind = choice_kind(obs, act)
            ok = (isinstance(pred, list) and sorted(pred) == sorted(act))
            total += 1
            by_kind[kind][1] += 1
            if ok:
                hit += 1
                by_kind[kind][0] += 1
            else:
                misses[kind] += 1
    return hit, total, by_kind, misses


def make_search_pilot(deck):
    from . import search_agent as SA
    from .state_eval import state_eval
    SA._DECK = list(deck)
    return SA.make_search_agent(eval_fn=state_eval, rollout=True, n_turns=3, rollout_budget=25)


def load_games(dir_, player):
    games = []
    for fn in sorted(glob.glob(os.path.join(dir_, "8*.json"))):
        g = extract_decisions(fn, player)
        if g and g["decisions"]:
            games.append(g)
    return games


def infer_deck(dir_, player):
    """対象プレイヤーの60枚デッキをリプレイから取得。"""
    for fn in sorted(glob.glob(os.path.join(dir_, "8*.json"))):
        d = json.load(open(fn))
        names = (d.get("info") or {}).get("TeamNames") or []
        if player not in names:
            continue
        pi = names.index(player)
        for st in d.get("steps") or []:
            a = st[pi].get("action")
            if a and len(a) == 60:
                return list(a)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/topwin")
    ap.add_argument("--player", default="Huangxiayiluo")
    ap.add_argument("--pilot", default="search", choices=["search", "simple"])
    ap.add_argument("--max-per-game", type=int, default=None)
    a = ap.parse_args()

    _ensure_engine_on_path()
    games = load_games(a.dir, a.player)
    deck = infer_deck(a.dir, a.player)
    n_dec = sum(len(g["decisions"]) for g in games)
    print(f"対象: {a.player} / {len(games)}試合 / 決定点{n_dec} / デッキ{'取得OK' if deck else '不明'}")

    if a.pilot == "search":
        agent = make_search_pilot(deck)
    else:
        from .crustle_bot import make_simple_bot
        agent = make_simple_bot(deck)

    hit, total, by_kind, misses = evaluate_pilot(agent, games, a.max_per_game)
    print(f"\n=== 一致率 [{a.pilot}] {hit}/{total} = {hit/total:.3f} ===")
    print("--- 種類別 (一致/総数) ---")
    for k, (h, t) in sorted(by_kind.items(), key=lambda x: -x[1][1]):
        print(f"  {k:22} {h:4}/{t:<4} = {h/t:.2f}")
    print("--- 不一致が多い種類 ---")
    for k, c in misses.most_common(8):
        print(f"  {k:22} miss {c}")


if __name__ == "__main__":
    main()
