# Install

Weapon Foundry is packaged as a standard Roboquest UE4.26 IoStore mod:

- `WeaponFoundry_P.pak`
- `WeaponFoundry_P.ucas`
- `WeaponFoundry_P.utoc`

Copy all three files into:

`RoboQuest/RoboQuest/Content/Paks/Mods`

Create the `Mods` folder if it does not exist.

The release ZIP also includes `Install/install.cmd`. Pass the game's `Paks` directory as the first argument or run it interactively.

Do not put the files beside the base `pakchunk*.pak/.ucas/.utoc` files without the `Mods` subfolder.

## Steam

Typical path:

`C:\Program Files (x86)\Steam\steamapps\common\Roboquest\RoboQuest\Content\Paks`

Non-default Steam libraries are supported; point the installer at the corresponding `Paks` folder.

## Xbox / Microsoft Store

The target is the game's writable `RoboQuest/Content/Paks/Mods` folder. Store packaging and permissions vary by installation, so this path still requires an installation-specific validation pass before the project claims one-click Game Pass support.

## First launch

Keep other Roboquest content mods disabled for the first smoke test. If Roboquest reaches the title screen, enable other mods one at a time.
