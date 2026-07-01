"""PTCG AI Battle 提出エージェント: Archaludon ex（鋼 / ブリジュラス）＋ 探索パイロット。

デッキは実ラダー最頻の Archaludon ex（archaludon_agent.py と同一）。操縦を「固定スコアの
simple_bot」から **3手読み探索** に置き換えたもの。各決定で *全ての合法オプション* を
エンジンの探索サンドボックス(search_begin/search_step)へ適用し、結果盤面を静的評価
(state_eval: サイド差>>マテリアル>脅威>資源、将棋流)で採点して最善手を選ぶ。

探索深さ N_TURNS=3（自分→相手→自分）。深さ 1〜4 の実測で「奇数=強い/偶数=弱い」
(1:0.56/2:0.44/3:0.75/4:0.42)。奇数深さは *自分のターン終了時*(実盤面)で評価するのに対し
偶数深さは *相手ターン終了時*(自デッキから再構成した空想相手)で評価するため誤差が乗る。
深さ3=「相手の反撃(KO)を1回読んでから自分の立て直しを評価」が費用対効果の最良点。

実測(同一相手=simple_bot操縦の実メタ, 先後入替):
  深さ比較(N=60/相手,計180戦): 深さ3 OVERALL 0.739[0.675,0.803] > 深さ1 0.633[0.563,0.704]（+0.11）。
  全マッチ改善: vs Grimmsnarl 0.57→0.80 / vs Alakazam 0.65→0.72 / vs MegaStarmie 0.68→0.70。
  提出ファイル直接検証(深さ3,計90戦)でも OVERALL 0.711・例外0。合計270戦でブリック/例外なし。

隠れ情報は自デッキ(ARCH_DECK)から再構成。相手デッキ未知でも 奇数深さ(自ターンで評価)は
自盤面の評価が主なので頑健。全て単一ファイル・cg.api のみ依存・相手デッキ非依存。

★ 提出安全化: 末尾の唯一の最終 def が agent(observation, ...)。探索が失敗しても全例外を握り、
  *空アクションで自滅しない*（実戦で空アクション自滅があったため根絶）。探索不能時は simple_bot 相当の
  安全手にフォールバック。
"""
from __future__ import annotations

import dataclasses
import enum
from collections import Counter
from typing import Any

# --- Archaludon ex デッキ（archaludon_agent.py と同一）-----------------------------
ARCH_DECK = (
    [169] * 4 + [190] * 4 + [666] * 4 + [1244] * 4 + [8] * 13
    + [1152] * 4 + [1121] * 4 + [1122] * 4 + [1097] * 4 + [1197] * 3
    + [1147] * 2 + [1159] * 1 + [1182] * 1 + [1185] * 4 + [1227] * 4
)
assert len(ARCH_DECK) == 60, len(ARCH_DECK)

# 探索パラメータ
N_TURNS = 3            # 3手読み(自分→相手→自分)。奇数深さ=自ターンで評価=空想相手誤差に頑健。
ROLLOUT_BUDGET = 25    # 1ターン内で貪欲に進める最大ステップ数

# ---------------------------------------------------------------------------
# カード/技テーブル（cg.api から一度だけロード、失敗しても動く）
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 静的評価 state_eval（将棋流: サイド差 >> マテリアル > 脅威 > 資源）
# ---------------------------------------------------------------------------
W_PRIZE_DIFF = 1000.0
W_PRIZE_VALUE = 300.0
W_HP_RATIO = 120.0
W_ENERGY_READY = 90.0
W_ENERGY_EXTRA = 15.0
W_STAGE2 = 60.0
W_STAGE1 = 30.0
W_TOOL = 25.0
W_CAN_KO = 250.0
W_WILL_BE_KOED = 200.0
W_DAMAGE_RATIO = 80.0
W_SC = {"poisoned": 40.0, "burned": 30.0, "asleep": 70.0, "paralyzed": 70.0, "confused": 35.0}
W_HAND = 8.0
W_DECK = 1.5
W_BENCH = 25.0
W_TOTAL_ENERGY = 6.0
TERMINAL = 100000.0


