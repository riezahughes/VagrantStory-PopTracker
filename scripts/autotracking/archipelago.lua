-- Archipelago auto-tracking for Vagrant Story.
-- ITEM_MAPPING / LOCATIONS_MAPPING / BREAKART_LOCATIONS are generated from the AP world (scripts/generated/mapping.lua).

ScriptHost:LoadScript("scripts/generated/mapping.lua")

CUR_INDEX = -1
SLOT_DATA = nil

local DEBUG = ENABLE_DEBUG_LOG

local function dbg(...)
    if DEBUG then
        print(...)
    end
end

local function each_path(p, fn)
    if type(p) == "table" then
        for _, x in ipairs(p) do
            fn(x)
        end
    else
        fn(p)
    end
end

local function reset_item(code, kind)
    local obj = Tracker:FindObjectForCode(code)
    if not obj then
        dbg("onClear: no item object for", code)
        return
    end
    if kind == "consumable" then
        obj.AcquiredCount = 0
    else
        obj.Active = false
    end
end

local function set_toggle(code, value)
    local obj = Tracker:FindObjectForCode(code)
    if obj then
        obj.Active = value and true or false
    end
end

function onClear(slot_data)
    SLOT_DATA = slot_data
    CUR_INDEX = -1

    -- locations back to unchecked
    for _, paths in pairs(LOCATIONS_MAPPING) do
        each_path(paths, function(path)
            local obj = Tracker:FindObjectForCode(path)
            if obj then
                obj.AvailableChestCount = obj.ChestCount
            else
                dbg("onClear: unknown location", path)
            end
        end)
    end

    -- items back to empty
    local done = {}
    for _, v in pairs(ITEM_MAPPING) do
        if not done[v[1]] then
            done[v[1]] = true
            reset_item(v[1], v[2])
        end
    end
    for _, code in pairs(BREAKART_LOCATIONS) do
        reset_item(code, "toggle")
    end

    -- abilities the game grants from the start (not in the item pool)
    for _, code in ipairs(START_ITEMS) do
        set_toggle(code, true)
    end

    -- settings from slot data
    local o = slot_data and slot_data["options"]
    if not o then
        return
    end
    if o.progression_option ~= nil then
        set_toggle("opt_open", o.progression_option == 1)
    end
    if o.open_world_option ~= nil then
        local start = Tracker:FindObjectForCode("start_0") -- progressive item shares one object across stage codes
        if start then
            start.CurrentStage = tonumber(o.open_world_option) or 0
        end
    end
    if o.include_prologue ~= nil then
        set_toggle("prologue", o.include_prologue == 1)
    end
    if o.include_time_trial ~= nil then
        set_toggle("timetrial", o.include_time_trial == 1)
    end
    if o.include_new_game_plus ~= nil then
        set_toggle("ngplus", o.include_new_game_plus ~= 0)
    end
    if o.roomsanity ~= nil then
        set_toggle("roomsanity", o.roomsanity == 1)
    end
    if o.panelsanity ~= nil then
        set_toggle("panelsanity", o.panelsanity == 1)
    end
    -- Teleport / Rood Inverse: option value 1 = "on" (you simply have it); 2 = in the item pool (arrives as an item)
    if o.include_teleport ~= nil then
        set_toggle("teleport", o.include_teleport == 1)
    end
    if o.include_new_game_plus ~= nil then
        set_toggle("rood_inverse", o.include_new_game_plus == 1)
    end
    if o.blood_sin_quantity ~= nil then
        local q = tonumber(o.blood_sin_quantity)
        local bs = Tracker:FindObjectForCode("blood_sin_total")
        if bs then
            bs.AcquiredCount = q
        end
        -- the Blood Sin Piece counter can't go past what the seed contains
        local bsp = Tracker:FindObjectForCode("blood_sin_piece")
        if bsp then
            bsp.MaxCount = q
        end
    end
end

function onItem(index, item_id, item_name, player_number)
    if index <= CUR_INDEX then
        return
    end
    CUR_INDEX = index

    local v = ITEM_MAPPING[item_id]
    if not v then
        dbg("onItem: unmapped item", item_id, item_name)
        return
    end
    local obj = Tracker:FindObjectForCode(v[1])
    if not obj then
        dbg("onItem: no object for", v[1])
        return
    end
    if v[2] == "consumable" then
        obj.AcquiredCount = obj.AcquiredCount + obj.Increment
    else
        obj.Active = true
    end
end

function onLocation(location_id, location_name)
    local paths = LOCATIONS_MAPPING[location_id]
    if paths then
        -- some checks (grimoire pickups) appear both under their room and on the Ashley tab
        each_path(paths, function(path)
            local obj = Tracker:FindObjectForCode(path)
            if obj then
                if obj.AvailableChestCount > 0 then
                    obj.AvailableChestCount = obj.AvailableChestCount - 1
                end
            else
                dbg("onLocation: no location object for", path)
            end
        end)
    else
        dbg("onLocation: unmapped location", location_id, location_name)
    end

    -- the Credits goal toggle in Settings
    local ba = BREAKART_LOCATIONS[location_id]
    if ba then
        set_toggle(ba, true)
    end
end

Archipelago:AddClearHandler("vs clear handler", onClear)
Archipelago:AddItemHandler("vs item handler", onItem)
Archipelago:AddLocationHandler("vs location handler", onLocation)
