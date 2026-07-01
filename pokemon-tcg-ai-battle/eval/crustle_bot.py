"""Reproduction of the Day-1 #1 "Crustle Bot" (from a public Kaggle notebook).

Crustle (345): Stage 1, 150 HP, Ability negates ALL damage from opponent's
Pokémon-ex attacks -> it walls the ex-based meta. With Hero's Cape (1159) it
becomes 250 HP; heals via Jumbo Ice Cream (1147) / Cook (1212); Battle Cage
(1264) protects the bench. All single-prize. A "low-power deck + baby-simple
pilot" that still reached #1 because ex decks simply can't damage it.

Counter (our champion): all NON-ex attackers, so Crustle's ability does nothing;
Iron Boulder (170) one-shots a 150 HP Crustle before it can heal.

Deck + agent are transcribed faithfully from the notebook.
"""
from __future__ import annotations

from .engine_driver import _ensure_engine_on_path

# 60-card Crustle deck (transcribed from the notebook's deck.csv)
CRUSTLE_DECK: list[int] = (
    [344] * 4      # Dwebble (basic, evolves to Crustle)
    + [345] * 4    # Crustle (Stage 1 wall, negates ex damage)
    + [1147] * 4   # Jumbo Ice Cream (heal 80)
    + [1159] * 1   # Hero's Cape (+100 HP)
    + [1264] * 4   # Battle Cage (stadium, protects bench)
    + [1212] * 4   # Cook (heal 70)
    + [1224] * 4   # Cheren (draw 3)
    + [18] * 4     # Grow Grass Energy (special)
    + [11] * 4     # Mist Energy (special)
    + [1086] * 4   # Buddy-Buddy Poffin (search basics)
    + [14] * 4     # Spiky Energy (special)
    + [1] * 19     # Basic Grass Energy
)
assert len(CRUSTLE_DECK) == 60, len(CRUSTLE_DECK)


def _get_card(obs, area, index, player_index):
    ps = obs.current.players[player_index]
    import cg.api as api  # noqa: PLC0415
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


def crustle_agent(obs_dict: dict) -> list[int]:
    """Baby-simple rule-based pilot for the Crustle wall deck (from the notebook)."""
    _ensure_engine_on_path()
    import cg.api as api  # noqa: PLC0415
    OptionType, SelectContext, AreaType = api.OptionType, api.SelectContext, api.AreaType
    Pokemon = api.Pokemon

    obs = api.to_observation_class(obs_dict)
    if obs.select is None:
        return list(CRUSTLE_DECK)

    select = obs.select
    options = select.option
    context = select.context
    scores = []
    for o in options:
        score = 0
        if context == SelectContext.MAIN:
            if o.type == OptionType.ATTACH:
                score = 1000
                card = _get_card(obs, o.area, o.index, obs.current.yourIndex)
                if card is not None and card.id == 1159:
                    score = 2100 if o.inPlayArea == AreaType.ACTIVE else 0
            elif o.type == OptionType.EVOLVE:
                score = 800
            elif o.type == OptionType.PLAY:
                score = 600
                card = _get_card(obs, AreaType.HAND, o.index, obs.current.yourIndex)
                if card is not None:
                    if card.id == 1147:  # Jumbo Ice Cream: heal only if damaged w/ 3+ energy
                        active = obs.current.players[obs.current.yourIndex].active
                        if active and active[0] is not None:
                            p = active[0]
                            score = 2000 if (p.hp < p.maxHp and len(p.energies) >= 3) else 0
                    elif card.id == 1212:  # Cook: heal only if damaged
                        active = obs.current.players[obs.current.yourIndex].active
                        if active and active[0] is not None:
                            p = active[0]
                            score = 1500 if p.hp < p.maxHp else 0
                    elif card.id == 1224:  # Cheren draw
                        score = 1400
                    elif card.id == 1264:  # Battle Cage stadium
                        score = 1300
            elif o.type == OptionType.ABILITY:
                score = 400
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


def make_simple_bot(deck: list[int]):
    """A generic 'setup-then-attack' rule-based pilot (same brain as Crustle bot)
    piloting an arbitrary deck. Handles evolve/attach/play/ability, attacks last."""
    _ensure_engine_on_path()
    import cg.api as api  # noqa: PLC0415
    OptionType, SelectContext, AreaType = api.OptionType, api.SelectContext, api.AreaType
    Pokemon = api.Pokemon

    def agent(obs_dict):
        obs = api.to_observation_class(obs_dict)
        if obs.select is None:
            return list(deck)
        select = obs.select; options = select.option; context = select.context
        scores = []
        for o in options:
            score = 0
            if context == SelectContext.MAIN:
                if o.type == OptionType.ATTACH: score = 1000
                elif o.type == OptionType.EVOLVE: score = 800
                elif o.type == OptionType.PLAY: score = 600
                elif o.type == OptionType.ABILITY: score = 700
                elif o.type == OptionType.ATTACK: score = 100
                elif o.type == OptionType.RETREAT: score = -1
            else:
                score = 2000
                if o.type == OptionType.CARD:
                    card = _get_card(obs, o.area, o.index, o.playerIndex)
                    if card is not None:
                        if context in (SelectContext.EVOLVE, SelectContext.TO_BENCH): score += 500
                        if isinstance(card, Pokemon):
                            if o.playerIndex != obs.current.yourIndex:
                                score += 500 if o.area == AreaType.ACTIVE else 100
                                score += len(card.energies) * 50
                            else:
                                score += card.hp
                elif o.type == OptionType.YES: score += 100
                elif o.type == OptionType.NUMBER: score += o.number
            scores.append(score)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in range(min(len(order), select.maxCount)):
            idx = order[i]
            if scores[idx] >= 0 or len(out) < select.minCount:
                out.append(idx)
        return out
    return agent


# Archaludon ex deck (Metal, weak Fire) - the current PTCG-AI ladder environment
ARCHALUDON_DECK = (
    [992] * 4      # Duraludon (basic, -> Archaludon ex)
    + [190] * 4    # Archaludon ex (300 HP, Metal Defender 220, weak Fire, EX)
    + [57] * 2     # Relicanth
    + [1192] * 4 + [1227] * 4 + [1213] * 4 + [1182] * 3 + [1097] * 4   # Carmine/Lillie/Judge/Boss/NightStretcher
    + [1121] * 4 + [1152] * 4 + [1122] * 3 + [1123] * 2 + [1159] * 1 + [1244] * 3  # UltraBall/PokePad/Pokegear/Switch/HeroCape/FullMetalLab
    + [8] * 14     # Basic Metal Energy
)
assert len(ARCHALUDON_DECK) == 60, len(ARCHALUDON_DECK)
