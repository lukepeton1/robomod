# Uninstall

Remove only these files from `RoboQuest/RoboQuest/Content/Paks/Mods`:

- `WeaponFoundry_P.pak`
- `WeaponFoundry_P.ucas`
- `WeaponFoundry_P.utoc`

The release ZIP includes `Install/uninstall.cmd` to do this automatically.

Weapon Foundry's build scripts never modify the original Roboquest containers in place.

During development, save compatibility of future grafted multi-affix weapon state remains a validation item. Before testing experimental graft/save builds, keep a backup of any profile/run save you care about.
