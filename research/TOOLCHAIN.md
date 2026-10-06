# Verified Roboquest modding toolchain

Last checked: 2026-10-06.

This document records the packaging workflow we will target for Weapon Foundry. It distinguishes the Roboquest-specific community workflow from generic Unreal advice.

## Verified current Roboquest workflow

The July 2026 Roboquest data-table tutorial by reymo documents the following process for the current game:

1. Convert the installed IoStore containers to legacy editable packages with `retoc to-legacy --version UE4_26`.
2. Treat Roboquest as Unreal Engine 4.26.x (the guide identifies 4.26.2.0).
3. Edit cooked legacy `.uasset` packages in UAssetGUI.
4. Stage the modified legacy packages under their original virtual path, e.g. `Staging/RoboQuest/Content/Data/...`.
5. Preserve the package pair: edited DataTables have both a `.uasset` and corresponding `.uexp`.
6. Rebuild IoStore containers with `retoc to-zen --version UE4_26 .\Staging <ModName>_P.utoc`.
7. Install the generated patch triplet under `RoboQuest/RoboQuest/Content/Paks/Mods`.

Primary source:
- https://docs.google.com/document/d/e/2PACX-1vT-PzJN22YMLECFo8Uvjg0CuOnub-RnNDmWUtKd3v4Jb4wnDJc8RHNOgYw268gBT9uRUsWuOW4WTwu7/pub
- Tutorial mirror/announcement: https://www.nexusmods.com/roboquest/images/1

The tutorial's own worked example edits `DT_PlayerSkills`, including target detection, projectile speed, homing, VFX and trails. This independently agrees with the fields in our installed-build JSON catalog.

## Verified release/install shape

Roboquest Redux v1.0.5 (updated May 2026) ships three container files and installs them in the `Mods` directory:

- `.pak`
- `.ucas`
- `.utoc`

Its documented Steam path is:

`RoboQuest/RoboQuest/Content/Paks/Mods`

and its PC Xbox App instructions likewise use a `Paks/Mods` directory below the accessible Roboquest content tree.

Source:
- https://www.nexusmods.com/roboquest/mods/1?tab=docs

A second 2026 Roboquest mod documents the same three-file install model:
- https://www.nexusmods.com/roboquest/mods/2

## Why raw FModel exports are not enough to patch

Generic IoStore modding documentation warns that FModel's directly exported IoStore/Zen assets are not necessarily suitable for UAssetGUI editing. The safe route for this project is therefore to obtain **legacy-converted** `.uasset + .uexp` packages from `retoc to-legacy`, edit those, and convert the staged tree back to Zen.

Reference:
- https://github.com/Dmgvol/UE_Modding/blob/main/TheBasics/ExtractingIoStore.md

## UAssetGUI automation

UAssetGUI supports command-line JSON conversion, including `tojson`, and its underlying UAssetAPI format is a viable basis for repeatable DataTable patches rather than hand-clicking thousands of fields.

Reference:
- https://github.com/atenfyr/UAssetGUI

For Weapon Foundry the intended build pipeline is therefore:

```text
installed Roboquest IoStore
        |
        | retoc to-legacy --version UE4_26
        v
clean legacy extraction (.uasset + .uexp)
        |
        | deterministic patch scripts / UAssetAPI JSON roundtrip
        v
project staging tree
RoboQuest/Content/...
        |
        | retoc to-zen --version UE4_26
        v
WeaponFoundry_P.pak
WeaponFoundry_P.ucas
WeaponFoundry_P.utoc
        |
        v
RoboQuest/RoboQuest/Content/Paks/Mods
```

## Important retoc caution

There is an open retoc issue from a Roboquest/UE4.26 user reporting that a particular `to-zen` workflow created containers that did not work for their UE4SS actor mod. That does **not** invalidate the 2026 Roboquest data-table tutorial—the tutorial explicitly uses retoc successfully—but it means our build scripts must validate the exact generated containers and must not treat a zero exit code as proof that a runtime-logic package loads correctly.

Reference:
- https://github.com/trumank/retoc/issues/34

Consequences for this project:

- use the Roboquest-specific 2026 command sequence as the baseline;
- preserve exact virtual package paths;
- validate resulting containers with retoc;
- require an actual game-launch smoke test before release;
- do not assume a Blueprint-bytecode modification packs correctly merely because DataTable overrides do.

## Repository policy

`vanilla-json/` is research input only.

The repository must not accumulate a full vanilla legacy extraction. Build scripts should instead accept a local clean-extraction directory and copy only the required source packages into a project staging directory before patching.

The final release must contain only the mod's modified/original project packages and generated containers, not a redistributable dump of Roboquest content.
