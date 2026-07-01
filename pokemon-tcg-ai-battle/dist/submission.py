"""PTCG AI Battle 提出エージェント: Marnie's Grimmsnarl ex（悪）— 現環境トップのコピー。

トップ層の決勝級ログ(83010255)で両者が使っていた環境No.1デッキ。
Marnie's Grimmsnarl ex(648): 悪・HP320・Shadow Bullet[937]=**180＋ベンチ30 を たった2エネ**。
Punk Up(進化加速)で立ち上がりが速く、**2エネ攻撃なのでブリックしない**（我々の炎デッキの
最大の欠点＝3エネ待ちで倒される問題を構造的に回避）。実測でも最大8エネまで乗り、
Grimmsnarl 到達 17/20 と機能する。

構成: 進化デッキ(Impidimp646→Morgrem647→Grimmsnarl648, ふしぎなアメ1079で直接進化)。
Munkidori(112)は悪エネ有で Adrena-Brain(ダメカン移動)が使える＝Grimmsnarlのベンチ30/
Froslassの散布と噛み合う。全て単一ファイル・cg.api のみ依存・相手デッキ非依存。

★ 提出安全化: 末尾の唯一の最終 def が agent(observation, ...)。全例外を握り、
  *空アクションで自滅しない*（実戦で空アクション69/136の自滅があったため根絶）。
"""
from __future__ import annotations

# --- トップ10の精製版 Grimmsnarl（Dunsparce/Dudunsparce ドローエンジン採用）-------
# 上位データ比較で コピー版 < 精製版 が全マッチで優位（vs Alakazam 0.63→0.85 等）。
GRIMM_DECK = (
    [646] * 4 + [647] * 3 + [648] * 3 + [112] * 4        # Impidimp/Morgrem/Grimmsnarl ex/Munkidori
    + [305] * 3 + [66] * 2 + [649] * 1                   # Dunsparce/Dudunsparce(ドロー特性)/Marnie's Morpeko
    + [1086] * 4 + [1152] * 4 + [1079] * 3 + [1097] * 2  # Poffin/PokePad/RareCandy/NightStretcher
    + [1119] * 1 + [1139] * 1 + [1159] * 1               # (tech)/(tech)/Hero's Cape
    + [1227] * 4 + [1231] * 4 + [1197] * 2               # Lillie/Dawn/(supporter)
    + [1259] * 4                                         # Spikemuth Gym
    + [7] * 10                                           # Basic Dark Energy
)
assert len(GRIMM_DECK) == 60

ENERGY_ID = 7          # 基本悪エネルギー
SHADOW_BULLET = 937    # Grimmsnarl の本命技(180+ベンチ30, 2エネ)
GRIMMSNARL, MORGREM, IMPIDIMP = 648, 647, 646
RARE_CANDY = 1079
MUNKIDORI = 112
# 進化の優先: Grimmsnarl(攻撃) > Morgrem > Froslass
EVOLVE_PRIORITY = {GRIMMSNARL: 300, MORGREM: 200, 104: 120}
ATTACKER_PRIORITY = [GRIMMSNARL, MORGREM, MUNKIDORI, 104, IMPIDIMP, 860]

T_YES, T_NO = 1, 2
T_PLAY, T_ATTACH, T_EVOLVE, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END = 7, 8, 9, 10, 11, 12, 13, 14
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
SC_TO_HAND = 7
AREA_ACTIVE, AREA_BENCH = 4, 5

# デッキ→手札サーチで優先するカード
SEARCH_PRIORITY = [1227, 648, 647, 646, 1079, 1182, 112, 104, 860, 1086, 1152, 7]

_CARD_TABLE = None
_ATTACK_TABLE = None


def _ensure_tables():
    global _CARD_TABLE, _ATTACK_TABLE
    if _CARD_TABLE is not None:
        return
    try:
        from cg.api import all_card_data, all_attack  # type: ignore
        _CARD_TABLE = {c.cardId: c for c in all_card_data()}
        _ATTACK_TABLE = {a.attackId: a for a in all_attack()}
    except Exception:
        _CARD_TABLE, _ATTACK_TABLE = {}, {}


def _card_data(cid):
    _ensure_tables()
    return None if cid is None else _CARD_TABLE.get(cid)


def _attack_data(aid):
    _ensure_tables()
    return None if aid is None else _ATTACK_TABLE.get(aid)


