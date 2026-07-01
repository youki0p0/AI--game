# 提出（submissions）

## fire_single_agent.py — Fire 単サイド（現行の提出候補）

自己完結の単一ファイルエージェント。`cg.api` 以外を import せず、Kaggle サンドボックスで
そのまま動く。`agent(obs_dict) -> list[int]` を公開し、デッキ選択フェーズ
（`select is None`）では 60 枚の cardId 配列を返す。

### デッキ
Fire 単サイド（全非ex・弱点炎アグロ）。18 Pokémon / 30 Trainer / 12 Energy。
- アタッカー: Victini(240) / Volcanion(260) / Ho-Oh / Turtonator / Ogerpon（数値は弱点×2打点）
- 安定トレーナー30枚（engine 安全カードのみ）＋ 基本炎エネルギー12

### 実測勝率（先後入替）
| 相手 | 勝率 |
|---|---|
| Buddy（サンプル/Mega Lucario ex）| 0.66 |
| Archaludon（現環境/ブリジュラスex）| 0.515（互角）|
| Crustle（Day-1 #1 壁）| 0.015（苦手）|

詳細は `../docs/meta-crustle-archaludon.md`。

### 提出方法（Kaggle CABT）
`fire_single_agent.py` をそのまま提出物のエントリにする。`agent` 関数が呼ばれる。
デッキは pickle 不要でファイル内にリテラル定義（`FIRE_DECK`）。

### ローカル検証
```bash
cd pokemon-tcg-ai-battle
python - <<'PY'
import importlib.util, pickle
from eval.engine_driver import _ensure_engine_on_path, _get_engine_dir, play_game
_ensure_engine_on_path()
spec = importlib.util.spec_from_file_location("sub", "submissions/fire_single_agent.py")
sub = importlib.util.module_from_spec(spec); spec.loader.exec_module(sub)
from eval.agents_buddy import load_buddy_agent
bd = list(pickle.load(open(_get_engine_dir()/"deck.pkl","rb")))
w = sum(1 for g in range(50) if play_game(sub.agent, load_buddy_agent(), deck0=sub.FIRE_DECK, deck1=bd)==0)
print("submission vs buddy (先手50戦):", w/50)
PY
```
