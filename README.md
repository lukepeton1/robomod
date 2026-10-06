# Roboquest Weapon Foundry

Weapon Foundry is a deep weapon-composition overhaul for **Roboquest** built around the game's existing weapon, affix, skill, projectile, status, merchant, networking and Power Cell systems.

The goal is Noita-like combinatorial depth without importing Noita's UI or inventing a parallel combat system: native Roboquest mechanics should combine into increasingly ridiculous guns as the run progresses.

## Current state

Weapon Foundry is now at **0.1.0-rc1** architecture.

Verified in the game:

- a custom UE4.26 `.pak/.ucas/.utoc` mod loads successfully;
- cooked `DT_WeaponAffix` edits load;
- cooked Blueprint/Kismet edits to Fragmentation load;
- Fragments can be generalized beyond their vanilla one-weapon pool;
- a diagnostic weapon successfully combined **Seeker + Fragments + Burn + Explosive + Freewheel + Buckshot**;
- Freewheel repeated the complete Buckshot-transformed shot;
- fragment/status/explosion behavior composed without obvious runaway recursion or severe performance failure;
- ordinary affix rows work through Roboquest's native affix-merchant / player mutation transaction.

The release-candidate build intentionally excludes the diagnostic starter-gun edits.

Foundry complexity is now tied to Roboquest's native weapon quality/color state instead of a flat global limit: Common weapons cannot buy ordinary Foundry affixes; the four upgraded tiers cap at 3 / 4 / 5 / 6 affixes respectively.

## Release-candidate production core

The generated production policy currently supports:

- **74** standard Projectile/Raycast weapon chassis for the broad composition primitives;
- **74** standard chassis for Seeker/Homing through the production raycast→projectile resolver;
- **15** resolved native elite secondary-fire/weapon-mod rows widened across the standard chassis set;
- **18** globally safe ordinary affixes exposed through the native Foundry merchant surface;
- a **six-affix purchase guard** matching the existing weapon-tooltip capacity.

Unusual `None`/unresolved edge cases remain held back instead of being guessed.

### Fragmentation

`BP_WA_Fragmentation` is patched through same-shape decoded Kismet substitutions. Generated child projectiles inherit the originating `ASkill.GameplayTags`, while the vanilla `Fragmentation` child tag remains as a recursion guard.

### Seeker / Homing

`BP_WA_Homing` now has a real live hit-model resolver. While Seeker is applied it sets:

- `HitType = Projectile`;
- `Speed = ProjectileSpeed`;
- `CollisionSize = ProjectileCollisionSize`;
- `GravityScale = 0`.

Vanilla `OnRemove` restores `HitType = BaseHitType`.

This non-same-shape Kismet edit is layout-validated and rebases absolute flow offsets through `tools/kismet_layout.py`. It still needs final in-game validation on a weapon whose primary skill is natively Raycast.

## Foundry progression

The first production construction surface reuses Roboquest's existing Perfumer/affix merchant.

Weapon Foundry seeds its native affix pool with the **18 globally safe/generalized ordinary affixes** while retaining:

- the native merchant UI;
- native Power Cell spending;
- the existing `BP_APlayer.AddEnchantedAffix` path;
- reliable server RPC;
- reliable multicast;
- native weapon mutation.

A generated transfer policy identifies **50 ordinary affixes** and **15 resolved alt-fires** as target-aware graft candidates while locking identity, enchanted-slot, dependent-upgrade and narrow chassis-specific rows. The random merchant deliberately exposes only the 18 rows safe across the whole standard chassis set.

The intended final ground loop remains:

1. find a donor weapon;
2. choose **GRAFT** instead of swapping;
3. choose an eligible donor affix/alt-fire;
4. spend Power Cells;
5. consume the donor;
6. keep building the held weapon.

Ground-donor row enumeration is the remaining blocker for that exact UX. The next targeted legacy handoff now includes the native weapon-tooltip/affix-display path that should expose those row IDs.

## Build

See [Docs/BUILDING.md](Docs/BUILDING.md).

With the current development folder layout:

```cmd
tools\windows\run-weapon-foundry.cmd
```

builds, verifies, packs and installs the full release candidate.

## Repository layout

- `Source/composition/` — composition/inheritance contract.
- `Source/grafting/` — transferability, transaction and economy policy.
- `Source/patches/` — declarative production cooked-asset patches.
- `Source/probes/` — diagnostic-only probes.
- `research/` — reverse-engineering findings and generated catalogs.
- `tools/` — catalog, UAssetAPI, Kismet, build and packaging tooling.
- `tests/` — composition, policy, Kismet and native-transaction regression tests.
- `Docs/` — install/build/design/compatibility/testing documentation.
- `packaging/` — release install/uninstall helpers.

## Asset policy

Release packages do **not** redistribute extracted raw Roboquest `.uasset/.uexp` files. Production assets are rebuilt locally from the user's own installation.
