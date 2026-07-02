# Pokémon TCG AI Battle Challenge（Simulation）

Kaggle コンペ **「The Pokémon Company - PTCG AI Battle Challenge Simulation」** の作業フォルダ。

- コンペ: https://www.kaggle.com/competitions/pokemon-tcg-ai-battle
- データ: https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/data
- **APIドキュメント（CABT）**: https://matsuoinstitute.github.io/cabt/

## コンペ概要

ポケモンカードゲーム（TCG）の対戦AI（Training Agent）を作って競う**シミュレーション競技**。
確率・不確定情報・戦略立案が勝敗を分ける環境で、競技用シミュレータ上でエージェント同士を対戦させる。

- 基盤: **kaggle-environments** 上に構築された対戦シミュレータ
- エージェントの動作: **毎ターン observation（ゲームログ＋盤面＋合法手リスト）を受け取り、選択する手の「インデックス」を返す**
  - エンジンは常に合法手のみを提示するので、非合法手の心配は不要
- 公式ポケモンTCGルールと一部差異あり（CABTドキュメント参照）

## 評価・提出の仕組み

- 1チームあたり**1日最大5エージェント**を提出可能
- 各提出はラダー上で**近いレーティングの相手**とエピソード（対戦）を行い、勝ちで上昇・負けで下降・引き分けで均衡（Elo的）
- 集計対象は**最新2提出**（最終提出にも使用）
- 競技自体に賞金はないが、**Hackathonトラックにレポート提出**すると賞の対象。最終順位は競技リーダーボード＋Hackathon評価の両方で決定（Hackathon参加は任意・本競技とは別）

## タイムライン（2026年）

| 日付 | 内容 |
|---|---|
| 6/16 | 開始 |
| 8/9 | エントリー締切 / チームマージ締切（この日までにルール同意が必要） |
| 8/16 | **最終提出締切** |
| 8/17〜8/末頃 | 対戦継続・最終集計 |

## フォルダ構成

```
pokemon-tcg-ai-battle/
├── README.md
├── requirements.txt
├── data/              Kaggle データ（Git管理外）
├── notebooks/         分析・実験
├── src/
│   ├── agent.py       方策ロジック（合法手 → 選択index）
│   └── main.py        kaggle-environments 提出エントリ
└── submissions/       提出物（Git管理外）
```

## セットアップ

```bash
pip install -r requirements.txt   # kaggle, kaggle-environments など

# Kaggle APIトークンを ~/.kaggle/kaggle.json に配置（権限600）
cd pokemon-tcg-ai-battle
kaggle competitions download -c pokemon-tcg-ai-battle -p data/
unzip -o "data/*.zip" -d data/
```

## 進め方

1. `data/` を取得し、CABTドキュメント（observation/action の具体仕様・カードデータ）を確認
2. `src/agent.py` の `choose_action` を観測スキーマに合わせて実装
   - まずは**ルールベース**（攻撃可能なら最大ダメージ手を選ぶ等）でベースラインを作る
   - 次に**探索（先読み）／学習**を検討
3. ローカルで `kaggle-environments` を使って自己対戦させ検証
4. `main.py` を提出（Notebook 経由 or CLI）。1日5回まで → 上位2提出が残る

## 人間 vs AI で遊ぶ（`play_vs_human`）

これまで育てたエージェント（`champion` / `buddy` / `submissions/*`）を相手に、
ターミナルから自分で手を選んで対戦できる。盤面・選択肢は日本語ラベルで表示され、
番号入力（カンマ区切りで複数選択可）で操作する。`q` でいつでも投了できる。

```bash
cd pokemon-tcg-ai-battle
python -m eval.play_vs_human --list                       # 対戦相手一覧を表示
python -m eval.play_vs_human                               # champion 相手（デフォルト）
python -m eval.play_vs_human --opponent buddy
python -m eval.play_vs_human --opponent grimmsnarl --human-deck psy_single
python -m eval.play_vs_human --opponent submissions/fire_single_agent.py
```

要 `engine/`（CABT本体。競技規約により非再配布のため `.gitignore` 済み・各自配置）。
未配置の場合はエラーメッセージで案内される。エンジン非依存の部分（盤面表示・選択肢
表示・入力パース・対戦相手解決）は `tests/test_play_vs_human.py` でテスト済み。

## メモ

- observation/action の正確なスキーマはデータ取得・CABTドキュメント確認後に確定する
- 大きなデータ・モデルはコミットしない（`.gitignore` 済み）
