"""本物のエンジンで1試合を記録し、自己完結の対戦リプレイHTML(盤面GUI+ログ+prev/next/autoplay)を生成。"""
import os, sys, json, importlib.util
sys.path.insert(0, os.getcwd())
from eval.engine_driver import _ensure_engine_on_path, play_game
import eval.search_agent as SA
import eval.state_eval as SE
_ensure_engine_on_path()
import cg.api as api
cards={c.cardId:c for c in api.all_card_data()}
atks={a.attackId:a for a in api.all_attack()}
def nm(cid): 
    c=cards.get(cid); return getattr(c,"name",str(cid)) if c else str(cid)
def pk(p):
    if p is None: return None
    cd=cards.get(p.get("id"))
    return {"name":nm(p.get("id")),"hp":p.get("hp"),"maxHp":p.get("maxHp"),
            "e":len(p.get("energies") or []),"tools":len(p.get("tools") or []),
            "ex":bool(getattr(cd,"ex",False) or getattr(cd,"megaEx",False)) if cd else False}
def side(pl):
    a=(pl.get("active") or [None]); 
    return {"prize":len(pl.get("prize") or []),"deck":pl.get("deckCount"),"hand":pl.get("handCount"),
            "active":pk(a[0] if a else None),"bench":[pk(x) for x in (pl.get("bench") or []) if x]}
NAMES=sys.argv[1:3] if len(sys.argv)>2 else ["Archaludon","MegaStarmie"]
DECKS={
 "Archaludon":[169]*4+[190]*4+[666]*4+[1244]*4+[8]*13+[1152]*4+[1121]*4+[1122]*4+[1097]*4+[1197]*3+[1147]*2+[1159]*1+[1182]*1+[1185]*4+[1227]*4,
 "MegaStarmie":[3]*9+[17]*4+[666]*4+[1030]*3+[1031]*3+[1086]*4+[1097]*2+[1120]*4+[1121]*1+[1122]*4+[1145]*4+[1159]*1+[1182]*1+[1189]*4+[1223]*2+[1225]*2+[1227]*4+[1229]*4,
}
d0=DECKS[NAMES[0]]; d1=DECKS[NAMES[1]]
SUBS={"Archaludon":"archaludon_search_agent.py","MegaStarmie":"megastarmie_search_agent.py"}
def load(name):
    p=os.path.join("submissions",SUBS[name]); s=importlib.util.spec_from_file_location("a",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m.agent
a0=load(NAMES[0]); a1=load(NAMES[1])
frames=[]; log=[]; state={"lastturn":-1,"pz":[None,None]}
def obs_hook(cur, acting):
    if cur is None: return
    ps=cur.get("players") or []
    if len(ps)<2: return
    t=cur.get("turn"); pz=[len((ps[i] or {}).get("prize") or []) for i in (0,1)]
    note=None
    if t!=state["lastturn"]:
        actor=NAMES[cur.get("yourIndex",0)] if False else None
        note=f"ターン{t} 開始"; state["lastturn"]=t
    if state["pz"]!=[None,None] and pz!=state["pz"]:
        for i in (0,1):
            if state["pz"][i] is not None and pz[i]<state["pz"][i]:
                log.append(f"⚔ {NAMES[i]} がサイドを取った（残り{pz[i]}）")
        note=note or "サイド取得"
    state["pz"]=pz
    if note:
        log.append(f"— {note} —" if "開始" in note else note)
        frames.append({"turn":t,"note":note,"p0":side(ps[0]),"p1":side(ps[1]),
                       "p0pz":pz[0],"p1pz":pz[1],"log":list(log[-16:])})
r=play_game(a0,a1,deck0=list(d0),deck1=list(d1),observer=obs_hook)
res={0:f"{NAMES[0]} の勝ち",1:f"{NAMES[1]} の勝ち",2:"引き分け"}[r]
log.append(f"🏆 試合終了: {res}")
# capture final
frames.append({"turn":frames[-1]["turn"] if frames else 0,"note":"試合終了","p0":frames[-1]["p0"] if frames else None,
               "p1":frames[-1]["p1"] if frames else None,"p0pz":state["pz"][0],"p1pz":state["pz"][1],
               "log":list(log[-16:]),"final":res})
open("/tmp/frames.json","w").write(json.dumps({"names":NAMES,"result":res,"frames":frames},ensure_ascii=False))
print(f"frames={len(frames)} result={res}")
