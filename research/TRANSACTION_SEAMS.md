# Native transaction, replication, and save seams

This file records the installed-build hooks that can be reused for the weapon-grafting overhaul. These are concrete exported signatures, not proposed APIs.

## Existing player RPCs already mutate weapon affixes

`BP_APlayer_C` exposes the following Blueprint functions:

| Function | Relevant flags | Parameters |
| --- | --- | --- |
| `AddEnchantedAffix` | BlueprintCallable / BlueprintEvent | `RowName: Name` |
| `OnServerAddEnchantedAffix` | Net, Reliable, **Server** | `RowName: Name`, `Weapon: AWeapon` |
| `OnMulticastAddEnchantedAffix` | Net, Reliable, **Multicast** | `RowName: Name`, `Weapon: AWeapon` |
| `OnServerRerollAffix` | Net, Reliable, **Server** | `Weapon: AWeapon`, `bKeepAffixBundle: Bool` |
| `MulticastRerollAffix` | Net, Reliable, **Multicast** | `Weapon: AWeapon`, `bKeepAffixBundle: Bool` |
| `OnServerMulticastUpgradeQuality` | Net, Reliable, **Server** | `Weapon: AWeapon` |
| `OnMulticastUpgradeQuality` | Net, Reliable, **Multicast** | `Weapon: AWeapon` |

This is a major simplification for grafting.

A first implementation should **not** invent a separate replicated mod-state channel just to add an affix. The game already has an authoritative server -> multicast path whose payload is exactly an affix row name plus a weapon actor.

The immediate grafting hypothesis is therefore:

1. identify an eligible donor affix row;
2. charge Power Cells authoritatively;
3. invoke/extend the existing add-affix transaction on the target `AWeapon`;
4. destroy/consume the donor pickup through the normal authoritative interaction path;
5. let the native weapon-affix initialization pipeline instantiate the behavior class referenced by the affix row.

The missing `DT_WeaponAffix` is required to verify the row structure and whether this path naturally supports ordinary common/rare affixes in addition to the game's current enchanted/perfumer use case.

## Existing interactive surfaces are already server-aware

`BP_Interactive_Weapon_C`:

- derives from native `AInteractiveWeapon`;
- has `bReplicates = true`;
- has `bServerValidation = true`;
- exposes `GetLoot`;
- exposes normal interaction text for equip/switch/purchase and Superbot's eat interaction;
- loads weapon rows through `SyncLoadWeaponRow`.

`BP_Merchant_Weapon_C` also has `bReplicates = true` and its graph uses `IsServer` before weapon spawning.

`BP_Interactive_Merchant_RerollAffix_C` and `BP_Interactive_Merchant_UpgradeWeaponQuality_C` contain explicit `IsServer` checks.

Therefore both candidate grafting UX surfaces have existing authority machinery:

- **preferred first target:** smith/merchant affix editor;
- **secondary target:** direct action on a dropped weapon.

The merchant path remains the safer first implementation because the add-affix, reroll, quality, pricing, and HUD concepts already coexist there.

## Save/quit support has a native weapon array

`BP_SaveGame_Profile_C` stores:

- `bIsValidSaved`;
- `Saved_PlayerData: PlayerRunSaveGame`;
- `Saved_GeneratorData: GeneratorRunSaveGame`.

The default `PlayerRunSaveGame` value visibly contains a `Weapons` array alongside player level, items, Power Cells, run currency, and other run state.

`BP_AGameInstance_C` exposes/uses:

- `SaveRun`;
- `InvalidateRunSaved`;
- `HaveRunSaved`;
- `GetPlayerSavedRunData() -> PlayerRunSaveGame`;
- `GetGeneratorSavedRunData() -> GeneratorRunSaveGame`;
- native calls named `GeneratePlayerSaveRunData` and `GenerateGeneratorSaveRunData`.

This is favorable for the design requirement that customized weapons survive normal save/quit. If grafting updates the same native weapon/affix state that the existing run serializer reads, no separate mod-side save format should be necessary.

The unresolved part is the native element type of `PlayerRunSaveGame.Weapons`. That struct lives in `/Script/RoboQuest` and is not expanded by the current property export. It must be validated before claiming stacked/ordered affix state round-trips perfectly.

## Fragmentation already carries network skill state

`BP_WA_Fragmentation_C` constructs `NetworkSkillInfo` values and quantized vectors before calling `SpawnCustomProjectiles`. This means at least one vanilla child-projectile affix already routes secondary attacks through network-oriented skill metadata.

Composition work should extend this native path where possible. Creating child projectiles directly as untracked local actors would throw away exactly the replication behavior the game already provides.

## Consequences for the composition architecture

The implementation should prefer these rules:

1. **Weapon configuration remains native state.** Affix rows/classes are the persistent source of truth.
2. **Weapon mutation remains host-authoritative.** Reuse the player server/multicast RPC path for graft/reroll/quality operations.
3. **Child attacks remain skills/network-skill events.** Reuse `NetworkSkillInfo` and native projectile-spawn paths.
4. **Save data should be extended only if native weapon serialization proves insufficient.** Do not create an independent save format preemptively.
5. **Deterministic RNG belongs at the skill/child-event level.** Vanilla Fragmentation already uses a `RandomStream`, which is preferable to wall-clock/client-local RNG.

These findings make a native-feeling implementation materially more realistic than the initial JSON dump alone suggested.
