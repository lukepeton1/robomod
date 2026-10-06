# Native graft transaction probe

## Purpose

The remaining unknown in the cleanest PAK-only grafting path is not networking or UI. Cooked `BP_APlayer` proves that Roboquest already owns a replicated weapon-affix transaction:

1. local `AddEnchantedAffix(RowName)` calls native `AWeapon.AddEnchantedAffix(RowName)` on `currentWeapon`;
2. a server calls `OnMulticastAddEnchantedAffix(RowName, Weapon)`;
3. a client calls reliable server RPC `OnServerAddEnchantedAffix(RowName, Weapon)`;
4. the server invokes the multicast;
5. non-local recipients call the same native `AWeapon.AddEnchantedAffix(RowName)`.

The unknown is what native `AWeapon.AddEnchantedAffix` does when `RowName` names an ordinary active affix rather than a row whose `bEnchantedAffix` flag is true.

## Probe implementation

`Source/probes/graft_merchant_probe.json` patches only the class-default `AffixRows : Array<Name>` on:

`/Game/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix`

The array is pre-seeded with the 49 ordinary affixes currently marked transferable.

Vanilla `InitializeAffixPool` then appends its 11 active enchanted rows. It does not clear the pre-seeded array.

Everything else remains native:

- merchant spawn/interaction;
- random offer selection;
- price/currency interaction;
- tooltip/UI;
- `BP_APlayer.AddEnchantedAffix`;
- server RPC;
- multicast;
- native `AWeapon.AddEnchantedAffix`.

The probe therefore answers the storage question without inventing a substitute transaction.

## Test

Use a weapon with no important existing perfume affix.

At a Perfumer:

1. choose an offer whose name is clearly an ordinary weapon affix (examples: Burn, Bounce, Pierce, Ricochet, Buckshot, Freewheel, Fragments);
2. buy it and verify Power Cells are charged;
3. verify whether the effect becomes active / appears on the weapon;
4. later buy a second ordinary affix on the same weapon;
5. check whether the first ordinary affix remains.

## Result interpretation

### A — ordinary rows accumulate

If both ordinary rows remain active:

- native `AddEnchantedAffix` is usable as the core graft mutation primitive;
- preserve the existing BP_APlayer server/multicast chain;
- next work is donor extraction/consumption and presenting the selected donor row to this transaction.

This is the ideal PAK-only result.

### B — ordinary row works, second replaces first

If the first ordinary row disappears when the second is added:

- the native path is a singular slot regardless of row type;
- it remains useful for one editable special slot but cannot represent the full graft bundle;
- ordinary grafting must target the weapon's regular affix bundle through another native generation/mutation seam or a minimal runtime hook.

### C — ordinary row is rejected/no-op

If the merchant purchase succeeds but the ordinary row never applies:

- native AddEnchantedAffix validates the row's enchanted flag or equivalent native state;
- do not fake grafting by toggling every row to enchanted;
- continue to regular affix-bundle mutation.

### D — crash/corrupt state

Remove the probe by rebuilding the production core. Preserve the log/result and do not repeat on a valued run save.

## Restore production core

```cmd
tools\windows\run-weapon-foundry.cmd
```

This rebuilds and installs the production core without the merchant CDO probe.
