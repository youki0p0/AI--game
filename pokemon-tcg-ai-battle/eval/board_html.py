"""観測(obs)を『ポケカ風GUI盤面HTML』に描画する。human_game から使う。"""
from __future__ import annotations

OPT = {1: "はい", 2: "いいえ", 7: "出す/使う", 8: "エネ付け", 9: "進化", 10: "特性",
       11: "トラッシュ", 12: "にげる", 13: "こうげき", 14: "ターン終了"}
AREA = {4: "アクティブ", 5: "ベンチ"}


def _nm(cards, cid):
    c = cards.get(cid)
    return getattr(c, "name", str(cid)) if c else str(cid)


def _pk(cards, atks, p):
    if p is None:
        return None
    cd = cards.get(p.get("id"))
    return {
        "name": _nm(cards, p.get("id")),
        "hp": p.get("hp"), "maxHp": p.get("maxHp"),
        "energy": len(p.get("energies") or []),
        "tools": len(p.get("tools") or []),
        "ex": bool(getattr(cd, "ex", False) or getattr(cd, "megaEx", False)) if cd else False,
    }


def opt_label(cards, atks, obs, o):
    t = o.get("type"); base = OPT.get(t, f"type{t}")
    cur = obs.get("current") or {}; me = cur.get("yourIndex", 0)
    players = cur.get("players") or []; mp = players[me] if len(players) > me else {}
    if t in (7, 9):
        idx = o.get("index"); hand = mp.get("hand") or []
        if idx is not None and 0 <= idx < len(hand):
            return f"{base}: {_nm(cards, hand[idx].get('id'))}"
    if t == 8:
        ar = o.get("inPlayArea"); ii = o.get("inPlayIndex")
        arr = mp.get("active") if ar == 4 else (mp.get("bench") if ar == 5 else None)
        tgt = arr[ii] if (isinstance(arr, list) and ii is not None and 0 <= ii < len(arr)) else None
        return f"{base}→{AREA.get(ar,'?')} {_nm(cards, tgt.get('id')) if tgt else ''}"
    if t == 13:
        a = atks.get(o.get("attackId"))
        if a:
            return f"{base}: {getattr(a,'name','')} (ダメ{getattr(a,'damage',0)})"
    if o.get("cardId") is not None:
        return f"{base}: {_nm(cards, o.get('cardId'))}"
    return base


def board_data(cards, atks, obs, seq, log):
    cur = obs.get("current") or {}; sel = obs.get("select") or {}
    me = cur.get("yourIndex", 0); players = cur.get("players") or []
    mp = players[me] if len(players) > me else {}
    op = players[1 - me] if len(players) > 1 - me else {}
    opts = sel.get("option") or []
    ma = (mp.get("active") or [None]); oa = (op.get("active") or [None])
    return {
        "seq": seq, "turn": cur.get("turn"), "over": False, "winner": None,
        "me": {
            "prize": len(mp.get("prize") or []), "deck": mp.get("deckCount"),
            "hand": [_nm(cards, c.get("id")) for c in (mp.get("hand") or [])],
            "active": _pk(cards, atks, ma[0] if ma else None),
            "bench": [_pk(cards, atks, p) for p in (mp.get("bench") or []) if p],
        },
        "opp": {
            "prize": len(op.get("prize") or []), "deck": op.get("deckCount"), "handCount": op.get("handCount"),
            "active": _pk(cards, atks, oa[0] if oa else None),
            "bench": [_pk(cards, atks, p) for p in (op.get("bench") or []) if p],
        },
        "options": [{"i": i, "label": opt_label(cards, atks, obs, o)} for i, o in enumerate(opts)],
        "maxCount": int(sel.get("maxCount", 1) or 1), "minCount": int(sel.get("minCount", 0) or 0),
        "log": log[-14:],
    }


def _card_html(pk, big=False):
    if pk is None:
        return '<div class="card empty">―</div>'
    hpr = 0
    if pk["maxHp"]:
        hpr = max(0, min(100, round(100 * (pk["hp"] or 0) / pk["maxHp"])))
    exbadge = '<span class="ex">ex</span>' if pk["ex"] else ""
    pips = "●" * min(pk["energy"], 6) + ("+" if pk["energy"] > 6 else "")
    tool = f'<span class="tool">🔧{pk["tools"]}</span>' if pk["tools"] else ""
    cls = "card big" if big else "card"
    return f'''<div class="{cls}">
      <div class="cname">{pk["name"]}{exbadge}</div>
      <div class="hpbar"><div class="hpfill" style="width:{hpr}%"></div></div>
      <div class="hptext">HP {pk["hp"]}/{pk["maxHp"]}</div>
      <div class="ene">{pips or "－"} {tool}</div>
    </div>'''


