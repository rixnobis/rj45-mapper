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
LED_X = [9.0 + 5.5 * i for i in range(9)]
assert "LED_X = [for (i = [0:8]) 9.0 + 5.5 * i];" in src, "LED_X changed in case.scad"
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

# Plug reachability: an RJ45 plug body (11.7 x 6.8 mm, +0.15 mm) must slide in from outside
# the case to 3 mm inside the jack face, through free space in the case AND through the
# jack's own cavity. The cavity arm reads the jack MODEL, so a jack whose opening is not
# at the board edge (a top-entry part) fails here even when every body clearance passes.
PLUG_W = 11.7 + 0.3
# the model's cavity at the face is clear from z 2.9 (floor lip) to 10.0 (roof) above the board
PLUG_Z0 = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0      # above board top
PLUG_Z1 = PLUG_Z0 + 6.8
jstl = ROOT / "build" / "jack.stl"
subprocess.run(["kicad-cli", "pcb", "export", "stl", "--subst-models", "--force", "--no-board-body",
                "--component-filter", "J1", "--user-origin", "100x100mm", "-o", str(jstl),
                str(ROOT / "rj45-mapper.kicad_pcb")], check=True, capture_output=True)
jack = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", jstl.read_bytes())
jv = [(float(x), -float(y), float(z)) for x, y, z in jack]     # K = board y, down positive
if len(jv) < 300:
    print("CANNOT CHECK: jack model has", len(jv), "vertices")
    sys.exit(2)
# the plug axis comes from the jack MODEL, never from case.scad, so a cutout in the wrong
# place cannot carry the probe along with it
PLUG_X = (min(p[0] for p in jv) + max(p[0] for p in jv)) / 2
# Rays, not vertices: a flat face carries vertices only at its corners, so a vertex test
# reads a closed face as an open cavity. Each ray runs along +K from outside the north wall
# and must reach 3 mm past the jack face before it meets any jack triangle.
tris = [jv[k:k + 3] for k in range(0, len(jv) - 2, 3)]


def first_hit(o, d):
    best = None
    for a, b, c in tris:
        e1 = [b[k] - a[k] for k in range(3)]
        e2 = [c[k] - a[k] for k in range(3)]
        p = [d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0]]
        det = sum(e1[k] * p[k] for k in range(3))
        if abs(det) < 1e-12:
            continue
        t0 = [o[k] - a[k] for k in range(3)]
        u = sum(t0[k] * p[k] for k in range(3)) / det
        if u < 0 or u > 1:
            continue
        q = [t0[1] * e1[2] - t0[2] * e1[1], t0[2] * e1[0] - t0[0] * e1[2], t0[0] * e1[1] - t0[1] * e1[0]]
        w = sum(d[k] * q[k] for k in range(3)) / det
        if w < 0 or u + w > 1:
            continue
        t = sum(e2[k] * q[k] for k in range(3)) / det
        if t > 0 and (best is None or t < best):
            best = t
    return best


K0 = -(g.C + g.T + 2.0)
in_plug = []
nx, nz = 9, 6
for ix in range(nx):
    x = PLUG_X - PLUG_W / 2 + PLUG_W * ix / (nx - 1)
    for iz in range(nz):
        z = PLUG_Z0 + (PLUG_Z1 - PLUG_Z0) * iz / (nz - 1)
        t = first_hit((x, K0, z), (0.0, 1.0, 0.0))     # jack frame: (x, K, z above board)
        if t is not None and K0 + t < 3.0:
            in_plug.append((round(x, 2), round(K0 + t, 2), round(z, 2)))
probe_hits = {}
step = 0.5
y = -(g.C + g.T + 2.0)                    # start outside the north wall (case frame y = -K)
while y <= 3.0:
    x = PLUG_X - PLUG_W / 2
    while x <= PLUG_X + PLUG_W / 2:
        z = PLUG_Z0
        while z <= PLUG_Z1:
            s = solid(x, -y, g.Z_BT + z)
            if s:
                probe_hits[s] = probe_hits.get(s, 0) + 1
            z += step
        x += step
    y += step
print(f"plug probe at x {PLUG_X:.2f}: {len(in_plug)} of {nx * nz} plug-path rays blocked by the jack before 3 mm; "
      f"case solids in the path: {probe_hits or 'none'}")
sys.exit(1 if hits or in_plug or probe_hits else 0)
