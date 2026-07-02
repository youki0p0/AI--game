"""ローカルWeb対戦アプリ: ブラウザでクリック操作して提出エージェント(本物のエンジン)と対戦する。

使い方(engineを置いたローカルPCで):
    cd pokemon-tcg-ai-battle
    python eval/play_server.py            # 既定: あなた=Archaludon vs AI=Archaludon探索版
    # ブラウザで http://localhost:8000 を開く
    python eval/play_server.py --port 8000 --human archaludon --opp megastarmie

依存: Python標準ライブラリのみ(Flask不要) + CABTエンジン(engine/)。全手番は logs/play-*.jsonl に保存。
ブラウザ内ではエンジンは動かせないため、サーバ側で本物のエンジン+AIが応答し、盤面をGUI描画する。
"""
from __future__ import annotations
import argparse, json, os, sys, time, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.engine_driver import _ensure_engine_on_path  # noqa: E402
from eval import board_html as BH  # noqa: E402

_ensure_engine_on_path()  # cg エンジンを import 可能にする(以降の import cg.* のため)

DECKS = {
 "archaludon": [169]*4+[190]*4+[666]*4+[1244]*4+[8]*13+[1152]*4+[1121]*4+[1122]*4+[1097]*4+[1197]*3+[1147]*2+[1159]*1+[1182]*1+[1185]*4+[1227]*4,
 "grimmsnarl": [646]*4+[647]*3+[648]*3+[112]*4+[305]*3+[66]*2+[649]*1+[1086]*4+[1152]*4+[1079]*3+[1097]*2+[1119]*1+[1139]*1+[1159]*1+[1227]*4+[1231]*4+[1197]*2+[1259]*4+[7]*10,
 "megastarmie": [3]*9+[17]*4+[666]*4+[1030]*3+[1031]*3+[1086]*4+[1097]*2+[1120]*4+[1121]*1+[1122]*4+[1145]*4+[1159]*1+[1182]*1+[1189]*4+[1223]*2+[1225]*2+[1227]*4+[1229]*4,
}
OPP_FILE = {"archaludon": "archaludon_search_agent.py", "megastarmie": "megastarmie_search_agent.py"}

STATE = {"obs": None, "over": False, "winner": None, "log": [], "prev_pz": [None, None],
         "cards": None, "atks": None, "opp_agent": None, "human_deck": None, "opp_deck": None,
         "logfile": None, "seq": 0}


def _load_agent(name):
    here = os.path.join(os.path.dirname(__file__), "..", "submissions", OPP_FILE.get(name, OPP_FILE["archaludon"]))
    spec = importlib.util.spec_from_file_location("opp", here)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.agent


def _tables():
    import cg.api as api
    return {c.cardId: c for c in api.all_card_data()}, {a.attackId: a for a in api.all_attack()}


def _prizes(o):
    cur = o.get("current") or {}; ps = cur.get("players") or []
    return [len((ps[i] or {}).get("prize") or []) for i in range(2)] if len(ps) >= 2 else [None, None]


