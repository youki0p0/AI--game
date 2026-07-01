# 提出パッケージ（PTCG AI Battle / CABT）

作成: 2026-07-01 ／ ブランチ: claude/kagura-makina-image-gen-rm1hd0

## 提出フォーマット
CABT/kaggle-environments のエージェントは **単一 Python ファイルの `agent` 関数** が
エントリポイント。本パッケージは各案を `main.py` として同梱（`.tar.gz` も併置）。

- エントリ: `agent(observation: dict, configuration=None) -> list[int]`
- デッキ選択フェーズ（`observation["select"] is None`）で 60枚の cardId 配列を返す
- デッキはファイル内にリテラル埋め込み（`deck.pkl` 等の外部成果物は不要）
- 依存は `cg.api`（エンジン提供）のみ。相手デッキ非依存で動作

## 中身
| ファイル | 役割 | 実測総合 |
|---|---|---|
| `meta_search/main.py`（`meta_search.tar.gz`）| **本命**: アーキタイプ検知型 探索 | **0.480** |
| `fire_single/main.py`（`fire_single.tar.gz`）| **安定枠**: 自己完結ヒューリスティック | 0.383 |

「最新2提出が集計対象」のため、**二枚看板**（本命＋安定枠）での提出を推奨。

## 検証エビデンス（自作ガントレット・先後入替）

### 本命 meta_search（N=40、Crustleのみ N=120）
| 相手 | 勝率 |
|---|---|
| Buddy（メガルカリオ）| 0.725 |
| Archaludon（現環境）| 0.525 |
| Fire | 0.500 |
| Crustle（イワパレス）| 0.375 [0.288,0.462] |
| Psychic（未検知→フォールバック）| 0.275 |
| **総合** | **0.480** |

- 仕組み: 相手盤面の固有ポケモンで buddy/Crustle/Archaludon を判定 → 該当既知デッキを
  仮定して `search_begin` の1手読み探索 → 未知/失敗は軽量ヒューリスティックにフォールバック。
- 速度: 検知時 ~1.15s/game（1手読み）、未検知 ~0.04s/game。

### 安定枠 fire_single（N=60）
| 相手 | 勝率 |
|---|---|
| Buddy | 0.667（当初ゴール ≥0.65 達成）|
| Archaludon | 0.433 |
| Psychic | 0.400 |
| Crustle | 0.033 |
| **総合** | **0.383** |

- 探索を使わない純ヒューリスティック。未知の相手にも挙動が安定（メタ外し耐性）。

## 提出手順（例）
```bash
# 単一ファイルをそのまま提出する場合
#   meta_search/main.py または fire_single/main.py を提出物として指定。
# tar.gz を要求する運用の場合
#   meta_search.tar.gz / fire_single.tar.gz を提出。
# ローカル動作確認:
python - <<'PY'
import importlib.util
spec=importlib.util.spec_from_file_location("main","dist/submission/meta_search/main.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("deck-select:", len(m.agent({"select":None,"current":None})), "cards")  # -> 60
PY
```

## 残リスク・既知の限界
- **Crustle（イワパレス）は 0.375**。回復壁はエンジン上の構造的天敵で、探索を提出形式に
  してもこれが上限（heuristic 0.00 からは大幅前進）。以前口頭で出た「0.56」は高分散の
  単発サンプルで、安定計測の真値は 0.375。
- meta_search は **未検知の相手ではフォールバック挙動が弱め**（psychic 0.275）。ラダー主流が
  環境デッキ（buddy/Archaludon/Crustle）である前提で最適。psychic系が多いと fire_single の
  方が安定する場面がある → 二枚看板でリスク分散。
- 探索は 1手読み（n_turns=1）。深くすると強くなり得るが速度が提出制限に触れるリスク。

## ロールバック
- 二枚看板のどちらかが不調なら、もう一方＋前バージョンへ差し替え（各ファイルは独立・自己完結）。
- ソースは `submissions/`（追跡対象）に保持。`git revert` で前提出構成へ即戻し可能。

## Human Gate
- 実提出（アップロード）は人間承認事項。本パッケージは提出可能状態まで準備済み。
