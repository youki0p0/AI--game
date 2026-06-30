"""PTCG AI Battle 用エージェントの方策ロジック。

コンペ仕様: 毎ターン observation（ゲームログ・盤面・合法手リスト）を受け取り、
選択する手の「インデックス」を返す。エンジンは合法手のみ提示する。

observation/action の正確なスキーマは CABT ドキュメントとデータで確定する:
  https://matsuoinstitute.github.io/cabt/

ここでは「合法手のリストから1つ選んでそのインデックスを返す」最小実装を置く。
まずは安全に動くベースラインとし、後でルールベース→探索→学習に発展させる。
"""
from __future__ import annotations

from typing import Any, Sequence


def extract_legal_options(observation: Any) -> Sequence[Any]:
    """observation から合法手リストを取り出す。

    実スキーマ確定までの暫定。よくありそうなキーを順に探す。
    """
    if isinstance(observation, dict):
        for key in ("legal_options", "legal_actions", "options", "actions", "choices"):
            if key in observation:
                return observation[key]
    # dict でない/見つからない場合は observation 自体を候補列とみなす
    return observation if isinstance(observation, (list, tuple)) else []


def choose_index(observation: Any) -> int:
    """選択する手のインデックスを返す（ベースライン: 先頭の合法手）。

    置き換えポイント:
      - ルールベース: 攻撃可能なら最大ダメージ手、無理ならエネルギー付け/ドロー等
      - 探索: 合法手それぞれを評価して最良を選ぶ
    """
    options = extract_legal_options(observation)
    if not options:
        return 0  # 念のため（合法手が無いケースはエンジン側で来ない想定）
    return 0


class Agent:
    """状態を持ちたい場合の入れ物（学習方策・先読みキャッシュ等）。"""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def reset(self) -> None:
        """対戦開始時の初期化フック。"""

    def act(self, observation: Any) -> int:
        return choose_index(observation)


if __name__ == "__main__":
    demo = {"legal_options": ["attack:A", "attach_energy", "pass"]}
    print("chosen index:", choose_index(demo))
