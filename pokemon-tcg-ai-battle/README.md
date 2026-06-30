# Pokémon TCG AI Battle Challenge

Kaggle コンペ **「The Pokémon Company - PTCG AI Battle Challenge Simulation」** の作業フォルダ。

- コンペURL: https://www.kaggle.com/competitions/pokemon-tcg-ai-battle
- データ: https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/data

> ⚠️ コンペの詳細（ルール・評価指標・提出形式）はログインが必要なため、
> データ取得後にこの README を正式版へ更新する。下記は一般的なシミュレーション
> 系（対戦エージェント提出）コンペを想定した暫定構成。

## フォルダ構成

```
pokemon-tcg-ai-battle/
├── README.md          このファイル
├── data/              Kaggle から取得したデータ（Git 管理外）
├── notebooks/         分析・実験用ノートブック
├── src/               エージェント本体・共通コード
│   └── agent.py       提出するエージェントのひな型
└── submissions/       提出物（Git 管理外）
```

## セットアップ

```bash
# Kaggle CLI（未導入の場合）
pip install kaggle

# APIトークンを ~/.kaggle/kaggle.json に配置（Kaggleのアカウント設定から取得）
chmod 600 ~/.kaggle/kaggle.json

# コンペ規約に同意した上でデータ取得
cd pokemon-tcg-ai-battle
kaggle competitions download -c pokemon-tcg-ai-battle -p data/
unzip -o "data/*.zip" -d data/
```

## 進め方（暫定）

1. `data/` を取得し、配布物（ルールエンジン / サンプルエージェント / 提出仕様）を確認
2. この README に正式なルール・評価指標・提出形式を追記
3. `src/agent.py` のひな型に方策（ルールベース → 探索 / 学習）を実装
4. ローカルで対戦シミュレーションを回して検証
5. `submissions/` に提出物を生成して提出

## メモ

- 学習・探索を入れる場合は依存（numpy 等）を `requirements.txt` に追記する
- 大きなデータ・モデルはコミットしない（`.gitignore` 済み）
