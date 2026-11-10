-- Vagrant Story logic.
--
-- The world is a graph of rooms joined by exits; some exits need keys, sigils, the Blood Sin Pieces, or a boss
-- room to be reachable (see Rules.py in the AP world). scripts/generated/graph.lua holds that graph, generated
-- straight from the world source. Here we flood-fill it from the start room with the items the tracker currently
-- has, and expose the result to location access rules as  $vs_room|<room_slug>.
--
-- Mirrors the AP world exactly, including:
--   * vanilla vs open progression (different rule sets, different start room)
--   * time trial sigil rules (always in vanilla, only with "timetrial" setting in open)
--   * "player_has_location(boss)" rules  ->  "that boss room is reachable"
--   * Blood Sin Piece gate: The Atrium -> Dome
-- (Chain unlocks and break arts are plain item toggles in the bottom panel; no logic.)

VS = VS or {}
ScriptHost:LoadScript("scripts/generated/graph.lua")

local function cnt(code)
    return Tracker:ProviderCountForCode(code)
end

local function has(code)
    return cnt(code) > 0
end

local function evaluate(expr, reached)
    local t = expr[1]
    if t == "item" then
        return has(expr[2])
    elseif t == "room" then
        return reached[expr[2]] == true
    elseif t == "bsall" then
        return cnt("blood_sin_piece") >= cnt("blood_sin_total")
    elseif t == "and" then
        for i = 2, #expr do
            if not evaluate(expr[i], reached) then
                return false
            end
        end
        return true
    end
    return false
end

local cache_sig = nil
local cache_reached = {}

local function start_room(open)
    if not open then
        return VS.VANILLA_START
    end
    for i = 0, #VS.OPEN_STARTS - 1 do
        if has("start_" .. i) then
            return VS.OPEN_STARTS[i + 1]
        end
    end
    return VS.OPEN_STARTS[1]
end

-- Flood fill; cached until any logic-relevant item/setting changes.
function vs_reached()
    local parts = {}
    for i, code in ipairs(VS.SIG_CODES) do
        parts[i] = cnt(code)
    end
    local sig = table.concat(parts, ",")
    if sig == cache_sig then
        return cache_reached
    end

    local open = has("opt_open")
    local timetrial = has("timetrial")
    local reached = {}
    reached[start_room(open)] = true

    local changed = true
    while changed do
        changed = false
        for _, e in ipairs(VS.EDGES) do
            if reached[e.f] and not reached[e.t] then
                local rule
                if open then
                    rule = (timetrial and e.tt) or e.o
                else
                    rule = e.v
                end
                if rule == nil or evaluate(rule, reached) then
                    reached[e.t] = true
                    changed = true
                end
            end
        end
    end

    cache_sig = sig
    cache_reached = reached
    return reached
end

-- $vs_room|<slug>
function vs_room(slug)
    return vs_reached()[slug] == true
end

-- Ashley tab checks -------------------------------------------------------------------------
-- Thresholds from set_break_art_rules / set_chain_unlock_rules: 0, 20%, 40%, 60% of the Blood Sin Pieces in the seed.
local function tier(total, n)
    local t = { 0, math.max(1, math.floor(total / 5)), math.max(1, math.floor(2 * total / 5)), math.max(1, math.floor(3 * total / 5)) }
    return t[n]
end

-- $vs_chain|<n>   chain unlocks 1-7 free, 8-15 need ~20%, 16-22 need ~40% of the Blood Sin Pieces
function vs_chain(n)
    n = tonumber(n)
    local total = cnt("blood_sin_total")
    local have = cnt("blood_sin_piece")
    if n <= 7 then
        return true
    elseif n <= 15 then
        return have >= math.max(1, math.floor(total / 5))
    end
    return have >= math.max(1, math.floor(2 * total / 5))
end

-- $vs_break|<weapon_slug>|<level>
-- Mirrors set_break_art_rules + set_break_art_workshop_prerequisite: ANY blade of that weapon type (Bare Hands = Knuckles),
-- the Blood Sin tier for the level, and a reachable workshop (open mode starts in one).
function vs_break(weapon, level)
    level = tonumber(level)
    if not has("blade_" .. weapon) then
        return false
    end
    -- no workshop reachable = no crafting = no break arts
    local reached = vs_reached()
    local workshop = false
    for _, ws in ipairs(VS.WORKSHOPS) do
        if reached[ws] then
            workshop = true
            break
        end
    end
    if not workshop then
        return false
    end
    local need = tier(cnt("blood_sin_total"), level)
    return need == 0 or cnt("blood_sin_piece") >= need
end