def _iter_pokemon(player):
    if player is None:
        return
    for p in (_g(player, "active", []) or []):
        if p is not None:
            yield p
    for p in (_g(player, "bench", []) or []):
        if p is not None:
            yield p


def _active(player):
    arr = _g(player, "active", []) or []
    return arr[0] if len(arr) > 0 else None


def _prize_value(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return 1
    if _g(d, "megaEx"):
        return 3
    if _g(d, "ex"):
        return 2
    return 1


def _energy_requirement(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return None
    costs = []
    for aid in (_g(d, "attacks", []) or []):
        a = _attack_data(aid)
        if a is None:
            continue
        costs.append(len(_g(a, "energies", []) or []))
    return min(costs) if costs else None


def _best_attack_damage(pk):
    d = _card_data(_g(pk, "id"))
    if d is None:
        return 0
    have = len(_g(pk, "energies", []) or [])
    best = 0
    for aid in (_g(d, "attacks", []) or []):
        a = _attack_data(aid)
        if a is None:
            continue
        if have >= len(_g(a, "energies", []) or []):
            best = max(best, int(_g(a, "damage", 0) or 0))
    return best


def _pokemon_value(pk):
    if pk is None:
        return 0.0
    s = W_PRIZE_VALUE * _prize_value(pk)
    hp = float(_g(pk, "hp", 0) or 0)
    mhp = float(_g(pk, "maxHp", 0) or 0)
    if mhp > 0:
        s += W_HP_RATIO * max(0.0, min(1.0, hp / mhp))
    have = len(_g(pk, "energies", []) or [])
    req = _energy_requirement(pk)
    if req is None:
        s += W_ENERGY_EXTRA * have
    else:
        s += W_ENERGY_READY * min(have, req) + W_ENERGY_EXTRA * max(0, have - req)
    d = _card_data(_g(pk, "id"))
    if d is not None:
        if _g(d, "stage2"):
            s += W_STAGE2
        elif _g(d, "stage1"):
            s += W_STAGE1
    s += W_TOOL * len(_g(pk, "tools", []) or [])
    return s


def _effective_damage(attacker, defender):
    dmg = float(_best_attack_damage(attacker))
    if dmg <= 0:
        return dmg
    ad = _card_data(_g(attacker, "id"))
    dd = _card_data(_g(defender, "id"))
    if ad is None or dd is None:
        return dmg
    at = _g(ad, "energyType")
    weak = _g(dd, "weakness")
    resist = _g(dd, "resistance")
    if weak is not None and at is not None and at == weak:
        return dmg * 2.0
    if resist is not None and at is not None and at == resist:
        return max(0.0, dmg - 30.0)
    return dmg


def _sc_score(player):
    s = 0.0
    for k, v in W_SC.items():
        if _g(player, k):
            s += v
    return s


def state_eval(current, me):
    if current is None:
        return 0.0
    res = _g(current, "result", -1)
    if res is not None and res != -1:
        if res == 2:
            return 0.0
        return TERMINAL if res == me else -TERMINAL
    players = _g(current, "players", []) or []
    if len(players) < 2 or me not in (0, 1):
        return 0.0
    mp, op = players[me], players[1 - me]

    score = 0.0
    # サイド差（支配項）
    score += W_PRIZE_DIFF * (len(_g(op, "prize", []) or []) - len(_g(mp, "prize", []) or []))
    # マテリアル差
    score += sum(_pokemon_value(p) for p in _iter_pokemon(mp)) \
        - sum(_pokemon_value(p) for p in _iter_pokemon(op))
    # 脅威/テンポ
    ma, oa = _active(mp), _active(op)
    if ma is not None and oa is not None:
        dmg = _effective_damage(ma, oa)
        ohp = float(_g(oa, "hp", 0) or 0)
        if ohp > 0:
            if dmg >= ohp:
                score += W_CAN_KO + W_DAMAGE_RATIO
            else:
                score += W_DAMAGE_RATIO * (dmg / ohp)
        dmg2 = _effective_damage(oa, ma)
        mhp = float(_g(ma, "hp", 0) or 0)
        if mhp > 0:
            if dmg2 >= mhp:
                score -= W_WILL_BE_KOED + W_DAMAGE_RATIO
            else:
                score -= W_DAMAGE_RATIO * (dmg2 / mhp)
    score -= _sc_score(mp)
    score += _sc_score(op)
    # 資源差
    score += W_HAND * (float(_g(mp, "handCount", 0) or 0) - float(_g(op, "handCount", 0) or 0))
    score += W_DECK * (float(_g(mp, "deckCount", 0) or 0) - float(_g(op, "deckCount", 0) or 0))
    score += W_BENCH * (len(_g(mp, "bench", []) or []) - len(_g(op, "bench", []) or []))
    me_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(mp))
    op_e = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(op))
    score += W_TOTAL_ENERGY * (me_e - op_e)
    return score


