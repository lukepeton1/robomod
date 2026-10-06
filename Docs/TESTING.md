# Release-candidate testing matrix

Every release candidate should be tested with no other content mods first.

## Load / packaging

- production builder reaches 14/14;
- every UAssetGUI clean and patched round-trip succeeds;
- Kismet layout validation succeeds;
- retoc emits `.pak/.ucas/.utoc`;
- game reaches the title screen;
- uninstalling only Weapon Foundry restores vanilla load.

## Composition

Test at least:

- Burn + Cryo + Shock;
- Bounce + Ricochet;
- Pierce + Explosive/Volatile;
- Bounce + Explosive;
- Seeker + Bounce;
- Buckshot + Freewheel;
- Seeker + Buckshot;
- Fragments + Burn;
- Fragments + Explosive;
- Fragments + Seeker where visually isolatable.

## Raycast Seeker release gate

Use a weapon whose vanilla primary skill is Raycast.

Confirm:

- the weapon still fires normally before Seeker;
- adding Seeker produces visible traveling projectiles;
- projectiles home;
- damage/fire cadence remain sensible;
- removing/replacing the Seeker weapon state does not leave the skill permanently converted;
- no crash when changing weapon/map.

## Foundry progression

Confirm:

- ordinary affix offers appear at the existing affix merchant;
- Power Cells are charged;
- ordinary rows apply;
- multiple different ordinary rows coexist;
- Common-quality weapons cannot buy ordinary Foundry affixes;
- upgraded quality tiers enforce 3 / 4 / 5 / 6 affix caps;
- a top-tier weapon at six affixes can no longer buy another Foundry affix;
- existing vanilla enchanted/perfume offers still appear.

## Native alt-fires

On several unrelated chassis, acquire/test representative widened secondary fires:

- projectile secondary;
- raycast/mark secondary;
- explosive/sticky secondary;
- mobility secondary such as Rocket Jump.

Confirm input binding, cooldown/charge and original primary-fire behavior.

## Save/load release gate

With a multi-affix Foundry weapon:

1. note chassis, quality, all visible affixes and Power Cells;
2. save/quit;
3. reload the run;
4. confirm the weapon state and currency;
5. cross a level/map save boundary and repeat.

## Multiplayer release gate

With both players modded:

- host buys a Foundry affix and client observes it;
- client buys one and host observes it;
- Power Cells debit once;
- no duplicate transaction;
- composed child projectiles/effects agree between peers;
- save/reconnect behavior remains coherent.

## Stress

- six-effect projectile build;
- Buckshot + Freewheel + Fragments + payload/status;
- repeated explosive/pierce/bounce interactions;
- watch actor/projectile growth and frame time;
- do not deliberately support duplicate spawn/proc rows until provenance is implemented.