def render_html(d):
    over = d.get("over"); winner = d.get("winner")
    def side_bench(bench):
        cells = "".join(_card_html(p) for p in bench) or '<div class="card empty">ベンチなし</div>'
        return f'<div class="bench">{cells}</div>'
    opp = d["opp"]; me = d["me"]
    opts_html = "".join(
        f'<div class="opt"><span class="oi">{o["i"]}</span> {o["label"]}</div>' for o in d.get("options", [])
    )
    banner = ""
    if over:
        msg = "🏆 あなたの勝ち！" if winner == 0 else ("💀 AIの勝ち…" if winner == 1 else "引き分け")
        banner = f'<div class="banner">{msg}</div>'
    mc = d.get("maxCount", 1); mn = d.get("minCount", 0)
    prompt = "" if over else f'<div class="prompt">あなたの番：番号を返信（{mn}〜{mc}個{"・カンマ区切り" if mc>1 else ""}）</div>'
    log_html = "".join(f"<div>{x}</div>" for x in d.get("log", []))
    hand_html = " ".join(f'<span class="h">{n}</span>' for n in me["hand"]) or "（手札なし）"
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PTCG 対戦</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:system-ui,'Segoe UI',sans-serif;background:radial-gradient(circle at 50% 30%,#1c3a2e,#0d1f18);color:#eaf3ee;padding:10px}}
.wrap{{max-width:820px;margin:0 auto}}
.side{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:10px;margin:8px 0}}
.side.opp{{border-top:3px solid #d9534f}}
.side.me{{border-bottom:3px solid #4a90d9}}
.hdr{{display:flex;gap:14px;font-size:13px;color:#b8ccc2;flex-wrap:wrap;align-items:center}}
.hdr b{{color:#fff}}
.row{{display:flex;gap:10px;align-items:flex-start;margin-top:8px}}
.activewrap{{flex:0 0 auto}}
.bench{{display:flex;gap:6px;flex-wrap:wrap;flex:1}}
.card{{background:linear-gradient(160deg,#2b4a3c,#1e352b);border:1px solid rgba(255,255,255,.14);border-radius:9px;padding:7px 8px;min-width:96px;max-width:120px}}
.card.big{{min-width:130px;background:linear-gradient(160deg,#356048,#204034);box-shadow:0 2px 10px rgba(0,0,0,.4)}}
.card.empty{{opacity:.4;display:flex;align-items:center;justify-content:center;min-height:52px}}
.cname{{font-weight:600;font-size:13px;line-height:1.2;margin-bottom:5px}}
.ex{{background:#c9a227;color:#1a1a1a;border-radius:4px;font-size:10px;padding:0 4px;margin-left:4px;font-weight:700}}
.hpbar{{height:6px;background:#0c1913;border-radius:4px;overflow:hidden}}
.hpfill{{height:100%;background:linear-gradient(90deg,#5cd18a,#c9d15c)}}
.hptext{{font-size:11px;color:#a9c0b4;margin-top:2px}}
.ene{{font-size:12px;color:#7fd1ff;letter-spacing:1px;margin-top:3px}}
.tool{{color:#f0c674;margin-left:6px}}
.prize{{display:inline-flex;gap:3px}}
.prize i{{width:10px;height:14px;background:#4a90d9;border-radius:2px;display:inline-block}}
.center{{text-align:center;font-size:13px;color:#cfe;margin:6px 0}}
.hand{{font-size:12px;color:#cfe3d9;margin-top:6px;line-height:1.7}}
.hand .h{{background:rgba(255,255,255,.08);border-radius:5px;padding:2px 6px;margin:0 2px;white-space:nowrap;display:inline-block}}
.opts{{background:#12241c;border:1px solid #2c4a3b;border-radius:12px;padding:10px;margin-top:8px}}
.opt{{padding:7px 9px;border-bottom:1px solid rgba(255,255,255,.06);font-size:14px}}
.opt:last-child{{border:0}}
.oi{{display:inline-block;min-width:26px;height:24px;line-height:24px;text-align:center;background:#4a90d9;color:#fff;border-radius:6px;font-weight:700;margin-right:8px}}
.prompt{{background:#25406f;border-radius:8px;padding:8px 10px;margin-top:8px;font-weight:600;text-align:center}}
.banner{{background:#c9a227;color:#1a1a1a;font-weight:800;font-size:20px;text-align:center;padding:12px;border-radius:10px;margin:8px 0}}
.logbox{{background:#0c1913;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12px;color:#9fb8ac;max-height:130px;overflow:auto}}
h3{{margin:2px 0 0;font-size:12px;color:#87a396;text-transform:uppercase;letter-spacing:1px}}
</style></head><body><div class="wrap">
{banner}
<div class="center">ターン {d.get("turn")} ／ あなた(青) vs AI(赤)</div>

<div class="side opp"><div class="hdr">
  <span>🔴 <b>相手AI</b></span>
  <span>サイド残 <span class="prize">{"".join("<i></i>" for _ in range(opp["prize"]))}</span> {opp["prize"]}</span>
  <span>手札 <b>{opp["handCount"]}</b></span><span>山 <b>{opp["deck"]}</b></span>
</div><div class="row">
  <div class="activewrap"><h3>アクティブ</h3>{_card_html(opp["active"], big=True)}</div>
  <div style="flex:1"><h3>ベンチ</h3>{side_bench(opp["bench"])}</div>
</div></div>

<div class="side me"><div class="hdr">
  <span>🔵 <b>あなた</b></span>
  <span>サイド残 <span class="prize">{"".join("<i></i>" for _ in range(me["prize"]))}</span> {me["prize"]}</span>
  <span>山 <b>{me["deck"]}</b></span>
</div><div class="row">
  <div class="activewrap"><h3>アクティブ</h3>{_card_html(me["active"], big=True)}</div>
  <div style="flex:1"><h3>ベンチ</h3>{side_bench(me["bench"])}</div>
</div>
<div class="hand"><h3>手札</h3>{hand_html}</div></div>

<div class="opts"><h3>選択肢</h3>{opts_html or "（自動処理中…）"}</div>
{prompt}
<div class="logbox"><h3>ログ</h3>{log_html}</div>
</div></body></html>'''
