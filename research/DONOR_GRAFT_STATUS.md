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
- or add an external runtime reflection layer.

None of those matches the intended deterministic “choose this donor property” design.

## Why the weapon tooltip is the next seam

The game already displays the donor's affixes in `WGT_Tooltip_Weapon`, with six `WGT_Tooltip_WeaponAffix` entries.

The FModel export shows that the widget derives from native `WeaponTooltipWidget` and contains the six affix display widgets, but does not include the function implementation that supplies their data.

The expanded legacy handoff manifest now includes:

- `Blueprint/HUD/Tooltip/Weapon/WGT_Tooltip_Weapon`;
- `Blueprint/HUD/Tooltip/Weapon/WGT_Tooltip_WeaponAffix`;
- `Blueprint/HUD/Merchant/WGT_Merchant_AddEnchantedAffix`;
- `Blueprint/HUD/Merchant/WGT_Merchant_UpgradeWeapon`;
- `Blueprint/Interactive/Reward/BP_Interactive_WeaponSpawner`;
- `Blueprint/Interactive/Merchant/BP_Interactive_Merchant_Casino`;
- `Blueprint/Interactive/Reward/BP_Interactive_GambleGarry`;
- `Blueprint/Player/BP_IngamePlayerController`.

The next raw handoff should reveal either:

1. a native getter already returning affix row data;
2. a widget initialization struct containing the row IDs;
3. or a clean Blueprint seam to expose the same data to the dropped-weapon interaction.

## Planned ground transaction

Once donor row enumeration is available:

1. focus dropped donor;
2. collect transferable rows from donor;
3. show only legal rows under `transfer_policy.json`;
4. select row;
5. server validates donor still contains that row;
6. server computes Power Cell cost;
7. apply row through the existing native affix transaction;
8. verify target mutation;
9. consume donor exactly once;
10. let the native run-save path persist resulting weapon/currency state.

## Fallback

A runtime reflection layer remains a last resort only if the native tooltip/pickup paths do not expose the row data even in cooked bytecode. The project remains PAK-only until that is actually proven necessary.
