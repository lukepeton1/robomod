# Ground-donor GRAFT status

## What is already solved

Weapon Foundry already has a working mutation path for ordinary affix rows:

- native merchant UI;
- Power Cell transaction;
- `BP_APlayer.AddEnchantedAffix(RowName)`;
- reliable server RPC;
- reliable multicast;
- native weapon mutation.

The production transfer policy already classifies which ordinary affixes/alt-fires are legal graft candidates.

## Raw UAssetAPI handoff result

The expanded UE4.26 legacy handoff has now been collected and analyzed. It contains the relevant dropped-weapon, player, affix, tooltip, merchant, compendium, weapon and DataTable packages with decoded Kismet bytecode.

The raw pass confirms there is no obvious Blueprint-callable native function that simply returns every ordinary affix row name attached to an `AWeapon`.

The tooltip path is also not the row-enumeration source of truth:

- `WGT_Tooltip_Weapon` is a thin child of native `WeaponTooltipWidget`;
- `WGT_Tooltip_WeaponAffix` is a thin child of native `WeaponAffixTooltipWidget`;
- `WGT_WeaponCompendium_Affix` can render a supplied `WeaponAffixRow`, but it does not discover live donor rows.

The singular native `AWeapon.GetCurrentEnchantedAffixRowName()` getter remains useful for the perfume slot but is not the ordinary-affix enumerator.

## Runtime identity breakthrough

The raw affix Blueprints expose a more useful native seam.

Live `AWeaponAffix` behavior objects expose/consume:

- `WeaponRef`, identifying the weapon instance the affix belongs to;
- `GetCustomFloatProperties(Name)`, exposing the row-supplied custom parameter values;
- their concrete UObject/AActor class identity.

The generated `DT_WeaponAffix` and `DT_WeaponMod` catalogs already map every transferable row to:

- its affix class;
- its custom-float payload;
- its property kind;
- its transfer policy.

Therefore donor rows do not need to be inferred from display text.

The production identity model is:

1. enumerate live `AWeaponAffix` instances;
2. keep only instances whose `WeaponRef` is the donor `AWeapon`;
3. map the concrete affix class to candidate transferable rows;
4. where multiple transferable rows share a class, query only the minimum custom-float keys necessary to distinguish them;
5. subtract/guard the donor's current enchanted row through `GetCurrentEnchantedAffixRowName()`;
6. use donor chassis/native provenance to reject locked base/internal variants;
7. fail closed if an active locked variant remains ambiguous.

This is materially stronger than tooltip parsing and remains PAK/native-first.

## Generated donor identity catalog

`tools/generate_donor_identity.py` now generates:

`Source/grafting/donor_identity_catalog.json`

from:

- `research/generated/affixes.json`;
- `research/generated/weapon_mods.json`;
- `Source/grafting/transfer_policy.json`.

Current catalog coverage:

- 65 transferable rows total;
- 50 rows have an exact class/custom runtime signature with no locked-row collision;
- 15 rows require an explicit context/provenance guard;
- 4 transferable class families require custom-property discrimination.

The four same-class transferable families are distinguished by native custom properties rather than names or tooltip strings.

The generator deliberately fails if a future transferable row develops an unresolved runtime-identity collision.

## Context-guarded collisions

The remaining signature collisions are known rather than hidden.

They fall into three classes:

1. **enchanted-slot variants**
   - identified separately by `GetCurrentEnchantedAffixRowName()`;
2. **chassis/internal variants**
   - removed using weapon/chassis provenance and fail-closed behavior;
3. **inactive rows**
   - never exposed as donor choices.

Examples include ordinary vs enchanted forms of Area Size, Boss Damage, Critical, Fire Rate, Reload Speed and similar rows, plus internal variants such as `IceBlank`, `ShockBlank`, BuddyBot rows and the narrow `RocketJump_0` alt-fire row.

## Current live gate: AWeaponAffix actor enumeration

One fact remains unproven in the actual game:

> whether live `AWeaponAffix` objects can be enumerated through
> `GameplayStatics.GetAllActorsOfClass(AWeaponAffix)`.

The naming/runtime structure strongly suggests this is viable, but production GRAFT must not assume it.

A deterministic cooked probe now exists:

- patcher: `tools/patch_donor_identity_probe.py`;
- builder: `tools/windows/build-donor-identity-probe.ps1`;
- runner: `tools/windows/run-donor-identity-probe.cmd`.

The probe layers on top of the normal production release candidate and patches only:

`RoboQuest/Content/Blueprint/Interactive/Reward/BP_Interactive_Weapon`

When a dropped weapon's `GetInteractSound` executes, it prints:

`Weapon Foundry AWeaponAffix count:`

followed by the global live `AWeaponAffix` actor count.

It does not modify weapon state or consume a donor.

### Interpretation

- positive non-zero count with affixed weapons live -> promote actor enumeration into the cooked GRAFT implementation;
- zero with known affixed weapons live -> actor enumeration is not sufficient; continue to the next native ownership seam;
- load/crash failure -> restore normal RC and treat actor enumeration as disproven/unusable.

## Planned ground transaction

Once live donor enumeration is validated:

1. focus dropped donor;
2. enumerate donor-owned transferable rows using `WeaponRef` + the generated identity catalog;
3. show legal and useful blocked choices using the shared rule engine;
4. player selects one exact donor row;
5. server re-enumerates/revalidates donor state;
6. server validates transferability, target compatibility, conflicts, duplicates, complexity and alt-fire slot;
7. server computes Power Cell cost;
8. reserve/debit Power Cells;
9. mutate the target through the existing native affix transaction, or the corresponding native weapon-mod path;
10. verify target mutation;
11. consume donor exactly once;
12. replicate result;
13. rely on native run-save serialization unless testing proves it insufficient.

The donor is never consumed before successful target mutation verifies.

## UI direction after enumeration

The handoff confirms `WGT_WeaponCompendium_Affix` already owns an `AffixRow : WeaponAffixRow` field and native formatted-description behavior.

That makes it a useful visual building block/reference for:

- donor-choice rows;
- Smith rows;
- compatibility/cost previews.

It should be reused or matched rather than inventing a detached developer menu.

## Fallback order

1. enumerate live `AWeaponAffix` actors and filter by `WeaponRef`;
2. if actor enumeration fails, identify another native registry/container carrying those affix objects;
3. minimally expose the existing native state through cooked Blueprint;
4. introduce runtime reflection only if cooked/native paths are conclusively insufficient.

The project remains PAK-only until that boundary is actually reached.
