# Testing matrix

Every release candidate should be tested with no other content mods first.

## Load / packaging

- production builder completes;
- UAssetGUI round-trip verification passes;
- retoc emits `.pak/.ucas/.utoc`;
- game reaches title screen;
- removing only Weapon Foundry files restores vanilla load.

## Composition smoke tests

Test at least:

- Burn + Cryo + Shock;
- Bounce + Ricochet;
- Pierce + Explosive/Volatile;
- Bounce + Explosive;
- Buckshot + Freewheel;
- Seeker + Buckshot on projectile weapons;
- Fragments + Burn;
- Fragments + Explosive;
- Fragments + Seeker where visually isolatable.

## Progression

Once grafting is active:

- donor disappears exactly once;
- Power Cells are charged exactly once;
- target gains exactly the selected legal property;
- locked identity/dependent rows cannot be grafted;
- invalid/insufficient-funds transactions do nothing;
- repeated interaction cannot duplicate the transaction.

## Save/load

- save and quit with a grafted weapon;
- reload the run;
- confirm chassis, quality, affix rows and custom parameters;
- repeat after changing map/level if the game saves at that boundary.

## Multiplayer

- host performs graft;
- client observes target state;
- client performs graft and server validates it;
- no duplicate currency spend;
- child projectiles/effects agree between host/client;
- reconnect/load behavior remains coherent.

## Stress

- late-game multi-effect projectile weapon;
- Buckshot + Freewheel + Fragments + payload/status;
- repeated explosive/pierce/bounce collisions;
- monitor frame time and actor/projectile growth;
- prove recursion guards terminate before declaring duplicate spawn-affix support.
