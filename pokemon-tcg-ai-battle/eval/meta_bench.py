"""デッキ最適化の適応度関数: 候補デッキを「実メタ勢」と対戦させ総合勝率を返す。

Fable 等の探索エージェントが「デッキ→強さ」を1コマンドで測れるようにするためのCLI/関数。
候補デッキは grimmsnarl 専用パイロット（既定）または simple_bot で操縦。相手は上位データ由来の
メタ勢（Grimmsnarl / MegaStarmie / Archaludon / Alakazam / Buddy / Dragapult）。

使い方(CLI):
  python -m eval.meta_bench --deck "646*4,647*3,648*3,112*4,305*3,66*2,649*1,1086*4,1152*4,1079*3,1097*2,1119*1,1139*1,1159*1,1227*4,1231*4,1197*2,1259*4,7*10" --games 40
  # -> 総合勝率と各マッチを表示。--pilot simple で汎用パイロット。
"""
from __future__ import annotations

import importlib.util
import math
import multiprocessing as mp
import os
import pickle

from .engine_driver import _ensure_engine_on_path, _get_engine_dir

_HERE = os.path.dirname(__file__)
_SUB = os.path.join(_HERE, "..", "submissions")

# --- メタ勢デッキ（上位10データ由来）-----------------------------------------
FIELD_DECKS = {
    "MegaStarmie": [3]*9+[17]*4+[666]*4+[1030]*3+[1031]*3+[1086]*4+[1097]*2+[1120]*4+[1121]*1+[1122]*4+[1145]*4+[1159]*1+[1182]*1+[1189]*4+[1223]*2+[1225]*2+[1227]*4+[1229]*4,
    "Archaludon": [169]*4+[190]*4+[666]*4+[1244]*4+[8]*13+[1152]*4+[1121]*4+[1122]*4+[1097]*4+[1197]*3+[1147]*2+[1159]*1+[1182]*1+[1185]*4+[1227]*4,
    "Alakazam": [5]*3+[13]*1+[19]*4+[66]*3+[305]*4+[741]*4+[742]*4+[743]*4+[1079]*4+[1081]*4+[1086]*4+[1097]*3+[1129]*1+[1152]*4+[1182]*3+[1184]*1+[1225]*4+[1231]*4+[1264]*1,
    "Dragapult": [2]*4+[5]*4+[7]*2+[112]*1+[119]*4+[120]*4+[121]*3+[140]*1+[184]*1+[235]*2+[1071]*1+[1080]*1+[1086]*4+[1097]*2+[1120]*4+[1121]*4+[1152]*4+[1182]*3+[1198]*3+[1213]*1+[1227]*4+[1231]*1+[1246]*2,
    "GrimmMirror": [646]*4+[647]*3+[648]*3+[112]*4+[305]*3+[66]*2+[649]*1+[1086]*4+[1152]*4+[1079]*3+[1097]*2+[1119]*1+[1139]*1+[1159]*1+[1227]*4+[1231]*4+[1197]*2+[1259]*4+[7]*10,
    "Buddy": None,  # deck.pkl（下でロード）
}


def _load_module(path):
    spec = importlib.util.spec_from_file_location("m", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _make_candidate_pilot(deck, pilot):
    """候補デッキ用のエージェント（deck-select で必ずこの deck を返す）。"""
    _ensure_engine_on_path()
    if pilot == "grimmsnarl":
        m = _load_module(os.path.join(_SUB, "grimmsnarl_agent.py"))
        m.GRIMM_DECK = list(deck)  # deck-select をこの候補に差し替え
        return m.agent
    from .crustle_bot import make_simple_bot
    return make_simple_bot(deck)


def _make_field_agent(name, deck):
    _ensure_engine_on_path()
    if name == "Buddy":
        from .agents_buddy import load_buddy_agent
        return load_buddy_agent()
    if name == "GrimmMirror":
        m = _load_module(os.path.join(_SUB, "grimmsnarl_agent.py"))
        return m.agent
    from .crustle_bot import make_simple_bot
    return make_simple_bot(deck)


def _field():
    d = dict(FIELD_DECKS)
    d["Buddy"] = list(pickle.load(open(_get_engine_dir() / "deck.pkl", "rb")))
    return d


def _worker(args):
    cand_deck, pilot, oppname, oppdeck, N = args
    from .engine_driver import play_game
    w = 0
    for gi in range(N):
        ca = _make_candidate_pilot(cand_deck, pilot)
        oa = _make_field_agent(oppname, oppdeck)
        if gi % 2 == 0:
            r = play_game(ca, oa, deck0=cand_deck, deck1=oppdeck); me = 0
        else:
            r = play_game(oa, ca, deck0=oppdeck, deck1=cand_deck); me = 1
        if r == me:
            w += 1
    return (oppname, N, w)


def eval_deck(deck, pilot="grimmsnarl", games=40, workers=None):
    assert len(deck) == 60, f"deck must be 60 cards, got {len(deck)}"
    field = _field()
    tasks = [(list(deck), pilot, n, dk, games) for n, dk in field.items()]
    workers = workers or min(len(tasks), max(1, (mp.cpu_count() or 2)))
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=workers) as pool:
        res = pool.map(_worker, tasks)
    per = {n: w / N for n, N, w in res}
    tot_w = sum(w for _, _, w in res)
    tot_n = sum(N for _, N, _ in res)
    return {"overall": tot_w / tot_n, "n": tot_n, "per_matchup": per}


def _parse(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        cid, mult = part.split("*")
        out += [int(cid)] * int(mult)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help='"cid*n,cid*n,..." (計60枚)')
    ap.add_argument("--pilot", default="grimmsnarl", choices=["grimmsnarl", "simple"])
    ap.add_argument("--games", type=int, default=40)
    a = ap.parse_args()
    deck = _parse(a.deck)
    r = eval_deck(deck, pilot=a.pilot, games=a.games)
    wr = r["overall"]
    se = math.sqrt(wr * (1 - wr) / r["n"])
    print(f"OVERALL {wr:.4f}  95%CI[{wr-1.96*se:.3f},{wr+1.96*se:.3f}]  (n={r['n']})")
    for k, v in sorted(r["per_matchup"].items(), key=lambda x: -x[1]):
        print(f"   vs {k:12} {v:.3f}")
