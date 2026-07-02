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

PLAY_PRIO = {1079: 8800, 1086: 8600, 119: 8500, 1121: 8400, 1152: 8300, 1210: 8200,
             1120: 8000, 1198: 7800, 1097: 7600, 1071: 7500, 140: 7400, 184: 7300,
             235: 7200, 1080: 7000, 1256: 6900, 1156: 6500, 1182: 5600, 1227: 7100}
SEARCH_PRIO = [120, 5, 121, 119, 184, 235, 140, 2, 1071, 1079, 1227, 1182, 1086, 1121]

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

        # --- MAIN ---
        if ctx == 0 and mc <= 1:
            best_i, best_s = 0, -1.0
            active = (_g(mp_, "active", []) or [None])
            active = active[0] if active else None
            act_id = _g(active, "id") if active else None
            for i, o in enumerate(opts):
                t = _g(o, "type")
                s = 50.0
                if t == 10:
                    s = 10000  # 特性は常に使う
                elif t == 9:
                    cid = hand_card(mp_, _g(o, "index"))
                    s = 9500 + (200 if cid == DRAKLOAK else (100 if cid == DRAGAPULT else 0))
                elif t == 7:
                    cid = hand_card(mp_, _g(o, "index"))
                    s = PLAY_PRIO.get(cid, 6000)
                    if cid == 1227:  # Lillie's は手札が細い時だけ
                        hc = len(_g(mp_, "hand", []) or [])
                        s = 7100 if hc <= 4 else 3000
                elif t == 8:
                    tgt = inplay(pls, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
                    tid = _g(tgt, "id")
                    ecnt = len(_g(tgt, "energies", []) or []) if tgt else 0
                    if _g(o, "inPlayArea") == 5 and tid in (DRAGAPULT, DRAKLOAK, DREEPY) and ecnt < 2:
                        s = 8100 - ecnt * 10
                    elif _g(o, "inPlayArea") == 4 and tid == DRAGAPULT and ecnt < 2:
                        s = 8050
                    else:
                        s = 4000
                elif t == 13:
                    a = atks.get(_g(o, "attackId"))
                    nm_ = _g(a, "name", "") if a else ""
                    if nm_ == PHANTOM_DIVE_NAME:
                        s = 6000
                    elif nm_ == "Itchy Pollen" and turn <= 6:
                        s = 5800
                    else:
                        s = 5200
                elif t == 12:
                    bench = [p for p in (_g(mp_, "bench", []) or []) if p]
                    ready = any(_g(p, "id") == DRAGAPULT and len(_g(p, "energies", []) or []) >= 2
                                for p in bench)
                    s = 5900 if (ready and act_id in (BUDEW, DREEPY) and turn > 6) else 1000
                elif t == 14:
                    s = 100
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
