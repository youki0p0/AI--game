"""人間 vs 提出エージェント の対戦環境（チャット越しプレイ用）。

エンジンをバックグラウンドで生かしたまま、人間(player0)の手番では盤面と選択肢を
STATE_FILE に人間可読で書き出し、MOVE_FILE から指し手(番号)を受け取って進める。
相手(player1)は提出エージェント(既定=Archaludon探索版)。

IPCプロトコル:
  STATE_FILE (JSON): {"seq":N, "over":bool, "text":"...盤面と選択肢...", "nopt":K, "maxCount":mc, "minCount":mn}
  MOVE_FILE  (text): 1行 "SEQ:idx[,idx...]"（例 "3:0" / "5:0,2"）。SEQ が現在の決定番号に一致する行を採用。

使い方: python -m eval.human_game [opponent] [human_deck]
  opponent: archaludon(既定) / megastarmie
  human_deck: archaludon(既定) / grimmsnarl / megastarmie
"""
from __future__ import annotations
import json, os, sys, time, importlib.util
from .engine_driver import _ensure_engine_on_path

STATE_FILE = "/tmp/hvg_state.json"
MOVE_FILE = "/tmp/hvg_move.txt"

DECKS = {
 "archaludon": [169]*4+[190]*4+[666]*4+[1244]*4+[8]*13+[1152]*4+[1121]*4+[1122]*4+[1097]*4+[1197]*3+[1147]*2+[1159]*1+[1182]*1+[1185]*4+[1227]*4,
 "grimmsnarl": [646]*4+[647]*3+[648]*3+[112]*4+[305]*3+[66]*2+[649]*1+[1086]*4+[1152]*4+[1079]*3+[1097]*2+[1119]*1+[1139]*1+[1159]*1+[1227]*4+[1231]*4+[1197]*2+[1259]*4+[7]*10,
 "megastarmie": [3]*9+[17]*4+[666]*4+[1030]*3+[1031]*3+[1086]*4+[1097]*2+[1120]*4+[1121]*1+[1122]*4+[1145]*4+[1159]*1+[1182]*1+[1189]*4+[1223]*2+[1225]*2+[1227]*4+[1229]*4,
}
OPP_FILE = {
 "archaludon": "archaludon_search_agent.py",
 "megastarmie": "megastarmie_search_agent.py",
}

OPT = {1:"はい", 2:"いいえ", 7:"出す/使う", 8:"エネ付け", 9:"進化", 10:"特性", 11:"トラッシュ", 12:"にげる", 13:"こうげき", 14:"ターン終了"}
AREA = {4:"アクティブ", 5:"ベンチ"}


def _load_tables():
    import cg.api as api
    cards = {c.cardId: c for c in api.all_card_data()}
    atks = {a.attackId: a for a in api.all_attack()}
    return cards, atks


def _nm(cards, cid):
    c = cards.get(cid)
    return getattr(c, "name", str(cid)) if c else str(cid)


def _pk_line(cards, pk):
    if pk is None:
        return "(なし)"
    nm = _nm(cards, pk.get("id"))
    hp = pk.get("hp"); mhp = pk.get("maxHp")
    e = len(pk.get("energies") or [])
    tools = len(pk.get("tools") or [])
    t = f"{nm} HP{hp}/{mhp} エネ{e}"
    if tools:
        t += f" 道具{tools}"
    return t


def _opt_label(cards, atks, obs, o):
    t = o.get("type")
    base = OPT.get(t, f"type{t}")
    cur = obs.get("current") or {}
    me = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    mp = players[me] if len(players) > me else {}
    if t in (7, 9):  # PLAY / EVOLVE : hand index
        idx = o.get("index"); hand = mp.get("hand") or []
        if idx is not None and 0 <= idx < len(hand):
            return f"{base}: {_nm(cards, hand[idx].get('id'))}"
    if t == 8:  # ATTACH
        ar = o.get("inPlayArea"); ii = o.get("inPlayIndex")
        arr = mp.get("active") if ar == 4 else (mp.get("bench") if ar == 5 else None)
        tgt = arr[ii] if (isinstance(arr, list) and ii is not None and 0 <= ii < len(arr)) else None
        return f"{base}→{AREA.get(ar,'?')} {_nm(cards, tgt.get('id')) if tgt else ''}"
    if t == 13:  # ATTACK
        a = atks.get(o.get("attackId"))
        if a:
            return f"{base}: {getattr(a,'name','')} (ダメ{getattr(a,'damage',0)})"
    if o.get("cardId") is not None:
        return f"{base}: {_nm(cards, o.get('cardId'))}"
    return base


