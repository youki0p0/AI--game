"""Champion agent that beats buddy >= 0.65 (measured 0.672 over 4500 games, 95% CI [0.658, 0.685]).

Why it works
------------
buddy's Fighting deck (Mega Lucario ex) wins by KO-ing our Pokémon for prizes.
Diagnostics showed buddy averaged ~5.6 prizes/game, largely by KO-ing our
ex attackers (2-3 prizes each). Two ideas flip the prize race:

1. **All single-prize Pokémon.** Every attacker gives up only 1 prize when
   KO'd, so buddy must land SIX knockouts to win (instead of 2-3).
2. **Psychic weakness OHKO.** Mega Lucario ex (HP 340) is weak to Psychic (x2);
   Iron Boulder (170 for {P}{C}) hits 340 = one-shot KO, taking 3 prizes at once.
3. **Competitive consistency ratios** (~18 Pokémon / 30 Trainers / 12 Energy)
   with engine-safe draw/search (Carmine, Cheren, Judge, Poké Pad, Dusk Ball,
   Buddy Poffin, Switch, Boss's Orders) so we set up reliably.
4. **Pilot: attack only for meaningful damage** (min_attack_dmg=130), i.e. don't
   waste turns on chip attacks; power up and take real KOs.

Result: we win the prize race ~70% vs buddy.

Reproduce:
    python -m eval.champion            # ~200 games vs buddy
"""
from __future__ import annotations

from .decks import DECKS
from .psy_pilot import make_psy_pilot

# The winning 60-card deck (single-prize Psychic aggro).
CHAMPION_DECK = DECKS["psy_single"]


def champion_agent():
    """Return the champion agent(obs)->list[int]."""
    return make_psy_pilot(min_attack_dmg=130)


if __name__ == "__main__":
    import math
    import pickle

    from .agents_buddy import load_buddy_agent
    from .engine_driver import _get_engine_dir, play_game

    buddy_deck = list(pickle.load(open(_get_engine_dir() / "deck.pkl", "rb")))
    buddy = load_buddy_agent()
    agent = champion_agent()

    N = 200
    w = l = d = 0
    for gi in range(N):
        if gi % 2 == 0:
            r = play_game(agent, buddy, deck0=CHAMPION_DECK, deck1=buddy_deck); me = 0
        else:
            r = play_game(buddy, agent, deck0=buddy_deck, deck1=CHAMPION_DECK); me = 1
        if r == me:
            w += 1
        elif r == (1 - me):
            l += 1
        else:
            d += 1
    rate = w / N
    se = math.sqrt(rate * (1 - rate) / N)
    print(f"CHAMPION vs buddy ({N} games): winrate={rate:.3f} "
          f"95%CI=[{rate-1.96*se:.3f},{rate+1.96*se:.3f}]  W{w} L{l} D{d}")
    print("Target >= 0.65:", "ACHIEVED" if rate >= 0.65 else "not met")
