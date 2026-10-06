# Modified assets

## Production core

Weapon Foundry's current production core overrides exactly these cooked Roboquest packages:

### `/Game/Data/DT_WeaponAffix`

Purpose:

- remove selected artificial compatibility exclusions already proven/decoded to coexist;
- broaden safe weapon eligibility for composition primitives;
- keep Seeker limited to natively projectile-based primary skills until hit-model conversion is implemented.

Generated policy source:

`Source/patches/weapon_foundry_core.json`

### `/Game/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation`

Purpose:

- remove the vanilla gameplay-tag gate that prevented generalized Fragmentation;
- validate the spawned fragment for child-tag propagation;
- inherit GameplayTags from the originating `ASkill`, including raycast-origin cases.

The patch uses same-shape Kismet substitutions: it inserts/removes no expressions and changes no absolute execution-flow offsets.

Patch source:

`tools/patch_fragmentation_bytecode.py`

## Diagnostic-only assets

The Phase 3 diagnostic additionally overrode:

- `/Game/Data/DT_Weapons`
- `/Game/Data/DT_PlayerSkills`

to force the starter HandGun into a six-effect projectile test. Those overrides are **not part of the production build**.

## Planned graft/editor assets

The merchant/player/interactive packages under investigation are not listed as production modifications until their patch is committed to the production builder.

## Vanilla assets

Weapon Foundry source control and release packages do not include the user's extracted vanilla `.uasset/.uexp` game files.
