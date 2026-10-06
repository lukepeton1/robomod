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

## Seeker safety rollback

The synthetic Raycast → Projectile Seeker resolver is currently disabled after an actual UE4 runtime crash in `BP_WA_Homing.OnApply` reporting an unknown code token.

Release candidates must confirm:

- `BP_WA_Homing` is absent from the mod container override list;
- the Homing row remains on its vanilla seven weapon chassis;
- Homing is absent from the global Foundry merchant pool;
- native projectile Seeker behavior still works on vanilla-supported chassis;
- no test or release script claims raycast Seeker support until a replacement resolver passes a real in-game gate.

Do not use the old raycast-Seeker smoke expectation as a release criterion while this rollback is active.

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

The release source includes `Source/composition/alt_fire_skill_profiles.json`, which classifies all 15 widened native secondaries.

For the first RC pass, test at least one representative from each high-value behavior class:

- raycast volley: **Bullet Hail / CombiShotgun**;
- projectile volley: **LaserShotgun**;
- sticky explosive projectile: **Sticky Grenade** or **Sticky Mines**;
- homing explosive projectile: **Missile Blast**;
- prefab projectile: **Arc Wave** or **Hoverball**;
- primary retrigger: **Trigger Tap**;
- state/utility: **Booster** or **Rocket Jump**;
- mark utility: one Sonar Shot variant.

Confirm input binding, cooldown/charge, original primary-fire behavior and whether elements/Buckshot propagate as predicted by the profile. Traversal inheritance (Seeker/Bounce/Pierce) is deliberately treated as a separate validation axis rather than assumed.

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
