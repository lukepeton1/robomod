# Weapon Foundry 0.1.0-rc1

This is the first release-candidate architecture for the Roboquest Weapon Foundry overhaul.

## Included

- 74 standard Projectile/Raycast weapon chassis in the broad composition pool.
- Live Raycast → Projectile Seeker resolver across those 74 chassis.
- Generalized Fragments with native GameplayTag inheritance.
- Multi-element pool unlocks.
- Bounce + Ricochet.
- Pierce/Bounce + explosive/volatile combinations.
- Seeker + Bounce.
- Seeker + Buckshot.
- Freewheel + transformed native shots.
- 15 widened native elite secondary-fire rows.
- 18 globally safe/generalized ordinary Foundry affixes offered through the native affix merchant.
- 50 ordinary affixes retained in the target-aware GRAFT transfer catalog.
- Native Power Cell / server / multicast mutation path.
- Native quality-scaled Foundry complexity gate: Common disabled, then 3/4/5/6 affix caps across the upgraded tiers.
- Reproducible UE4.26 build, verification and IoStore packaging.
- Install/uninstall helpers and source-side patch tooling.

## Already proven in-game

A six-effect diagnostic weapon successfully combined:

- Seeker;
- Fragments;
- Burn;
- Explosive;
- Freewheel;
- Buckshot.

Freewheel repeated the complete Buckshot shot, fragments/status/explosion behavior composed, and no obvious runaway recursion or severe performance collapse was observed.

## RC validation still required

Before calling this 1.0:

- game-test the production Raycast Seeker resolver;
- game-test the six-affix Foundry guard;
- sample the widened alt-fire matrix;
- verify save/load persistence;
- verify host/client multiplayer.

## Not yet complete

The exact dropped-donor **GRAFT** UI (select an affix from a ground weapon, spend Cells, consume donor) is not in this RC. The native weapon mutation path works, but the current cooked handoff does not expose the donor's ordinary affix row IDs. The handoff manifest now includes the weapon-tooltip/affix-display path required to finish that cleanly.

Duplicate spawn/proc affix instances are also not deliberately exposed until modifier-instance provenance is implemented.
