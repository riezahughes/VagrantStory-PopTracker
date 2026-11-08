"""
Reads the Vagrant Story AP world *source* (no Archipelago imports needed) and exposes
rooms, exits, location tables/ids and the entrance rules from Rules.py.

Nothing here is hand-copied: re-run generate_pack.py after the world changes and the pack follows.
"""
import ast
import importlib.util
import os
import re

DEFAULT_WORLD = r"D:\Archipelago\dev\VagrantStoryAPWorld\worlds\vagrantstory"


class World:
    def __init__(self, world_dir=DEFAULT_WORLD):
        self.dir = world_dir
        self._load_rooms()
        self._load_locations()
        self._load_items()

    # ------------------------------------------------------------------ rooms
    def _load_rooms(self):
        rooms_dir = os.path.join(self.dir, "rooms")
        init_src = open(os.path.join(rooms_dir, "__init__.py"), encoding="utf-8").read()
        pairs = re.findall(r'"([^"]+)":\s*(\w+)\.room_data', init_src)
        self.major_regions = {}  # key -> {room: {"exits": [(target, req)]}}
        for key, mod in pairs:
            spec = importlib.util.spec_from_file_location(f"_vs_{mod}", os.path.join(rooms_dir, mod + ".py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            self.major_regions[key] = m.room_data
        # same flattening as rooms/__init__.py -> all_minor_regions (first position wins, last value wins)
        self.minor = {}
        self.room_major = {}
        for key, rd in self.major_regions.items():
            for room, data in rd.items():
                self.minor[room] = data
                self.room_major.setdefault(room, key)

    # -------------------------------------------------------------- locations
    def _load_locations(self):
        tree = ast.parse(open(os.path.join(self.dir, "Locations.py"), encoding="utf-8").read())
        tables = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "location_tables":
                tables = node.value
        assert tables is not None, "location_tables not found"
        self.location_tables = {}
        for k, v in zip(tables.keys, tables.values):
            rows = []
            for call in v.elts:
                name = call.args[0].value
                default = call.args[1].value
                cat = call.args[2].attr
                rows.append((name, default, cat))
            self.location_tables[k.value] = rows
        # ids: identical to VagrantStoryLocation.get_name_to_id
        base, off = 99350000, 1000
        order = ["Ashley", "Prologue", *self.minor.keys(), "Credits"]
        self.loc_id = {}
        for i, region in enumerate(order):
            for j, (name, _d, _c) in enumerate(self.location_tables.get(region, [])):
                self.loc_id[name] = base + i * off + j

    # ------------------------------------------------------------------ items
    def _load_items(self):
        src = open(os.path.join(self.dir, "Items.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        raw = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_all_items_raw":
                raw = node.value
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_all_items_raw":
                raw = node.value
        assert raw is not None, "_all_items_raw not found"
        self.items = []  # (name, category, code)
        self.item_weapon = {}  # name -> WeaponType enum member names (from the 5th argument, where given)
        for i, call in enumerate(raw.elts):
            name = call.args[0].value
            cat = call.args[1].attr
            self.items.append((name, cat, 9901000 + i + 1))
            if len(call.args) > 4 and isinstance(call.args[4], ast.List):
                self.item_weapon[name] = [e.attr for e in call.args[4].elts]
        self.item_id = {n: c for n, _cat, c in self.items}
        # extras added in get_name_to_id
        self.item_id["Teleport"] = 9910000
        self.item_id["Rood Inverse"] = 9920000
        self.item_id["Blood Sin Piece"] = 9930000
        self.item_cat = {n: cat for n, cat, _c in self.items}

    # ------------------------------------------------------------ entrances
    def entrances(self):
        """List (entrance_name, from_room, to_room) using the exact naming rule in __init__.create_regions."""
        out = []
        for room, data in self.minor.items():
            targets = [e[0] for e in data["exits"]]
            used = {}
            for ex in data["exits"]:
                if ex[0] in self.minor:
                    if targets.count(ex[0]) > 1:
                        c = used.get(ex[0], 1)
                        name = f"{room} -> {ex[0]} ({c})"
                        used[ex[0]] = c + 1
                    else:
                        name = f"{room} -> {ex[0]}"
                    out.append((name, room, ex[0]))
        return out

    # ---------------------------------------------------------------- rules
    def entrance_rules(self):
        """
        Parse Rules.py into {mode: {entrance_name: expr}} where expr is a nested tuple:
          ("item", name) | ("loc", location_name) | ("and", [expr...])
        modes: vanilla (key+boss progression), open (open progression), time_trial (overlay)
        """
        tree = ast.parse(open(os.path.join(self.dir, "Rules.py"), encoding="utf-8").read())
        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

        def lam_expr(lam):
            def conv(n):
                if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.And):
                    return ("and", [conv(v) for v in n.values])
                if isinstance(n, ast.Call):
                    f = n.func.id
                    if f in ("has_key_required", "has_sigil_required"):
                        return ("item", n.args[1].value)
                    if f == "has_rood_inverse":
                        return ("item", "Rood Inverse")
                    if f == "player_has_location":
                        return ("loc", n.args[1].value)
                raise ValueError(ast.dump(n))

            return conv(lam.body)

        def collect(fname):
            ops = []
            for node in ast.walk(funcs[fname]):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("set_rule", "add_rule"):
                    tgt = node.args[0]
                    if (
                        isinstance(tgt, ast.Call)
                        and getattr(tgt.func, "attr", "") == "get_entrance"
                        and isinstance(node.args[1], ast.Lambda)
                    ):
                        ops.append((node.func.id, tgt.args[0].value, lam_expr(node.args[1]), node.lineno))
            ops.sort(key=lambda o: o[3])
            return ops

        def apply(ops_lists):
            rules = {}
            for ops in ops_lists:
                for kind, ent, expr, _ln in ops:
                    if kind == "set_rule" or ent not in rules:
                        rules[ent] = expr
                    else:
                        rules[ent] = ("and", [rules[ent], expr])
            return rules

        return {
            "vanilla": apply([collect("set_vanilla_key_item_progression"), collect("set_vanilla_boss_progression")]),
            "open": apply([collect("set_open_progression")]),
            "time_trial": apply([collect("set_time_trial_rules")]),
        }


if __name__ == "__main__":
    import collections

    w = World()
    print("rooms", len(w.minor), "major", len(w.major_regions))
    dup = collections.Counter(r for rd in w.major_regions.values() for r in rd)
    print("duplicate room names:", [r for r, c in dup.items() if c > 1])
    print("tables w/o room:", [r for r in w.location_tables if r not in w.minor and r not in ("Ashley", "Prologue", "Credits")])
    print("rooms w/o table:", [r for r in w.minor if r not in w.location_tables][:20])
    print("loc ids", len(w.loc_id), "unique", len(set(w.loc_id.values())))
    cnt = collections.Counter(c for rows in w.location_tables.values() for _n, _d, c in rows)
    print(cnt)
    print("slash/comma names:", [r for r in w.minor if "/" in r or "," in r])
    ents = w.entrances()
    print("entrances", len(ents))
    names = {e[0] for e in ents}
    r = w.entrance_rules()
    for m, d in r.items():
        print(m, len(d), "missing entrances:", [e for e in d if e not in names])
    bad_targets = [(rm, e[0]) for rm, d in w.minor.items() for e in d["exits"] if e[0] not in w.minor]
    print("exit targets not rooms:", bad_targets)
