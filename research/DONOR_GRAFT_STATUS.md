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

## Cooked UAssetAPI handoff result

The expanded UE4.26 legacy handoff contains the dropped-weapon, player, weapon, affix, tooltip, merchant, compendium and relevant DataTable packages with decoded Kismet bytecode.

The cooked pass did **not** contain a Blueprint graph that called a full ordinary-affix enumerator, so the getter signature was not recoverable from a compiled Blueprint call site.

The tooltip path is not the row-enumeration source of truth:

- `WGT_Tooltip_Weapon` is a thin child of native `WeaponTooltipWidget`;
- `WGT_Tooltip_WeaponAffix` is a thin child of native `WeaponAffixTooltipWidget`;
- `WGT_WeaponCompendium_Affix` can render a supplied `WeaponAffixRow`, but it does not discover live donor rows.

The singular native `AWeapon.GetCurrentEnchantedAffixRowName()` getter remains useful for perfume-slot provenance.

## Empirical result: world-actor enumeration is disproven

The first cooked runtime probe attempted:

`GameplayStatics.GetAllActorsOfClass(AWeaponAffix)`

through `BP_Interactive_Weapon`.

Actual in-game result:

- the game loaded and entered a run normally;
- an affixed dropped Igniter Gun was visibly present;
- the probe executed when the player actually pressed the normal interaction key (**E**);
- merely hovering/focusing was not sufficient for that probe path;
- the displayed result was:
  - `WF PROBE: AWeaponAffix count = 0`.

Therefore:

> `AWeaponAffix` must not be treated as an enumerable world actor for GRAFT.

The result is recorded in:

`Source/probes/donor_runtime_probe_results.json`

Production GRAFT must not call `GetAllActorsOfClass(AWeaponAffix)`.

## Shipping-binary metadata breakthrough

A filtered metadata scan of `RoboQuest-Win64-Shipping.exe` exposed the native `AAWeapon` state that cooked Blueprint graphs never referenced directly.

The findings are summarized in:

`Source/probes/native_affix_metadata_findings.json`

### Reflected AAWeapon property block

The same reflected property cluster contains:

- `DT_WeaponAffix`;
- `DT_WeaponMod`;
- `WeaponStatManager`;
- `WeaponSkillManager`;
- `Affixes`;
- `TmpAffixPool`;
- `RandomAffixes`;
- `RandomAffixesRarity`.

This materially upgrades the old `Affixes` hypothesis: it is no longer inferred from the unrelated stealth trigger. `Affixes` is an actual reflected `AAWeapon` field name in the shipping binary.

### Reflected AAWeapon native function block

The same native callable-function cluster contains:

- `AddEnchantedAffix`;
- `AddRandomAffixe`;
- `GetAffixAmountByRarity`;
- `GetAffixLevel`;
- `GetAffixRow`;
- `GetAffixRowNames`;
- `GetCurrentEnchantedAffixRowName`;
- `GetDataRowName`;
- `InitializeAffixe`;
- `RerollRandomAffixes`;
- `UpgradeWeaponAffixQuality`.

This is the most important new seam.

`GetAffixRowNames` appears in the same reflected native function table as `GetCurrentEnchantedAffixRowName` and `GetDataRowName`, both of which are already observed as usable native Blueprint calls elsewhere in the cooked game.

### Native implementation strings

The shipping binary also exposes implementation/debug strings for:

- `AAWeapon::InitializeAffixe`;
- `AAWeapon::RemoveAffixes`;
- `AAWeapon::RemoveEliteAffixe`;
- `AAWeapon::GetRandomAffixBundle`;
- `AAWeapon::SetWeaponSavedData`;
- `AAWeapon::InitWeaponSavedData`;
- `AAWeapon::GetRandomAffixe`.

This strongly supports `AAWeapon` itself as the authoritative affix owner, not an external world registry.

### Row-level identity types

Native metadata contains:

- `LoadedAffix`;
- `bEnchantedAffix`;
- `WeaponAffixRow`;
- `WeaponAffixRowHandle`;
- `WeaponAffixBundleRowHandle`.

That confirms stable row-level identity exists below the tooltip layer.

## Verified native donor enumerator

The cooked runtime probe succeeded on a visibly affixed dropped Dual Rascals:

`WF ROW PROBE: GetAffixRowNames returned rows`

The probe was triggered by the normal interaction key and called:

`BP_Interactive_Weapon.SpawnedWeapon.GetAffixRowNames()`

Therefore `AAWeapon.GetAffixRowNames()` is now a **verified native/cooked seam** and the preferred authoritative donor row source.

Production-direction consequences:

