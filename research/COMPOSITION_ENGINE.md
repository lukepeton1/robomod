# Composition engine architecture

## Status

This is the implementation contract for Weapon Foundry's generalized effect composition.

It is grounded in the installed-build DataTables and Blueprint signatures. It is **not** a claim that the runtime patch has already been installed; the cooked Blueprint packages still need to be modified and game-tested.

## Why a generalized engine fits Roboquest

The installed build already exposes most of the abstractions needed:

- weapon chassis own skill/stat managers;
- weapon affixes are behavior objects with `OnApply`/`OnRemove` and skill callbacks;
- several affixes subscribe to skill registration and skill-use events;
- trigger affix bases already maintain state and deterministic `RandomStream` values;
- on-damage affixes receive `RQDamageInfo`;
- Fragmentation receives `ASkill + RQHitResult + AProjectile`;
- Fragmentation constructs `NetworkSkillInfo` and calls `SpawnCustomProjectiles`;
- launch-skill affix bases use `NetworkSkillInfo`, `RQDamageInfo`, and native `GetSkillByClass`;
- the player already has server/multicast weapon-affix mutation RPCs.

Weapon Foundry should therefore extend the native skill/event model rather than introduce a parallel “mod projectile/damage” universe.

## Core data model

### ResolvedWeaponContext

Created/rebuilt only when a weapon's configuration changes.

Fields:

- weapon instance identity;
- chassis row ID;
- primary/secondary skill row IDs;
- ordered modifier instances;
- resolved compatibility conversions;
- precomputed inheritance profiles;
- stack reductions (bounce count, ricochet count, etc.);
- native gameplay tags/status semantics;
- generation/version number for cache invalidation.

This is the expensive static part and must not be reconstructed for every projectile.

### AttackContext

A compact per-trigger/per-child value.

Fields:

- origin weapon instance;
- root skill/action;
- current skill/action;
- shot sequence counter;
- deterministic RNG seed;
- event kind;
- generation depth;
- parent event ID;
- modifier-instance provenance mask/set;
- active passive semantic flags;
- resource state snapshot where required;
- damage ancestry metadata;
- projectile ancestry metadata.

The runtime representation should use compact native-friendly IDs/bitsets rather than strings once implemented.

### ModifierInstance

A modifier instance is:

`(affix row ID, stable instance ordinal, resolved parameters)`

Two copies of Ricochet are two distinct instances. This is what permits useful duplicate stacking while preventing one instance from recursively triggering itself forever.

## Event kinds

The conceptual engine uses:

- `trigger_pull`
- `duplicate_shot`
- `pellet`
- `projectile`
- `pierce_hit`
- `bounce`
- `impact`
- `explosion`
- `fragment`
- `ricochet_hit`
- `alt_fire`
- `summon_attack`
- `kill`
- `reload`

These names are an internal research vocabulary. The in-game UI continues to say Bounce, Fragments, Seeker, Burn, etc.

## Modifier roles

### Passive semantic modifiers

Examples:

- Burn / Cryo / Shock;
- damage-type tags;
- compatible critical semantics;
- Mark/status semantics.

They normally propagate to child damage/attack events without consuming a recursion token.

### Traversal modifiers

Examples:

- Bounce;
- Pierce;
- Seeker;
- Ricochet.

They apply to projectile/raycast traversal as supported by the resolved hit model. A traversal modifier that **spawns** a secondary event, such as a Ricochet child hit, consumes that modifier instance for the branch it created.

### Shot-shape modifiers

Example:

- Buckshot.

They transform one shot operation into multiple hits/pellets. A duplicate shot receives the already-resolved shot shape.

### Spawn/proc modifiers

Examples:

- Freewheel;
- Fragmentation;
- trigger-count explosions;
- launch-skill affixes.

When a modifier creates a child operation, that exact modifier instance is added to the branch's provenance set before the child can evaluate spawn/proc modifiers.

## Provenance rule

**A modifier instance may not create a descendant from a branch in which that same instance has already been consumed.**

This is the primary loop-prevention rule.

It is deliberately more precise than “a Fragment can never fragment”:

- Fragmentation instance A creates fragments -> A is consumed in those branches.
- Fragmentation instance B on the same weapon remains available and may create a second generation.
- Burn, Seeker, Pierce and other non-spawning semantics remain active.
- A Freewheel instance that duplicated a shot cannot duplicate its own duplicate, but another Freewheel instance can.

This creates deep builds without literal self-recursion.

## Hard crash guards

Provenance is the gameplay-semantic safeguard. Separate hard guards exist only for corrupted/unforeseen graphs:

- generous maximum generation depth;
- generous maximum child-event count per root trigger;
- maximum live generated projectiles per owner only as a last-resort stability fuse.

