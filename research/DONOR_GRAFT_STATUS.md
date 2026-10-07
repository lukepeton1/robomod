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

The expanded UE4.26 legacy handoff has been collected and analyzed. It contains the dropped-weapon, player, weapon, affix, tooltip, merchant, compendium and relevant DataTable packages with decoded Kismet bytecode.

The raw pass confirms there is no obvious Blueprint-callable native function that simply returns every ordinary affix row name attached to an `AWeapon`.

The tooltip path is also not the row-enumeration source of truth:

- `WGT_Tooltip_Weapon` is a thin child of native `WeaponTooltipWidget`;
- `WGT_Tooltip_WeaponAffix` is a thin child of native `WeaponAffixTooltipWidget`;
- `WGT_WeaponCompendium_Affix` can render a supplied `WeaponAffixRow`, but it does not discover live donor rows.

The singular native `AWeapon.GetCurrentEnchantedAffixRowName()` getter remains useful for perfume-slot provenance but is not the ordinary-affix enumerator.

## Runtime identity model

The raw affix Blueprints expose the state needed to identify a row once a live affix object reference is available.

`AWeaponAffix` behavior objects expose/consume:

- `WeaponRef`, identifying the weapon instance the affix belongs to;
- `GetCustomFloatProperties(Name)`, exposing row-supplied custom parameter values;
- concrete UObject class identity.

The generated `DT_WeaponAffix` and `DT_WeaponMod` catalogs map every transferable row to:

- its affix class;
- its custom-float payload;
- its property kind;
- its transfer policy.

Therefore donor row identity does **not** need to be inferred from display strings.

The identity algorithm remains:

1. obtain live `AWeaponAffix` object references from the authoritative weapon/native owner container;
2. keep only objects whose `WeaponRef` is the donor `AWeapon`;
3. map concrete affix class to candidate transferable rows;
4. where multiple transferable rows share a class, query only the minimum custom-float keys necessary to distinguish them;
5. subtract/guard the donor's current enchanted row through `GetCurrentEnchantedAffixRowName()`;
6. subtract chassis-native/internal lookalikes using donor weapon-row provenance;
7. fail closed if an active locked variant remains ambiguous.

## Generated donor identity catalog

`tools/generate_donor_identity.py` generates:

`Source/grafting/donor_identity_catalog.json`

from:

- `research/generated/affixes.json`;
- `research/generated/weapon_mods.json`;
- `research/generated/weapons.json`;
- `Source/grafting/transfer_policy.json`.

Current catalog coverage:

- 65 transferable rows total;
- 50 rows have an exact class/custom runtime signature with no locked-row collision;
- 15 rows require an explicit context/provenance guard;
- 4 transferable class families require custom-property discrimination.

The generator deliberately fails if a future transferable row develops an unresolved runtime-identity collision.

## Context-guarded collisions

The remaining signature collisions are known rather than hidden.

They fall into three classes:

1. **enchanted-slot variants**
   - identified separately by `GetCurrentEnchantedAffixRowName()`;
2. **chassis/internal variants**
   - subtracted from the live multiset using weapon-row preset provenance;
3. **inactive rows**
   - never exposed as donor choices.

Examples include ordinary vs enchanted forms of Area Size, Boss Damage, Critical, Fire Rate and Reload Speed, plus internal rows such as `IceBlank`, `ShockBlank`, BuddyBot variants and the narrow `RocketJump_0` alt-fire row.

`tools/reconcile_donor_affixes.py` implements the reference multiset reconciliation behavior.

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

The old actor-enumeration probe is diagnostic history only. Production GRAFT must not call `GetAllActorsOfClass(AWeaponAffix)`.

## New static ownership evidence

The same raw handoff gives a stronger explanation for the zero result.

### Weapon-owned native managers

`BP_AWeapon` serializes native inherited references to:

- `WeaponStatManager`;
- `WeaponSkillManager`;
- `DT_WeaponAffix`;
- `DT_WeaponMod`.

Those manager objects are now primary candidates for the live affix/object ownership seam.

### Non-actor AWeaponAffix arrays exist in native gameplay objects

`BP_APlayer.SetStealthState` provides direct compiled-Kismet evidence that Roboquest uses `AWeaponAffix` as ordinary object references:

1. it creates a native `Trigger_Weapon` with `SpawnObject`;
2. it constructs a typed `TArray<AWeaponAffix>`;
3. it calls `SetArrayPropertyByName` on the trigger with property name `Affixes`.

This proves two important facts:

- `AWeaponAffix` references can live in ordinary UObject arrays rather than the world actor registry;
- native Roboquest gameplay objects already use an `Affixes` array typed as `AWeaponAffix`.

It does **not** yet prove that the owning `AWeapon` property itself is named `Affixes`; that must be discovered rather than guessed.

### Confirmed AWeaponAffix ownership pointer

Across the collected affix Blueprints, the native `AWeaponAffix` base exposes `WeaponRef`. Once the actual owner/container yields object references, donor filtering is straightforward and does not require UI text.

## Current gate: locate the native UObject container

The next gate is no longer row identification. It is acquiring the live affix UObject references.

Priority order:

1. discover an `AWeapon` native array/container of `AWeaponAffix` references;
2. inspect `WeaponStatManager` / `WeaponSkillManager` ownership or registries;
3. inspect reflected native class/property metadata from the installed game if the relevant field is never referenced by collected Blueprint bytecode;
4. only after the exact native field/API is known, add a cooked probe that reads it;
5. runtime DLL/reflection hooks remain a last resort.

Do **not** guess a field such as `AWeapon.Affixes` merely because `Trigger_Weapon.Affixes` exists.

## Planned ground transaction

Once donor-owned affix references/rows are available:

1. focus dropped donor;
2. resolve donor-owned transferable rows through the native container + `WeaponRef` + donor identity catalog;
3. show legal and useful blocked choices using the shared rule engine;
4. player selects one exact donor row;
5. server re-reads the donor-native state and verifies the row still exists;
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

1. exact native `AWeapon` / manager UObject container;
2. minimal cooked Blueprint exposure of that exact native container;
3. native tooltip/row-payload seam if it can be proven to carry stable row identity;
4. minimal runtime reflection layer only if cooked/native paths are conclusively insufficient.

The project remains PAK-only until that boundary is actually reached.