def _g(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _dmg(aid) -> int:
    a = _attack_data(aid)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff(aid, atk_type, defender) -> int:
    d = _dmg(aid)
    if d <= 0 or defender is None:
        return d
    dd = _card_data(_g(defender, "id"))
    if dd is None:
        return d
    if _g(dd, "weakness") is not None and atk_type is not None and _g(dd, "weakness") == atk_type:
        return d * 2
    if _g(dd, "resistance") is not None and atk_type is not None and _g(dd, "resistance") == atk_type:
        return max(0, d - 30)
    return d


def _my_inplay(players, me, area, idx):
    if area is None or idx is None or len(players) <= me:
        return None
    arr = _g(players[me], "active", []) if area == AREA_ACTIVE else (
        _g(players[me], "bench", []) if area == AREA_BENCH else None)
    if isinstance(arr, list) and 0 <= idx < len(arr):
        return arr[idx]
    return None


def _prize_val(cd) -> int:
    if cd is None:
        return 1
    return 3 if _g(cd, "megaEx") else (2 if _g(cd, "ex") else 1)


def _impl(obs):
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    if sel is None:
        return list(GRIMM_DECK)
    options = _g(sel, "option", []) or []
    n = len(options)
    if n == 0:
        return []
    stype = _g(sel, "type")
    sctx = _g(sel, "context")
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    me = _g(cur, "yourIndex", 0) if cur is not None else 0
    players = (_g(cur, "players", []) or []) if cur is not None else []
    my_active = opp_active = None
    if len(players) >= 2:
        ma = _g(players[me], "active", []) or []
        my_active = ma[0] if ma else None
        oa = _g(players[1 - me], "active", []) or []
        opp_active = oa[0] if oa else None

    def first_k():
        return list(range(min(max(mc, mn if mn > 0 else 1), n)))

    # 先攻/後攻: テンポ重視で先攻
    if sctx == SC_IS_FIRST:
        for i, o in enumerate(options):
            if _g(o, "type") == T_YES:
                return [i]
        return [0]
    if sctx == SC_MULLIGAN:
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]

    # 攻撃選択: Shadow Bullet 最優先、無ければ実効ダメージ最大
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_s = 0, -1.0
        for i, o in enumerate(options):
            aid = _g(o, "attackId")
            s = float(_eff(aid, atk_type, opp_active)) + (1000 if aid == SHADOW_BULLET else 0)
            if s > best_s:
                best_s, best_i = s, i
        return [best_i]

    # MAIN: 特性>進化>エネ付け(Grimmsnarlへ)>展開>攻撃>後退>終了
    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= 5
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ABILITY:
                s = 9500
            elif t == T_EVOLVE:
                cid = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    cid = _g(hand[idx], "id")
                s = 8800 + EVOLVE_PRIORITY.get(cid, 0)
            elif t == T_ATTACH:
                tgt = _my_inplay(players, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
                tid = _g(tgt, "id")
                s = 8000
                if tid == GRIMMSNARL:
                    s = 8600
                elif _g(o, "inPlayArea") == AREA_ACTIVE:
                    s = 8300
                elif tid == MUNKIDORI:
                    s = 8100
            elif t == T_PLAY:
                cid = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    cid = _g(hand[idx], "id")
                card = _card_data(cid)
                cty = _g(card, "cardType") if card else None
                boost = 3000 if thin else 0
                if cid == RARE_CANDY:
                    s = 7000
                elif cty == 3:
                    s = 6500 + boost
                elif cty in (1, 2, 4):
                    s = 5500 + boost
                else:
                    s = 6000
            elif t == T_ATTACK:
                d = _eff(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                ko = oh > 0 and d >= oh
                if _g(o, "attackId") == SHADOW_BULLET:
                    s = 10500 + d + (50000 if ko else 0)
                elif d >= 60 or ko:
                    s = 9000 + d + (50000 if ko else 0)
                else:
                    s = 300
            elif t == T_RETREAT:
                s = 1500
            elif t == T_DISCARD:
                s = 800
            elif t == T_END:
                s = 100
            else:
                s = 50
            scores.append(s)
        return [max(range(n), key=lambda i: scores[i])]

    # 配置: 自軍はアタッカー優先／相手指定(gust)はサイド大の的
    if sctx in SC_PLACEMENT:
        targets_opp = any(_g(o, "playerIndex") == (1 - me) for o in options)
        rank = {cid: i for i, cid in enumerate(ATTACKER_PRIORITY)}

        def keyf(i):
            cid = _g(options[i], "cardId")
            if not targets_opp and cid in rank:
                return (0, rank[cid])
            cd = _card_data(cid)
            if targets_opp:
                return (1, -_prize_val(cd))
            return (1, -float(_g(cd, "hp", 0) or 0))
        scored = sorted(range(n), key=keyf)
        return [scored[0]] if mc <= 1 else sorted(scored[:max(mc, mn)])

    # デッキ→手札サーチ
    if sctx == SC_TO_HAND:
        rank = {cid: i for i, cid in enumerate(SEARCH_PRIORITY)}
        order = sorted(range(n), key=lambda i: rank.get(_g(options[i], "cardId"), 999))
        return [order[0]] if mc <= 1 else sorted(order[:max(mc, mn)])

    # ダメカン散布/狙撃(Grimmsnarlベンチ30/Munkidori移動): 相手ポケモン優先
    opp_opts = [i for i, o in enumerate(options) if _g(o, "playerIndex") == (1 - me)]
    if opp_opts:
        def okey(i):
            o = options[i]
            pl = _g(o, "playerIndex"); area = _g(o, "area"); idx = _g(o, "index")
            hp = None
            arr = None
            if pl is not None and area is not None and len(players) > pl:
                arr = _g(players[pl], "active", []) if area == AREA_ACTIVE else (
                    _g(players[pl], "bench", []) if area == AREA_BENCH else None)
            if isinstance(arr, list) and idx is not None and 0 <= idx < len(arr) and arr[idx] is not None:
                hp = float(_g(arr[idx], "hp", 0) or 0)
            cd = _card_data(_g(o, "cardId"))
            return (-(_prize_val(cd) * 1000) + (hp if hp is not None else 999))
        order = sorted(opp_opts, key=okey)
        if mc <= 1:
            for i in opp_opts:
                if _g(options[i], "area") == AREA_ACTIVE or _g(options[i], "inPlayArea") == AREA_ACTIVE:
                    return [i]
            return [order[0]]
        picks = order[:mc]
        if len(picks) < max(mn, 1):
            for i in range(n):
                if i not in picks:
                    picks.append(i)
                if len(picks) >= max(mn, 1):
                    break
        return sorted(picks[:max(mc, mn)])

    # 自軍対象/エネルギー: Grimmsnarl 優先 → 悪エネ → 先頭
    energy_choice = grimm_choice = None
    for i, o in enumerate(options):
        if _g(o, "cardId") == ENERGY_ID and energy_choice is None:
            energy_choice = i
        if _g(o, "cardId") == GRIMMSNARL and grimm_choice is None:
            grimm_choice = i
        tgt = _my_inplay(players, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
        if _g(tgt, "id") == GRIMMSNARL and grimm_choice is None:
            grimm_choice = i
    if mc <= 1:
        if grimm_choice is not None:
            return [grimm_choice]
        return [energy_choice if energy_choice is not None else 0]
    chosen = []
    for i, o in enumerate(options):
        if _g(o, "cardId") == ENERGY_ID:
            chosen.append(i)
        if len(chosen) >= mc:
            break
    if len(chosen) < (mn or mc):
        for i in range(n):
            if i not in chosen:
                chosen.append(i)
            if len(chosen) >= max(mn, mc):
                break
    return sorted(chosen[:max(mc, mn)]) if chosen else first_k()


def _safe_default(observation):
    sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
    if sel is None:
        return list(GRIMM_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


# Kaggle エントリ: 末尾の唯一の最終 def。全例外を握り *空アクション自滅を根絶*。
def agent(observation, configuration=None):
    try:
        out = _impl(observation)
    except Exception:
        return _safe_default(observation)
    try:
        sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
        if sel is None:
            return out if (isinstance(out, list) and len(out) == 60) else list(GRIMM_DECK)
        opts = _g(sel, "option", []) or []
        n = len(opts)
        if n == 0:
            return []
        mc = int(_g(sel, "maxCount", 1) or 1)
        mn = int(_g(sel, "minCount", 0) or 0)
        ok = (isinstance(out, list) and len(out) >= max(1, mn) and len(out) <= mc
              and len(set(out)) == len(out)
              and all(isinstance(i, int) and 0 <= i < n for i in out))
        return out if ok else _safe_default(observation)
    except Exception:
        return _safe_default(observation)
