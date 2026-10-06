# Phase 3 deterministic composition diagnostic

This is a **temporary diagnostic build**, not the intended progression/economy design.

Phase 1 and Phase 2 proved that DataTable and cooked Kismet overrides load. Phase 3 makes the next behavior test deterministic so a tester does not have to wait for random loot.

## Diagnostic starter gun

The `HandGun` weapon row is temporarily forced to exactly six affixes:

- Fragments (`Fragmentation`)
- Seeker (`Homing`)
- Burn
- Explosive (`ExplosiveBlank`)
- Freewheel (`FreeShot`)
- Buckshot (`AutoShotgun`)

The vanilla tooltip exposes six affix slots, so the diagnostic intentionally stays at six.

The `PF_Handgun` skill is temporarily changed from Raycast to the native generic Projectile path with:

- `TargetDetection = Projectile`
- `Speed = 12500`
- `CollisionSize = 10`
- `GravityScale = 0`

The speed/collision values are the otherwise-unused `ProjectileSpeed` and `ProjectileCollisionSize` values shipped on the vanilla Homing/Seeker affix.

## What this single weapon tests

### Fragments + Seeker

If generated fragments visibly steer toward enemies, `SpawnCustomProjectiles` is inheriting the skill's native homing state. If only the parent projectile homes, Phase 4 needs to explicitly copy guidance fields onto fragment actors.

### Burn + Fragments

Phase 2 explicitly changes child GameplayTags to come from the originating skill. Burn on fragment impacts is therefore a direct test of that patch.

### Explosive + Fragments

Explosive is carried as a native skill gameplay tag. Exploding fragment impacts would demonstrate that the same semantic propagation works for payload behavior, not just status.

### Freewheel + Buckshot

Vanilla Freewheel calls `APlayerSkill.UseSkill()` after setting `bNoCostForNextShot`. Buckshot modifies the same native skill's hit amount/spawn geometry. A Freewheel proc should therefore duplicate the complete Buckshot-transformed shot rather than one naked bullet.

## What not to infer

This diagnostic does **not** prove the final raycast-to-projectile resolver. The HandGun is statically converted only for testing. Final Seeker support on arbitrary raycast weapons still needs a runtime conditional conversion tied to the modifier.

The diagnostic also does not implement grafting, economy, rarity budgets, or save semantics.

## Reverting

Running the Phase 2 builder again restores the normal HandGun/skill while retaining the verified Phase 1 + Phase 2 Weapon Foundry changes.


## Manual in-game result — 2026-10-06

The Phase 3 diagnostic builder completed and Roboquest launched successfully with the deterministic six-affix HandGun installed.

Observed in-game behavior:

- parent projectile homing: confirmed;
- Fragmentation spawning: confirmed;
- Burn behavior from the composed weapon/fragments: confirmed;
- explosive behavior from the composed weapon/fragments: confirmed;
- Freewheel repeating the Buckshot-transformed shot: confirmed;
- performance/stability: no obvious infinite recursion, freeze, severe frame-rate collapse, or crash observed;
- child-fragment homing: probable but not yet visually isolated from the parent's homing behavior.

This is the first direct in-game confirmation that several formerly mutually exclusive/native effects can coexist on one weapon and execute through Roboquest's existing skill/projectile systems rather than a parallel custom damage implementation.

### Child-homing isolation test

To verify child homing without changing the build, fire the parent projectile into a wall or ground surface beside a live enemy. The parent projectile terminates on the surface. If the spawned fragments then curve toward the nearby target, homing is active on the child projectiles independently of the parent.