Those limits are not balance knobs and must be set high enough that intentional monster builds remain spectacular.

The reference simulator currently uses:

- generation depth: 12;
- event budget per root trigger: 4096.

These values are provisional until real profiling.

## Deterministic RNG

Proc RNG must not use wall-clock time or independent client state.

A deterministic root seed should be derived from stable gameplay values such as:

- weapon instance/network identity;
- owning player identity;
- shot sequence counter;
- run seed where available.

A child seed is derived from:

- parent seed;
- modifier instance ID;
- child index;
- event kind.

Vanilla Fragmentation and trigger-affix bases already use `RandomStream`, so this follows an existing game pattern.

## Child inheritance

Inheritance is defined by semantics, not by copying every raw property.

A child event receives:

1. semantic/passive flags that are meaningful for its event kind;
2. traversal behavior meaningful for its resolved hit model;
3. still-unconsumed spawn/proc modifier instances whose profile permits that child kind;
4. native source tags/skill metadata required by item/perk/class callbacks.

Examples:

### Seeker + Fragmentation

Fragment children are projectile events, so they receive Seeker and native homing parameters.

### Explosive + Fragmentation

Fragments receive the weapon's compatible explosive payload. The Fragmentation instance is consumed, not the Explosive instance.

### Burn + Ricochet

The ricochet child hit keeps Burn/status semantics. The Ricochet instance that spawned it is consumed for that branch.

### Freewheel + Buckshot

Freewheel duplicates the whole shot operation. The duplicate is then represented with the same resolved Buckshot shot shape.

### Pierce + Explosive

Every eligible collision can emit an explosion while the root projectile continues until its pierce budget is exhausted. Explosion children cannot self-regenerate through the same explosion modifier instance.

## Native event integration strategy

The runtime patch should intercept/extend the smallest native seams.

### Primary skills

On affix application or weapon configuration change, resolve the weapon context and mutate/register native skills in the same manner as existing affixes.

### Fragmentation

Use `BP_WA_Fragmentation` as the first child-projectile implementation. Its existing `GetFragNetworkInfo` + `SpawnCustomProjectiles` path should be extended so generated projectiles receive the resolved child context.

### Trigger-count/luck affixes

Reuse their existing `RandomStream`, `OnSkillTrigger`, `OnUsed`, and firerate-delay machinery. Add provenance checks around child launches rather than replacing their timing code.

### On-damage launch skills

Preserve `RQDamageInfo` and `NetworkSkillInfo` so native damage/item/perk logic continues seeing ordinary Roboquest skills.

### Alt-fire

The existing `AddSecondaryFire` affix base and `SkillInputBP` registration path remain the source of secondary skills. Composition resolves against that skill rather than creating an unrelated mod-only alt-fire object.

## Hit-model resolver

The resolver operates before a weapon context is committed.

It determines whether the requested affix graph can operate on the current skill representation.

Examples:

- Raycast + Bounce: leave raycast if native Bounce supports it.
- Raycast + Pierce: leave raycast if native Pierce supports it.
- Raycast + Ricochet: leave raycast.
- Raycast + Seeker: generate/attach projectile-compatible derivative because homing needs travel time.
- Projectile + Hitscan: use the native Hitscan behavior.

Conversions are cached with the weapon context and never recomputed per shot.

## Native semantics are the API boundary

A composed event must continue to present itself to the rest of Roboquest through native constructs:

- `ASkill`;
- `RQDamageInfo`;
- `RQHitResult`;
- `NetworkSkillInfo`;
- native gameplay tags/status enums;
- native weapon stat manager;
- native projectile actors/pools.

This is what allows items, perks, classes, critical effects, explosion bonuses and elemental callbacks to continue functioning without bespoke compatibility code for every item.

## Performance

The engine must:

- pre-resolve static weapon graphs on configuration changes;
- store compact inherited context with child attacks;
- avoid allocations in hot projectile loops;
- reuse native projectile pools;
- avoid repeated DataTable lookups per child;
- avoid repeated full homing target scans where a cached/pooled target-query path is possible;
- profile projectile count, explosion count, GC, event resolution and homing searches.

The target is to optimize the machinery rather than reduce the spectacle.

## First runtime milestone

The first in-game implementation slice should prove one native end-to-end chain:

1. a normal weapon acquires **Fragments** through an existing/native affix-add transaction;
2. Fragmentation uses the native network projectile path;
3. fragment children inherit **Seeker** and one element;
4. the same Fragmentation instance cannot recursively create infinite descendants;
5. save/quit/reload preserves the affix state;
6. host/client observe the same child projectiles.

Once that works, extend the same context propagation to Bounce, Pierce, Explosive, Ricochet, Freewheel, Buckshot and alt-fire rather than implementing each synergy ad hoc.
