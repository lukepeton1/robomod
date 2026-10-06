# Roboquest Weapon Foundry

Weapon Foundry is a deep weapon-composition overhaul for **Roboquest** built around the game's existing weapon, affix, skill, projectile, status, merchant and Power Cell systems.

The goal is Noita-like combinatorial depth without importing Noita's UI or inventing a parallel combat system: native Roboquest mechanics should combine into increasingly ridiculous guns as the run progresses.

## Current verified state

The project has moved beyond static reverse engineering.

Verified in the game:

- a custom UE4.26 `.pak/.ucas/.utoc` mod loads successfully;
- cooked `DT_WeaponAffix` edits load;
- cooked Blueprint/Kismet edits to Fragmentation load;
- Fragments can be generalized beyond their vanilla one-weapon pool;
- a diagnostic weapon successfully combined **Seeker + Fragments + Burn + Explosive + Freewheel + Buckshot**;
- Freewheel repeated the complete Buckshot-transformed shot;
- fragment/status/explosion behavior composed without obvious runaway recursion or severe performance failure.

The production build intentionally excludes the diagnostic starter-gun edits.

## Production core

`Source/patches/weapon_foundry_core.json` is generated from the extracted game catalog and currently opens the verified composition primitives across:

- **74** standard Projectile/Raycast weapon chassis;
- **39** natively Projectile weapon chassis for Seeker/Homing;
- **15** resolved native elite secondary-fire/weapon-mod rows widened across the 74 standard chassis set.

Unusual `None`/unresolved edge cases remain held back instead of being guessed.

`BP_WA_Fragmentation` is patched through same-shape decoded Kismet substitutions so no absolute execution-flow offsets need rebasing.

## Grafting

The intended progression loop is:

1. find a donor weapon;
2. choose **GRAFT** instead of simply swapping;
3. transfer an eligible donor affix/alt-fire to the held weapon;
4. spend **Power Cells**;
5. consume the donor;
6. keep building the target weapon through the run.

A generated transfer policy currently identifies **49 ordinary affixes** and **15 resolved alt-fires** as graft candidates while locking identity, enchanted-slot, dependent-upgrade and narrow chassis-specific rows.

The native server-authoritative ordinary-affix transaction has now been promoted into production through the existing Perfumer/affix merchant. The merchant acts as the first **Foundry surface**, mixing curated transferable ordinary affixes into its normal Power Cell purchase flow.

Ground-donor GRAFT selection/consumption and the full deterministic smith/editor are still being implemented.

## Build

See [Docs/BUILDING.md](Docs/BUILDING.md).

With the development folder layout used during reverse engineering:

```cmd
tools\windows\run-weapon-foundry.cmd
```

builds, verifies, packs and installs the production core.

## Repository layout

- `Source/composition/` — composition/inheritance contract.
- `Source/grafting/` — transferability and economy policy.
- `Source/patches/` — declarative cooked-asset patches.
- `research/` — reverse-engineering findings and generated catalogs.
- `tools/` — catalog, UAssetAPI, Kismet and packaging tooling.
- `tests/` — composition and patch regression tests.
- `Docs/` — install/build/design/compatibility/testing documentation.
- `packaging/` — release install/uninstall helpers.

## Documentation

- [Design](Docs/DESIGN.md)
- [Install](Docs/INSTALL.md)
- [Uninstall](Docs/UNINSTALL.md)
- [Building](Docs/BUILDING.md)
- [Compatibility](Docs/COMPATIBILITY.md)
- [Testing](Docs/TESTING.md)
- [Known issues](Docs/KNOWN_ISSUES.md)
- [Modified assets](Docs/MODIFIED_ASSETS.md)
- [Changelog](Docs/CHANGELOG.md)

## Asset policy

The repository's `vanilla-json/` directory contains research exports used to understand the installed build. Release packages do **not** redistribute the user's extracted raw Roboquest `.uasset/.uexp` files. Production assets are rebuilt locally from the user's own installation.
