"""人間 vs AI: ターミナルで CABT エンジンの対戦を手動プレイする。

使い方 (要 engine/ 配置。競技規約により非再配布のため .gitignore 済み):

    cd pokemon-tcg-ai-battle
    python -m eval.play_vs_human                     # champion 相手にデフォルトデッキで対戦
    python -m eval.play_vs_human --opponent buddy
    python -m eval.play_vs_human --opponent grimmsnarl --human-deck psy_single
    python -m eval.play_vs_human --list               # 対戦相手一覧を表示するだけ

毎ターン、盤面(アクティブ/ベンチ/サイド/手札枚数など)と選択肢を日本語ラベル付きで
表示し、番号をカンマ区切りで入力すると `game.battle_select` に渡す。
'q' / 'quit' / '投了' で投了できる。
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from .state_eval import _card_data, _attack_data, _g

# OptionType (cg.api 由来。typed_pilot.py / psy_pilot.py と同じ定義)
T_NUMBER, T_YES, T_NO, T_CARD, T_TOOL_CARD, T_ENERGY_CARD, T_ENERGY = 0, 1, 2, 3, 4, 5, 6
T_PLAY, T_ATTACH, T_EVOLVE, T_ABILITY, T_DISCARD, T_RETREAT, T_ATTACK, T_END, T_SKILL, T_SPECIAL = \
    7, 8, 9, 10, 11, 12, 13, 14, 15, 16

OPTION_TYPE_LABELS = {
    T_NUMBER: "数値", T_YES: "はい", T_NO: "いいえ",
    T_CARD: "カード", T_TOOL_CARD: "ツール", T_ENERGY_CARD: "エネルギーカード", T_ENERGY: "エネルギー",
    T_PLAY: "プレイ", T_ATTACH: "エネルギー付与", T_EVOLVE: "進化", T_ABILITY: "特性",
    T_DISCARD: "トラッシュ", T_RETREAT: "にげる", T_ATTACK: "こうげき", T_END: "ターン終了",
    T_SKILL: "スキル", T_SPECIAL: "特殊",
}

SC_IS_FIRST, SC_MULLIGAN = 41, 42


class HumanResign(Exception):
    """人間側が投了したことを示す。"""


# ---------------------------------------------------------------------------
# ラベル整形 (カード名は取得できない環境ではIDにフォールバックする)
# ---------------------------------------------------------------------------

def _card_label(card_id: Any) -> str:
    if card_id is None:
        return "?"
    card = _card_data(card_id)
    for key in ("name", "cardName", "displayName", "enName", "label"):
        v = _g(card, key)
        if v:
            return f"{v}(#{card_id})"
    return f"card#{card_id}"


def _attack_label(attack_id: Any) -> str:
    if attack_id is None:
        return "?"
    atk = _attack_data(attack_id)
    name = None
    for key in ("name", "attackName", "displayName"):
        v = _g(atk, key)
        if v:
            name = v
            break
    dmg = _g(atk, "damage")
    parts = [name or f"attack#{attack_id}"]
    if dmg is not None:
        parts.append(f"{dmg}dmg")
    return " ".join(parts)


def _status_flags(pokemon: Any) -> list[str]:
    labels = {
        "poisoned": "どく", "burned": "やけど", "asleep": "ねむり",
        "paralyzed": "まひ", "confused": "こんらん",
    }
    return [jp for key, jp in labels.items() if _g(pokemon, key)]


def _mon_label(pokemon: Any) -> str:
    cid = _g(pokemon, "id")
    hp = _g(pokemon, "hp")
    max_hp = _g(pokemon, "maxHp")
    energies = _g(pokemon, "energy") or _g(pokemon, "energies") or []
    n_energy = len(energies) if isinstance(energies, list) else energies
    s = f"{_card_label(cid)} HP {hp}/{max_hp}"
    if n_energy:
        s += f" エネルギー{n_energy}"
    status = _status_flags(pokemon)
    if status:
        s += " [" + ",".join(status) + "]"
    return s


def render_board(current: Any, me: int) -> None:
    if current is None:
        return
    players = _g(current, "players", []) or []
    turn = _g(current, "turn")
    print(f"\n===== ターン {turn} =====")
    for i, p in enumerate(players):
        who = "あなた" if i == me else "相手"
        active = _g(p, "active", []) or []
        bench = _g(p, "bench", []) or []
        prize = _g(p, "prize", []) or []
        hand_ct = _g(p, "handCount")
        deck_ct = _g(p, "deckCount")
        discard = _g(p, "discard", []) or []
        print(f"--- {who}(P{i}) --- 残りサイド:{len(prize)}  手札:{hand_ct}  山札:{deck_ct}  トラッシュ:{len(discard)}")
        for pk in active:
            if pk is not None:
                print("  アクティブ:", _mon_label(pk))
        for pk in bench:
            if pk is not None:
                print("  ベンチ    :", _mon_label(pk))
    stadium = _g(current, "stadium")
    if stadium:
        print(f"スタジアム: {_card_label(_g(stadium, 'id', stadium))}")


def _hand_card_label(o: Any, players: list, me: int) -> str | None:
    idx = _g(o, "index")
    if idx is None:
        return None
    hand = _g(players[me], "hand", []) if players and len(players) > me else None
    if isinstance(hand, list) and 0 <= idx < len(hand):
        cid = _g(hand[idx], "id", hand[idx])
        return _card_label(cid)
    return None


def describe_option(o: Any, current: Any, me: int) -> str:
    t = _g(o, "type")
    if t == T_YES:
        return "はい"
    if t == T_NO:
        return "いいえ"

    players = _g(current, "players", []) or [] if current is not None else []
    parts = [OPTION_TYPE_LABELS.get(t, f"type={t}")]

    attack_id = _g(o, "attackId")
    if attack_id is not None:
        parts.append(_attack_label(attack_id))

    hand_label = _hand_card_label(o, players, me)
    if hand_label is not None:
        parts.append(hand_label)

    card_id = _g(o, "cardId")
    if card_id is not None:
        parts.append(_card_label(card_id))

    pidx = _g(o, "playerIndex")
    if pidx is not None:
        parts.append("相手側" if pidx != me else "自分側")

    area = _g(o, "area", _g(o, "inPlayArea"))
    if area is not None:
        parts.append(f"area={area}")

    idx = _g(o, "index")
    if idx is not None and hand_label is None:
        parts.append(f"(#{idx})")

    return " / ".join(parts)


# ---------------------------------------------------------------------------
# 人間エージェント
# ---------------------------------------------------------------------------

def make_human_agent(human_deck: list[int], me: int = 0,
                      input_fn: Callable[[str], str] = input) -> Callable[[dict], list]:
    """人間が標準入力で操作する agent(obs) -> list[int] を返す。

    'q'/'quit'/'投了' が入力されると HumanResign を送出する。
    """

    def human_agent(obs: dict) -> list:
        sel = obs.get("select")
        current = obs.get("current")
        if sel is None:
            print(f"\n[デッキ提出] あなたのデッキ({len(human_deck)}枚)を提出します。")
            return list(human_deck)

        render_board(current, me)
        options = sel.get("option") or []
        if not options:
            return []

        print("\n選択肢:")
        for i, o in enumerate(options):
            print(f"  [{i}] {describe_option(o, current, me)}")

        max_count = int(sel.get("maxCount") or 1)
        min_count = int(sel.get("minCount") or 0)

        while True:
            prompt = f"番号を選んでください (0〜{len(options) - 1}, カンマ区切り可, 'q'で投了): "
            raw = input_fn(prompt).strip()
            if raw.lower() in ("q", "quit", "resign", "投了"):
                raise HumanResign()
            if raw == "":
                if min_count == 0:
                    return []
                print(f"最低{min_count}個選んでください。")
                continue
            try:
                idxs = [int(x) for x in raw.replace(" ", "").split(",") if x != ""]
            except ValueError:
                print("数字をカンマ区切りで入力してください。")
                continue
            if any(i < 0 or i >= len(options) for i in idxs):
                print("範囲外の番号があります。")
                continue
            if len(idxs) > max_count:
                print(f"最大{max_count}個までです。")
                continue
            if len(idxs) < min_count:
                print(f"最低{min_count}個選んでください。")
                continue
            return idxs

    return human_agent


# ---------------------------------------------------------------------------
# 対戦相手レジストリ
# ---------------------------------------------------------------------------

def _pkg_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# name -> (submissions ファイル名, その提出物「自分の」デッキ変数名)
_SUBMISSION_REGISTRY: dict[str, tuple[str, str]] = {
    "archaludon": ("archaludon_agent.py", "ARCH_DECK"),
    "crustle_slayer": ("crustle_slayer_agent.py", "FIRE_DECK"),
    "fire_adaptive": ("fire_adaptive_agent.py", "FIRE_DECK"),
    "fire_single": ("fire_single_agent.py", "FIRE_DECK"),
    "grimmsnarl": ("grimmsnarl_agent.py", "GRIMM_DECK"),
    "megastarmie": ("megastarmie_agent.py", "STARMIE_DECK"),
    "meta_search": ("meta_search_agent.py", "FIRE_DECK"),
    "psy_champion": ("psy_champion_agent.py", "PSY_DECK"),
}


def list_opponents() -> list[str]:
    return ["champion", "buddy", *sorted(_SUBMISSION_REGISTRY)]


def resolve_opponent(name: str) -> tuple[Callable[[dict], list], list[int]]:
    """name から (agent呼び出し可能オブジェクト, そのAIが使うデッキ) を返す。"""
    if name == "champion":
        from .champion import CHAMPION_DECK, champion_agent
        return champion_agent(), list(CHAMPION_DECK)

    if name == "buddy":
        from .agents_buddy import load_buddy_agent
        from .engine_driver import load_default_deck
        return load_buddy_agent(), load_default_deck()

    if name in _SUBMISSION_REGISTRY:
        filename, deck_attr = _SUBMISSION_REGISTRY[name]
        module = _load_module(_pkg_root() / "submissions" / filename)
        agent = getattr(module, "agent")
        deck = list(getattr(module, deck_attr))
        return agent, deck

    # 任意のファイルパス指定: "path/to/file.py" または "path/to/file.py:DECK_VAR"
    path_str, _, deck_attr = name.partition(":")
    path = Path(path_str)
    if not path.is_file():
        raise ValueError(
            f"不明な対戦相手: {name!r}. 選べるのは {list_opponents()} か "
            "'path/to/file.py[:DECK_VAR]' 形式のパスです。"
        )
    module = _load_module(path)
    agent = getattr(module, "agent")
    if deck_attr:
        deck = list(getattr(module, deck_attr))
    else:
        candidates = [
            (n, v) for n, v in vars(module).items()
            if n.endswith("DECK") and isinstance(v, (list, tuple)) and len(v) == 60
        ]
        if not candidates:
            raise ValueError(f"{path} 内に60枚デッキの定数(*_DECK)が見つかりません。--opponent {path}:DECK_VAR で指定してください。")
        deck_name, deck = candidates[0]
        print(f"[情報] {path.name} のデッキ定数として {deck_name} を自動選択しました。")
        deck = list(deck)
    return agent, deck


def _resolve_human_deck(name: str | None) -> list[int]:
    from .engine_driver import load_default_deck
    if name is None:
        return load_default_deck()
    from .decks import DECKS
    if name not in DECKS:
        raise ValueError(f"不明なデッキ名: {name!r}. 選べるのは {sorted(DECKS)} です。")
    return list(DECKS[name])


# ---------------------------------------------------------------------------
# メインループ
# ---------------------------------------------------------------------------

def play(opponent_name: str, human_deck_name: str | None = None) -> int:
    """人間(P0) vs 指定AI(P1) の1ゲームをターミナルで対話的に実行する。

    戻り値: 0=あなたの勝ち, 1=AIの勝ち, 2=引き分け/投了。
    """
    from .engine_driver import _ensure_engine_on_path

    try:
        _ensure_engine_on_path()
    except FileNotFoundError as e:
        print("エラー: CABT エンジン(engine/)が見つかりません。")
        print(str(e))
        print(
            "\n競技規約によりリポジトリには含まれていません。"
            "各自でエンジン一式を取得し、pokemon-tcg-ai-battle/ と同じ階層に"
            "engine/ (中に cg/ を含む)を配置してから再実行してください。"
        )
        return 2

    import cg.game as game  # noqa: PLC0415
    from cg.sim import Battle, lib  # noqa: PLC0415

    human_deck = _resolve_human_deck(human_deck_name)
    opponent_agent, opponent_deck = resolve_opponent(opponent_name)
    human_agent = make_human_agent(human_deck, me=0)

    print(f"=== あなた(P0) vs {opponent_name}(P1) ===")
    print("番号入力で選択、'q' で投了できます。\n")

    obs, _start = game.battle_start(list(human_deck), list(opponent_deck))
    resigned = False
    try:
        while True:
            current = obs.get("current") if obs else None
            if current is not None:
                result = current.get("result", -1)
                if result != -1:
                    return int(result)

            serial_data = lib.GetBattleData(Battle.battle_ptr)
            acting_player = int(serial_data.selectPlayer)
            agent = human_agent if acting_player == 0 else opponent_agent

            try:
                action = agent(obs)
            except HumanResign:
                resigned = True
                print("\n投了しました。")
                return 1

            obs = game.battle_select(action)
    finally:
        game.battle_finish()
        if resigned:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CABT エンジンで人間 vs AI エージェントを対戦する")
    ap.add_argument("--opponent", default="champion",
                    help=f"対戦相手 ({', '.join(list_opponents())}, もしくは path/to/file.py[:DECK_VAR])")
    ap.add_argument("--human-deck", default=None,
                    help="eval.decks.DECKS のキー名 (省略時は engine のデフォルトデッキ)")
    ap.add_argument("--list", action="store_true", help="対戦相手一覧を表示して終了する")
    args = ap.parse_args(argv)

    if args.list:
        print("対戦相手:", ", ".join(list_opponents()))
        return 0

    result = play(args.opponent, args.human_deck)
    if result == 0:
        print("\n🎉 あなたの勝ちです！")
    elif result == 1:
        print("\nAIの勝ちです。")
    else:
        print("\n引き分け（もしくは中断）です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
