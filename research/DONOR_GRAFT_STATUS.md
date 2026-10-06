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

## Exact remaining blocker

The dropped weapon actor in the current raw handoff exposes:

- the spawned weapon object;
- `AffixAmount`;
- `CurrentAffixBundle`;
- normal pickup/swap interaction;
- server-validation behavior.

It does **not** expose, in the currently collected Blueprint bytecode, a function/property that enumerates the actual ordinary affix row IDs contained by the donor.

Without the donor row IDs, a ground GRAFT implementation would have to:

- choose a random property;
- infer from display text;
- reconstruct a random roll from insufficient state;
- or add an external runtime reflection layer.

None of those matches the intended deterministic “choose this donor property” design.

## Repository-side FModel pass after the first expanded manifest

The committed `vanilla-json/` property dump now includes the tooltip, merchant, dropped-weapon, weapon-spawner and player-controller surfaces needed for a second static pass.

That pass established several concrete facts:

1. `WGT_Tooltip_Weapon` derives from native `WeaponTooltipWidget` and owns six `WGT_Tooltip_WeaponAffix` children.
2. `WGT_Tooltip_WeaponAffix` derives from native `WeaponAffixTooltipWidget`; its Blueprint shell only exposes presentation widgets (`Image_Line` and `Text_Description`). The row payload is therefore supplied by native/base behavior that the FModel property dump does not contain.
3. `BP_Interactive_Weapon` exposes the weapon row lookup path (`GetDataRowName` -> `SyncLoadWeaponRow`) but no Blueprint-local active-affix row array.
4. `BP_Interactive_Merchant_AddEnchantedAffix.CanInteract` calls the singular native getter `GetCurrentEnchantedAffixRowName`. This is useful evidence that at least one affix row ID is Blueprint-readable, but it is not a complete ordinary-affix enumerator.
5. `BP_Interactive_Merchant_AddEnchantedAffix.InitializeAffixRow` resolves a `WeaponAffix` row from a row name, confirming the existing merchant path is suitable once a donor row ID is known.
6. `WGT_WeaponCompendium_Affix` has an explicit `AffixRow : WeaponAffixRow` property. It is a promising native-looking row-rendering surface for GRAFT/Smith UI, but it still does not identify which rows belong to a live donor.
7. `DA_CommonWeaponData.AffixBundleByLevel` stores rarity-pattern bundles (for example common/rare counts plus quality/color), not the actual row IDs selected for an individual weapon. Therefore `CurrentAffixBundle` cannot be safely reverse-mapped into the donor's exact affixes from the static generation table.

The legacy handoff manifest now also requests:

- `Blueprint/HUD/Compendium/Weapons/WGT_WeaponCompendium_Affix`

so the next UAssetAPI collection includes the strongest newly identified UI/data seam.

## Why raw UAssetAPI bytecode is still the next gate

The committed FModel dump is intentionally a property/signature export. It does not contain the compiled Kismet call graph needed to answer whether a Blueprint-accessible native getter already enumerates the live weapon's ordinary affix rows.

The next raw handoff needs to resolve one of:

1. a native getter returning all active affix row names;
2. a tooltip/recap initialization payload that receives those row names;
3. a native weapon array/struct that can be read from the dropped weapon;
4. a minimal Blueprint patch that exposes the already-existing native state.

The singular `GetCurrentEnchantedAffixRowName` getter is not sufficient to claim full donor enumeration.

## Planned ground transaction

Once donor row enumeration is available:

1. focus dropped donor;
2. collect transferable rows from donor;
3. show only legal rows under `transfer_policy.json`;
4. select one exact donor row;
5. server re-reads donor state and verifies the row still exists;
6. server computes Power Cell cost;
7. reserve/debit Power Cells;
8. apply the row through the existing native affix transaction (or the native weapon-mod path for alt-fires);
9. verify target mutation;
10. consume donor exactly once;
11. replicate the result;
12. let the native run-save path persist resulting weapon/currency state.

The donor is never consumed before successful target mutation verifies.

## Fallback order

1. existing native getter / tooltip / pickup seam;
2. native `CurrentAffixBundle` or weapon-state structure if it contains exact row identities;
3. minimal cooked Blueprint exposure of that native state;
4. minimal runtime reflection layer only if the cooked/native paths are conclusively insufficient.

The project remains PAK-only until that is actually proven necessary.