def _log_line(s):
    STATE["log"].append(s)
    if STATE["logfile"]:
        try:
            with open(STATE["logfile"], "a") as f:
                f.write(json.dumps({"t": "log", "msg": s}, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _attack_note(obs, idxs, who):
    sel = obs.get("select") or {}; opts = sel.get("option") or []
    for i in (idxs or []):
        if 0 <= i < len(opts) and opts[i].get("type") == 13:
            a = STATE["atks"].get(opts[i].get("attackId"))
            return f"{who}：こうげき「{getattr(a,'name','?') if a else '?'}」(ダメ{getattr(a,'damage',0) if a else 0})"
    return None


def _advance_to_human():
    """AI手番・強制手を自動で進め、人間の実選択 or 終局で止める。"""
    import cg.game as game
    from cg.sim import Battle, lib
    obs = STATE["obs"]
    for _ in range(100000):
        cur = obs.get("current")
        pz = _prizes(obs)
        if STATE["prev_pz"] != [None, None] and pz != STATE["prev_pz"]:
            for i in (0, 1):
                if STATE["prev_pz"][i] is not None and pz[i] is not None and pz[i] < STATE["prev_pz"][i]:
                    _log_line(f"⚔ {'あなた' if i==0 else 'AI'} がサイドを取った（残り{pz[i]}）")
        STATE["prev_pz"] = pz
        if cur is not None and cur.get("result", -1) != -1:
            STATE["over"] = True; STATE["winner"] = cur.get("result")
            _log_line(f"🏆 試合終了: {'あなたの勝ち' if STATE['winner']==0 else ('AIの勝ち' if STATE['winner']==1 else '引き分け')}")
            STATE["obs"] = obs; return
        acting = int(lib.GetBattleData(Battle.battle_ptr).selectPlayer)
        if acting == 1:
            act = STATE["opp_agent"](obs)
            note = _attack_note(obs, act if isinstance(act, list) else [], "AI")
            if note:
                _log_line(note)
            obs = game.battle_select(act); continue
        sel = obs.get("select")
        if sel is None:
            obs = game.battle_select(list(STATE["human_deck"])); continue
        opts = sel.get("option") or []
        if len(opts) == 0:
            obs = game.battle_select([]); continue
        if len(opts) == 1 and int(sel.get("maxCount", 1) or 1) >= 1:
            obs = game.battle_select([0]); continue
        STATE["obs"] = obs; return  # 人間の実選択で停止
    STATE["obs"] = obs


def _new_game(human, opp):
    import cg.game as game
    try:
        game.battle_finish()
    except Exception:
        pass
    _ensure_engine_on_path()
    if STATE["cards"] is None:
        STATE["cards"], STATE["atks"] = _tables()
    STATE["human_deck"] = DECKS.get(human, DECKS["archaludon"])
    STATE["opp_deck"] = DECKS.get(opp, DECKS["archaludon"])
    STATE["opp_agent"] = _load_agent(opp)
    STATE["log"] = []; STATE["over"] = False; STATE["winner"] = None; STATE["prev_pz"] = [None, None]; STATE["seq"] = 0
    os.makedirs("logs", exist_ok=True)
    STATE["logfile"] = os.path.join("logs", f"play-{human}-vs-{opp}-{int(time.time())}.jsonl")
    obs, _ = game.battle_start(list(STATE["human_deck"]), list(STATE["opp_deck"]))
    STATE["obs"] = obs
    _log_line(f"新規対戦: あなた={human} / AI={opp}")
    _advance_to_human()


def _current_state_json():
    obs = STATE["obs"]
    STATE["seq"] += 1
    d = BH.board_data(STATE["cards"], STATE["atks"], obs, STATE["seq"], STATE["log"])
    d["over"] = STATE["over"]; d["winner"] = STATE["winner"]
    if STATE["logfile"]:
        d["logfile"] = STATE["logfile"]
    return d


def _apply_move(idxs):
    import cg.game as game
    obs = STATE["obs"]
    sel = obs.get("select") or {}
    opts = sel.get("option") or []
    mc = int(sel.get("maxCount", 1) or 1); mn = int(sel.get("minCount", 0) or 0)
    idxs = [i for i in idxs if isinstance(i, int) and 0 <= i < len(opts)]
    idxs = list(dict.fromkeys(idxs))
    if len(idxs) < max(1, mn) or len(idxs) > mc:
        idxs = list(range(min(max(mc, mn if mn > 0 else 1), len(opts))))
    note = _attack_note(obs, idxs, "あなた")
    if note:
        _log_line(note)
    else:
        try:
            d = BH.board_data(STATE["cards"], STATE["atks"], obs, 0, [])
            _log_line("あなた：" + (d["options"][idxs[0]]["label"] if idxs and idxs[0] < len(d["options"]) else str(idxs)))
        except Exception:
            pass
    if STATE["logfile"]:
        with open(STATE["logfile"], "a") as f:
            f.write(json.dumps({"t": "move", "idxs": idxs}, ensure_ascii=False) + "\n")
    STATE["obs"] = game.battle_select(idxs)
    _advance_to_human()


PAGE = """<!doctype html><html lang=ja><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>PTCG 対戦</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font-family:system-ui,'Segoe UI',sans-serif;background:radial-gradient(circle at 50% 25%,#1c3a2e,#0b1a14);color:#eaf3ee;padding:10px}
.wrap{max-width:860px;margin:0 auto}h1{font-size:16px;text-align:center;margin:4px 0}
.bar{display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap;margin:6px 0}
select,button{background:#25406f;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-size:14px;cursor:pointer}
.side{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:10px;margin:8px 0}
.side.opp{border-top:3px solid #d9534f}.side.me{border-bottom:3px solid #4a90d9}
.hdr{display:flex;gap:14px;font-size:13px;color:#b8ccc2;flex-wrap:wrap}.hdr b{color:#fff}
.row{display:flex;gap:10px;margin-top:8px}.bench{display:flex;gap:6px;flex-wrap:wrap;flex:1}
.card{background:linear-gradient(160deg,#2b4a3c,#1e352b);border:1px solid rgba(255,255,255,.14);border-radius:9px;padding:7px 8px;min-width:100px;max-width:130px}
.card.big{min-width:140px;background:linear-gradient(160deg,#356048,#204034)}
.card.empty{opacity:.4;display:flex;align-items:center;justify-content:center;min-height:56px}
.cname{font-weight:600;font-size:13px;margin-bottom:5px}.ex{background:#c9a227;color:#1a1a1a;border-radius:4px;font-size:10px;padding:0 4px;margin-left:4px;font-weight:700}
.hpbar{height:6px;background:#0c1913;border-radius:4px;overflow:hidden}.hpfill{height:100%;background:linear-gradient(90deg,#5cd18a,#c9d15c)}
.hptext{font-size:11px;color:#a9c0b4;margin-top:2px}.ene{font-size:12px;color:#7fd1ff;margin-top:3px}
.prize i{width:10px;height:14px;background:#4a90d9;border-radius:2px;display:inline-block;margin:0 1px}.opp .prize i{background:#d9534f}
.hand{font-size:12px;margin-top:6px}.hand span{background:rgba(255,255,255,.08);border-radius:5px;padding:2px 6px;margin:0 2px;display:inline-block}
h3{margin:2px 0 0;font-size:11px;color:#87a396;text-transform:uppercase}
.opts{background:#12241c;border:1px solid #2c4a3b;border-radius:12px;padding:10px;margin-top:8px}
.obtn{display:block;width:100%;text-align:left;background:#1d3550;margin:5px 0;padding:9px 12px;font-size:15px;border-radius:8px}
.obtn.sel{background:#c9a227;color:#1a1a1a;font-weight:700}
.prompt{background:#25406f;border-radius:8px;padding:8px;margin-top:8px;text-align:center;font-weight:600}
.banner{background:#c9a227;color:#1a1a1a;font-weight:800;font-size:20px;text-align:center;padding:12px;border-radius:10px;margin:8px 0}
.logbox{background:#0c1913;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12px;color:#9fb8ac;max-height:150px;overflow:auto}
.note{text-align:center;color:#cfe;font-size:13px;margin:4px 0}
</style></head><body><div class=wrap>
<h1>🎮 PTCG 対戦（あなた=青 vs AI=赤）</h1>
<div class=bar>
 あなた:<select id=human><option value=archaludon>Archaludon</option><option value=grimmsnarl>Grimmsnarl</option><option value=megastarmie>MegaStarmie</option></select>
 AI:<select id=opp><option value=archaludon>Archaludon(探索)</option><option value=megastarmie>MegaStarmie(探索)</option></select>
 <button onclick=newGame()>新しい試合</button>
 <a id=dl href=# download style="text-decoration:none"><button>ログDL</button></a>
</div>
<div id=banner></div><div class=note id=note></div>
<div class="side opp"><div class=hdr><span>🔴 <b>AI</b></span><span>サイド <span class="prize" id=oprize></span></span><span>手札 <b id=ohand></b></span><span>山 <b id=odeck></b></span></div>
 <div class=row><div><h3>アクティブ</h3><div id=oactive></div></div><div style=flex:1><h3>ベンチ</h3><div class=bench id=obench></div></div></div></div>
<div class="side me"><div class=hdr><span>🔵 <b>あなた</b></span><span>サイド <span class="prize" id=mprize></span></span><span>山 <b id=mdeck></b></span></div>
 <div class=row><div><h3>アクティブ</h3><div id=mactive></div></div><div style=flex:1><h3>ベンチ</h3><div class=bench id=mbench></div></div></div>
 <div class=hand><h3>手札</h3><div id=mhandlist></div></div></div>
<div class=opts><h3>選択肢（クリックで選ぶ）</h3><div id=opts></div><div id=submit></div></div>
<div class=logbox id=log></div>
<div class=bar style="margin-top:8px"><button onclick=copyLog()>📋 棋譜をコピー</button><span id=copied style="color:#5cd18a;font-size:12px"></span></div>
<textarea id=kifu readonly placeholder="棋譜（ここを全選択してコピペ可）"
 style="width:100%;height:130px;background:#0c1913;color:#cfe3d9;border:1px solid #2c4a3b;border-radius:8px;font-size:12px;padding:8px;font-family:monospace"></textarea>
</div>
<script>
let S=null,sel=new Set();
function cardHTML(p,big){if(!p)return '<div class="card empty">―</div>';
 let hpr=p.maxHp?Math.max(0,Math.min(100,Math.round(100*(p.hp||0)/p.maxHp))):0;
 let pips='●'.repeat(Math.min(p.energy,6))+(p.energy>6?'+':'');
 return `<div class="card ${big?'big':''}"><div class=cname>${p.name}${p.ex?'<span class=ex>ex</span>':''}</div>
 <div class=hpbar><div class=hpfill style="width:${hpr}%"></div></div><div class=hptext>HP ${p.hp}/${p.maxHp}</div>
 <div class=ene>${pips||'－'}${p.tools?' 🔧'+p.tools:''}</div></div>`;}
function pr(n){return '<i></i>'.repeat(n)+' '+n;}
function render(){const d=S;if(!d)return;sel=new Set();
 document.getElementById('note').textContent=`ターン ${d.turn}`;
 const o=d.opp,m=d.me;
 document.getElementById('oactive').innerHTML=cardHTML(o.active,true);
 document.getElementById('obench').innerHTML=o.bench.length?o.bench.map(x=>cardHTML(x)).join(''):'<div class="card empty">なし</div>';
 document.getElementById('oprize').innerHTML=pr(o.prize);document.getElementById('ohand').textContent=o.handCount;document.getElementById('odeck').textContent=o.deck;
 document.getElementById('mactive').innerHTML=cardHTML(m.active,true);
 document.getElementById('mbench').innerHTML=m.bench.length?m.bench.map(x=>cardHTML(x)).join(''):'<div class="card empty">なし</div>';
 document.getElementById('mprize').innerHTML=pr(m.prize);document.getElementById('mdeck').textContent=m.deck;
 document.getElementById('mhandlist').innerHTML=m.hand.length?m.hand.map(n=>`<span>${n}</span>`).join(''):'（なし）';
 document.getElementById('log').innerHTML=(d.log||[]).map(x=>`<div>${x}</div>`).join('');
 document.getElementById('log').scrollTop=1e9;
 document.getElementById('kifu').value=`# PTCG棋譜 あなた=${document.getElementById('human').value} vs AI=${document.getElementById('opp').value}\n`+(d.log||[]).join('\n');
 if(d.logfile)document.getElementById('dl').href='/log';
 const bn=document.getElementById('banner');const op=document.getElementById('opts');const sb=document.getElementById('submit');
 if(d.over){bn.innerHTML=`<div class=banner>${d.winner==0?'🏆 あなたの勝ち！':(d.winner==1?'💀 AIの勝ち…':'引き分け')}</div>`;op.innerHTML='';sb.innerHTML='';return;}
 bn.innerHTML='';
 op.innerHTML=d.options.map(o=>`<button class=obtn data-i="${o.i}" onclick="pick(${o.i})"><b>[${o.i}]</b> ${o.label}</button>`).join('');
 sb.innerHTML = d.maxCount>1 ? `<div class=prompt>${d.minCount}〜${d.maxCount}個選んで <button onclick=commit()>決定</button></div>` : '<div class=prompt>クリックで即実行（単一選択）</div>';
}
function pick(i){if(S.maxCount<=1){move([i]);return;}
 if(sel.has(i))sel.delete(i);else if(sel.size<S.maxCount)sel.add(i);
 document.querySelectorAll('.obtn').forEach(b=>{b.classList.toggle('sel',sel.has(+b.dataset.i));});}
function commit(){if(sel.size<Math.max(1,S.minCount)){alert('選ぶ数が足りません');return;}move([...sel]);}
async function move(idxs){const r=await fetch('/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idxs})});S=await r.json();render();}
function copyLog(){const t=document.getElementById('kifu');t.select();t.setSelectionRange(0,99999);
 const done=()=>{document.getElementById('copied').textContent=' コピーしました！';setTimeout(()=>document.getElementById('copied').textContent='',2000);};
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t.value).then(done,()=>{try{document.execCommand('copy');done();}catch(e){}});}
 else{try{document.execCommand('copy');done();}catch(e){}}}
async function newGame(){const h=document.getElementById('human').value,o=document.getElementById('opp').value;
 const r=await fetch('/new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({human:h,opp:o})});S=await r.json();render();}
newGame();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/state":
            return self._send(200, json.dumps(_current_state_json(), ensure_ascii=False))
        if self.path == "/log":
            try:
                data = open(STATE["logfile"], "rb").read()
                self.send_response(200); self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(STATE["logfile"])}"')
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            except Exception:
                return self._send(404, "{}")
        return self._send(404, "{}")

    def do_POST(self):
        try:
            if self.path == "/new":
                b = self._body(); _new_game(b.get("human", "archaludon"), b.get("opp", "archaludon"))
                return self._send(200, json.dumps(_current_state_json(), ensure_ascii=False))
            if self.path == "/move":
                b = self._body(); _apply_move(b.get("idxs", []))
                return self._send(200, json.dumps(_current_state_json(), ensure_ascii=False))
        except Exception as e:
            return self._send(200, json.dumps({"over": False, "error": str(e),
                              "turn": 0, "me": {"prize": 0, "deck": 0, "hand": [], "active": None, "bench": []},
                              "opp": {"prize": 0, "deck": 0, "handCount": 0, "active": None, "bench": []},
                              "options": [], "maxCount": 1, "minCount": 0, "log": ["エラー: " + str(e)]}, ensure_ascii=False))
        return self._send(404, "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--human", default="archaludon")
    ap.add_argument("--opp", default="archaludon")
    a = ap.parse_args()
    _new_game(a.human, a.opp)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"▶ 対戦サーバ起動: http://localhost:{a.port}  (Ctrl+Cで終了)")
    print(f"  あなた={a.human} vs AI={a.opp} / ログ: {STATE['logfile']}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n終了")


if __name__ == "__main__":
    main()
