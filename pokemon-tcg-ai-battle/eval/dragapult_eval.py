"""(2) planning用の壁対応評価関数（ドラパルト ex 向け）。

課題: state_eval は「相手アクティブがexダメージを無効化する壁(イワパレス=Crustle)」を
知らない。_effective_damage/threat がドラパルト ex のファントムダイブ200を有効打として
数えてしまい（実際は無効）、探索が「ドラパルトを立て続ける」＝勝てない手を選ぶ。

本評価関数の補正:
  1) 相手アクティブがex技無効の壁のとき、こちらの *ex* アタッカーの脅威を0にする
     （ファントムダイブの過大評価を除去）。
  2) 代わりに、こちらの *非ex* アタッカー（ヨノワール=影縛り150）の「技到達度」を報酬化。
     ベンチより **アクティブに居る方**を高く評価 → 探索がヨノワールにエネを積み、前線へ
     上げて影縛りを撃つ多ターン計画を選ぶようになる。

これにより search（deck_battle.make_deck_agent）を planning 型に格上げする。
"""
from __future__ import annotations

from typing import Any, Optional

from .state_eval import (
    DEFAULT_WEIGHTS, Weights, _active, _card_data, _effective_damage,
    _energy_requirement, _g, _iter_pokemon, _special_condition_score,
    material_diff, prize_diff, resources, state_eval_breakdown,
)

# 壁として既知のカード（ex技ダメージ無効）。テキスト判定の取りこぼし保険。
_KNOWN_EX_WALLS = {345}  # Crustle (イワパレス) "Mysterious Rock Inn"

# planning 補正の強さ
W_SETUP = 3.0            # 非exアタッカーの到達度×実効ダメージ への係数
ACTIVE_BONUS = 2.0       # そのアタッカーがアクティブなら上乗せ（前線化を促す）
W_WALL_PROGRESS = 3.0    # ex無効壁に乗った累積ダメージ(=削り進捗)。回復で見えなくなるのを補う
W_WALL_FINISH = 4000.0   # 低HPの壁を「非ex攻撃/カースドボムでKOできる」状態への大報酬


def _is_ex(card_data: Any) -> bool:
    return bool(_g(card_data, "ex") or _g(card_data, "megaEx"))


def _blocks_ex_damage(pokemon: Any) -> bool:
    """この個体が『相手exポケモンの技ダメージを無効化』する壁か。"""
    cd = _card_data(_g(pokemon, "id"))
    if cd is None:
        return False
    if _g(cd, "cardId") in _KNOWN_EX_WALLS or _g(pokemon, "id") in _KNOWN_EX_WALLS:
        return True
    for s in (_g(cd, "skills", []) or []):
        text = (_g(s, "text", "") or "").lower()
        if "prevent all damage" in text and ("{ex}" in text or "ex}" in text or "pokémon ex" in text):
            return True
    return False


def _eff_dmg_exaware(attacker: Any, defender: Any) -> float:
    """壁(ex無効)を考慮した実効ダメージ。攻撃側がexで防御側が壁なら0。"""
    ad = _card_data(_g(attacker, "id"))
    if _is_ex(ad) and _blocks_ex_damage(defender):
        return 0.0
    return _effective_damage(attacker, defender)


def _threat_exaware(current: Any, my_index: int, w: Weights) -> float:
    """state_eval.threat を ex無効壁対応で再計算した版。"""
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me, op = players[my_index], players[1 - my_index]
    my_act, op_act = _active(me), _active(op)
    s = 0.0
    if my_act is not None and op_act is not None:
        dmg = _eff_dmg_exaware(my_act, op_act)
        oh = float(_g(op_act, "hp", 0) or 0)
        if oh > 0:
            if dmg >= oh:
                s += w.w_can_ko + w.w_damage_ratio
            else:
                s += w.w_damage_ratio * (dmg / oh)
    if op_act is not None and my_act is not None:
        dmg = _eff_dmg_exaware(op_act, my_act)
        mh = float(_g(my_act, "hp", 0) or 0)
        if mh > 0:
            if dmg >= mh:
                s -= w.w_will_be_koed + w.w_damage_ratio
            else:
                s -= w.w_damage_ratio * (dmg / mh)
    # 状態異常（state_eval.threat と同じ寄与。非壁マッチでの一致のため必ず含める）
    s -= _special_condition_score(me, w)
    s += _special_condition_score(op, w)
    return s


def _has_cursed_blast_ready(me: Any) -> bool:
    """場に ヨノワール(133)/サマヨール(132) が居るか（カースドボムで壁をKO可能）。"""
    for p in _iter_pokemon(me):
        if _g(p, "id") in (133, 132):
            return True
    return False


def _nonex_setup_gradient(current: Any, my_index: int) -> float:
    """相手アクティブがex無効壁のとき、非exアタッカーの組成・削り進捗・トドメ機会を報酬化。"""
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me, op = players[my_index], players[1 - my_index]
    op_act = _active(op)
    if op_act is None or not _blocks_ex_damage(op_act):
        return 0.0
    my_act = _active(me)
    oh = float(_g(op_act, "hp", 0) or 0)
    omax = float(_g(op_act, "maxHp", 0) or 0)
    bonus = 0.0

    # (a) 壁に乗った累積ダメージ = 削り進捗（回復されても "近づいている" を評価）
    if omax > 0:
        bonus += W_WALL_PROGRESS * max(0.0, omax - oh)

    # (b) 非exアタッカーの技到達度（アクティブなら大）。壁を貫通できる打点を用意させる。
    best = 0.0
    finisher = False
    for p in _iter_pokemon(me):
        cd = _card_data(_g(p, "id"))
        if cd is None or _is_ex(cd):
            continue  # 非exのみ
        dmg = _effective_damage(p, op_act)
        if dmg <= 0:
            continue
        req = _energy_requirement(p) or 3
        have = len(_g(p, "energies", []) or [])
        readiness = min(1.0, have / max(1, req))
        val = dmg * readiness * (ACTIVE_BONUS if p is my_act else 1.0)
        best = max(best, val)
        # トドメ機会: 技が撃てて壁の残HP以上のダメージ → KOできる非ex打点
        if have >= req and oh > 0 and dmg >= oh:
            finisher = True
    bonus += W_SETUP * best

    # (c) 低HPの壁を「今KOできる」状態への大報酬（非ex攻撃 or カースドボム）
    if oh > 0:
        can_finish = finisher or (oh <= 130 and _has_cursed_blast_ready(me))
        if can_finish:
            bonus += W_WALL_FINISH
    return bonus


def dragapult_eval(current: Any, my_index: int,
                   weights: Optional[Weights] = None) -> float:
    """壁対応の planning 評価値。state_eval の threat を ex無効対応に差し替え、
    非exアタッカーの組成勾配を加える。"""
    w = weights or DEFAULT_WEIGHTS
    bd = state_eval_breakdown(current, my_index, w)
    if bd.get("terminal"):
        return bd["total"]
    # threat を ex無効対応版に差し替え、非ex組成勾配を追加
    total = (prize_diff(current, my_index, w)
             + material_diff(current, my_index, w)
             + _threat_exaware(current, my_index, w)
             + resources(current, my_index, w)
             + _nonex_setup_gradient(current, my_index))
    return total
