"""Dragapult 専用パイロット v2（トップエージェント Huangxiayiluo のリプレイ14試合=1308決定点から抽出）。

既存の eval/dragapult_pilot.py（晴れる屋ガイド由来・ヨノワール型）とは別物。こちらは
実ラダー#1級エージェントの行動分布を模倣ターゲットにする（検証: eval/imitation.py）。

抽出した型:
  - 必ず後攻を選ぶ（6/6）
  - 特性は常に使う（Recon Directive 等、全て無償バリュー）
  - 進化最優先（Drakloak 39回 > Dragapult 18回、ふしぎなアメ併用）
  - エネはベンチの Dragapult ライン優先（前で Budew がロック中に後ろを育てる）
  - 攻撃は Phantom Dive 主体（47回）、序盤は Budew の Itchy Pollen（アイテムロック12回）
  - Phantom Dive の散布（ctx14）=「相手の進化前(Duraludon等)・エンジンの狙撃」+「KO圏の刈り取り」
  - サーチ優先: Drakloak > 超エネ > Dragapult ex > Dreepy > Latias > Budew > Fezandipiti
未対応コンテキストは汎用探索（search_agent）へフォールバック。
"""
from __future__ import annotations

from .engine_driver import _ensure_engine_on_path

DRAG_DECK = ([2]*4+[5]*4+[119]*4+[120]*4+[121]*3+[140]*1+[184]*1+[235]*2+[1071]*1
             +[1079]*2+[1080]*1+[1086]*4+[1097]*2+[1120]*4+[1121]*4+[1152]*3+[1156]*1
             +[1182]*3+[1198]*4+[1210]*2+[1227]*4+[1256]*2)
assert len(DRAG_DECK) == 60

DRAGAPULT, DRAKLOAK, DREEPY, BUDEW = 121, 120, 119, 235
PHANTOM_DIVE_NAME = "Phantom Dive"

# v3: 混同行列から抽出した手順 — コイン/情報系(Hammer/Pad)を最初、進化→特性、Lillie's重用
PLAY_PRIO = {1120: 9800, 1152: 9700, 1079: 9550, 1256: 9450,
             1121: 8450, 119: 8380, 1086: 8360, 1198: 8340, 1210: 8320, 1097: 8300,
             1071: 8280, 140: 8260, 184: 8240, 235: 8220, 1080: 8200, 1156: 6500,
             1182: 5600, 1227: 2500}
SEARCH_PRIO = [120, 5, 121, 119, 184, 235, 140, 2, 1071, 1079, 1227, 1182, 1086, 1121]

# リプレイ631決定からBradley-Terry風にフィットした大域ランキング(MAIN用)
FITTED_MAIN = {"PLAY:1079": 5.82, "PLAY:119": 4.19, "ATTACH:A:1071": 3.55, "ABILITY": 3.24, "PLAY:1120": 3.17, "EVOLVE:121": 2.56, "PLAY:140": 2.28, "EVOLVE:120": 1.74, "ATTACK:Phantom Dive": 1.39, "PLAY:235": 1.33, "PLAY:1256": 1.27, "PLAY:184": 1.18, "PLAY:1152": 1.05, "PLAY:1086": 0.91, "PLAY:1227": 0.87, "ATTACH:B:121": 0.82, "ATTACH:A:121": 0.76, "PLAY:1080": 0.74, "ATTACH:A:140": 0.73, "ATTACH:B:119": 0.70, "PLAY:1198": 0.60, "PLAY:1182": 0.45, "PLAY:1210": 0.38, "PLAY:1121": 0.37, "ATTACH:A:235": 0.31, "ATTACH:B:120": -0.12, "PLAY:1071": -0.15, "PLAY:1097": -0.23, "ATTACH:A:119": -0.36, "ATTACH:A:120": -0.48, "ATTACH:A:184": -0.54, "ATTACK:Itchy Pollen": -0.86, "ATTACK:Jet Headbutt": -0.87, "ATTACK:Bite": -1.09, "RETREAT": -1.45, "ATTACK:Petty Grudge": -2.05, "END": -2.23, "ATTACK:Dragon Headbutt": -4.12, "ATTACH:B:1071": -6.13, "ATTACH:B:184": -6.47, "ATTACH:B:235": -6.49, "ATTACH:B:140": -6.80}

_CARDS = None
_ATKS = None
_EVO_SET = None


def _tables():
    global _CARDS, _ATKS
    if _CARDS is None:
        _ensure_engine_on_path()
        import cg.api as api
        _CARDS = {c.cardId: c for c in api.all_card_data()}
        _ATKS = {a.attackId: a for a in api.all_attack()}
    return _CARDS, _ATKS


def _g(d, k, de=None):
    if d is None:
        return de
    return d.get(k, de) if isinstance(d, dict) else getattr(d, k, de)


