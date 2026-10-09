# Momentum startup crash isolation

Status: **Native movement startup is not yet proven stable in Roboquest.**
The latest known real-world failure is `Can't find ClassConstructor for class /Game/Blueprint/Player/BP_APlayer.BP_APlayer_C` during player Blueprint loading, **before any target CalcVelocity samples**. Do not treat the lack of early movement samples as a physics-core failure, and do not assume the deferred hook resolved the crash without a new in-game test.

## Controlled diagnostic modes

All modes use the same reversible test runner. Select one mode per run; never combine flags.

| Invocation (PowerShell from repository root) | Staged UE4SS? | Momentum Lua? | Native DLL? | Patches movement vtable? | Runtime artifact ZIP required? |
| --- | --- | --- | --- | --- | --- |
| `.\tools\windows\run-momentum-runtime-test.cmd -Baseline` | No | No | No | No | No |
| `.\tools\windows\run-momentum-runtime-test.cmd -LoaderOnly` | Yes | No | No | No | No |
| `.\tools\windows\run-momentum-runtime-test.cmd -BootstrapOnly` | Yes | Yes, reflection-only | No | No | No |
| `.\tools\windows\run-momentum-runtime-test.cmd` | Yes | Yes | Yes, observe mode | Yes; no velocity edits | Yes |
| `.\tools\windows\run-momentum-runtime-test.cmd -Active` | Yes | Yes | Yes, active mode | Yes; edits velocity | Yes |

**Start with `-LoaderOnly`, not `-Active`.** The game was previously known to run without this temporary loader, so the isolated loader is the highest-value immediate comparison. If it crashes, do a `-Baseline` control before changing any native code.

The pinned UE4SS development asset is `zDEV-UE4SS_v3.0.1-1161-g6eb3d9bc.zip`, SHA-256 `580a244bc30352cfd0d0019c4c63726c2bddd5bb04ef91f985df237aa81b06e9`. The runner rejects a changed asset/digest. This isolates the tested UE4SS build rather than silently switching to a newer experimental loader.

## Isolation guarantees and limitations

- The loader-only mode does **not** require or look for `MomentumOverhaul-runtime.zip`.
- The baseline backs up UE4SS/proxy DLLs and stages no loader.
- Loader-only stages the pinned UE4SS and explicitly disables bundled mods in both `mods.txt` and `mods.json`, removing `enabled.txt` markers **from the temporary package only**.
- Bootstrap-only stages the checked-in `Source/runtime/native/Scripts/main.lua` and its config, but **no native DLL**. It waits for a non-default `Character_Player` with a usable world, reads UClass/CDO pointers and writes `runtime-bindings.ini`, then stops without patching any vtable.
- Observe mode uses the compiled GitHub Actions artifact and calls the guarded native hook only after a live player/world is found. Vanilla velocity is not replaced. The DLL validates the exact executable fingerprint and hook target.
- The baseline cannot disable modifications injected by entirely separate external tools, or proxy hooks installed outside the game Win64 directory.
- Disabling UE4SS Lua/C++ bundled mods does **not** disable internal UE4SS engine hooks needed for UE4SS to initialize; loader-only specifically tests those.
- Multiplayer/co-op and active physics tests remain prohibited until observe-mode startup and state telemetry are clean.

The supported game binary is `RoboQuest-Win64-Shipping.exe` with SHA-256 `158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f`. The runner refuses native/bootstrap tests on a different game build.

## Setup and diagnostics

In PowerShell:

```powershell
cd "C:\path\to\robomod"
git switch feature/movement-overhaul
git pull --ff-only
.\tools\windows\run-momentum-runtime-test.cmd -LoaderOnly
```

Enter the same game/basecamp state in which the crash previously occurred; quit normally after approximately 30 seconds. The runner collects UE4SS and fresh Roboquest logs, detects common fatal signatures, restores original files, and produces:

```text
handoff\momentum-runtime-test.zip
```

The diagnostic manifest contains `mode`, `status`, `fatal_error_detected`, `game_files_restored`, runtime artifact SHA (null for isolation modes), game executable hash and UE4SS archive SHA.

For observe mode, download the `MomentumOverhaul-runtime` artifact from the latest successful **Build Momentum Runtime** GitHub Actions run and place it at `handoff\MomentumOverhaul-runtime.zip`. The artifact should contain:

```text
Scripts/main.lua
config/momentum.ini
native/main.dll
runtime-build.txt
```

Use only an artifact whose `runtime-build.txt` `build_commit` matches the intended source version. The test runner accepts either `native/main.dll` or the legacy `dlls/main.dll`, but new builds use `native/main.dll`.

If restoration was interrupted, **close Roboquest** and run:

```powershell
.\tools\windows\cleanup-movement-runtime-probe.cmd
```

The cleanup script uses a cached/statically discovered shipping executable path (or accepts `-GameExePath`) and preserves the backup if any original file cannot be safely recovered. Never manually delete `.momentum-runtime-probe-backup` without inspecting its contents.

## Interpreting outcomes

| Observed result | What it establishes | Next investigation |
| --- | --- | --- |
| Baseline crashes | Failure occurs without this staged UE4SS installation | Verify game integrity, unrelated loader/proxy conflicts |
| Baseline passes; loader-only crashes | The crash can occur without Momentum Lua/native DLL | UE4SS internal hooks, UE4.26 layout, engine loading compatibility |
| Loader-only passes; bootstrap-only crashes | Lua/reflection/startup timing contributes, independently of native vtable patch | `FindFirstOf`, `GetWorld`, `StaticFindObject`, `GetCDO` sequence |
| Bootstrap-only passes; observe crashes | Native DLL loading, hook installation, or hook interactions implicated | Exact global vtable patch timing, thread-safety, ABI and hook dispatch |
| Observe passes with no fatal signatures and valid samples | Startup was stable **for that one run** | Repeat ability/slide telemetry checks before any active test |
| Observe passes; active fails | Startup crash was distinct from active movement-state issues | Check equations and state transitions without touching loader |

A green GitHub Actions run tests build/static logic and staging restoration, **not live game compatibility**. Do not claim the constructor crash is fixed solely because CI passes.
