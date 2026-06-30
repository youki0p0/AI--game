"""Static state evaluation for Pokemon TCG (CABT), inspired by Shogi static eval.

設計思想(将棋流):
    将棋の静的評価値 = 駒得 + 位置/玉安全 の重み付き和。
    これを PTCG へ翻訳する:
        - 駒得         -> サイド差 (勝利への距離) + 盤面マテリアル差
        - 玉の安全      -> 自分アクティブの HP 余裕・状態異常の有無
        - 速度/手得     -> 脅威(KO 可能性)・テンポ
        - 駒の効率      -> 資源(手札/山札/ベンチ展開/エネルギー)

本モジュールは engine 非依存の純関数として `state_eval(current, my_index)` を提供する。
入力は obs["current"](dict)。隠れ情報(相手手札中身/裏サイドの中身)は使わず「数」だけを使う。

カード固有情報(ex/megaEx, hp, attacks 等)は engine.cg.api.all_card_data()/all_attack() を
遅延ロードしてキャッシュする。ロードできない環境でもカード情報なしのフォールバックで動く。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# カードデータの遅延ロード(engine 非依存・失敗してもフォールバック)
# ---------------------------------------------------------------------------

_CARD_TABLE: Optional[dict] = None      # cardId -> CardData
_ATTACK_TABLE: Optional[dict] = None    # attackId -> Attack


def _ensure_tables() -> None:
    """engine.cg.api からカード/技テーブルを一度だけロードしてキャッシュする。

    import に失敗した場合は空の dict を入れて以後フォールバック動作にする。
    state_eval を engine 非依存の純関数に保つため、ここで例外を握り潰す。
    """
    global _CARD_TABLE, _ATTACK_TABLE
    if _CARD_TABLE is not None:
        return
    try:
        from cg.api import all_card_data, all_attack  # type: ignore
        _CARD_TABLE = {c.cardId: c for c in all_card_data()}
        _ATTACK_TABLE = {a.attackId: a for a in all_attack()}
    except Exception:
        _CARD_TABLE = {}
        _ATTACK_TABLE = {}


def _card_data(card_id: Any):
    """cardId -> CardData。未ロード/不明なら None。"""
    _ensure_tables()
    if card_id is None:
        return None
    return _CARD_TABLE.get(card_id)  # type: ignore[union-attr]


def _attack_data(attack_id: Any):
    """attackId -> Attack。未ロード/不明なら None。"""
    _ensure_tables()
    if attack_id is None:
        return None
    return _ATTACK_TABLE.get(attack_id)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 重み(チューニング可能)
# ---------------------------------------------------------------------------

@dataclass
class Weights:
    """評価値の重み。桁感は「サイド差 >> マテリアル差 > 脅威 > 資源」。

    根拠:
        - サイド差は勝敗に直結する支配項。1サイドの価値を最大級にし、
          マテリアルやテンポより一桁上に置く。残りサイドが少ない側が勝利に近い。
        - マテリアルは将棋の駒得相当。盤面のポケモン価値差。サイドより一桁下。
        - 脅威(KO 可能性・状態異常)はテンポ項。マテリアルより小さめ。
        - 資源は最も小さい補正(序盤の展開差を緩く反映)。
    """

    # --- 支配項: サイド差 ---
    # 自分が取られていない(残っている)サイドが少ないほど勝利に近い。
    # 「相手残サイド - 自分残サイド」に乗じる。1サイド差 = 1000 点級。
    prize_diff: float = 1000.0

    # --- マテリアル: 盤面ポケモン価値差 ---
    material_diff: float = 1.0  # pokemon_value() が既に点数化済みなので等倍で合算

    # --- マテリアル内訳(pokemon_value で使用) ---
    # サイド価値(KO されると相手が取るサイド数)= リスク。megaEx=3, ex=2, その他=1。
    # buddy の prize_count()*1000 を踏襲し、盤面1体の存在価値の基礎にする。
    w_prize_value: float = 300.0     # サイド1枚相当の盤面価値(prize_diff より控えめ)
    w_hp_ratio: float = 120.0        # 現HP/maxHP。満タンで満点、瀕死で0。玉の体力相当
    w_energy_ready: float = 90.0     # 技要求エネルギーに届いた本数の価値
    w_energy_extra: float = 15.0     # 余剰エネルギー(届いた後の追加)は小さく評価
    w_stage2: float = 60.0           # 進化段階(投資量)の上乗せ
    w_stage1: float = 30.0
    w_tool: float = 25.0             # 付与ツール1個あたり

    # --- 脅威/テンポ ---
    w_can_ko: float = 250.0          # 自分アクティブが相手アクティブを KO 可能なら加点
    w_will_be_koed: float = 200.0    # 相手アクティブが自分アクティブを KO 可能なら減点
    w_damage_ratio: float = 80.0     # KO に届かなくても与ダメ割合をテンポとして評価

    # 状態異常(自分アクティブにあると減点 / 相手アクティブにあると加点)
    w_sc_poison: float = 40.0
    w_sc_burn: float = 30.0
    w_sc_sleep: float = 70.0         # 行動不能級は重く
    w_sc_paralyze: float = 70.0
    w_sc_confuse: float = 35.0

    # --- 資源(重みは小さめ) ---
    w_hand: float = 8.0              # 手札枚数差
    w_deck: float = 1.5              # 山札枚数差(山切れ負けの遠い回避)
    w_bench: float = 25.0            # ベンチ展開数差(後続の確保)
    w_total_energy: float = 6.0      # 盤面総エネルギー数差

    # --- 終局値 ---
    terminal: float = 100000.0       # 勝ち=+terminal, 負け=-terminal, 分=0


DEFAULT_WEIGHTS = Weights()


# ---------------------------------------------------------------------------
# 小さなユーティリティ(dict アクセスは .get で堅牢に)
# ---------------------------------------------------------------------------

def _g(d: Any, key: str, default: Any = None) -> Any:
    """dict からも dataclass からも安全に属性/キーを取り出す。"""
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _iter_pokemon(player: Any):
    """プレイヤーの場の全ポケモン(active + bench)を yield する。None は除外。"""
    if player is None:
        return
    for p in _g(player, "active", []) or []:
        if p is not None:
            yield p
    for p in _g(player, "bench", []) or []:
        if p is not None:
            yield p


def _active(player: Any):
    """アクティブポケモン(無ければ None)。active は size 0 or 1。"""
    arr = _g(player, "active", []) or []
    if len(arr) > 0:
        return arr[0]
    return None


# ---------------------------------------------------------------------------
# サイド価値(buddy の prize_count 相当): KO されたとき相手が取るサイド数
# ---------------------------------------------------------------------------

def prize_value(pokemon: Any) -> int:
    """この個体が KO されたら相手が取るサイド数。megaEx=3, ex=2, その他=1。

    エネルギー/ツールによる減算(buddy の特殊カード)は一次情報が個別カード依存で
    汎用化しづらいため、ここでは基本ルール(ex/megaEx)のみを反映する。
    """
    data = _card_data(_g(pokemon, "id"))
    if data is None:
        return 1
    if _g(data, "megaEx"):
        return 3
    if _g(data, "ex"):
        return 2
    return 1


# ---------------------------------------------------------------------------
# 技要求エネルギーへの到達度
# ---------------------------------------------------------------------------

def _energy_requirement(pokemon: Any) -> Optional[int]:
    """この個体の技のうち「最も安い技」の必要エネルギー数。技不明なら None。"""
    data = _card_data(_g(pokemon, "id"))
    if data is None:
        return None
    attacks = _g(data, "attacks", []) or []
    costs = []
    for aid in attacks:
        atk = _attack_data(aid)
        if atk is None:
            continue
        energies = _g(atk, "energies", []) or []
        costs.append(len(energies))
    if not costs:
        return None
    return min(costs)


def _best_attack_damage(pokemon: Any) -> int:
    """付与エネルギーで撃てる技のうち最大の素ダメージ。撃てる技が無ければ0。

    弱点/抵抗/効果テキストは無視した概算(静的評価のための粗い見積り)。
    """
    data = _card_data(_g(pokemon, "id"))
    if data is None:
        return 0
    have = len(_g(pokemon, "energies", []) or [])
    best = 0
    for aid in _g(data, "attacks", []) or []:
        atk = _attack_data(aid)
        if atk is None:
            continue
        cost = len(_g(atk, "energies", []) or [])
        if have >= cost:
            best = max(best, int(_g(atk, "damage", 0) or 0))
    return best


# ---------------------------------------------------------------------------
# 1体のポケモン価値(マテリアル)
# ---------------------------------------------------------------------------

def pokemon_value(pokemon: Any, w: Weights) -> float:
    """場の1体のマテリアル価値。HP余裕・サイドリスク・エネ充足・進化段階・ツール。"""
    if pokemon is None:
        return 0.0
    score = 0.0

    # サイド価値(取られると相手が得るサイド数)= 盤面に残っている価値
    score += w.w_prize_value * prize_value(pokemon)

    # HP 余裕(玉の体力相当)
    hp = float(_g(pokemon, "hp", 0) or 0)
    max_hp = float(_g(pokemon, "maxHp", 0) or 0)
    if max_hp > 0:
        score += w.w_hp_ratio * max(0.0, min(1.0, hp / max_hp))

    # エネルギー充足度: 最安技の要求に対する到達本数
    have = len(_g(pokemon, "energies", []) or [])
    req = _energy_requirement(pokemon)
    if req is None:
        # 技不明: 付与エネルギーを薄く評価
        score += w.w_energy_extra * have
    else:
        ready = min(have, req)
        extra = max(0, have - req)
        score += w.w_energy_ready * ready
        score += w.w_energy_extra * extra

    # 進化段階(これまでの投資)
    data = _card_data(_g(pokemon, "id"))
    if data is not None:
        if _g(data, "stage2"):
            score += w.w_stage2
        elif _g(data, "stage1"):
            score += w.w_stage1

    # 付与ツール
    score += w.w_tool * len(_g(pokemon, "tools", []) or [])

    return score


# ---------------------------------------------------------------------------
# 特徴量(自分視点の差分: 正=自分有利)
# ---------------------------------------------------------------------------

def prize_diff(current: Any, my_index: int, w: Weights) -> float:
    """支配項: サイド差。残サイドが少ない側が勝利に近い。

    self.prize は「自分がまだ取られていない=取らせていないサイド」の list。
    残りが少ない=サイドを多く取った=勝利に近い。
    指標 = (相手残サイド - 自分残サイド)。正なら自分が先行。
    """
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me = players[my_index]
    op = players[1 - my_index]
    my_remain = len(_g(me, "prize", []) or [])
    op_remain = len(_g(op, "prize", []) or [])
    return w.prize_diff * (op_remain - my_remain)


def material_diff(current: Any, my_index: int, w: Weights) -> float:
    """盤面マテリアル差: 自分の場のポケモン価値合計 - 相手の合計。"""
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me = players[my_index]
    op = players[1 - my_index]
    my_val = sum(pokemon_value(p, w) for p in _iter_pokemon(me))
    op_val = sum(pokemon_value(p, w) for p in _iter_pokemon(op))
    return w.material_diff * (my_val - op_val)


def _special_condition_score(player: Any, w: Weights) -> float:
    """このプレイヤーのアクティブに付く状態異常の「悪さ」合計(正の値)。"""
    s = 0.0
    if _g(player, "poisoned"):
        s += w.w_sc_poison
    if _g(player, "burned"):
        s += w.w_sc_burn
    if _g(player, "asleep"):
        s += w.w_sc_sleep
    if _g(player, "paralyzed"):
        s += w.w_sc_paralyze
    if _g(player, "confused"):
        s += w.w_sc_confuse
    return s


def threat(current: Any, my_index: int, w: Weights) -> float:
    """脅威/テンポ: KO 可能性と状態異常。

    - 自分アクティブが相手アクティブを KO できそう -> 加点(can_ko + damage_ratio)
    - 相手アクティブが自分アクティブを KO できそう -> 減点(will_be_koed + damage_ratio)
    - 状態異常: 自分側にあると減点 / 相手側にあると加点
    弱点/抵抗/効果は無視した概算ダメージ(静的評価)。
    """
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me = players[my_index]
    op = players[1 - my_index]
    my_act = _active(me)
    op_act = _active(op)

    s = 0.0

    # 自分 -> 相手
    if my_act is not None and op_act is not None:
        dmg = _best_attack_damage(my_act)
        op_hp = float(_g(op_act, "hp", 0) or 0)
        if op_hp > 0:
            if dmg >= op_hp:
                s += w.w_can_ko
                s += w.w_damage_ratio  # 満額のダメージ割合
            else:
                s += w.w_damage_ratio * (dmg / op_hp)

    # 相手 -> 自分
    if op_act is not None and my_act is not None:
        dmg = _best_attack_damage(op_act)
        my_hp = float(_g(my_act, "hp", 0) or 0)
        if my_hp > 0:
            if dmg >= my_hp:
                s -= w.w_will_be_koed
                s -= w.w_damage_ratio
            else:
                s -= w.w_damage_ratio * (dmg / my_hp)

    # 状態異常(自分側は不利=減点, 相手側は有利=加点)
    s -= _special_condition_score(me, w)
    s += _special_condition_score(op, w)

    return s


def resources(current: Any, my_index: int, w: Weights) -> float:
    """資源差: 手札/山札/ベンチ展開/盤面総エネルギー。重みは小さめ。"""
    players = _g(current, "players", []) or []
    if len(players) < 2:
        return 0.0
    me = players[my_index]
    op = players[1 - my_index]

    s = 0.0
    s += w.w_hand * (float(_g(me, "handCount", 0) or 0) - float(_g(op, "handCount", 0) or 0))
    s += w.w_deck * (float(_g(me, "deckCount", 0) or 0) - float(_g(op, "deckCount", 0) or 0))

    my_bench = len(_g(me, "bench", []) or [])
    op_bench = len(_g(op, "bench", []) or [])
    s += w.w_bench * (my_bench - op_bench)

    my_energy = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(me))
    op_energy = sum(len(_g(p, "energies", []) or []) for p in _iter_pokemon(op))
    s += w.w_total_energy * (my_energy - op_energy)

    return s


# ---------------------------------------------------------------------------
# メイン評価関数
# ---------------------------------------------------------------------------

def state_eval(current: Any, my_index: int, weights: Optional[Weights] = None) -> float:
    """局面の静的評価値(自分視点, 正=自分有利)を返す純関数。

    Args:
        current: obs["current"](dict)。State 相当。None も許容。
        my_index: 自分のプレイヤー index(state["yourIndex"] を渡す想定)。
        weights: 重み。None なら DEFAULT_WEIGHTS。

    Returns:
        float: 評価値。終局(result != -1)では terminal 級の確定値を返す。
            勝ち=+terminal, 負け=-terminal, 分=0。current=None も 0。
    """
    w = weights or DEFAULT_WEIGHTS

    # --- 終局・無効入力の扱い ---
    if current is None:
        return 0.0
    result = _g(current, "result", -1)
    if result is not None and result != -1:
        if result == 2:          # 引き分け
            return 0.0
        if result == my_index:   # 自分勝ち
            return w.terminal
        return -w.terminal        # 相手勝ち

    players = _g(current, "players", []) or []
    if len(players) < 2 or my_index not in (0, 1):
        return 0.0

    # --- 重み付き和 ---
    score = 0.0
    score += prize_diff(current, my_index, w)
    score += material_diff(current, my_index, w)
    score += threat(current, my_index, w)
    score += resources(current, my_index, w)
    return score


def state_eval_breakdown(current: Any, my_index: int,
                         weights: Optional[Weights] = None) -> dict:
    """各項の内訳を返す(検証・デバッグ用)。"""
    w = weights or DEFAULT_WEIGHTS
    if current is None:
        return {"total": 0.0, "terminal": True}
    result = _g(current, "result", -1)
    if result is not None and result != -1:
        total = 0.0 if result == 2 else (w.terminal if result == my_index else -w.terminal)
        return {"total": total, "terminal": True, "result": result}
    parts = {
        "prize_diff": prize_diff(current, my_index, w),
        "material_diff": material_diff(current, my_index, w),
        "threat": threat(current, my_index, w),
        "resources": resources(current, my_index, w),
    }
    parts["total"] = sum(v for k, v in parts.items())
    parts["terminal"] = False
    return parts


# ---------------------------------------------------------------------------
# 最小自己確認(engine/deck.pkl で初期局面を1つ作り評価)
# ---------------------------------------------------------------------------

def _resolve_engine_dir() -> str:
    """engine ディレクトリの絶対パスを解決する。

    worktree 配下に engine が無い場合(サブツリー未チェックアウト)に備えて、
    共有チェックアウト側の engine もフォールバック候補にする。
    """
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(here, "..", "engine")),
        "/home/user/AI--game/pokemon-tcg-ai-battle/engine",
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "deck.pkl")):
            return c
    return candidates[0]


def _smoke_main() -> int:
    import os
    import sys
    import pickle
    import math

    engine_dir = _resolve_engine_dir()
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)

    deck_path = os.path.join(engine_dir, "deck.pkl")
    with open(deck_path, "rb") as f:
        deck = pickle.load(f)

    from cg.game import battle_start, battle_finish  # type: ignore

    obs, _start = battle_start(list(deck), list(deck))
    if obs is None:
        print("[smoke] battle_start returned None obs")
        return 1

    current = obs.get("current")
    if current is None:
        print("[smoke] current is None at start (deck-select phase). eval=0.0 (expected).")
        my_index = 0
    else:
        my_index = current.get("yourIndex", 0)

    val = state_eval(current, my_index)
    bd = state_eval_breakdown(current, my_index)
    print(f"[smoke] my_index={my_index}")
    print(f"[smoke] state_eval = {val}")
    print(f"[smoke] breakdown  = {bd}")

    ok = isinstance(val, float) and math.isfinite(val)
    print(f"[smoke] finite float? {ok}")

    try:
        battle_finish()
    except Exception:
        pass
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(_smoke_main())
