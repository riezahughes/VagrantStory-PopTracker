"""
Generates the data-driven parts of the Vagrant Story PopTracker pack from the AP world source.

    python tools/generate_pack.py [path\\to\\worlds\\vagrantstory]

Writes (relative to the pack root, i.e. the parent of tools/):
    items/*.json                         tracker items (keys, sigils, grimoires, break arts, blades, settings)
    locations/*.json                     one file per map (rooms -> sections, access rules, map markers)
    maps/maps.json                       map definitions
    scripts/generated/*.lua              room graph + rules, AP id -> item/location mappings
    layouts/*.json                       tab layout (areas come from the AREAS table below)
    images/**                         PLACEHOLDER art, only where no file exists yet (never overwrites yours)
    IMAGES_NEEDED.md                     what art is still placeholder / needed
    tools/rooms_by_map.json              input for tools/map_picker.html

Hand-maintained (not touched): manifest.json, scripts/init.lua, scripts/logic.lua,
scripts/autotracking/archipelago.lua, tools/map_layout.json (marker coordinates; missing rooms get an auto grid slot).
"""
import json
import math
import os
import re
import sys

from worlddata import World, DEFAULT_WORLD

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPRITESHEET = os.environ.get("VS_SPRITESHEET", r"C:\Users\Dan\Downloads\iron-weapons.png")

# --------------------------------------------------------------------------------------------
# Presentation tables
# --------------------------------------------------------------------------------------------
# tab label -> list of (map_key, floor label). Order = tab order in the tracker.
AREAS = [
    ("Prologue", [("prologue", "Prologue")]),
    ("Wine Cellar", [("wine_cellar", "Wine Cellar")]),
    ("Catacombs", [("catacombs", "Catacombs")]),
    ("Sanctum", [("sanctum", "Sanctum")]),
    ("Undercity", [("undercity_west", "West"), ("undercity_east", "East")]),
    ("Town Centre", [("town_centre_west", "West"), ("town_centre_south", "South"), ("town_centre_east", "East")]),
    ("City Walls", [("city_walls_west", "West"), ("city_walls_south", "South"), ("city_walls_east", "East"), ("city_walls_north", "North")]),
    ("The Keep", [("the_keep", "The Keep")]),
    ("Temple of Kiltia", [("temple_of_kiltia", "Temple of Kiltia")]),
    ("Snowfly Forest", [("snowfly_forest", "Snowfly Forest"), ("snowfly_forest_east", "East")]),
    ("Limestone Quarry", [("limestone_quarry", "Limestone Quarry")]),
    ("Abandoned Mines", [("abandoned_mines_b1", "B1"), ("abandoned_mines_b2", "B2")]),
    ("Iron Maiden", [("iron_maiden_b1", "B1"), ("iron_miden_b2", "B2"), ("iron_miden_b3", "B3")]),
    (
        "Great Cathedral",
        [
            ("great_cathedral_B1", "B1"),
            ("great_cathedral_L1", "L1"),
            ("great_cathedral_L2", "L2"),
            ("great_cathedral_L3", "L3"),
            ("great_cathedral_L4", "L4"),
            ("great_cathedral_dome", "Dome"),
        ],
    ),
    ("Forgotten Pathway", [("forgotten_pathway", "Forgotten Pathway")]),
    ("Escapeway", [("escapeway", "Escapeway")]),
    ("Ashley", [("ashley", "Ashley")]),
]
MAP_TITLES = {key: f"{tab} - {floor}" if tab != floor else tab for tab, floors in AREAS for key, floor in floors}

# weapon rows for the break-art panel (order = rows) and the sprite cells used for tiers 1-4 on the sheet
WEAPONS = ["Dagger", "Sword", "Great Sword", "Axes & Maces", "Great Axe", "Stave", "Heavy Mace", "Polearm", "Crossbow", "Bare Hands"]
SHEET_CELLS = {  # (col, row) per level, 16px cells on iron-weapons.png. Swap freely - purely cosmetic.
    "Dagger": [(6, 10), (6, 12), (6, 14), (6, 16)],
    "Sword": [(2, 1), (2, 3), (2, 5), (2, 7)],
    "Great Sword": [(7, 1), (7, 3), (7, 5), (7, 7)],
    "Axes & Maces": [(1, 10), (1, 12), (1, 14), (1, 16)],
    "Great Axe": [(2, 10), (2, 12), (2, 14), (2, 16)],
    "Stave": [(20, 1), (20, 3), (20, 5), (20, 7)],
    "Heavy Mace": [(22, 10), (22, 12), (22, 14), (22, 16)],
    "Polearm": [(16, 0), (16, 2), (16, 4), (16, 6)],
    "Crossbow": [(19, 10), (19, 12), (19, 14), (19, 16)],
    "Bare Hands": None,  # not on the sheet -> placeholder fist
}

KEY_COLORS = {
    "crimson": (170, 30, 40), "gold": (212, 175, 55), "bronze": (176, 112, 60), "platinum": (200, 210, 225),
    "chest": (120, 90, 60), "iron": (110, 110, 120), "steel": (150, 165, 180), "silver": (190, 190, 200),
}
SIGIL_COLORS = {}  # filled lazily (hash based)

WEAPON_ENUM = {"AXE_MACE": "Axes & Maces", "BARE_HANDS": "Bare Hands", "CROSSBOW": "Crossbow", "DAGGER": "Dagger", "GREAT_AXE": "Great Axe",
               "GREAT_SWORD": "Great Sword", "HEAVY_MACE": "Heavy Mace", "POLEARM": "Polearm", "STAFF": "Stave", "SWORD": "Sword"}
