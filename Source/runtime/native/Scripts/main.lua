-- MomentumOverhaul UE4SS Lua bootstrap (UTF-8 without BOM).
-- No per-frame Lua movement logic, actor transforms, or RPCs here.

local function announce(s)
    print("[MomentumOverhaul] " .. tostring(s))
end

local function script_root()
    local ok, info = pcall(function() return debug.getinfo(1, "S").source end)
    if ok and type(info) == "string" then
        local normalized = info:gsub("^@", ""):gsub("\\", "/")
        local root = normalized:match("^(.*)/Scripts/[^/]+$")
        if root then return root end
    end
    local ok_dirs, dirs = pcall(IterateGameDirectories)
    if ok_dirs and dirs and dirs.Game and dirs.Game.Binaries and dirs.Game.Binaries.Win64 then
        local win64 = dirs.Game.Binaries.Win64.__absolute_path
        if type(win64) == "string" then
            return win64:gsub("\\", "/") .. "/ue4ss/Mods/MomentumOverhaul"
        end
    end
    return nil
end

local root = script_root()
if not root then
    announce("ERROR: could not locate installed mod directory.")
    return
end

local config_path = root .. "/config/momentum.ini"
do
    local existing = io.open(config_path, "r")
    if existing then
        existing:close()
    else
        local output = io.open(config_path, "w")
        if output then
            output:write("# Default observation-only, set active=1 explicitly after verification.\n")
            output:write("active=0\n")
            output:close()
        end
    end
end

local loaded = false
local slide_hook_pre = nil
local slide_hook_post = nil

local function bootstrap()
    if loaded then return true end

    local movement_class = StaticFindObject("/Script/RoboQuest.RoboquestMovementComponent")
    local player_class = StaticFindObject("/Script/RoboQuest.Character_Player")
    if not movement_class or not movement_class:IsValid()
        or not player_class or not player_class:IsValid() then
        announce("Native classes are not loaded yet; retrying.")
        return false
    end

    local movement_cdo = movement_class:GetCDO()
    if not movement_cdo or not movement_cdo:IsValid() then
        announce("Movement component CDO is not ready.")
        return false
    end

    local movement_address = movement_class:GetAddress()
    local player_address = player_class:GetAddress()
    local cdo_address = movement_cdo:GetAddress()
    if type(movement_address) ~= "number" or type(player_address) ~= "number"
        or type(cdo_address) ~= "number" then
        announce("Could not resolve native class/CDO addresses.")
        return false
    end

    local binding_file, error_text = io.open(root .. "/runtime-bindings.ini", "w")
    if not binding_file then
        announce("ERROR: cannot write runtime bindings: " .. tostring(error_text))
        return false
    end
    binding_file:write("schema=1\n")
    binding_file:write(string.format("movement_class=0x%X\n", movement_address))
    binding_file:write(string.format("player_class=0x%X\n", player_address))
    binding_file:write(string.format("movement_cdo=0x%X\n", cdo_address))
    binding_file:close()

    local dll = root .. "/native/main.dll"
    if not package or not package.loadlib then
        announce("ERROR: Lua package.loadlib is unavailable in this UE4SS build.")
        return false
    end

    local native_loader, load_error = package.loadlib(dll, "luaopen_momentum_native")
    local native_uninstall, uninstall_error =
        package.loadlib(dll, "luaopen_momentum_native_uninstall")
    local native_slide_end, slide_end_error =
        package.loadlib(dll, "luaopen_momentum_slide_end")

    if not native_loader then
        announce("ERROR: native DLL load failed: " .. tostring(load_error))
        return false
    end
    if not native_uninstall then
        announce("ERROR: native uninstall export missing: " .. tostring(uninstall_error))
        return false
    end
    if not native_slide_end then
        announce("ERROR: native PowerSlide end export missing: " .. tostring(slide_end_error))
        return false
    end

    local ok, result = pcall(native_loader)
    if not ok then
        announce("ERROR: native DLL bootstrap failed: " .. tostring(result))
        return false
    end

    local function install_slide_end_hook_when_player_exists()
        if slide_hook_pre then return end

        local player = FindFirstOf("Character_Player")
        if not player or not player:IsValid() then
            if ExecuteInGameThreadWithDelay then
                ExecuteInGameThreadWithDelay(1000, install_slide_end_hook_when_player_exists)
            end
            return
        end

        local hook_ok, pre_id, post_id = pcall(
            RegisterHook,
            "/Script/RoboQuest.Character_Player:OnEndPowerSlide",
            function()
                local event_ok, event_error = pcall(native_slide_end)
                if not event_ok then
                    announce("PowerSlide end latch callback failed: " .. tostring(event_error))
                end
            end
        )

        if not hook_ok then
            announce("PowerSlide end hook deferred/failed: " .. tostring(pre_id))
            if ExecuteInGameThreadWithDelay then
                ExecuteInGameThreadWithDelay(1000, install_slide_end_hook_when_player_exists)
            end
            return
        end

        slide_hook_pre = pre_id
        slide_hook_post = post_id
        announce("PowerSlide end hook installed after player construction.")
    end

    loaded = true
    if ExecuteInGameThreadWithDelay then
        ExecuteInGameThreadWithDelay(1000, install_slide_end_hook_when_player_exists)
    else
        install_slide_end_hook_when_player_exists()
    end
    local status = io.open(root .. "/runtime-status.txt", "r")
    if status then
        announce(status:read("*l") or "native loader returned")
        status:close()
    else
        announce("Native DLL returned; no status file was produced.")
    end

    if ModRef then
        ModRef.OnUnload = function()
            if slide_hook_pre then
                pcall(
                    UnregisterHook,
                    "/Script/RoboQuest.Character_Player:OnEndPowerSlide",
                    slide_hook_pre,
                    slide_hook_post
                )
                slide_hook_pre = nil
                slide_hook_post = nil
            end
            pcall(native_uninstall)
        end
    end

    return true
end

local attempts = 0
local function try_bootstrap()
    attempts = attempts + 1
    local ok, result = pcall(bootstrap)
    if not ok then announce("Bootstrap error: " .. tostring(result)) end

    if not loaded and attempts < 20 and ExecuteInGameThreadWithDelay then
        ExecuteInGameThreadWithDelay(1000, try_bootstrap)
    elseif not loaded then
        announce("Bootstrap could not initialize. Vanilla movement remains unchanged.")
    end
end

if ExecuteInGameThreadWithDelay then
    ExecuteInGameThreadWithDelay(1000, try_bootstrap)
else
    try_bootstrap()
end
