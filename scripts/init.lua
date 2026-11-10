-- Entry point for the Vagrant Story PopTracker pack.
-- Lua API: https://github.com/black-sliver/PopTracker/blob/master/doc/PACKS.md#lua-interface

ENABLE_DEBUG_LOG = false

local variant = Tracker.ActiveVariantUID
IS_ITEMS_ONLY = variant:find("items_only") ~= nil
print("Vagrant Story tracker, variant: ", variant)

-- Logic (room graph flood fill)
ScriptHost:LoadScript("scripts/logic.lua")

-- Items
Tracker:AddItems("items/keys_sigils.json")
Tracker:AddItems("items/grimoires.json")
Tracker:AddItems("items/breakarts.json")
Tracker:AddItems("items/blades.json")
Tracker:AddItems("items/chain.json")
Tracker:AddItems("items/settings.json")

if not IS_ITEMS_ONLY then
    Tracker:AddMaps("maps/maps.json")

    local map_files = {
        "prologue", "wine_cellar", "catacombs", "sanctum", "undercity_west", "undercity_east",
        "town_centre_west", "town_centre_south", "town_centre_east",
        "city_walls_west", "city_walls_south", "city_walls_east", "city_walls_north",
        "the_keep", "temple_of_kiltia", "snowfly_forest", "snowfly_forest_east", "limestone_quarry",
        "abandoned_mines_b1", "abandoned_mines_b2", "iron_maiden_b1", "iron_miden_b2", "iron_miden_b3",
        "great_cathedral_B1", "great_cathedral_L1", "great_cathedral_L2", "great_cathedral_L3",
        "great_cathedral_L4", "great_cathedral_dome", "forgotten_pathway", "escapeway", "ashley",
    }
    for _, f in ipairs(map_files) do
        Tracker:AddLocations("locations/" .. f .. ".json")
    end
end

-- Layouts
Tracker:AddLayouts("layouts/items.json")
Tracker:AddLayouts("layouts/broadcast.json")
if IS_ITEMS_ONLY then
    Tracker:AddLayouts("layouts/tracker_items_only.json")
else
    Tracker:AddLayouts("layouts/tracker.json")
end

-- Archipelago auto-tracking
ScriptHost:LoadScript("scripts/autotracking/archipelago.lua")
