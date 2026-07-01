"""ドラパルト ex 専用パイロット（晴れる屋2 の回し方ガイドに基づく）。

ガイド要点:
  - 先攻を取る（エネがシビア。後攻より早くエネを付ける）。
  - 序盤: ドラメシヤ(119)×3・ヨマワル(131)×1-2 を並べる。ボール系12枚で展開。
    先2で スボミー(235) の「むずむずかふん」[323]（相手グッズロック）が撃てたら理想。
  - ドロンチ(120) の「ていさつしれい」= 強力ドロー特性。最優先で進化して毎ターン使う
    （山札を薄くし、終盤の手札干渉に強くする）。
  - ドラパルト ex(121) の「ファントムダイブ」[154]=本体200＋ベンチにダメカン6個散布。
    ヨノワール(133)「カースドボム」13個 / サマヨール(132)5個 / マシマシラ(112)移動 /
    キチキギス(140)「さかてにとる」でダメカンを生み・動かしてサイドをまとめ取り。
  - おおむね ファントムダイブ3回＋カースドボム1回 で試合終了。

実装方針（MAIN のスコア順）:
  ABILITY(ドロー/ダメカン) > EVOLVE(ドロンチ/ドラパルト優先) > ATTACH(アタッカーへ)
  > PLAY(展開/サーチ/アメ) > ATTACK(ファントムダイブ) > RETREAT > END
ダメカン散布・狙撃の select は「相手のポケモンで、倒しやすい/価値の高い的」を選ぶ。
"""
from __future__ import annotations

from .state_eval import _card_data, _attack_data, _g

# OptionType ints
T_NUMBER, T_YES, T_NO, T_CARD = 0, 1, 2, 3
T_PLAY, T_ATTACH, T_EVOLVE, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END = 7, 8, 9, 10, 11, 12, 13, 14
ST_MAIN, ST_ATTACK = 0, 6
SC_IS_FIRST, SC_MULLIGAN = 41, 42
SC_PLACEMENT = {1, 2, 3, 4, 5, 6}
AREA_ACTIVE, AREA_BENCH = 4, 5

PHANTOM_DIVE = 154       # 本命の攻撃
DRAGAPULT_EX = 121
DRAKLOAK = 120
DREEPY = 119
ENERGY_IDS = {2, 5, 7}   # 炎/超/悪

# 進化の優先度（先に育てたい順）: ドロンチ(ドロー) > ドラパルト(攻撃) > ヨノワール系
EVOLVE_PRIORITY = {DRAKLOAK: 300, DRAGAPULT_EX: 250, 133: 120, 132: 110}
# 自軍アタッカー配置優先
ATTACKER_PRIORITY = [DRAGAPULT_EX, DRAKLOAK, DREEPY, 131, 112, 140, 1071, 132, 133, 235]


def _dmg(attack_id) -> int:
    a = _attack_data(attack_id)
    return int(_g(a, "damage", 0) or 0) if a is not None else 0


def _eff(attack_id, atk_type, defender) -> int:
    d = _dmg(attack_id)
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


def make_dragapult_pilot(go_first: bool = True):
    def piloted(obs: dict) -> list[int]:
        return _impl(obs, go_first)
    return piloted


def _my_inplay(players, me, area, idx):
    """自軍の active/bench から (area,idx) のポケモンを取り出す。"""
    if area is None or idx is None or len(players) <= me:
        return None
    arr = None
    if area == AREA_ACTIVE:
        arr = _g(players[me], "active", [])
    elif area == AREA_BENCH:
        arr = _g(players[me], "bench", [])
    if isinstance(arr, list) and 0 <= idx < len(arr):
        return arr[idx]
    return None


def _remaining_hp(pk) -> float:
    return float(_g(pk, "hp", 0) or 0)


def _prize_val(cd) -> int:
    if cd is None:
        return 1
    if _g(cd, "megaEx"):
        return 3
    if _g(cd, "ex"):
        return 2
    return 1