1. donor discovery no longer needs world-object enumeration;
2. donor row identity no longer needs tooltip parsing;
3. donor row identity normally does not need class/custom-float reconstruction;
4. the server can re-read exact donor row IDs immediately before commit;
5. target mutation can be verified by re-reading the target's exact native row list.

The old row-name diagnostic runner is retired after this result.

## Current gate: end-to-end ground GRAFT transaction

The current diagnostic uses Roboquest's existing ping action as a temporary alternate dropped-weapon interaction while leaving **E** equip/swap untouched.

Files:

- policy generator: `tools/generate_ground_graft_probe.py`;
- generated policy: `Source/probes/ground_graft_ping_probe.json`;
- cooked patcher: `tools/patch_ground_graft_ping_probe.py`;
- builder: `tools/windows/build-ground-graft-ping-probe.ps1`;
- runner: `tools/windows/run-ground-graft-ping-probe.cmd`.

The patch hooks the existing reliable server RPC:

`BP_APlayer.OnServerPingActor(ActorRef, Location)`

For a dropped `AInteractiveWeapon`, the **server**:

1. resolves `SpawnedWeapon`;
2. reads `SpawnedWeapon.GetAffixRowNames()`;
3. chooses the first probe-approved donor row by deterministic priority;
4. rejects duplicates;
5. enforces the 0/3/4/5/6 quality complexity policy;
6. computes native Power Cell cost;
7. verifies `CurrentTicket` funds;
8. debits with `RemoveTicket`;
9. calls the existing replicated `BP_APlayer.AddEnchantedAffix(RowName)` path;
10. re-reads `currentWeapon.GetAffixRowNames()`;
11. refunds with `AddTicket` and leaves the donor if verification fails;
12. destroys the dropped donor interactive only after the target row is observed.

Non-weapon pings and validation failures fall through to vanilla ping behavior.

For the first transaction test, the automatic candidate pool is deliberately restricted to 11 globally-safe rows that are **never a shipping chassis preset**:

- Fragmentation
- Bounce
- Pierce
- Ricochet
- Burn
- Ice
- Shock
- FreeShot
- Firerate
- Impact
- MarkDamage

`AutoShotgun`, `AutoCritical`, and `ExplosiveBlank` are withheld from this diagnostic because they appear as native preset rows on at least one shipping chassis and could otherwise be mistaken for donor-transferable identity.

This automatic first-match selection is diagnostic only. The final GRAFT UX must replace it with explicit native-feeling donor-row selection.


## Runtime identity fallback

If `GetAffixRowNames()` succeeds, direct row IDs supersede most of the previously planned class/custom-property reconstruction.

The generated donor identity catalog remains useful for:

- validating transfer-policy coverage;
- identifying native/chassis lookalikes where needed;
- fallback reconstruction if some affix object exists without a row name;
- future provenance/recursion tracking.

If direct row enumeration fails, the fallback identity model is:

1. obtain `AWeaponAffix` UObject references from `AAWeapon.Affixes` or an exact native owner/container;
2. filter by `WeaponRef`;
3. map concrete affix class + minimum custom-float keys to row IDs;
4. subtract enchanted/chassis-native lookalikes;
5. fail closed on ambiguity.

`tools/reconcile_donor_affixes.py` implements the reference multiset reconciliation behavior.

## Planned ground transaction

Once authoritative donor row enumeration is validated:

1. focus dropped donor;
2. read exact donor affix/mod row IDs through the native weapon API;
3. show legal and useful blocked choices using the shared rule engine;
4. player selects one exact donor row;
5. server re-reads the donor-native row list and verifies the row still exists;
6. server validates transferability, target compatibility, conflicts, duplicates, complexity and alt-fire slot;
7. server computes Power Cell cost;
8. reserve/debit Power Cells;
9. mutate target through the existing native affix transaction, or native weapon-mod path;
10. verify target mutation;
11. consume donor exactly once;
12. replicate result;
13. rely on native run-save serialization unless testing proves it insufficient.

The donor is never consumed before successful target mutation verifies.

## UI direction

The handoff confirms `WGT_WeaponCompendium_Affix` owns an explicit `AffixRow : WeaponAffixRow` field and already implements native-style formatted affix descriptions.

That remains a useful visual building block/reference for:

- donor-choice rows;
- Smith rows;
- compatibility/cost previews.

It should be reused or matched rather than inventing a detached developer menu.

## Fallback order

1. direct `AAWeapon.GetAffixRowNames()`;
2. exact `AAWeapon.Affixes` / native manager UObject container;
3. minimal cooked Blueprint exposure of that exact native state;
4. minimal runtime reflection layer only if cooked/native paths are conclusively insufficient.

The project remains PAK-only until that boundary is actually reached.
