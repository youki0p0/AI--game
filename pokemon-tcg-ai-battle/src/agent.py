"""PTCG AI Battle 用エージェントのひな型。

コンペの実際の I/O 仕様（観測・行動空間・提出形式）はデータ取得後に確定する。
ここでは「観測を受け取り行動を返す」一般的なインターフェースだけ用意しておく。
"""
from __future__ import annotations

from typing import Any


class Agent:
    """対戦エージェントの基底。

    実際のコンペAPIに合わせて choose_action のシグネチャを調整する。
    """

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def reset(self) -> None:
        """1試合の開始時に呼ぶ初期化フック。"""

    def choose_action(self, observation: Any, legal_actions: list[Any]) -> Any:
        """観測と合法手から行動を1つ選ぶ。

        暫定実装: 合法手の先頭を返すだけ（ベースライン）。
        まずはランダム/ルールベースに置き換え、その後に探索・学習を入れる。
        """
        if not legal_actions:
            raise ValueError("合法手がありません")
        return legal_actions[0]


if __name__ == "__main__":
    # 最小の動作確認
    agent = Agent()
    agent.reset()
    print(agent.choose_action(observation=None, legal_actions=["pass", "attack"]))
