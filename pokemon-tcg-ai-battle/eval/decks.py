"""Tournament-style decklists built from CABT cards at competitive ratios.

Meta stats (real PTCG): ~15-18 Pokémon / ~30-36 Trainers / ~8-12 Energy.
We use a fixed STABLE trainer package (engine-safe cards only) + a type's
attackers + that type's basic energy.  Different types exploit different
weaknesses -> a rock-paper-scissors (三すくみ) metagame.

Engine-SAFE trainers (verified no segfault): Carmine 1192, Cheren 1224,
Judge 1213, Poké Pad 1152, Dusk Ball 1102, Buddy Poffin 1086, Switch 1123,
Boss's Orders 1182.  AVOID (segfault): Master Ball 1125, Reboot Pod 1089,
Precious Trolley 1126.
"""
from __future__ import annotations

# basic energy ids
ENERGY = {"GRA": 1, "FIR": 2, "WAT": 3, "LIG": 4, "PSY": 5, "FGT": 6, "DRK": 7, "MET": 8}

# 30-card stable consistency package (draw + search + gust + switch)
TRAINER_PACKAGE = (
    [1192] * 4   # Carmine        draw
    + [1224] * 4 # Cheren         draw 3
    + [1213] * 4 # Judge          draw 4 / disrupt
    + [1152] * 4 # Poké Pad       search non-ex Pokémon
    + [1102] * 4 # Dusk Ball      search Pokémon
    + [1086] * 4 # Buddy Poffin   search small basics
    + [1123] * 4 # Switch         mobility
    + [1182] * 2 # Boss's Orders  gust
)
assert len(TRAINER_PACKAGE) == 30


def build_deck(attackers: list[int], energy_type: str, n_energy: int = 12) -> list[int]:
    """attackers: list of card-ids (already with multiplicity, ~18 cards)."""
    deck = list(attackers) + list(TRAINER_PACKAGE) + [ENERGY[energy_type]] * n_energy
    if len(deck) != 60:
        # pad/trim with energy to exactly 60
        diff = 60 - len(deck)
        if diff > 0:
            deck += [ENERGY[energy_type]] * diff
        else:
            deck = deck[:60]
    assert len(deck) == 60, len(deck)
    return deck


# 18-Pokémon attacker cores per type (basic attackers; mix of ex/non-ex)
DECKS: dict[str, list[int]] = {
    "psychic": build_deck(
        [971] * 4 + [184] * 4 + [216] * 4 + [431] * 4 + [764] * 2, "PSY"),
    "fire": build_deck(
        [259] * 4 + [663] * 4 + [490] * 4 + [99] * 4 + [573] * 2, "FIR"),
    "metal": build_deck(
        [336] * 4 + [192] * 4 + [142] * 4 + [992] * 4 + [547] * 2, "MET"),
    "darkness": build_deck(
        [1062] * 4 + [777] * 4 + [985] * 4 + [138] * 4 + [139] * 2, "DRK"),
    "fighting": build_deck(
        [979] * 4 + [682] * 4 + [1050] * 4 + [886] * 4 + [117] * 2, "FGT"),
    "colorless": build_deck(
        [249] * 4 + [304] * 4 + [337] * 4 + [1002] * 4 + [176] * 2, "PSY"),
}

# single-prize-only Psychic aggro: deny buddy easy 2-3 prize KOs (all 1-prize Pokémon)
DECKS["psy_single"] = build_deck(
    # all single-prize; Munkidori(110HP,60/2) adds bulk over fragile Meloetta -> 0.70 vs buddy
    [971] * 4 + [216] * 4 + [112] * 4 + [751] * 4 + [764] * 2, "PSY", n_energy=12)

# single-prize FIRE aggro: counter to Crustle (Grass, weak Fire) - all non-ex, OHKO via x2
DECKS["fire_single"] = build_deck(
    [490] * 4 + [663] * 4 + [318] * 4 + [1027] * 4 + [358] * 2, "FIR", n_energy=12)

# Crustle-slayer (WEB調査ベース): 全基本の炎非ex + Jamming Tower(1246)でヒーローマント剥がし
# + Hearthflame Ogerpon(358) Fire Kagura でエネ加速。Volcanion Backfire 130->弱点x2=260 で
# ヒーローマント剥ぎ後の Crustle(150) はもちろん素の 250 でも OHKO。単サイドでサイドレース有利。
# 3エネ技の組成が要るため *探索型パイロット* 運用前提(ヒューリスティックでは組成不能)。
DECKS["fire_slayer"] = (
    [663] * 4 + [358] * 4 + [1027] * 4 + [318] * 4          # Volcanion/Ogerpon/Turtonator/Ho-Oh (16)
    + [1192] * 4 + [1224] * 4 + [1213] * 2 + [1152] * 4     # Carmine/Cheren/Judge/PokéPad
    + [1102] * 4 + [1086] * 4 + [1123] * 2 + [1182] * 3     # DuskBall/BuddyPoffin/Switch/Boss
    + [1246] * 3                                            # Jamming Tower (strip Hero's Cape)
    + [2] * 14                                              # Fire energy
)
# 注: Ho-Oh(318, 130HP)は Victini(80HP,ベンチ5体要求)より頑丈で対Crustle 0.375->0.425。
assert len(DECKS["fire_slayer"]) == 60, len(DECKS["fire_slayer"])