# ---------------------------------------------------------------------------
# 隠れ情報の再構成（自デッキ=ARCH_DECK から）
# ---------------------------------------------------------------------------
def _cards_in_play(pk):
    ids = [pk["id"]] if isinstance(pk, dict) else [_g(pk, "id")]
    for k in ("energyCards", "tools", "preEvolution"):
        for c in (_g(pk, k) or []):
            ids.append(_g(c, "id"))
    return [i for i in ids if i is not None]


def _visible_used(player):
    used = Counter()
    for c in (_g(player, "hand") or []):
        used[_g(c, "id")] += 1
    for area in ("active", "bench"):
        for pk in (_g(player, area) or []):
            if pk:
                for i in _cards_in_play(pk):
                    used[i] += 1
    for c in (_g(player, "discard") or []):
        used[_g(c, "id")] += 1
    return used


def _reconstruct(obs):
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    if cur is None:
        return None
    me = _g(cur, "yourIndex", 0)
    opp = 1 - me
    players = _g(cur, "players", []) or []
    if len(players) < 2:
        return None
    full = Counter(ARCH_DECK)
    mp, op = players[me], players[opp]
    my_unknown = list((full - _visible_used(mp)).elements())
    op_unknown = list((full - _visible_used(op)).elements())
    dc, pz = _g(mp, "deckCount", 0), len(_g(mp, "prize", []) or [])
    odc, opz, ohc = _g(op, "deckCount", 0), len(_g(op, "prize", []) or []), _g(op, "handCount", 0)
    if len(my_unknown) < dc + pz or len(op_unknown) < odc + opz + ohc:
        return None
    rec = {
        "your_deck": my_unknown[:dc],
        "your_prize": my_unknown[dc:dc + pz],
        "opp_deck": op_unknown[:odc],
        "opp_prize": op_unknown[odc:odc + opz],
        "opp_hand": op_unknown[odc + opz:odc + opz + ohc],
        "opp_active": [],
    }
    oa = _g(op, "active") or []
    if len(oa) > 0 and oa[0] is None:
        import cg.api as api  # noqa: PLC0415
        _ensure_tables()
        picked = None
        for cid in op_unknown:
            cd = _CARD_TABLE.get(cid)
            if cd and _g(cd, "basic") and _g(cd, "cardType") == api.CardType.POKEMON:
                picked = cid
                break
        if picked is None:
            return None
        rec["opp_active"] = [picked]
    return rec


