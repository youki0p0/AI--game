# 提出（submissions）

## ★ 提出ファイル: `fire_single_agent.py` — Fire 単サイド

自己完結の単一ファイルエージェント。`cg.api` 以外を import せず、**相手デッキに非依存**で
Kaggle サンドボックスでそのまま動く。`agent(obs_dict) -> list[int]` を公開し、デッキ選択
フェーズ（`select is None`）では 60 枚の cardId 配列を返す。

### デッキ
Fire 単サイド（全非ex・弱点炎アグロ）。18 Pokémon / 30 Trainer / 12 Energy。
- アタッカー: Victini(240) / Volcanion(260) / Ho-Oh / Turtonator / Ogerpon（数値は弱点×2打点）
- 安定トレーナー30枚（engine 安全カードのみ）＋ 基本炎エネルギー12

### 実測勝率（自己完結ヒューリスティック・先後入替・各N=60）
| 相手 | 勝率 |
|---|---|
| Buddy（サンプル/Mega Lucario ex）| **0.667**（当初ゴール ≥0.65 達成）|
| Archaludon（現環境/ブリジュラスex）| 0.433 |
| Psychic（自作単サイド）| 0.400 |
| Crustle（Day-1 #1 壁）| 0.033（苦手）|
| **総合** | **0.383** |

### なぜこれを提出するか（重要）
より強い探索型 **fire_slayer（総合0.73・vs Crustle 0.56）** は、`search_begin` の隠れ情報
復元に **相手デッキ** を必要とする。実戦では相手デッキが不明で復元できず、提出環境では
機能しない（ルール型にフォールバック）。したがって提出は「**相手デッキ非依存で動く
自己完結ヒューリスティック**」である本ファイルが最適。探索型は相手デッキ既知の
解析・チューニング専用（`../docs/` 参照）。

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

---

## ★ `crustle_slayer_agent.py` — イワパレス特攻（提出可能・自己完結）

天敵イワパレス(Crustle)を **提出フォーマットのまま** 倒すための特攻ビルド。相手デッキは
不可視だが相手 *盤面* から Crustle を認識できるので、「相手はCrustleデッキ」と仮定して
隠れ情報を復元し、`cg.api` の `search_begin` による1手読み探索を **その場で** 回して
弱点OHKO（Volcanion Backfire 260 等）を組み立てる。探索・復元・評価をすべて `cg.api`
だけで自己完結（相手デッキ非依存で動く）。

- デッキ = Fire非ex + Jamming Tower3（ヒーローマント無効化）。
- Crustle検知時のみ探索（特攻）。非検知/復元失敗/例外時は軽量ヒューリスティックへフォールバック。
- 速度 ~1.0秒/試合（1手読み。1決定あたり数十ms程度で提出の時間制限内）。

### 実測（自己完結・先後入替）
| 相手 | 勝率 |
|---|---|
| **Crustle（イワパレス）** | **0.35**（ヒューリスティックの 0.00 から大幅改善）|
| Buddy | 0.60 |
| Archaludon | 0.50 |

※ ルールベースでは 0.0x だったCrustleを、探索の自己完結化で **提出可能なまま** 崩せる。
  相手デッキ既知の研究版 fire_slayer(0.56) には及ばないが、実戦で使える対壁の切り札。

**使い分け**: 汎用ラダー用は `fire_single_agent.py`、Crustleを狙い撃つメタ読みが立つ大会では
`crustle_slayer_agent.py`。どちらも単一ファイルで提出可能。

---

## 参考: 研究レベルのより強いエージェント（提出不可・相手デッキ既知が前提）

| エージェント | 総合 | vs Crustle | 備考 |
|---|---|---|---|
| **fire_slayer**（探索型＋fire_slayer_eval）| **0.73** | **0.56** | WEB調査ベースの対壁デッキ。天敵イワパレスに勝ち越し |
| dragapult_search（探索型）| 0.52 | 0.03 | 実メタT1ドラパルトex。アグロに圧勝、壁は苦手 |

いずれも `eval/gauntlet.py` で相手デッキを渡して計測する研究用。実戦提出では相手デッキが
未知のため使えない。詳細は `docs/crustle-counter-research.md`, `docs/dragapult-*` を参照。
