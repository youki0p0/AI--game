"""PTCG AI Battle 提出エージェント: Archaludon ex（鋼 / ブリジュラス）— 実ラダー環境デッキ。

現 PTCG-AI ラダーの最頻アーキタイプ（上位10データで使用7/最多タイ）。Archaludon ex(190):
鋼・HP300・Metal Defender 220、弱点=炎。Duraludon(169)→Archaludon ex(190)の1進化で、
Full Metal Lab(1244)/基本鋼エネ厚めにより攻撃到達が安定。Cinderace(666)を差して炎枠・
サブアタッカーを兼ねる。全て単一ファイル・cg.api のみ依存・相手デッキ非依存。

採用理由（実メタ適合）:
  実メタ3柱（Archaludon鋼 / Alakazam超 / Grimmsnarl悪）に対し、simple_bot 操縦の本デッキは
  総合 0.597（高N）。H2Hで Grimmsnarl(0.64) と MegaStarmie(0.61) を上回り、3柱に対する
  ポジションが Grimmsnarl より良い。負けるのは希少な Buddy(0.36) のみ。

操縦（pilot）: 実測で最も安定して回った汎用 setup-then-attack ロジック（simple_bot）を
  インライン化。自作の専用パイロットは 0.44 と弱かったため、実測 0.597 の simple_bot を採用。

★ 提出安全化: 末尾の唯一の最終 def が agent(observation, ...)。全例外を握り、
  *空アクションで自滅しない*（実戦で空アクション自滅があったため根絶）。
"""
from __future__ import annotations

# --- Archaludon ex デッキ（上位10データ由来, meta_bench の FIELD Archaludon と同一）--------
ARCH_DECK = (
    [169] * 4      # Duraludon (basic -> Archaludon ex)
    + [190] * 4    # Archaludon ex (鋼, HP300, 弱点=炎)
    + [666] * 4    # Cinderace (炎サブアタッカー)
    + [1244] * 4   # Full Metal Lab (スタジアム)
    + [8] * 13     # 基本鋼エネルギー
    + [1152] * 4   # PokePad 等ドロー/サーチ
    + [1121] * 4   # Ultra Ball
    + [1122] * 4   # Pokegear
    + [1097] * 4   # Night Stretcher
    + [1197] * 3
    + [1147] * 2   # Jumbo Ice Cream (回復)
    + [1159] * 1   # Hero's Cape
    + [1182] * 1   # Boss's Orders
    + [1185] * 4
    + [1227] * 4   # Carmine 等
)
assert len(ARCH_DECK) == 60, len(ARCH_DECK)


def _get_card(obs, area, index, player_index):
    import cg.api as api  # noqa: PLC0415
    ps = obs.current.players[player_index]
    if area == api.AreaType.DECK:
        return obs.select.deck[index]
    if area == api.AreaType.HAND:
        return ps.hand[index]
    if area == api.AreaType.DISCARD:
        return ps.discard[index]
    if area == api.AreaType.ACTIVE:
        return ps.active[index]
    if area == api.AreaType.BENCH:
        return ps.bench[index]
    return None


def _impl(obs_dict):
    """実測 0.597 の汎用 setup-then-attack 操縦（simple_bot）をインライン化。"""
    import cg.api as api  # noqa: PLC0415
    OptionType, SelectContext, AreaType = api.OptionType, api.SelectContext, api.AreaType
    Pokemon = api.Pokemon

    obs = api.to_observation_class(obs_dict)
    if obs.select is None:
        return list(ARCH_DECK)
    select = obs.select
    options = select.option
    context = select.context
    scores = []
    for o in options:
        score = 0
        if context == SelectContext.MAIN:
            if o.type == OptionType.ATTACH:
                score = 1000
            elif o.type == OptionType.EVOLVE:
                score = 800
            elif o.type == OptionType.PLAY:
                score = 600
            elif o.type == OptionType.ABILITY:
                score = 700
            elif o.type == OptionType.ATTACK:
                score = 100
            elif o.type == OptionType.RETREAT:
                score = -1
        else:
            score = 2000
            if o.type == OptionType.CARD:
                card = _get_card(obs, o.area, o.index, o.playerIndex)
                if card is not None:
                    if context in (SelectContext.EVOLVE, SelectContext.TO_BENCH):
                        score += 500
                    if isinstance(card, Pokemon):
                        if o.playerIndex != obs.current.yourIndex:
                            score += 500 if o.area == AreaType.ACTIVE else 100
                            score += len(card.energies) * 50
                        else:
                            score += card.hp
            elif o.type == OptionType.YES:
                score += 100
            elif o.type == OptionType.NUMBER:
                score += o.number
        scores.append(score)

    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in range(min(len(order), select.maxCount)):
        idx = order[i]
        if scores[idx] >= 0 or len(out) < select.minCount:
            out.append(idx)
    return out


def _g(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _safe_default(observation):
    """絶対にブリックしない保険手。空アクション自滅を根絶する。"""
    sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
    if sel is None:
        return list(ARCH_DECK)
    opts = _g(sel, "option", []) or []
    n = len(opts)
    if n == 0:
        return []
    mc = int(_g(sel, "maxCount", 1) or 1)
    mn = int(_g(sel, "minCount", 0) or 0)
    return list(range(min(max(mc, mn if mn > 0 else 1), n)))


# Kaggle エントリ: 末尾の唯一の最終 def。全例外を握り *空アクション自滅を根絶*。
def agent(observation, configuration=None):
    try:
        out = _impl(observation)
    except Exception:
        return _safe_default(observation)
    try:
        sel = observation.get("select") if isinstance(observation, dict) else _g(observation, "select")
        if sel is None:
            return out if (isinstance(out, list) and len(out) == 60) else list(ARCH_DECK)
        opts = _g(sel, "option", []) or []
        n = len(opts)
        if n == 0:
            return []
        mc = int(_g(sel, "maxCount", 1) or 1)
        mn = int(_g(sel, "minCount", 0) or 0)
        ok = (isinstance(out, list) and len(out) >= max(1, mn) and len(out) <= mc
              and len(set(out)) == len(out)
              and all(isinstance(i, int) and 0 <= i < n for i in out))
        return out if ok else _safe_default(observation)
    except Exception:
        return _safe_default(observation)