# ---------------------------------------------------------------------------
# 1手読み探索パイロット
# ---------------------------------------------------------------------------
def _fallback(obs):
    """探索不能時の安全手（簡易 setup-then-attack 相当）。空アクションにしない。"""
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    if sel is None:
        return list(ARCH_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


def _search_impl(obs):
    sel = obs.get("select") if isinstance(obs, dict) else _g(obs, "select")
    if sel is None:
        return list(ARCH_DECK)  # デッキ選択フェーズ
    options = _g(sel, "option", []) or []
    n = len(options)
    if n == 0:
        return []
    max_count = int(_g(sel, "maxCount", 1) or 1)
    min_count = int(_g(sel, "minCount", 0) or 0)
    cur = obs.get("current") if isinstance(obs, dict) else _g(obs, "current")
    if cur is None:
        return _fallback(obs)
    me = _g(cur, "yourIndex", 0)

    rec = _reconstruct(obs)
    if rec is None:
        return _fallback(obs)

    import cg.api as api  # noqa: PLC0415
    try:
        ob = api.to_observation_class(obs)
        root = api.search_begin(
            ob, rec["your_deck"], rec["your_prize"],
            rec["opp_deck"], rec["opp_prize"], rec["opp_hand"], rec["opp_active"],
        )
    except Exception:
        return _fallback(obs)

    def value_of(ns):
        c = ns.observation.current
        if c is None:
            return 0.0
        r = getattr(c, "result", -1)
        if r != -1:
            return 1e9 if r == me else (-1e9 if r == (1 - me) else 0.0)
        return float(state_eval(c, me))

    def actor_value(ns, actor):
        c = ns.observation.current
        if c is None:
            return 0.0
        r = getattr(c, "result", -1)
        if r != -1:
            return 1e9 if r == actor else (-1e9 if r == (1 - actor) else 0.0)
        return float(state_eval(c, actor))

    def play_turn(ns):
        c0 = ns.observation.current
        if c0 is None:
            return ns
        actor = getattr(c0, "yourIndex", me)
        for _ in range(ROLLOUT_BUDGET):
            c = ns.observation.current
            if c is None or getattr(c, "result", -1) != -1:
                return ns
            if getattr(c, "yourIndex", actor) != actor:
                return ns
            s = ns.observation.select
            if s is None or not s.option:
                return ns
            mc = int(getattr(s, "maxCount", 1) or 1)
            nopt = len(s.option)
            if mc <= 1:
                best_v, best_ns = float("-inf"), None
                for i in range(nopt):
                    try:
                        nxt = api.search_step(ns.searchId, [i])
                    except Exception:
                        continue
                    v = actor_value(nxt, actor)
                    if v > best_v:
                        best_v, best_ns = v, nxt
                if best_ns is None:
                    return ns
                ns = best_ns
            else:
                try:
                    ns = api.search_step(ns.searchId, list(range(min(mc, nopt))))
                except Exception:
                    return ns
        return ns

    def score_of(select_list):
        try:
            ns = api.search_step(root.searchId, select_list)
        except Exception:
            return None
        for _ in range(N_TURNS):
            c = ns.observation.current
            if c is None or getattr(c, "result", -1) != -1:
                break
            ns = play_turn(ns)
        return value_of(ns)

    try:
        if max_count <= 1:
            best_i, best_s = None, float("-inf")
            for i in range(n):
                s = score_of([i])
                if s is not None and s > best_s:
                    best_s, best_i = s, i
            result = [best_i] if best_i is not None else _fallback(obs)
        else:
            chosen, remaining = [], set(range(n))
            cur_score = score_of([]) if min_count == 0 else None
            while len(chosen) < max_count and remaining:
                best_i, best_s = None, float("-inf")
                for i in list(remaining):
                    s = score_of(sorted(chosen + [i]))
                    if s is not None and s > best_s:
                        best_s, best_i = s, i
                if best_i is None:
                    break
                if len(chosen) >= min_count and cur_score is not None and best_s <= cur_score:
                    break
                chosen.append(best_i)
                remaining.discard(best_i)
                cur_score = best_s
            if len(chosen) < min_count:
                for i in range(n):
                    if i not in chosen:
                        chosen.append(i)
                    if len(chosen) >= min_count:
                        break
            result = sorted(chosen) if chosen else _fallback(obs)
    finally:
        try:
            api.search_end()
        except Exception:
            pass
    return result


def _safe_default(observation):
    """絶対にブリックしない保険手。空アクション自滅を根絶する。"""
    sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
    if sel is None:
        return list(ARCH_DECK)
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
        out = _search_impl(observation)
    except Exception:
        return _safe_default(observation)
    try:
        sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
        if sel is None:
            return out if (isinstance(out, list) and len(out) == 60) else list(ARCH_DECK)
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
