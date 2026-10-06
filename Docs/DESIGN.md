# Weapon Foundry design

Weapon Foundry turns Roboquest's existing weapon-affix system into a compositional build system. It does not add a parallel spell language, a new damage engine, or a new currency.

## Design rules

1. **The weapon chassis remains Roboquest.** Animation, recoil, sound, resource model, innate behavior and identity remain attached to the original weapon.
2. **Existing mechanics compose.** Bounce, Pierce, Ricochet, Seeker, Buckshot, Fragments, elements, explosions, Freewheel and native alt-fires are the building blocks.
3. **Power Cells are the crafting currency.** No new crafting currency is introduced.
4. **Loot still matters.** Ground weapons are donors, not obsolete trash once a player finds one good chassis.
5. **Quality is complexity.** Roboquest's existing quality/affix progression remains the baseline; deliberate grafting lets the player spend resources to push beyond random rolls.
6. **Absurd late builds are intentional.** Stability guards exist to stop corrupted recursion, not to flatten strong synergies.

## Composition

The runtime model distinguishes:

- passive semantics: Burn/Cryo/Shock and similar tags;
- traversal: Bounce/Pierce/Seeker/Ricochet;
- shot shape: Buckshot/Fork-style transformations;
- spawn/proc behavior: Fragments, Freewheel, Volatile/explosive launches;
- alt-fire skills.

Generated child attacks inherit only semantics meaningful to their event type.

The long-term recursion rule is modifier-instance provenance: an individual modifier instance may not spawn a descendant through itself after that instance has already been consumed on that branch. Distinct duplicate instances remain allowed to create deeper generations.

## Grafting

Intended ground-loop interaction:

1. hold a target weapon;
2. inspect a dropped donor weapon;
3. choose **GRAFT** instead of swap;
4. choose an eligible donor affix;
5. pay Power Cells;
6. consume the donor;
7. apply the affix to the target using a server-authoritative native weapon-mutation path.

Locked properties include chassis identity and narrow/special variants. Dependent upgrade rows are not directly grafted away from their parent affix.

The generated transfer policy currently marks 49 ordinary affixes and 15 resolved alt-fires as candidate transferable rows. This is policy data; the live graft transaction is still being implemented.

## Smith / editor

The smith/vendor path should expose the same legality/cost rules as ground grafting, with better planning:

- inspect current affixes;
- add from unlocked/available transferable rows;
- remove/replace where supported;
- upgrade quality;
- preview Power Cell cost and resulting complexity.

The UI should reuse native interaction surfaces as far as practical instead of presenting a detached mod configuration menu.

## Economy

Starting tuning targets:

- Common affix: 2 Power Cells;
- Rare affix: 4;
- Elite alt-fire: 7;
- complexity surcharge after the first few transferable affixes;
- duplicate-instance surcharge once duplicate semantics are validated.

These are tuning values, not architectural constants.


## Production Foundry merchant

The first production construction surface deliberately reuses Roboquest's existing Perfumer/affix merchant rather than adding a detached mod menu.

Weapon Foundry pre-seeds the merchant's native `AffixRows` array with the curated ordinary transferable-affix catalog. Vanilla initialization still appends the normal enchanted rows. Offer selection, tooltip UI, Power Cell price, player mutation call, server RPC and multicast remain native.

This is not the final donor-ground GRAFT UX, but it makes the composition loop available through ordinary runs while the donor interaction is built.
