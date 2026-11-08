"""
Static checks on the pack (no PopTracker needed):
  * every JSON parses
  * every image referenced by items / maps exists
  * every item code used in layouts exists
  * every location path in scripts/generated/mapping.lua exists in locations/*.json
  * every map referenced by a location/layout exists, markers sit inside the map image
  * Lua files at least compile (needs lupa; skipped if missing)
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def err(msg):
    errors.append(msg)


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


# items
codes, imgs = set(), set()
for f in glob.glob(os.path.join(ROOT, "items", "*.json")):
    for it in json.load(open(f, encoding="utf-8")):
        for c in str(it.get("codes", "")).split(","):
            if c:
                codes.add(c)
        if "img" in it:
            imgs.add(it["img"])
        for st in it.get("stages", []):
            imgs.add(st["img"])
            for c in str(st.get("codes", "")).split(","):
                if c:
                    codes.add(c)

maps = load("maps/maps.json")
map_names = {m["name"] for m in maps}
for m in maps:
    imgs.add(m["img"])
for i in sorted(imgs):
    if not os.path.exists(os.path.join(ROOT, i)):
        err(f"missing image {i}")

# layouts
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "rows":
                for row in v:
                    for c in row:
                        if c and c not in codes:
                            err(f"layout references unknown item code {c}")
            if k == "maps":
                for mname in v:
                    if mname not in map_names:
                        err(f"layout references unknown map {mname}")
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


for f in glob.glob(os.path.join(ROOT, "layouts", "*.json")):
    walk(json.load(open(f, encoding="utf-8")))

# locations
paths = set()
try:
    from PIL import Image
except ImportError:
    Image = None
sizes = {}
if Image:
    for m in maps:
        p = os.path.join(ROOT, m["img"])
        if os.path.exists(p):
            sizes[m["name"]] = Image.open(p).size
for f in glob.glob(os.path.join(ROOT, "locations", "*.json")):
    for area in json.load(open(f, encoding="utf-8")):
        for loc in area.get("children", []):
            names = set()
            for sec in loc.get("sections", []):
                if sec["name"] in names:
                    err(f"duplicate section {loc['name']}/{sec['name']}")
                names.add(sec["name"])
                paths.add(f"@{area['name']}/{loc['name']}/{sec['name']}")
            for ml in loc.get("map_locations", []):
                if ml["map"] not in map_names:
                    err(f"{loc['name']}: unknown map {ml['map']}")
                sz = sizes.get(ml["map"])
                if sz and not (0 <= ml["x"] <= sz[0] and 0 <= ml["y"] <= sz[1]):
                    err(f"{loc['name']}: marker {ml['x']},{ml['y']} outside {ml['map']} image {sz}")
            for rule in loc.get("access_rules", []):
                m = re.match(r"\$(vs_\w+)", rule)
                if not m:
                    err(f"unexpected rule {rule}")

mapping = open(os.path.join(ROOT, "scripts/generated/mapping.lua"), encoding="utf-8").read()
for p in re.findall(r'"(@[^"]+)"', mapping):
    if p not in paths:
        err(f"mapping.lua path not in locations: {p}")
for c in re.findall(r'"(breakart_[a-z_0-9]+|blade_[a-z_]+|[a-z_]+)", "(?:toggle|consumable)"', mapping):
    if c not in codes:
        err(f"mapping.lua item code has no item: {c}")
ids = re.findall(r"\[(\d+)\] = (?:\"@|\{)", mapping)
if len(ids) != len(set(ids)):
    err("duplicate location ids in mapping")

# lua syntax
try:
    from lupa import LuaRuntime

    lua = LuaRuntime()
    for f in glob.glob(os.path.join(ROOT, "scripts", "**", "*.lua"), recursive=True):
        try:
            lua.eval("function(s) return load(s) end")(open(f, encoding="utf-8").read())
            ok, e = lua.eval("function(s) local f, e = load(s) return f ~= nil, e end")(open(f, encoding="utf-8").read())
            if not ok:
                err(f"{os.path.relpath(f, ROOT)}: {e}")
        except Exception as ex:  # noqa: BLE001
            err(f"{f}: {ex}")
except ImportError:
    print("(lupa not installed - skipped Lua syntax check)")

print(f"{len(codes)} item codes, {len(paths)} location sections, {len(maps)} maps")
if errors:
    print("\n".join(errors[:60]))
    print(f"{len(errors)} problem(s)")
    sys.exit(1)
print("pack looks consistent")