def _evo_from_set(cards):
    global _EVO_SET
    if _EVO_SET is None:
        _EVO_SET = {(_g(c, "evolvesFrom") or "") for c in cards.values()} - {""}
    return _EVO_SET


def _is_evolving_basic(cards, cid):
    c = cards.get(cid)
    if c is None or not _g(c, "basic"):
        return False
    return _g(c, "name", "") in _evo_from_set(cards)


def make_top_dragapult_pilot():
    cards, atks = _tables()
    from . import search_agent as SA
    from .state_eval import state_eval
    SA._DECK = list(DRAG_DECK)
    fallback = SA.make_search_agent(eval_fn=state_eval, rollout=True, n_turns=3, rollout_budget=25)

    def hand_card(mp_, idx):
        hand = _g(mp_, "hand", []) or []
        if idx is not None and 0 <= idx < len(hand):
            return _g(hand[idx], "id")
        return None

    def inplay(pls, pl, area, idx):
        if pl is None or len(pls) <= pl:
            return None
        arr = _g(pls[pl], "active") if area == 4 else (_g(pls[pl], "bench") if area == 5 else None)
        if isinstance(arr, list) and idx is not None and 0 <= idx < len(arr):
            return arr[idx]
        return None

    def agent(obs):
        sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
        if sel is None:
            return list(DRAG_DECK)
        opts = _g(sel, "option", []) or []
        n = len(opts)
        if n == 0:
            return []
        ctx = _g(sel, "context")
        mc = int(_g(sel, "maxCount", 1) or 1)
        mn = int(_g(sel, "minCount", 0) or 0)
        cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
        me = _g(cur, "yourIndex", 0) if cur else 0
        pls = (_g(cur, "players", []) or []) if cur else []
        mp_ = pls[me] if len(pls) > me else {}
        turn = _g(cur, "turn", 0) or 0

        # --- 先攻選択: 必ず後攻 ---
        if ctx == 41:
            for i, o in enumerate(opts):
                if _g(o, "type") == 2:
                    return [i]
            return [0]

        # --- MAIN: フィット済み大域ランキングで選択 ---
        if ctx == 0 and mc <= 1:
            def main_label(o):
                t = _g(o, "type")
                if t == 7:
                    return f"PLAY:{hand_card(mp_, _g(o, 'index'))}"
                if t == 9:
                    return f"EVOLVE:{hand_card(mp_, _g(o, 'index'))}"
                if t == 8:
                    tgt = inplay(pls, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
                    ab = "A" if _g(o, "inPlayArea") == 4 else "B"
                    return f"ATTACH:{ab}:{_g(tgt, 'id')}"
                if t == 13:
                    a = atks.get(_g(o, "attackId"))
                    return f"ATTACK:{_g(a, 'name', '?') if a else '?'}"
                return {10: "ABILITY", 12: "RETREAT", 14: "END", 11: "DISCARD"}.get(t, f"t{t}")
            best_i, best_s = 0, -1e18
            for i, o in enumerate(opts):
                s = FITTED_MAIN.get(main_label(o), -3.0)
                if s > best_s:
                    best_s, best_i = s, i
            return [best_i]

        # --- ctx14: Phantom Dive 散布 ---
        if ctx == 14:
            rem = int(_g(sel, "remainDamageCounter", 0) or 0)
            def score(i):
                o = opts[i]
                pl = _g(o, "playerIndex")
                pk = inplay(pls, pl, _g(o, "area"), _g(o, "index"))
                if pk is None:
                    return -1e18
                if pl is None or pl == me:
                    return -1e9  # 自分側に置かない
                hp = float(_g(pk, "hp", 0) or 0)
                cid = _g(pk, "id")
                cd = cards.get(cid)
                if rem > 0 and hp <= rem * 10:
                    return 100000 + (2000 if (_g(cd, "ex") or _g(cd, "megaEx")) else 0) - hp
                if _is_evolving_basic(cards, cid):
                    return 5000 - hp  # 進化前の狙撃（Duraludon 等）
                return 1000 - hp * 0.5
            order = sorted(range(n), key=score, reverse=True)
            if mc <= 1:
                return [order[0]]
            k = max(mn, min(mc, n))
            return sorted(order[:k])

        # --- ctx7/8: 山サーチ ---
        if ctx in (7, 8):
            deck = _g(sel, "deck")
            def cid_of(o):
                c = _g(o, "cardId")
                if c is None and deck is not None:
                    idx = _g(o, "index")
                    if idx is not None and 0 <= idx < len(deck):
                        c = _g(deck[idx], "id")
                return c
            rank = {cid: r for r, cid in enumerate(SEARCH_PRIO)}
            order = sorted(range(n), key=lambda i: rank.get(cid_of(opts[i]), 999))
            if mc <= 1:
                return [order[0]]
            k = max(mn, min(mc, n))
            return sorted(order[:k])

        # --- その他は汎用探索へ ---
        return fallback(obs)

    return agent