ABILITY_COLORS = {"chain": (225, 70, 60), "defence": (70, 130, 230)}  # offensive = red, defensive = blue
SHORT = {"Axes & Maces": "Axe/Mace", "Great Sword": "G.Sword", "Great Axe": "G.Axe", "Heavy Mace": "H.Mace", "Bare Hands": "Hands"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def ensure(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def write_json(rel, data):
    p = ensure(os.path.join(ROOT, rel))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_text(rel, text):
    p = ensure(os.path.join(ROOT, rel))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def lua(v, indent=0):
    """Serialise python value to a Lua literal."""
    pad = "  " * indent
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua(x, indent) for x in v) + "}"
    if isinstance(v, dict):
        inner = []
        for k, x in v.items():
            key = f"[{k}]" if isinstance(k, int) else f"[{lua(k)}]"
            inner.append(f"{pad}  {key} = {lua(x, indent + 1)},")
        return "{\n" + "\n".join(inner) + f"\n{pad}}}"
    raise TypeError(type(v))


# --------------------------------------------------------------------------------------------
# Placeholder image helpers
# --------------------------------------------------------------------------------------------
PLACEHOLDERS = []  # (relpath, description)


def font(size):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def save_placeholder(rel, img, desc, art_kind="placeholder"):
    p = os.path.join(ROOT, rel)
    if os.path.exists(p):
        return False
    ensure(p)
    img.save(p)
    PLACEHOLDERS.append((rel, desc, art_kind))
    return True


def badge(label, color, size=32, text_color=(255, 255, 255)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, size - 2, size - 2], 5, fill=color + (255,), outline=(255, 255, 255, 200), width=1)
    f = font(11 if len(label) > 2 else 14)
    w = d.textlength(label, font=f)
    d.text(((size - w) / 2, size / 2 - 8), label, fill=text_color, font=f)
    return img


def color_for(name):
    h = abs(hash_str(name))
    return (60 + h % 140, 60 + (h // 7) % 140, 60 + (h // 49) % 140)


def hash_str(s):
    h = 7
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFF
    return h


def sheet_sprite(col, row):
    sheet = Image.open(SPRITESHEET).convert("RGBA")
    cell = sheet.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
    return cell.resize((32, 32), Image.NEAREST)


LEVEL_TINTS = [(205, 215, 230), (235, 185, 60), (225, 60, 50), (150, 90, 230)]  # L1 silver, L2 gold, L3 red, L4 violet


def tint(img, rgb):
    """Recolour a sprite to one hue, keeping its shading (same weapon, different colour per break art level)."""
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            lum = (0.3 * r + 0.59 * g + 0.11 * b) / 255
            k = 0.25 + 0.95 * lum
            px[x, y] = (min(255, int(rgb[0] * k)), min(255, int(rgb[1] * k)), min(255, int(rgb[2] * k)), a)
    return out


GRIMOIRE_ICON = os.path.join(HERE, "assets", "grimoire_base.png")  # made by tools/clean_grimoire_icon.py
GRIMOIRE_ORDER = []  # filled in main(): every grimoire/levelling grimoire name, so each gets its own hue


def recolor_book(index, total):
    """Rotate the purple/pink cover of the book icon to a unique hue; gold corners, page edge and ribbon are left alone."""
    import colorsys

    base = Image.open(GRIMOIRE_ICON).convert("RGBA")
    shift = index / total
    sat_mul, val_mul = [(1.0, 1.0), (0.6, 1.15), (1.0, 0.75)][index % 3]  # also vary tone so neighbours differ
    out = base.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            h, sv, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if sv > 0.3 and 0.70 <= h <= 0.97:  # purple/pink cover + trim
                h = (h + shift) % 1.0
                sv = min(1.0, sv * sat_mul)
                v = min(1.0, v * val_mul)
                r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, sv, v)]
                px[x, y] = (r, g, b, a)
    return out


KEY_BASE = {"bronze": "bronze", "gold": "gold", "silver": "silver", "iron": "grey", "steel": "silver", "platinum": "silver", "crimson": "gold", "chest": "bronze"}
KEY_TINT = {  # None = use the pack's own colour; otherwise recolour keeping the shading
    "bronze": None, "gold": None, "silver": None, "iron": None,
    "steel": (120, 150, 200), "platinum": (225, 240, 250), "crimson": (205, 35, 45), "chest": (80, 150, 115),
}
KEY_TILT = 45  # degrees counter-clockwise: bow top-left, teeth bottom-right, same diagonal as the weapon sprites


def key_icon(colour):
    """Key 9 from the Pixel Art Key Pack (flat), colour-coded and tilted to match the break art sprites."""
    base = Image.open(os.path.join(HERE, "assets", "keys", f"key9_{KEY_BASE[colour]}.png")).convert("RGBA")
    if KEY_TINT[colour]:
        base = tint(base, KEY_TINT[colour])
    big = base.resize((base.width * 2, base.height * 2), Image.NEAREST)
    canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    canvas.paste(big, ((96 - big.width) // 2, (96 - big.height) // 2), big)
    rot = canvas.rotate(KEY_TILT, resample=Image.BICUBIC)
    return _fit64(rot)


def boost_alpha(img, factor=4.0):
    """Thin, mostly-transparent line art (the teleport circle) vanishes on a dark tracker background; make it opaque enough."""
    img = img.copy()
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (min(255, int(r * 1.0) + 30), min(255, int(g * 1.25)), min(255, int(b * 1.25)), min(255, int(a * factor)))
    return img


def _fit64(img):
    box = img.getbbox()
    img = img.crop(box)
    scale = min(60 / img.width, 60 / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2), img)
    return out


def fist_sprite():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 8, 26, 26], 4, fill=(205, 165, 125, 255), outline=(60, 40, 25, 255), width=2)
    for i in range(4):
        d.line([(9 + i * 5, 9), (9 + i * 5, 17)], fill=(60, 40, 25, 255), width=1)
    d.rectangle([10, 24, 24, 30], fill=(120, 120, 135, 255), outline=(40, 40, 50, 255))
    return img


# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------
def main():
    world_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORLD
    w = World(world_dir)
    init_src = open(os.path.join(world_dir, "__init__.py"), encoding="utf-8", errors="replace").read()
    rules_src = open(os.path.join(world_dir, "Rules.py"), encoding="utf-8", errors="replace").read()

    # ---- sanity: special rules this generator hard-wires still exist in Rules.py ----
    for needle in ('"The Atrium -> Dome"', '"Rue Crimnade -> The House Gilgitte"', "_WORKSHOPS"):
        if needle not in rules_src:
            print(f"WARNING: expected {needle} in Rules.py - special-case logic in generate_pack.py may be stale")

    # ---- starting workshops (index = open_world_option value, exactly as __init__.create_regions uses it) ----
    m = re.search(r"list_of_starting_points\s*=\s*\[(.*?)\]", init_src, re.S)
    starts = re.findall(r'"([^"]+)"', m.group(1))
    assert all(s in w.minor for s in starts), starts
    # The world indexes list_of_starting_points with the open_world_option value, but that list is in a different order
    # from OpenWorldOptions (option 0 = Magic Hammer, yet list[0] = Godhands). The player's chosen workshop is the one
    # named by the option, so the tracker orders its starts by OpenWorldOptions. Set to False to mirror the list order.
    START_BY_OPTION_NAME = True
    if START_BY_OPTION_NAME:
        opts_src = open(os.path.join(world_dir, "Options.py"), encoding="utf-8", errors="replace").read()
        block = re.search(r"class OpenWorldOptions:(.*?)\n\n", opts_src, re.S).group(1)
        by_value = sorted((int(v), n) for n, v in re.findall(r"(\w+)\s*=\s*(\d+)", block))
        ordered = []
        for _v, name in by_value:
            key = name.replace("_", "").lower()
            match = [r for r in starts if re.sub(r"[^a-z]", "", r.lower().replace("workshop", "")).startswith(key.rstrip("s"))]
            assert len(match) == 1, (name, match)
            ordered.append(match[0])
        assert sorted(ordered) == sorted(starts)
        starts = ordered

    # ---- the weapon list must still match Rules.py (blades themselves are not tracked) ----
    gm = re.search(r"_BREAK_ART_WEAPON_GROUPS\s*=\s*\{(.*?)\}", rules_src, re.S)
    weapon_group = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', gm.group(1)))
    assert set(weapon_group) == set(WEAPONS), "weapon list drifted from Rules.py"

    # ------------------------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------------------------
    keys = [n for n, c, _ in w.items if c == "KEYS"]
    sigils = [n for n, c, _ in w.items if c == "SIGILS"]
    grimoires = [n for n, c, _ in w.items if c == "GRIMOIRE" and not n.startswith("Progressive")]
    prog_grim = {}  # name -> qty
    src = open(os.path.join(world_dir, "Items.py"), encoding="utf-8", errors="replace").read()
    for name, qty in re.findall(r'VagrantStoryItemData\("(Progressive Grimoire [^"]+)",\s*VagrantStoryItemCategory\.GRIMOIRE,\s*False,\s*(\d+)\)', src):
        prog_grim[name] = int(qty)

    ITEM_MAPPING = {}  # ap item id -> [code, kind]
    sig_codes = []

    def item_img(code):
        return f"images/items/{code}.png"

    items_keys, items_grim, items_ba, items_settings = [], [], [], []

    # keys
    for n in keys:
        code = slug(n)
        items_keys.append({"name": n, "type": "toggle", "img": item_img(code), "codes": code})
        ITEM_MAPPING[w.item_id[n]] = [code, "toggle"]
        sig_codes.append(code)
        col = KEY_COLORS.get(slug(n).split("_")[0], (130, 130, 130))
        if Image:
            save_placeholder(item_img(code), key_icon(slug(n).split("_")[0]), f"{n} icon (Key 9 from your key pack, colour-coded + tilted)", "from-asset")
    # blood sin
    items_keys.append(
        {
            "name": "Blood Sin Piece", "type": "consumable", "img": item_img("blood_sin_piece"), "codes": "blood_sin_piece",
            "min_quantity": 0, "max_quantity": 50, "increment": 1, "decrement": 1, "initial_quantity": 0,
            "overlay_background": "#000000AA", "overlay_font_size": 12,
        }
    )
    ITEM_MAPPING[w.item_id["Blood Sin Piece"]] = ["blood_sin_piece", "consumable"]
    sig_codes.append("blood_sin_piece")
    if Image:
        save_placeholder(item_img("blood_sin_piece"), tint(_fit64(Image.open(os.path.join(HERE, "assets", "hide.png")).convert("RGBA")), (200, 30, 40)), "Blood Sin Piece icon (your hide art, tinted red)", "from-asset")
    # sigils (alphabetical; one evenly spaced hue each)
    import colorsys as _cs

    sigil_rgb = {}
    for i, n in enumerate(sorted(sigils)):
        sat, val = [(0.70, 0.95), (0.50, 1.0), (0.80, 0.80)][i % 3]
        sigil_rgb[n] = tuple(int(c * 255) for c in _cs.hsv_to_rgb(i / len(sigils), sat, val))
    for n in sigils:
        code = slug(n)
        items_keys.append({"name": n, "type": "toggle", "img": item_img(code), "codes": code})
        ITEM_MAPPING[w.item_id[n]] = [code, "toggle"]
        sig_codes.append(code)
        if Image:
            save_placeholder(item_img(code), tint(_fit64(Image.open(os.path.join(HERE, "assets", "sigil.png")).convert("RGBA")), sigil_rgb[n]), f"{n} icon (your sigil art, one colour per sigil)", "from-asset")
    # teleport / rood inverse
    for n, code in (("Teleport", "teleport"), ("Rood Inverse", "rood_inverse")):
        items_keys.append({"name": n, "type": "toggle", "img": item_img(code), "codes": code})
        ITEM_MAPPING[w.item_id[n]] = [code, "toggle"]
        sig_codes.append(code)
        if Image:
            art = {"rood_inverse": "hide.png", "teleport": "teleport.png"}[code]
            icon = _fit64(boost_alpha(Image.open(os.path.join(HERE, "assets", art)).convert("RGBA")) if code == "teleport" else Image.open(os.path.join(HERE, "assets", art)).convert("RGBA"))
            save_placeholder(item_img(code), icon, f"{n} icon (your art, natural colour)", "from-asset")

    # grimoires
    grim_total_idx = {n: i for i, n in enumerate(list(grimoires) + list(prog_grim))}
    grim_total = len(grim_total_idx)
    for n in grimoires:
        code = slug(n)
        items_grim.append({"name": n, "type": "toggle", "img": item_img(code), "codes": code})
        ITEM_MAPPING[w.item_id[n]] = [code, "toggle"]
        if Image:
            if os.path.exists(GRIMOIRE_ICON):
                save_placeholder(item_img(code), recolor_book(grim_total_idx[n], grim_total), f"{n} icon (your book icon, recoloured)", "from-asset")
            else:
                save_placeholder(item_img(code), badge(n.replace("Grimoire ", "")[:3], color_for(n)), f"{n} icon (grimoire)")
    for n, qty in prog_grim.items():
        code = slug(n)
        items_grim.append(
            {
                "name": n, "type": "consumable", "img": item_img(code), "codes": code, "min_quantity": 0, "max_quantity": qty,
                "increment": 1, "decrement": 1, "initial_quantity": 0, "overlay_background": "#000000AA", "overlay_font_size": 12,
            }
        )
        ITEM_MAPPING[w.item_id[n]] = [code, "consumable"]
        if Image:
            if os.path.exists(GRIMOIRE_ICON):
                save_placeholder(item_img(code), recolor_book(grim_total_idx[n], grim_total), f"{n} icon (your book icon, recoloured)", "from-asset")
            else:
                save_placeholder(item_img(code), badge("P" + n.replace("Progressive Grimoire ", "")[:2], color_for(n)), f"{n} icon (levelling grimoire)")

    # blades: one toggle per weapon type, ticked when ANY blade of that type is received (the world gates every break art
    # on state.has_group("<Type> Blades"), see Rules.set_break_art_rules / Items.blade_name_groups)
    items_blades = []
    bgroups = w.blade_groups()
    assert set(bgroups) == set(WEAPON_ENUM), (sorted(bgroups), sorted(WEAPON_ENUM))
    for enum, weapon in WEAPON_ENUM.items():
        bcode = "blade_" + slug(weapon)
        items_blades.append({"name": f"{weapon} blade (any)", "type": "toggle", "img": f"images/blades/{slug(weapon)}.png", "codes": bcode})
        for blade in bgroups[enum]:
            ITEM_MAPPING[w.item_id[blade]] = [bcode, "toggle"]
        if Image:
            if SHEET_CELLS[weapon] and os.path.exists(SPRITESHEET):
                bimg, kind = sheet_sprite(*SHEET_CELLS[weapon][0]), "from-sheet"
            else:
                bimg, kind = fist_sprite(), "placeholder"
            save_placeholder(f"images/blades/{slug(weapon)}.png", bimg, f"{weapon} blade icon (untinted)", kind)
    write_json("items/blades.json", items_blades)

    # break arts (display items; ticked when the named art is received)
    breakart_loc = {}  # location id -> item code
    # Items.py tags every break art with its weapon type; levels 1-4 are the order they appear in for that type.
    ba_items = [n for n, c, _ in w.items if c == "BREAK_ARTS"]
    assert len(ba_items) == 40, "break art count changed"
    by_type = {}
    for n in ba_items:
        by_type.setdefault(w.item_weapon[n][0], []).append(n)
    assert all(len(v) == 4 for v in by_type.values()) and set(by_type) == set(WEAPON_ENUM), by_type.keys()
    ba_name = {(WEAPON_ENUM[t], lvl): names[lvl - 1] for t, names in by_type.items() for lvl in range(1, 5)}
    for wi, weapon in enumerate(WEAPONS):
        for lvl in range(1, 5):
            code = f"breakart_{slug(weapon)}_{lvl}"
            ITEM_MAPPING[w.item_id[ba_name[(weapon, lvl)]]] = [code, "toggle"]  # auto-ticks if ever sent as an item
            items_ba.append(
                {
                    "name": f"{ba_name[(weapon, lvl)].replace(' Break Art', '')} ({weapon} L{lvl})", "type": "toggle", "img": f"images/breakarts/{slug(weapon)}_{lvl}.png", "codes": code,
                    "overlay": str(lvl), "overlay_background": "#000000", "overlay_font_size": 11,
                }
            )
            if Image:
                if SHEET_CELLS[weapon] and os.path.exists(SPRITESHEET):
                    base = sheet_sprite(*SHEET_CELLS[weapon][0])
                    kind = "from-sheet"
                else:
                    base = fist_sprite()
                    kind = "placeholder"
                img = tint(base, LEVEL_TINTS[lvl - 1])
                desc = f"{weapon} break-art icon L{lvl} (same sprite, tinted per level; cut from your iron-weapons sheet)" if kind == "from-sheet" else f"{weapon} break-art icon L{lvl} (tinted per level)"
                save_placeholder(f"images/breakarts/{slug(weapon)}_{lvl}.png", img, desc, kind)

    # settings (also driven from AP slot data)
    def setting(code, name, letter, color, on_default=False):
        items_settings.append(
            {"name": name, "type": "toggle", "img": f"images/settings/{code}.png", "codes": code, "initial_active_state": on_default}
        )
        if Image:
            save_placeholder(f"images/settings/{code}.png", badge(letter, color), f"setting icon: {name}")

    setting("opt_open", "Open progression (off = vanilla)", "OP", (60, 120, 200))
    setting("roomsanity", "Roomsanity", "RM", (90, 160, 90))
    setting("panelsanity", "Panelsanity", "PN", (160, 120, 60))
    setting("ngplus", "New Game+ checks", "NG", (150, 70, 150))
    setting("prologue", "Prologue checks", "PR", (120, 120, 120))
    setting("timetrial", "Time trial checks (open mode)", "TT", (200, 100, 60), True)
    items_settings.append(
        {
            "name": "Open start workshop", "type": "progressive", "loop": True, "allow_disabled": False,
            "stages": [
                {"img": f"images/settings/start_{i}.png", "codes": f"start_{i}", "inherit_codes": False, "name": s.replace("Workshop ", "")}
                for i, s in enumerate(starts)
            ],
        }
    )
    for i, s in enumerate(starts):
        if Image:
            save_placeholder(f"images/settings/start_{i}.png", badge(f"W{i}", color_for(s)), f"start workshop icon: {s}")
    items_settings.append(
        {
            "name": "Blood Sin Pieces required", "type": "consumable", "img": "images/settings/blood_sin_total.png", "codes": "blood_sin_total",
            "min_quantity": 1, "max_quantity": 50, "increment": 1, "decrement": 1, "initial_quantity": 5,
            "overlay_background": "#000000AA", "overlay_font_size": 12,
        }
    )
    if Image:
        save_placeholder("images/settings/blood_sin_total.png", badge("REQ", (150, 20, 60)), "setting icon: Blood Sin Pieces required")

    write_json("items/keys_sigils.json", items_keys)
    write_json("items/grimoires.json", items_grim)
    write_json("items/breakarts.json", items_ba)
    write_json("items/settings.json", items_settings)

    # ------------------------------------------------------------------------------------
    # Rooms / graph / rules
    # ------------------------------------------------------------------------------------
    loc_room = {}
    for region, rows in w.location_tables.items():
        for name, _d, _c in rows:
            loc_room[name] = region

    def conv(expr):
        t = expr[0]
        if t == "item":
            return ["item", slug(expr[1])]
        if t == "loc":
            return ["room", slug(loc_room[expr[1]])]
        if t == "and":
            return ["and", *[conv(e) for e in expr[1]]]
        raise ValueError(expr)

    rules = w.entrance_rules()

    # location rules (e.g. the Chest Key chests): must be identical in vanilla and open mode for the tracker to apply them
    def expr_items(e):
        if e[0] == "item":
            return [slug(e[1])]
        if e[0] == "and":
            return [c for x in e[1] for c in expr_items(x)]
        raise ValueError(f"unsupported location rule {e}")

    lrules = w.location_rules()
    assert lrules["vanilla"] == lrules["open"], "location rules differ between vanilla and open; tracker needs mode-specific handling"
    loc_item_rules = {n: expr_items(e) for n, e in lrules["vanilla"].items()}
    bsall = ["bsall"]
    ents = w.entrances()
    edges = []
    for name, a, b in ents:
        e = {"f": slug(a), "t": slug(b)}
        for mode, key in (("vanilla", "v"), ("open", "o"), ("time_trial", "tt")):
            if name in rules[mode]:
                e[key] = conv(rules[mode][name])
        # special cases that live outside set_rule(get_entrance(..)) patterns in Rules.py
        if name == "The Atrium -> Dome":
            for key in ("v", "o"):
                e[key] = ["and", e[key], bsall] if key in e else bsall
        if name == "Rue Crimnade -> The House Gilgitte":
            for key in ("v", "o"):
                e[key] = ["room", "the_house_gilgitte"]
        edges.append(e)
    assert any(e["f"] == "the_atrium" and e["t"] == "dome" and "v" in e for e in edges), "Atrium -> Dome edge missing"

    # ------------------------------------------------------------------------------------
    # Locations & maps
    # ------------------------------------------------------------------------------------
    layout_path = os.path.join(HERE, "map_layout.json")
    layout = json.load(open(layout_path, encoding="utf-8")) if os.path.exists(layout_path) else {}

    maps_def = []
    rooms_by_map = {}
    LOCATIONS_MAPPING = {}
    rooms_json_by_map = {}

    SKIP_CATS = {"KEY_UNLOCKS", "SIGIL_UNLOCKS", "TELEPORT_UNLOCK"}  # never created by the world (see create_region)
    VIS = {"ROOM_ENTERED": ["roomsanity"], "FLOOR_TRAPS": ["panelsanity"], "BOSS_PLUS": ["ngplus"], "BOSS_UNLOCKS_PLUS": ["ngplus"]}

    def label_for(name, cat, room):
        if cat == "ROOM_ENTERED":
            return "Room Entered"
        parts = name.split(" - ")
        return " - ".join(parts[2:]) if len(parts) > 2 else name

    def auto_positions(rooms):
        cols = max(4, math.ceil(math.sqrt(len(rooms) * 2.4)))
        cw, ch, m = 190, 74, 24
        pos = {}
        for i, r in enumerate(rooms):
            cx, cy = i % cols, i // cols
            pos[r] = (m + cx * (cw + 14), 56 + m + cy * (ch + 14), cw, ch)
        width = m * 2 + cols * (cw + 14)
        height = 56 + m * 2 + math.ceil(len(rooms) / cols) * (ch + 14)
        return pos, width, height

    def marker(map_key, room, pos):
        lay = layout.get(map_key, {})
        if room in lay:
            return lay[room]
        x, y, cw, ch = pos[room]
        return [x + cw - 16, y + ch - 14]

    for key, rd in w.major_regions.items():
        rooms = list(rd.keys())
        pos, width, height = auto_positions(rooms)
        children = []
        room_list = []
        for room in rooms:
            rows = w.location_tables.get(room, [])
            sections, seen = [], {}
            for name, _d, cat in rows:
                if cat in SKIP_CATS or name not in w.loc_id or w.room_major.get(room) != key:
                    continue
                lbl = label_for(name, cat, room)
                if lbl in seen:
                    seen[lbl] += 1
                    lbl = f"{lbl} ({seen[lbl]})"
                else:
                    seen[lbl] = 1
                sec = {"name": lbl, "item_count": 1}
                if name in loc_item_rules:  # e.g. Chest Key chests: room reachable AND the item(s)
                    sec["access_rules"] = [",".join([f"$vs_room|{slug(room)}", *loc_item_rules[name]])]
                if cat in VIS:
                    sec["visibility_rules"] = VIS[cat]
                sections.append(sec)
                LOCATIONS_MAPPING[w.loc_id[name]] = f"@{MAP_TITLES[key]}/{room}/{lbl}"
            if not sections:
                continue
            x, y = marker(key, room, pos)
            children.append(
                {
                    "name": room,
                    "access_rules": [f"$vs_room|{slug(room)}"],
                    "sections": sections,
                    "map_locations": [{"map": key, "x": x, "y": y}],
                }
            )
            room_list.append(room)
        write_json(f"locations/{key}.json", [{"name": MAP_TITLES[key], "children": children}])
        maps_def.append({"name": key, "location_size": 36, "location_border_thickness": 3, "img": f"images/maps/{key}.png"})
        rooms_by_map[key] = room_list
        if Image:
            img = Image.new("RGB", (width, height), (10, 10, 14))
            d = ImageDraw.Draw(img)
            d.text((24, 14), f"PLACEHOLDER MAP: {MAP_TITLES[key]}  (replace images/maps/{key}.png with real art)", fill=(220, 200, 90), font=font(20))
            f = font(14)
            for room in rooms:
                x, y, cw, ch = pos[room]
                d.rectangle([x, y, x + cw, y + ch], outline=(110, 110, 120), fill=(26, 26, 32))
                words, line, lines = room.split(), "", []
                for wd in words:
                    t = (line + " " + wd).strip()
                    if d.textlength(t, font=f) > cw - 12:
                        lines.append(line)
                        line = wd
                    else:
                        line = t
                lines.append(line)
                for li, t in enumerate(lines[:3]):
                    d.text((x + 6, y + 5 + li * 16), t, fill=(200, 200, 210), font=f)
            save_placeholder(f"images/maps/{key}.png", img, f"Map art for {MAP_TITLES[key]} ({len(rooms)} rooms)", "MAP")

    # ---- Prologue map (3 checks, no rooms) ----
    pr_children, pr_rows = [], [r for r in w.location_tables["Prologue"]]
    for i, (name, _d, cat) in enumerate(pr_rows):
        short = name.replace("PR - Prologue - ", "")
        lm = layout.get("prologue", {}).get(short, [120 + i * 180, 120])
        pr_children.append(
            {
                "name": short, "sections": [{"name": short, "item_count": 1, "visibility_rules": ["prologue"]}],
                "map_locations": [{"map": "prologue", "x": lm[0], "y": lm[1]}],
            }
        )
        LOCATIONS_MAPPING[w.loc_id[name]] = f"@{MAP_TITLES['prologue']}/{short}/{short}"
    write_json("locations/prologue.json", [{"name": MAP_TITLES["prologue"], "children": pr_children}])
    maps_def.append({"name": "prologue", "location_size": 18, "location_border_thickness": 2, "img": "images/maps/prologue.png"})
    rooms_by_map["prologue"] = [n.replace("PR - Prologue - ", "") for n, _d, _c in pr_rows]
    if Image:
        img = Image.new("RGB", (720, 260), (10, 10, 14))
        d = ImageDraw.Draw(img)
        d.text((24, 14), "PLACEHOLDER MAP: Prologue (replace images/maps/prologue.png)", fill=(220, 200, 90), font=font(20))
        for i, (n, _d, _c) in enumerate(pr_rows):
            d.text((60 + i * 180, 150), n.replace("PR - Prologue - ", ""), fill=(200, 200, 210), font=font(13))
        save_placeholder("images/maps/prologue.png", img, "Map art for the Prologue (3 checks)", "MAP")

    # ---- chain / defence ability ITEMS (bottom panel) + goal toggle ----
    chain_abilities = [n for n, c, _ in w.items if c == "CHAIN_ABILITY"]
    defence_abilities = [n for n, c, _ in w.items if c == "DEFENCE_ABILITY"]
    link_path = os.path.join(HERE, "assets", "chain_link.png")
    items_chain = []
    for group_names, colour, label in ((chain_abilities, ABILITY_COLORS["chain"], "Chain Ability"), (defence_abilities, ABILITY_COLORS["defence"], "Defence Ability")):
        for n in group_names:
            code = slug(n)
            items_chain.append({"name": n, "type": "toggle", "img": f"images/chain/{code}.png", "codes": code})
            ITEM_MAPPING[w.item_id[n]] = [code, "toggle"]  # auto-ticks if the world ever sends them as items
            if Image:
                base = _fit64(Image.open(link_path).convert("RGBA")) if os.path.exists(link_path) else badge("CH", colour)
                save_placeholder(f"images/chain/{code}.png", tint(base, colour), f"{n} icon ({label}: your chain-link art, one colour per group)", "from-asset")
    items_chain.append({"name": "Game End: Credits", "type": "toggle", "img": "images/chain/goal.png", "codes": "goal"})
    breakart_loc[w.loc_id["Game End: Credits"]] = "goal"
    if Image:
        save_placeholder("images/chain/goal.png", badge("END", (200, 160, 40)), "Goal / credits icon")
    write_json("items/chain.json", items_chain)
    items_src = open(os.path.join(world_dir, "Items.py"), encoding="utf-8", errors="replace").read()
    start_block = re.search(r"_STARTING_ABILITIES\s*=\s*frozenset\(\s*\[(.*?)\]", items_src, re.S)
    start_abilities = [slug(n) for n in re.findall(r'"([^"]+)"', start_block.group(1))] if start_block else []
    assert all(a in {i["codes"] for i in items_chain} for a in start_abilities), start_abilities

    # ---- Ashley tab: chain unlock checks, break art checks, grimoire pickups, goal. Image is fully generated. ----
    ash_children = []
    chain = [n for n, _d, c in w.location_tables["Ashley"] if c == "ABILITY_UNLOCKS"]
    grim_locs = []
    for room, rows in w.location_tables.items():
        if room in ("Ashley", "Prologue", "Credits") or room not in w.minor:
            continue
        for name, _d, cat in rows:
            if cat == "GRIMOIRE_UNLOCKS" and name in w.loc_id:
                grim_locs.append((name, room))
    cell, mx, my = 62, 30, 90
    gcols, gcell, gx0 = 9, 84, 800
    width = gx0 + gcols * gcell + 30
    base_y = my + 2 * cell + 50
    height = max(base_y + 4 * 54 + 50, my + math.ceil(len(grim_locs) / gcols) * 70 + 70)
    img = Image.new("RGB", (width, height), (10, 10, 14)) if Image else None
    d = ImageDraw.Draw(img) if img else None
    ASH = MAP_TITLES["ashley"]

    def add_ash(name, rule, x, y, sec=None):
        ash_children.append(
            {"name": name, "access_rules": [rule] if rule else [], "sections": [{"name": sec or name, "item_count": 1}],
             "map_locations": [{"map": "ashley", "x": x, "y": y}]}
        )
        if not rule:
            del ash_children[-1]["access_rules"]

    if d:
        d.text((30, 14), "Ashley: chain unlock checks, break art checks, grimoire pickups, goal", fill=(220, 200, 90), font=font(20))
        d.text((30, 60), "Chain Unlocks (Blood Sin gated: 8-15 / 16-22)", fill=(200, 200, 210), font=font(14))
        d.text((gx0, 60), "Grimoire pickups (bosses / chests; need their room)", fill=(200, 200, 210), font=font(14))
        d.text((30, base_y - 28), "Break Arts (columns = weapon, rows = level 1-4)", fill=(200, 200, 210), font=font(14))
    for i, name in enumerate(chain):
        x, y = mx + (i % 11) * cell + 20, my + (i // 11) * cell + 14
        add_ash(name, f"$vs_chain|{name.split()[-1]}", x, y)
        LOCATIONS_MAPPING[w.loc_id[name]] = f"@{ASH}/{name}/{name}"
        if d:
            d.text((x - 20, y + 14), name.replace("Chain Unlock ", "#"), fill=(170, 170, 185), font=font(12))
    for wi, weapon in enumerate(WEAPONS):
        for lvl in range(1, 5):
            name = f"Break Art {weapon} Level {lvl}"
            x, y = mx + wi * (cell + 4) + 20, base_y + (lvl - 1) * 54 + 20
            add_ash(f"{weapon} Level {lvl}", f"$vs_break|{slug(weapon)}|{lvl}", x, y)
            LOCATIONS_MAPPING[w.loc_id[name]] = f"@{ASH}/{weapon} Level {lvl}/{weapon} Level {lvl}"
        if d:
            d.text((mx + wi * (cell + 4) + 4, base_y - 8), SHORT.get(weapon, weapon), fill=(170, 170, 185), font=font(11))
    if d:
        for lvl in range(1, 5):
            d.text((6, base_y + (lvl - 1) * 54 + 14), f"L{lvl}", fill=(170, 170, 185), font=font(12))
    for i, (name, room) in enumerate(grim_locs):
        x, y = gx0 + (i % gcols) * gcell + 24, my + (i // gcols) * 70 + 14
        parts = name.split(" - ")
        child = " - ".join(parts[1:])  # drop the area abbreviation; unique because the AP name is
        add_ash(child, ",".join([f"$vs_room|{slug(room)}", *loc_item_rules.get(name, [])]), x, y)
        path = f"@{ASH}/{child}/{child}"
        prev = LOCATIONS_MAPPING[w.loc_id[name]]
        LOCATIONS_MAPPING[w.loc_id[name]] = [prev, path] if isinstance(prev, str) else [*prev, path]
        if d:
            short = parts[-1].replace("Grimoire ", "")
            d.text((x - 22, y + 14), short[:11], fill=(170, 170, 185), font=font(11))
    goal = "Game End: Credits"
    gx, gy = mx + 11 * cell - 40, 40
    add_ash(goal, "$vs_room|dome", gx, gy)
    LOCATIONS_MAPPING[w.loc_id[goal]] = f"@{ASH}/{goal}/{goal}"
    if d:
        d.text((gx - 60, gy + 14), "Goal: Credits", fill=(170, 170, 185), font=font(12))
        img.save(ensure(os.path.join(ROOT, "images/maps/ashley.png")))  # fully generated, always refreshed
    write_json("locations/ashley.json", [{"name": ASH, "children": ash_children}])
    maps_def.append({"name": "ashley", "location_size": 18, "location_border_thickness": 2, "img": "images/maps/ashley.png"})

    # PopTracker scales every map image to fit the window, so a fixed pixel size looks different per map. Size each
    # marker relative to how much its image gets shrunk (fit = max(width, 1.6 * height)); 36px at a 2500px-wide map.
    if Image:
        for md in maps_def:
            if md["name"] in ("ashley", "prologue"):
                continue
            with Image.open(os.path.join(ROOT, md["img"])) as im:
                fit = max(im.width, 1.6 * im.height)
            md["location_size"] = max(14, round(36 * fit / 2500))
            md["location_border_thickness"] = 3 if md["location_size"] >= 24 else 2
    write_json("maps/maps.json", maps_def)
    write_json("tools/rooms_by_map.json", rooms_by_map)

    # ------------------------------------------------------------------------------------
    # Lua data
    # ------------------------------------------------------------------------------------
    sig = sig_codes + [f"start_{i}" for i in range(len(starts))] + ["opt_open", "timetrial", "blood_sin_total"]
    data = [
        "-- GENERATED by tools/generate_pack.py from the Vagrant Story AP world. DO NOT EDIT BY HAND.",
        "VS = VS or {}",
        f"VS.VANILLA_START = {lua(slug('Entrance to Darkness'))}",
        f"VS.OPEN_STARTS = {lua([slug(s) for s in starts])}",
        "VS.GOAL_ROOM = \"dome\"",
        f"VS.WORKSHOPS = {lua([slug(r) for r in w.workshops()])}",
        f"VS.SIG_CODES = {lua(sig)}",
        "VS.EDGES = {",
    ]
    for e in edges:
        data.append("  " + lua(e) + ",")
    data.append("}")
    write_text("scripts/generated/graph.lua", "\n".join(data) + "\n")

    mapping = [
        "-- GENERATED by tools/generate_pack.py. DO NOT EDIT BY HAND.",
        "ITEM_MAPPING = " + lua({k: v for k, v in sorted(ITEM_MAPPING.items())}),
        "LOCATIONS_MAPPING = " + lua({k: v for k, v in sorted(LOCATIONS_MAPPING.items())}),
        "START_ITEMS = " + lua(start_abilities),
        "BREAKART_LOCATIONS = " + lua({k: v for k, v in sorted(breakart_loc.items())}),
    ]
    write_text("scripts/generated/mapping.lua", "\n".join(mapping) + "\n")

    write_layouts(keys, sigils, grimoires, list(prog_grim), chain_abilities, defence_abilities)
    write_images_needed(rooms_by_map, w)
    print(f"rooms: {len(w.minor)}  edges: {len(edges)}  location sections mapped: {len(LOCATIONS_MAPPING)}  item ids mapped: {len(ITEM_MAPPING)}")
    print(f"placeholder images written this run: {len(PLACEHOLDERS)}")


def write_layouts(keys, sigils, grimoires, prog_grimoires, chain_abilities, defence_abilities):
    def grid(rows, margin="3"):
        return {"type": "itemgrid", "item_size": "28", "item_margin": margin, "rows": rows}

    def chunk(codes, n):
        return [codes[i : i + n] for i in range(0, len(codes), n)]

    key_codes = [slug(k) for k in sorted(keys)]
    sigil_codes = [slug(s) for s in sorted(sigils)]

    def grim_sort(name):  # "Progressive Grimoire Foudre" sorts as "Foudre"
        return name.replace("Progressive ", "").replace("Grimoire ", "").lower()

    grim_codes = [slug(g) for g in sorted(list(grimoires) + list(prog_grimoires), key=grim_sort)]
    ba_rows = [[f"breakart_{slug(wp)}_{lvl}" for lvl in range(1, 5)] for wp in WEAPONS]

    shared = {
        "breakart_grid": grid(ba_rows, "2"),
        "blade_grid": grid([["blade_" + slug(wp)] for wp in WEAPONS], "2"),
        "chain_ability_grid": grid(chunk([slug(n) for n in chain_abilities], 7), "2"),
        "defence_ability_grid": grid(chunk([slug(n) for n in defence_abilities], 7), "2"),
        "blood_grid": grid([["blood_sin_piece"]]),
        "settings_grid": grid(
            [
                ["opt_open", "roomsanity", "panelsanity"],
                ["ngplus", "prologue", "timetrial"],
                ["teleport", "rood_inverse", "start_0"],
                ["goal"],
            ]
        ),
        "grimoire_grid": grid(chunk(grim_codes, 6), "2"),
        "keys_grid": grid(chunk(key_codes, 2), "2"),
        "sigils_grid": grid(chunk(sigil_codes, 3), "2"),
    }

    def group(header, *keys):
        return {
            "type": "group", "header": header,
            "content": {"type": "array", "orientation": "horizontal", "content": [{"type": "layout", "key": k} for k in keys]},
        }

    abilities = {
        "type": "group", "header": "Abilities",
        "content": {
            "type": "array", "orientation": "vertical",
            "content": [
                {"type": "group", "header": "Chain Abilities", "content": shared["chain_ability_grid"]},
                {"type": "group", "header": "Defence Abilities", "content": shared["defence_ability_grid"]},
            ],
        },
    }

    # everything on one page, left to right (items you hold; the checks live on the map tabs above)
    bottom_panel = {
        "type": "array", "orientation": "horizontal", "margin": "0,0",
        "content": [
            group("Blades | Break Arts", "blade_grid", "breakart_grid"),
            abilities,
            {"type": "group", "header": "Blood Sin", "content": shared["blood_grid"]},
            group("Grimoires", "grimoire_grid"),
            group("Keys | Sigils", "keys_grid", "sigils_grid"),
            group("Settings", "settings_grid"),
        ],
    }
    write_json("layouts/items.json", shared)

    def area_tab(tab, floors):
        if len(floors) == 1:
            return {"title": tab, "content": {"type": "map", "maps": [floors[0][0]]}}
        return {
            "title": tab,
            "content": {"type": "tabbed", "tabs": [{"title": fl, "content": {"type": "map", "maps": [k]}} for k, fl in floors]},
        }

    main = {
        "type": "container",
        "background": "#000000",
        "content": {
            "type": "dock",
            "content": [
                {"type": "dock", "dock": "bottom", "content": bottom_panel},
                {"type": "tabbed", "tabs": [area_tab(t, f) for t, f in AREAS]},
            ],
        },
    }
    write_json("layouts/tracker.json", {"tracker_default": main, "tracker_horizontal": main, "tracker_vertical": main})
    items_only = {"type": "container", "background": "#000000", "content": bottom_panel}
    write_json(
        "layouts/tracker_items_only.json",
        {"tracker_default": items_only, "tracker_horizontal": items_only, "tracker_vertical": items_only},
    )
    write_json(
        "layouts/broadcast.json",
        {
            "tracker_broadcast": {
                "type": "array", "orientation": "vertical",
                "content": [{"type": "layout", "key": "keys_grid"}, {"type": "layout", "key": "sigils_grid"}],
            }
        },
    )


def write_images_needed(rooms_by_map, w):
    lines = [
        "# Images the pack still needs",
        "",
        "Generated by `tools/generate_pack.py`. Every file below is a **placeholder** that was created because no file existed.",
        "Drop your own PNG over it (same path, same name) and it will be used; the generator never overwrites existing images.",
        "",
        "## 1. Map art (highest priority)",
        "",
        "One image per PopTracker map. Screenshots stitched per floor, like the Wine Cellar mock-up. Any size works - marker",
        "coordinates are in pixels of the image. After dropping art in, place the markers with `tools/map_picker.html`",
        "(see README) and save its output as `tools/map_layout.json`, then run `python tools/generate_pack.py`.",
        "",
        "| Image path | Area / floor | Rooms to place |",
        "|---|---|---|",
    ]
    for tab, floors in AREAS:
        for key, floor in floors:
            n = len(rooms_by_map.get(key, []))
            lines.append(f"| `images/maps/{key}.png` | {MAP_TITLES[key]} | {n} |")
    lines += [""]
    by_kind = {}
    for rel, desc, kind in PLACEHOLDERS:
        by_kind.setdefault(kind, []).append((rel, desc))
    lines += ["## 2. Item / UI icons", "", "32x32 PNG with transparency is ideal (PopTracker scales them).", ""]
    groups = [
        ("Keys, Blood Sin Piece, Teleport, Rood Inverse", lambda r: r.startswith("images/items/") and ("key" in r or r.endswith(("blood_sin_piece.png", "teleport.png", "rood_inverse.png")))),
        ("Sigils (23, one per flower)", lambda r: r.startswith("images/items/") and r.endswith("_sigil.png")),
        ("Grimoires (36 spells + 7 levelling)", lambda r: r.startswith("images/items/grimoire") or "progressive_grimoire" in r),
        ("Chain / defence ability icons (14 + 14) + goal icon", lambda r: r.startswith("images/chain/")),
        ("Blade icons (10, one per weapon type; untinted)", lambda r: r.startswith("images/blades/")),
        ("Break art icons (40 = 10 weapons x 4 levels; level number is overlaid by the tracker)", lambda r: r.startswith("images/breakarts/")),
        ("Settings icons", lambda r: r.startswith("images/settings/")),
    ]
    listed = set()
    for title, pred in groups:
        files = [(r, d) for r, d, k in PLACEHOLDERS if pred(r) and r not in listed]
        if not files:
            continue
        lines += [f"### {title} - {len(files)} files", ""]
        for r, d in files:
            listed.add(r)
            tag = " *(cut from your sprite sheet - swap if you want different art)*" if "sheet" in d else ""
            lines.append(f"- `{r}` - {d}{tag}")
        lines.append("")
    lines += [
        "## 3. Nice-to-have (not referenced yet)",
        "",
        "- `images/tabs/*.png` - optional tab icons per area",
        "- A logo for the top-left of each map (the VGC logo in the mock-up)",
        "- Separate chest / boss / floor-trap marker icons if you want the mock-up's extra glyphs on the maps. PopTracker draws one",
        "  coloured square per room; extra glyphs would have to be baked into the map art or the room split into several locations.",
        "",
    ]
    write_text("IMAGES_NEEDED.md", "\n".join(lines))


if __name__ == "__main__":
    if Image is None:
        print("Pillow is required for placeholder art: pip install pillow")
    main()
