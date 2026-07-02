import json
d=json.load(open("/tmp/frames.json"))
names=d["names"]; frames=d["frames"]; result=d["result"]
DATA=json.dumps(d,ensure_ascii=False)
html='''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PTCG 対戦リプレイ</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font-family:system-ui,'Segoe UI',sans-serif;background:radial-gradient(circle at 50% 25%,#1c3a2e,#0b1a14);color:#eaf3ee;padding:10px}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:16px;margin:4px 0 8px;text-align:center;color:#cfe}
.side{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:10px;margin:8px 0}
.side.opp{border-top:3px solid #d9534f}.side.me{border-bottom:3px solid #4a90d9}
.hdr{display:flex;gap:14px;font-size:13px;color:#b8ccc2;flex-wrap:wrap;align-items:center}.hdr b{color:#fff}
.row{display:flex;gap:10px;align-items:flex-start;margin-top:8px}
.bench{display:flex;gap:6px;flex-wrap:wrap;flex:1}
.card{background:linear-gradient(160deg,#2b4a3c,#1e352b);border:1px solid rgba(255,255,255,.14);border-radius:9px;padding:7px 8px;min-width:100px;max-width:130px}
.card.big{min-width:140px;background:linear-gradient(160deg,#356048,#204034);box-shadow:0 2px 10px rgba(0,0,0,.4)}
.card.empty{opacity:.4;display:flex;align-items:center;justify-content:center;min-height:56px}
.cname{font-weight:600;font-size:13px;line-height:1.2;margin-bottom:5px}
.ex{background:#c9a227;color:#1a1a1a;border-radius:4px;font-size:10px;padding:0 4px;margin-left:4px;font-weight:700}
.hpbar{height:6px;background:#0c1913;border-radius:4px;overflow:hidden}.hpfill{height:100%;background:linear-gradient(90deg,#5cd18a,#c9d15c)}
.hptext{font-size:11px;color:#a9c0b4;margin-top:2px}.ene{font-size:12px;color:#7fd1ff;letter-spacing:1px;margin-top:3px}.tool{color:#f0c674;margin-left:6px}
.prize i{width:10px;height:14px;background:#4a90d9;border-radius:2px;display:inline-block;margin:0 1px}
.opp .prize i{background:#d9534f}
h3{margin:2px 0 0;font-size:11px;color:#87a396;text-transform:uppercase;letter-spacing:1px}
.ctrl{display:flex;gap:8px;align-items:center;justify-content:center;margin:10px 0;flex-wrap:wrap}
button{background:#25406f;color:#fff;border:0;border-radius:8px;padding:8px 14px;font-size:15px;cursor:pointer;font-weight:600}
button:disabled{opacity:.4}
#slider{flex:1;min-width:160px}
.note{text-align:center;color:#cfe;font-size:14px;margin:6px 0;min-height:20px}
.banner{background:#c9a227;color:#1a1a1a;font-weight:800;font-size:20px;text-align:center;padding:12px;border-radius:10px;margin:8px 0}
.logbox{background:#0c1913;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12px;color:#9fb8ac;max-height:150px;overflow:auto}
</style></head><body><div class="wrap">
<h1>🎮 PTCG 対戦リプレイ ／ 青:'''+names[0]+''' vs 赤:'''+names[1]+'''</h1>
<div id="banner"></div>
<div class="note" id="note"></div>
<div class="side opp"><div class="hdr"><span>🔴 <b>'''+names[1]+'''</b>(AI)</span>
 <span>サイド残 <span class="prize" id="oprize"></span></span><span>手札 <b id="ohand"></b></span><span>山 <b id="odeck"></b></span></div>
 <div class="row"><div><h3>アクティブ</h3><div id="oactive"></div></div><div style="flex:1"><h3>ベンチ</h3><div class="bench" id="obench"></div></div></div></div>
<div class="ctrl">
 <button id="first">⏮</button><button id="prev">◀ 前</button>
 <button id="play">▶ 自動</button><button id="next">次 ▶</button><button id="last">⏭</button>
 <input type="range" id="slider" min="0" value="0"><span id="counter"></span></div>
<div class="side me"><div class="hdr"><span>🔵 <b>'''+names[0]+'''</b></span>
 <span>サイド残 <span class="prize" id="mprize"></span></span><span>手札 <b id="mhand"></b></span><span>山 <b id="mdeck"></b></span></div>
 <div class="row"><div><h3>アクティブ</h3><div id="mactive"></div></div><div style="flex:1"><h3>ベンチ</h3><div class="bench" id="mbench"></div></div></div></div>
<div class="logbox" id="log"></div>
</div>
<script>
const D=__DATA__;const F=D.frames;let idx=0,timer=null;
function cardHTML(p,big){if(!p)return '<div class="card empty">―</div>';
 let hpr=p.maxHp?Math.max(0,Math.min(100,Math.round(100*(p.hp||0)/p.maxHp))):0;
 let pips='●'.repeat(Math.min(p.e,6))+(p.e>6?'+':'');
 return `<div class="card ${big?'big':''}"><div class="cname">${p.name}${p.ex?'<span class="ex">ex</span>':''}</div>
 <div class="hpbar"><div class="hpfill" style="width:${hpr}%"></div></div>
 <div class="hptext">HP ${p.hp}/${p.maxHp}</div><div class="ene">${pips||'－'}${p.tools?' 🔧'+p.tools:''}</div></div>`;}
function prizeHTML(n){return '<i></i>'.repeat(n)+' '+n;}
function render(){const f=F[idx];if(!f)return;
 document.getElementById('note').textContent=(f.note?('▶ '+f.note):'')+`（ターン${f.turn}）`;
 const o=f.p1,m=f.p0;
 if(o){document.getElementById('oactive').innerHTML=cardHTML(o.active,true);
  document.getElementById('obench').innerHTML=(o.bench&&o.bench.length)?o.bench.map(x=>cardHTML(x)).join(''):'<div class="card empty">なし</div>';
  document.getElementById('oprize').innerHTML=prizeHTML(f.p1pz);document.getElementById('ohand').textContent=o.hand;document.getElementById('odeck').textContent=o.deck;}
 if(m){document.getElementById('mactive').innerHTML=cardHTML(m.active,true);
  document.getElementById('mbench').innerHTML=(m.bench&&m.bench.length)?m.bench.map(x=>cardHTML(x)).join(''):'<div class="card empty">なし</div>';
  document.getElementById('mprize').innerHTML=prizeHTML(f.p0pz);document.getElementById('mhand').textContent=m.hand;document.getElementById('mdeck').textContent=m.deck;}
 document.getElementById('log').innerHTML=(f.log||[]).map(x=>`<div>${x}</div>`).join('');
 document.getElementById('banner').innerHTML=f.final?`<div class="banner">🏆 ${f.final}</div>`:'';
 document.getElementById('counter').textContent=`${idx+1}/${F.length}`;
 document.getElementById('slider').value=idx;
 document.getElementById('prev').disabled=idx==0;document.getElementById('first').disabled=idx==0;
 document.getElementById('next').disabled=idx==F.length-1;document.getElementById('last').disabled=idx==F.length-1;}
function go(i){idx=Math.max(0,Math.min(F.length-1,i));render();}
document.getElementById('next').onclick=()=>go(idx+1);document.getElementById('prev').onclick=()=>go(idx-1);
document.getElementById('first').onclick=()=>go(0);document.getElementById('last').onclick=()=>go(F.length-1);
document.getElementById('slider').max=F.length-1;document.getElementById('slider').oninput=e=>go(+e.target.value);
document.getElementById('play').onclick=function(){if(timer){clearInterval(timer);timer=null;this.textContent='▶ 自動';return;}
 this.textContent='⏸ 停止';timer=setInterval(()=>{if(idx>=F.length-1){clearInterval(timer);timer=null;document.getElementById('play').textContent='▶ 自動';return;}go(idx+1);},1100);};
render();
</script></body></html>'''
html=html.replace("__DATA__",DATA)
open("/tmp/ptcg_replay.html","w").write(html)
print("viewer bytes:",len(html))