def render(cards, atks, obs, seq):
    cur = obs.get("current") or {}
    sel = obs.get("select") or {}
    me = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    mp = players[me] if len(players) > me else {}
    op = players[1-me] if len(players) > 1-me else {}
    L = []
    L.append(f"===== ターン{cur.get('turn')} / あなた=P{me} =====")
    L.append(f"[相手] サイド残{len(op.get('prize') or [])} 手札{op.get('handCount')} 山{op.get('deckCount')}")
    oa = (op.get("active") or [None])
    L.append(f"  相手アクティブ: {_pk_line(cards, oa[0] if oa else None)}")
    ob = [p for p in (op.get("bench") or []) if p]
    if ob:
        L.append("  相手ベンチ: " + " / ".join(_pk_line(cards, p) for p in ob))
    L.append(f"[あなた] サイド残{len(mp.get('prize') or [])} 山{mp.get('deckCount')}")
    ma = (mp.get("active") or [None])
    L.append(f"  あなたのアクティブ: {_pk_line(cards, ma[0] if ma else None)}")
    mb = [p for p in (mp.get("bench") or []) if p]
    if mb:
        L.append("  あなたのベンチ: " + " / ".join(_pk_line(cards, p) for p in mb))
    hand = mp.get("hand") or []
    if hand:
        L.append("  手札: " + ", ".join(_nm(cards, c.get("id")) for c in hand))
    opts = sel.get("option") or []
    mc = int(sel.get("maxCount", 1) or 1); mn = int(sel.get("minCount", 0) or 0)
    L.append(f"--- あなたの番 (選ぶ数: {mn}〜{mc}) ---")
    for i, o in enumerate(opts):
        L.append(f"  [{i}] {_opt_label(cards, atks, obs, o)}")
    if mc > 1:
        L.append(f"（複数選ぶ場合はカンマ区切り。例: 0,2）")
    return "\n".join(L), len(opts), mc, mn


def _write_state(seq, over, text, nopt=0, mc=1, mn=0, winner=None):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"seq": seq, "over": over, "text": text, "nopt": nopt,
                   "maxCount": mc, "minCount": mn, "winner": winner}, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def _wait_move(seq, nopt, mc, mn, timeout=3600):
    """MOVE_FILE から SEQ:idx... を待つ。妥当性検証して index list を返す。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if os.path.exists(MOVE_FILE):
                for line in reversed(open(MOVE_FILE).read().splitlines()):
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    s, rest = line.split(":", 1)
                    if s.strip() != str(seq):
                        continue
                    try:
                        idxs = [int(x) for x in rest.replace("、", ",").split(",") if x.strip() != ""]
                    except ValueError:
                        continue
                    idxs = [i for i in idxs if 0 <= i < nopt]
                    idxs = list(dict.fromkeys(idxs))  # dedup, keep order
                    if len(idxs) < max(1, mn) or len(idxs) > mc:
                        continue
                    return idxs
        except Exception:
            pass
        time.sleep(0.4)
    return list(range(min(max(mc, mn if mn > 0 else 1), nopt)))  # フォールバック


def main():
    _ensure_engine_on_path()
    import cg.game as game
    from cg.sim import Battle, lib
    cards, atks = _load_tables()

    opp_name = sys.argv[1] if len(sys.argv) > 1 else "archaludon"
    human_name = sys.argv[2] if len(sys.argv) > 2 else "archaludon"
    here = os.path.join(os.path.dirname(__file__), "..", "submissions", OPP_FILE.get(opp_name, OPP_FILE["archaludon"]))
    spec = importlib.util.spec_from_file_location("opp", here)
    oppmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(oppmod)
    opp_agent = oppmod.agent
    human_deck = DECKS.get(human_name, DECKS["archaludon"])
    opp_deck = DECKS.get(opp_name, DECKS["archaludon"])

    # reset IPC files
    open(MOVE_FILE, "w").close()

    obs, _ = game.battle_start(list(human_deck), list(opp_deck))
    seq = 0
    try:
        while True:
            cur = obs.get("current")
            if cur is not None and cur.get("result", -1) != -1:
                res = cur.get("result")
                who = "あなたの勝ち！" if res == 0 else ("相手(AI)の勝ち…" if res == 1 else "引き分け")
                _write_state(seq, True, f"===== 対戦終了: {who} =====", winner=res)
                return
            serial = lib.GetBattleData(Battle.battle_ptr)
            acting = int(serial.selectPlayer)
            if acting == 1:  # 相手=AI
                obs = game.battle_select(opp_agent(obs))
                continue
            # 人間(P0)の手番
            sel = obs.get("select")
            if sel is None:
                # デッキ選択フェーズ等: 人間側も自動で自デッキ
                obs = game.battle_select(list(human_deck))
                continue
            opts0 = sel.get("option") or []
            if len(opts0) == 0:
                obs = game.battle_select([]); continue
            # 強制手(選択肢1つ)は自動で進めて手間を減らす
            if len(opts0) == 1 and int(sel.get("maxCount", 1) or 1) >= 1:
                obs = game.battle_select([0]); continue
            seq += 1
            text, nopt, mc, mn = render(cards, atks, obs, seq)
            _write_state(seq, False, text, nopt, mc, mn)
            idxs = _wait_move(seq, nopt, mc, mn)
            obs = game.battle_select(idxs)
    finally:
        try:
            game.battle_finish()
        except Exception:
            pass


if __name__ == "__main__":
    main()
