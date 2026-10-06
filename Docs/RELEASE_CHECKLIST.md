# 0.1.0-rc1 release checklist

## Static / CI

- [x] production policy regenerates deterministically;
- [x] transfer policy regenerates deterministically;
- [x] native merchant policy regenerates deterministically;
- [x] native alt-fire policy regenerates deterministically;
- [x] Kismet layout tests pass;
- [x] Fragmentation semantic verifier passes;
- [x] Homing resolver semantic verifier passes;
- [x] Foundry six-affix guard verifier passes;
- [x] native server/multicast transaction contract is tested;
- [x] native run-save surface contains weapon array + Power Cell fields;
- [x] diagnostic HandGun/skill packages are excluded from production manifest.

## Build

- [ ] production builder reaches 14/14 on Windows;
- [ ] all six modified cooked packages round-trip;
- [ ] retoc emits the three IoStore containers;
- [ ] release ZIP packages as `Roboquest_WeaponFoundry_v0.1.0-rc1.zip`.

## Game smoke

- [ ] game reaches title screen;
- [ ] ordinary Foundry affix purchase works;
- [ ] six-affix cap blocks a seventh purchase;
- [ ] vanilla perfume/enchant offer still works;
- [ ] native Raycast weapon + Seeker becomes a homing projectile;
- [ ] native projectile Seeker remains normal;
- [ ] representative widened alt-fire works on a previously unsupported chassis;
- [ ] existing Phase 3 monster composition still behaves.

## Persistence

- [ ] Foundry-added ordinary affixes survive save/quit/reload;
- [ ] Power Cell debit survives;
- [ ] state survives a level/save boundary.

## Multiplayer

- [ ] host Foundry purchase replicates to client;
- [ ] client Foundry purchase is server-validated and visible to host;
- [ ] Power Cells debit once;
- [ ] composed child attacks agree between peers.

## Post-RC / 1.0 blockers

- [ ] exact ground-donor row enumeration;
- [ ] donor selection/consumption GRAFT UX;
- [ ] deterministic Smith/editor UX;
- [ ] modifier-instance provenance for deliberate duplicate spawn/proc affixes.
