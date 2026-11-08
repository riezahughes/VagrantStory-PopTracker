"""
Regression test: runs scripts/logic.lua (through lupa) against an independent Python model of Rules.py and
checks the reachable-room sets match for random item sets in vanilla and open mode.

    pip install lupa
    python tools/test_logic.py
"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lupa import LuaRuntime  # noqa: E402
from worlddata import World  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
w = World()
slug = lambda s: re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")  # noqa: E731

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(
    """
STATE = {}
Tracker = { ProviderCountForCode = function(self, c) return STATE[c] or 0 end }
ScriptHost = { LoadScript = function(self, p) end }
"""
)
lua.execute(open(os.path.join(ROOT, "scripts/generated/graph.lua"), encoding="utf-8").read())
lua.execute(open(os.path.join(ROOT, "scripts/logic.lua"), encoding="utf-8").read())
G = lua.globals()

rules = w.entrance_rules()
ents = w.entrances()
slug_to_room = {slug(r): r for r in w.minor}
starts = [slug_to_room[x] for x in G.VS.OPEN_STARTS.values()]  # same order the pack uses (option order)
loc_room = {n: r for r, rows in w.location_tables.items() for n, _d, _c in rows}


def py_reach(have, open_mode, tt, start_idx, total, bsp):
    def ev(e, reached):
        t = e[0]
        if t == "item":
            return slug(e[1]) in have
        if t == "loc":
            return loc_room[e[1]] in reached
        return all(ev(x, reached) for x in e[1])

    def rule_for(name):
        if open_mode:
            r = rules["open"].get(name)
            if tt and name in rules["time_trial"]:
                r = rules["time_trial"][name]
        else:
            r = rules["vanilla"].get(name)
        return r

    reached = {starts[start_idx] if open_mode else "Entrance to Darkness"}
    changed = True
    while changed:
        changed = False
        for name, a, b in ents:
            if a in reached and b not in reached:
                r = rule_for(name)
                ok = True if r is None else ev(r, reached)
                if name == "The Atrium -> Dome":
                    ok = ok and bsp >= total
                if name == "Rue Crimnade -> The House Gilgitte":
                    ok = b in reached
                if ok:
                    reached.add(b)
                    changed = True
    return reached


items = [slug(n) for n, c, _ in w.items if c in ("KEYS", "SIGILS")]
random.seed(7)
bad = 0
for trial in range(200):
    open_mode = trial % 2 == 1
    tt = random.random() < 0.5
    sidx = random.randrange(6)
    total = random.choice([5, 10, 23, 50])
    bsp = random.choice([0, total, random.randrange(total + 1)])
    p = random.choice([0.0, 0.3, 0.6, 0.9, 1.0])
    have = {i for i in items if random.random() < p}
    st = {i: 1 for i in have}
    st.update({"opt_open": 1 if open_mode else 0, "timetrial": 1 if tt else 0, "blood_sin_total": total, "blood_sin_piece": bsp, f"start_{sidx}": 1})
    lua.execute("STATE = {}")
    for k, v in st.items():
        G.STATE[k] = v
    lr = {slug(r) for r in w.minor if G.vs_room(slug(r))}
    pr = {slug(r) for r in py_reach(have, open_mode, tt, sidx, total, bsp)}
    if lr != pr:
        bad += 1
        print("MISMATCH trial", trial, "open" if open_mode else "vanilla", "lua-only", sorted(lr - pr)[:5], "py-only", sorted(pr - lr)[:5])
print("reachability mismatches:", bad)




def check(label, got, want):
    global bad
    ok = got == want
    bad += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + label)


lua.execute("STATE = {opt_open=1, blood_sin_total=10, blood_sin_piece=0}")
check("chain 7 free", G.vs_chain("7"), True)
check("chain 8 needs 2 BSP", G.vs_chain("8"), False)
check("break art L1 free", G.vs_break("dagger", "1"), True)
check("break art L2 needs BSP", G.vs_break("dagger", "2"), False)
lua.execute("STATE = {opt_open=1, blood_sin_total=10, blood_sin_piece=6}")
check("break art L4 with 6/10", G.vs_break("dagger", "4"), True)
check("chain 16 with 6/10", G.vs_chain("16"), True)
lua.execute("STATE = {opt_open=0, blood_sin_total=10, blood_sin_piece=10}")
check("vanilla break art blocked before Withered Spring", G.vs_break("dagger", "1"), False)
sys.exit(1 if bad else 0)
