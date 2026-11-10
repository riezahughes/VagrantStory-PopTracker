# Vagrant Story - Archipelago PopTracker pack

Map tracker + item tracker for the Vagrant Story AP world. Locations, ids and logic are **generated from the AP world
source** (`Locations.py`, `Rules.py`, `Items.py`, `rooms/`), not copied by hand.

## Install
Copy this folder (or a zip of its contents) into `PopTracker/packs/`, open PopTracker, pick *Vagrant Story Archipelago
Map Tracker*, then connect to the AP server with the AP button (slot name + password). Items, checked locations and the
slot options (progression mode, start workshop, roomsanity, panelsanity, NG+, prologue, time trials, Blood Sin count)
are picked up automatically; every setting can also be toggled by hand in *Settings*.

## What it shows
- Top tabs per area (floors nested), one square per room that has checks. Red = unreachable, green = reachable,
  grey = done. Hover/click a room for its checks (Room Entered, Chest, Boss, Grimoire, floor traps, ...).
- **Ashley** tab: the 22 chain unlock checks, 40 break art checks (Blood Sin gated), the 54 grimoire pickups, and the
  Credits goal. Green/red here follows the AP rules (Blood Sin tiers, "a workshop must be reachable" for break arts, Chest Key chests, room access).
  Break arts also need ANY blade of that weapon type (Bare Hands = Knuckles), exactly as the world's `has_group` gate.
- Bottom row = items you hold, on one page, all ticked from items **received** from the server: Blades (one icon per
  weapon type, ticks when any blade of that type arrives) and Break Arts (the 40 named
  arts), Chain and Defence Abilities (14 + 14, red / blue; the 6 the game grants at the start are ticked on connect),
  Blood Sin counter, Grimoires, Keys | Sigils (A-Z), Settings (incl. Teleport / Rood Inverse, set from your yaml).
- Room access uses the same graph the generator uses: a flood fill from the start room with the keys/sigils you hold.

## Updating after the world changes
```
python tools/generate_pack.py            # regenerates items, locations, ids, logic data, layouts
python tools/validate_pack.py            # static consistency checks
python tools/test_logic.py               # needs: pip install lupa  (Lua logic vs a Python model of Rules.py)
```
The generator never overwrites an image that already exists.

## Finishing the maps
Every map currently uses a generated placeholder (`images/maps/*.png`, rooms in an auto grid). To use real art:
1. Put your screenshot at `images/maps/<key>.png` (list: `IMAGES_NEEDED.md`).
2. Open `tools/map_picker.html` in a browser, load `tools/rooms_by_map.json`, choose the map, load the image, and click
   where each room's marker belongs. Copy the JSON it prints into `tools/map_layout.json`
   (load the existing file first with the second file box to add maps one at a time).
3. `python tools/generate_pack.py`.

## Notes / assumptions
- "Boss defeated" rules in the world (`player_has_location`) are treated as "that boss room is reachable", same as
  Archipelago's own logic.
- Key/sigil *unlock* locations and the Teleport unlock are never created by the world, so they are not tracked.
- Open mode start workshop is `list_of_starting_points[open_world_option]` exactly as `create_regions` does it.
