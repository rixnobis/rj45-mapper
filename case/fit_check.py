#!/usr/bin/env python3
"""Fit check: no component of the populated board may sit inside the case.

OpenSCAD cannot intersect the board export (KiCad's component meshes are not closed,
so CGAL refuses them and returns an EMPTY result that would read as a pass). This
samples every component triangle (vertices, edge midpoints, centroid) and tests each
point against the case solids, rebuilt here from the constants parsed out of
case.scad, grown by MARGIN so a near miss also fails.

usage: fit_check.py [margin_mm]      exits 1 on any collision, 2 if it cannot run
"""
import re
import subprocess
import sys
from math import hypot
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MARGIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
src = (HERE / "case.scad").read_text()


def num(name):
    m = re.search(r"(?:^|;)[ \t]*%s\s*=\s*([^;]+);" % name, src, re.M)
    if not m:
        print(f"CANNOT CHECK: cannot parse {name} from case.scad")
        sys.exit(2)
    return m.group(1)


env = {}
for name in ["BW", "BH", "BT", "C", "T", "FLOOR", "STANDOFF", "TALLEST", "BOSS_D",
             "JACK_CL", "USB_Y", "USB_W", "USB_H", "PAD_M", "LED_Y", "TUBE_ID", "TUBE_OD"]:
    env[name] = eval(num(name), {}, env)
env["Z_BB"] = env["FLOOR"] + env["STANDOFF"]
env["Z_BT"] = env["Z_BB"] + env["BT"]
env["CEIL"] = env["Z_BT"] + env["TALLEST"] + 0.8
env["TOP"] = env["CEIL"] + env["T"]
env["USB_ZC"] = eval(num("USB_ZC"))
env["TUBE_GAP"] = eval(num("TUBE_GAP"))
JACK = eval(num("JACK"))
PAD = eval(num("PAD"))
HOLES = eval(num("HOLES"))
LED_X = [9.0 + 5.5 * i for i in range(10)]
assert "LED_X = [for (i = [0:9]) 9.0 + 5.5 * i];" in src, "LED_X changed in case.scad"
g = type("G", (), env)

# components only: the board body touches the standoffs and bosses by design
stl = ROOT / "build" / "components.stl"
subprocess.run(["kicad-cli", "pcb", "export", "stl", "--subst-models", "--force", "--no-board-body",
                "--user-origin", "100x100mm", "-o", str(stl), str(ROOT / "rj45-mapper.kicad_pcb")],
               check=True, capture_output=True)
d = stl.read_bytes()
v = [tuple(map(float, m)) for m in re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", d)]
if len(v) < 300:
    print("CANNOT CHECK: component STL has", len(v), "vertices")
    sys.exit(2)
pts = []
for i in range(0, len(v) - 2, 3):
    a, b, c = v[i], v[i + 1], v[i + 2]
    pts += [a, b, c,
            tuple((a[k] + b[k]) / 2 for k in range(3)), tuple((b[k] + c[k]) / 2 for k in range(3)),
            tuple((a[k] + c[k]) / 2 for k in range(3)), tuple((a[k] + b[k] + c[k]) / 3 for k in range(3))]
pts = [(x, y, z + g.Z_BT) for x, y, z in pts]       # board top at Z_BT in the case frame
M = MARGIN


def in_cutout(x, y, z):
    if JACK[0] - g.JACK_CL < x < JACK[1] + g.JACK_CL and y > -1 and g.Z_BT - 0.3 < z < g.Z_BT + g.TALLEST + 0.3:
        return True
    if x < 0 and abs(y - g.USB_Y) < g.USB_W / 2 and abs(z - (g.Z_BT + g.USB_ZC)) < g.USB_H / 2:
        return True
    if x > PAD[0] - g.PAD_M and PAD[2] - g.PAD_M < y < PAD[3] + g.PAD_M and z > g.Z_BT - 0.2:
        return True
    return False


def solid(x, y, z):
    """Which case solid contains (x, y, z), grown by M; None if free space."""
    if in_cutout(x, y, z):
        return None
    inside_inner = -g.C + M < x < g.BW + g.C - M and -g.BH - g.C + M < y < g.C - M
    if z < g.FLOOR + M:
        return "base floor"
    if not inside_inner and z < g.TOP:
        return "wall"
    if z > g.CEIL - M:
        return "lid ceiling"
    for hx, hy in HOLES:
        if hypot(x - hx, y - hy) < g.BOSS_D / 2 + M:
            return "standoff" if z < g.Z_BB else "lid boss"
    if z > g.Z_BT + g.TUBE_GAP - M:
        for lx in LED_X:
            r = hypot(x - lx, y - g.LED_Y)
            if r < g.TUBE_OD / 2 + M:
                return "light tube"
    return None


hits = {}
for p in pts:
    s = solid(*p)
    if s:
        hits.setdefault(s, []).append(p)
print(f"fit_check: {len(pts)} sample points from {len(v) // 3} component triangles, margin {M} mm")
for s, ps in hits.items():
    xs, ys, zs = zip(*ps)
    print(f"  COLLISION {s}: {len(ps)} points, x {min(xs):.2f}..{max(xs):.2f} "
          f"y {min(ys):.2f}..{max(ys):.2f} z {min(zs):.2f}..{max(zs):.2f}")
sys.exit(1 if hits else 0)
