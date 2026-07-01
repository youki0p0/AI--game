"""PTCG AI Battle 提出エージェント: Psychic 単サイド チャンピオン（堅牢ヒューリスティック）。

方針: 全アタッカーが **2エネ主体の非ex**（Iron Boulder 170/{P}{C}, Mesprit 160/{P}{P} 等）。
軽く立ち上がり、確実にエネが乗って攻撃できる＝実戦でブリックしない。相手デッキ復元に
一切依存しない純ルールベースなので、相手の構築が何であれ挙動が安定する。

実測（先後入替・N=60〜80）:
  vs Buddy(メガルカリオ) 0.738 / vs Archaludon 0.317 / vs Crustle 0.025
  ＝ Buddy に強い。Archaludon(鋼・炎弱点)は超では弱点を突けず不利だが、少なくとも機能停止しない。

自己完結（cg.api 以外を import しない・相手デッキ非依存）。末尾の def `agent` がエントリ。
observation(dict) → action(list[int])。デッキ選択フェーズ(select is None)は60枚cardIdを返す。
"""
from __future__ import annotations

# --- 60枚デッキ: Psychic 単サイド（18 Pokémon / 30 Trainer / 12 Energy）----------
PSY_DECK = (
    [971] * 4      # Iron Boulder  170/{P}{C}（2エネ・弱点でメガルカリオOHKO）
    + [216] * 4    # Mesprit       160/{P}{P}（2エネ）
    + [112] * 4    # Munkidori     Mind Bend 60/{P}{P}（2エネ・特性ダメカン移動）
    + [751] * 4    # Xerneas
    + [764] * 2    # Cresselia
    + [1192] * 4   # Carmine
    + [1224] * 4   # Cheren
    + [1213] * 4   # Judge
    + [1152] * 4   # Poké Pad
    + [1102] * 4   # Dusk Ball
    + [1086] * 4   # Buddy Poffin
    + [1123] * 4   # Switch
    + [1182] * 2   # Boss's Orders
    + [5] * 12     # Basic Psychic Energy
)
assert len(PSY_DECK) == 60

ENERGY_ID = 5          # 基本超エネルギー
MIN_ATTACK_DMG = 130   # これ未満のチップ攻撃は避け、意味あるKOを取りに行く
IRON_BOULDER = 971
ATTACKER_PRIORITY = [971, 216, 751, 112, 764]

T_YES, T_NO = 1, 2
T_PLAY, T_ATTACH, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END = 7, 8, 10, 11, 12, 13, 14
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
AREA_ACTIVE = 4

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


def _attack_damage(aid) -> int:
    a = _attack_data(aid)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff_vs(aid, atk_type, defender) -> int:
    dmg = _attack_damage(aid)
    if dmg <= 0 or defender is None:
        return dmg
    dd = _card_data(_g(defender, "id"))
    if dd is None:
        return dmg
    weak = _g(dd, "weakness")
    if weak is not None and atk_type is not None and atk_type == weak:
        return dmg * 2
    res = _g(dd, "resistance")
    if res is not None and atk_type is not None and atk_type == res:
        return max(0, dmg - 30)
    return dmg


def _agent_impl(obs_dict: dict, configuration=None) -> list[int]:
    sel = obs_dict.get("select") if isinstance(obs_dict, dict) else _g(obs_dict, "select")
    cur = obs_dict.get("current") if isinstance(obs_dict, dict) else _g(obs_dict, "current")
    if sel is None:
        return list(PSY_DECK)
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
    opp_active = my_active = None
    if len(players) >= 2:
        oa = _g(players[1 - me], "active", []) or []
        opp_active = oa[0] if oa else None
        ma = _g(players[me], "active", []) or []
        my_active = ma[0] if ma else None

    def first_k():
        k = min(max(mc, mn if mn > 0 else 1), n)
        return list(range(k))

    if sctx in (SC_IS_FIRST, SC_MULLIGAN):
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]

    # 技選択: 実効ダメージ最大（弱点×2）
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_d = 0, -1
        for i, o in enumerate(options):
            d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
            if d > best_d:
                best_d, best_i = d, i
        return [best_i]

    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= 5
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ATTACK:
                d = _eff_vs(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                if d >= MIN_ATTACK_DMG:
                    s = 10000 + d + (50000 if (oh > 0 and d >= oh) else 0)
                else:
                    s = 200
            elif t == T_ABILITY:
                s = 9000
            elif t == T_ATTACH:
                s = 8000 + (300 if _g(o, "inPlayArea") == AREA_ACTIVE else 0)
            elif t == T_PLAY:
                card = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    card = _card_data(_g(hand[idx], "id"))
                ct = _g(card, "cardType") if card else None
                boost = 3000 if thin else 0
                if ct == 3:
                    s = 6500 + boost
                elif ct in (1, 2):
                    s = 5500 + boost
                else:
                    s = 5000
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
                pv = 3 if _g(cd, "megaEx") else (2 if _g(cd, "ex") else 1)
                return (1, -pv)
            return (1, -float(_g(cd, "hp", 0) or 0))
        scored = sorted(range(n), key=keyf)
        return [scored[0]] if mc <= 1 else sorted(scored[:max(mc, mn)])

    # 汎用の的/カード選択: 相手アクティブ優先 → 超エネ → Iron Boulder
    energy_choice = iron_choice = opp_active_choice = None
    for i, o in enumerate(options):
        cid = _g(o, "cardId")
        if cid == ENERGY_ID and energy_choice is None:
            energy_choice = i
        if cid == IRON_BOULDER and iron_choice is None:
            iron_choice = i
        if _g(o, "playerIndex") == (1 - me) and _g(o, "area") == AREA_ACTIVE and opp_active_choice is None:
            opp_active_choice = i
        if _g(o, "inPlayArea") == AREA_ACTIVE and _g(o, "playerIndex") == (1 - me) and opp_active_choice is None:
            opp_active_choice = i

    if mc <= 1:
        if opp_active_choice is not None:
            return [opp_active_choice]
        if energy_choice is not None:
            return [energy_choice]
        if iron_choice is not None:
            return [iron_choice]
        return [0]

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
    """例外/想定外でも *必ず合法な非空アクション* を返す最終防衛線。
    実戦ログでは提出物が空アクションを69/136回返して自滅していた。ここで根絶する。"""
    sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
    if sel is None:
        return list(PSY_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    k = min(max(mc, mn if mn > 0 else 1), n)
    return list(range(k))


# Kaggle エントリ: 提出仕様「末尾の def が observation を受け取り action を返す」に厳密適合。
# （agent 内に入れ子 def を持たせず、この関数をファイル末尾の唯一の最終 def にする）
def agent(observation, configuration=None):
    # 全例外を握り、常に合法な非空アクションを返す（空アクションでの自滅を防止）。
    try:
        out = _agent_impl(observation, configuration)
    except Exception:
        return _safe_default(observation)
    # 妥当性検証: select があるのに空/不正なら安全なデフォルトへ差し替え
    try:
        sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
        if sel is None:
            return out if (isinstance(out, list) and len(out) == 60) else list(PSY_DECK)
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