def _impl(obs: dict, go_first: bool) -> list[int]:
    from .dragapult_deck import DRAGAPULT_DECK
    sel = obs.get("select")
    cur = obs.get("current")
    if sel is None:
        return list(DRAGAPULT_DECK)
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
    opp_bench = []
    if len(players) >= 2:
        ma = _g(players[me], "active", []) or []
        my_active = ma[0] if ma else None
        oa = _g(players[1 - me], "active", []) or []
        opp_active = oa[0] if oa else None
        opp_bench = [p for p in (_g(players[1 - me], "bench", []) or []) if p is not None]

    def first_k():
        return list(range(min(max(mc, mn if mn > 0 else 1), n)))

    # 先攻/後攻
    if sctx == SC_IS_FIRST:
        want = T_YES if go_first else T_NO
        for i, o in enumerate(options):
            if _g(o, "type") == want:
                return [i]
        return [0]
    if sctx == SC_MULLIGAN:
        for i, o in enumerate(options):
            if _g(o, "type") == T_NO:
                return [i]
        return [0]

    # 攻撃選択: ファントムダイブ最優先、無ければ実効ダメージ最大
    if stype == ST_ATTACK:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        best_i, best_s = 0, -1.0
        for i, o in enumerate(options):
            aid = _g(o, "attackId")
            s = float(_eff(aid, atk_type, opp_active))
            if aid == PHANTOM_DIVE:
                s += 1000  # 本命
            if s > best_s:
                best_s, best_i = s, i
        return [best_i]

    # MAIN: マクロ行動
    if stype == ST_MAIN:
        atk_type = _g(_card_data(_g(my_active, "id")), "energyType") if my_active else None
        hand_ct = int(_g(players[me], "handCount", 0) or 0) if len(players) > me else 0
        thin = hand_ct <= 5
        scores = []
        for o in options:
            t = _g(o, "type")
            s = 0.0
            if t == T_ABILITY:
                s = 9500  # ドロー(ていさつしれい)/ダメカン系は最優先
            elif t == T_EVOLVE:
                pk = None
                cid = None
                # 進化後カード id を取得（inPlay 側）
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    cid = _g(hand[idx], "id")
                s = 8800 + EVOLVE_PRIORITY.get(cid, 0)
            elif t == T_ATTACH:
                # エネはアタッカーへ。ドラパルト ex(121) 最優先、次いでアクティブ、
                # 次いでマシマシラ(112: 悪エネで特性起動)。
                tgt = _my_inplay(players, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
                tid = _g(tgt, "id")
                s = 8000
                if tid == DRAGAPULT_EX:
                    s = 8600
                elif _g(o, "inPlayArea") == AREA_ACTIVE:
                    s = 8300
                elif tid == 112:
                    s = 8100
            elif t == T_PLAY:
                card = None
                cid = None
                idx = _g(o, "index")
                hand = _g(players[me], "hand", []) if len(players) > me else None
                if isinstance(hand, list) and idx is not None and 0 <= idx < len(hand):
                    cid = _g(hand[idx], "id")
                    card = _card_data(cid)
                ct = _g(card, "cardType") if card else None
                boost = 3000 if thin else 0
                if cid == 1198:    # Crispin（アカマツ）= エネ加速エンジン。最優先の supporter
                    s = 7200
                elif ct == 3:        # SUPPORTER
                    s = 6500 + boost
                elif ct in (1, 2):  # ITEM/TOOL（ボール・アメ）
                    s = 5500 + boost
                else:               # たねポケモン展開
                    s = 6000        # 序盤の並べを重視（アグロより高め）
            elif t == T_ATTACK:
                d = _eff(_g(o, "attackId"), atk_type, opp_active)
                oh = float(_g(opp_active, "hp", 0) or 0)
                aid = _g(o, "attackId")
                ko = oh > 0 and d >= oh
                # ファントムダイブ最優先。他の技も、盤面にプレッシャーをかけるため
                # 撃てるなら撃つ（チップ攻撃を止めると盤面を control されて負ける）。
                if aid == PHANTOM_DIVE:
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

    # ダメカン散布・狙撃・汎用カード選択:
    #   相手のポケモンを狙う select では「倒しやすい/価値が高い」的を選ぶ。
    #   自軍対象（エネ選択等）では炎/超/悪エネ、次いで先頭。
    def opp_target_key(i):
        o = options[i]
        # 現HPが低い（倒しやすい）＋サイド価値が高いほど優先
        cid = _g(o, "cardId")
        cd = _card_data(cid)
        # 盤面のポケモン参照が取れる場合の残HP
        hp = None
        # active/bench の実体から取得を試みる
        pl = _g(o, "playerIndex")
        area = _g(o, "area")
        idx = _g(o, "index")
        if pl is not None and area is not None and idx is not None and len(players) > pl:
            arr = None
            if area == AREA_ACTIVE:
                arr = _g(players[pl], "active", [])
            elif area == AREA_BENCH:
                arr = _g(players[pl], "bench", [])
            if isinstance(arr, list) and 0 <= idx < len(arr) and arr[idx] is not None:
                hp = _remaining_hp(arr[idx])
        prize = _prize_val(cd)
        return (-(prize * 1000) + (hp if hp is not None else 999))

    # 相手ポケモンを対象にできる select か？
    opp_opts = [i for i, o in enumerate(options)
                if _g(o, "playerIndex") == (1 - me)
                or _g(o, "inPlayArea") in (AREA_ACTIVE, AREA_BENCH) and _g(o, "playerIndex") == (1 - me)]
    if opp_opts:
        order = sorted(opp_opts, key=opp_target_key)
        # ダメカン散布は複数個置けることがある: 倒しやすい順に詰める
        if mc <= 1:
            return [order[0]]
        picks = order[:mc]
        # minCount 未満なら他の合法手で埋める
        if len(picks) < max(mn, 1):
            for i in range(n):
                if i not in picks:
                    picks.append(i)
                if len(picks) >= max(mn, 1):
                    break
        return sorted(picks[:max(mc, mn)])

    # 自軍対象/エネルギー等
    #   Crispin 等でエネを付ける先/自軍ポケ選択は ドラパルト ex(121) を最優先。
    energy_choice = pult_choice = None
    for i, o in enumerate(options):
        if _g(o, "cardId") in ENERGY_IDS and energy_choice is None:
            energy_choice = i
        # 自軍ポケモンを指す選択肢か
        oid = _g(o, "cardId")
        if oid == DRAGAPULT_EX and pult_choice is None:
            pult_choice = i
        tgt = _my_inplay(players, me, _g(o, "inPlayArea"), _g(o, "inPlayIndex"))
        if _g(tgt, "id") == DRAGAPULT_EX and pult_choice is None:
            pult_choice = i
    if mc <= 1:
        if pult_choice is not None:
            return [pult_choice]
        return [energy_choice if energy_choice is not None else 0]
    chosen = []
    for i, o in enumerate(options):
        if _g(o, "cardId") in ENERGY_IDS:
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
