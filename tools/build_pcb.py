#!/usr/bin/env python3
"""Build rj45-mapper.kicad_pcb from the schematic netlist.

  build_pcb.py place    - footprints, outline, silk, nets, and the scripted route
  build_pcb.py finish   - pour GND both layers, stitch, save

Coordinates are millimetres from the board's top-left corner (OX,OY sheet offset).
"""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
NAME = "rj45-mapper"
PCB = ROOT / f"{NAME}.kicad_pcb"
PRO = ROOT / f"{NAME}.kicad_pro"
SCH = ROOT / f"{NAME}.kicad_sch"
FPDIR = Path("/usr/share/kicad/footprints")
LOCALFP = ROOT / f"{NAME}.pretty"

OX, OY = 100.0, 100.0
W, H = 75.0, 50.0
EDGE = 0.3                     # copper-free margin from the board edge (JLC)

# Jack: RCH RC01937 rotated 180 so its mating face sits on the top edge.
# Footprint origin is pin 1; the courtyard runs 13.145 mm past it toward the face.
J1_X, J1_Y = 24.445, 13.0
# ULN2803A SOIC-18W rotated 270: inputs 1..9 along the top row, right to left, so
# input n sits directly under jack pin n (both at 1.27 mm pitch, pin 1 rightmost).
U1_X, U1_Y = J1_X - 5.08, 27.0
LED_Y, LEDR_Y = 41.0, 45.0
LED_X = [9.0 + 5.5 * i for i in range(10)]   # PWR, 1..8, S
ANODE_DX = 1.4                               # LED_1206 pad 2 (anode) offset
R_DX = 0.9125                                # R_0805 pad offset
BUS_Y = 48.3                                 # 5V bus under the resistor row
ROW_Y0, ROW_DY = 33.6, 0.8                   # B.Cu crossover rows, ULN outputs -> LEDs
# Row order per channel: an LED cathode column that lands near a ULN output column
# (LED2 near outputs 5/6, LED3 near output 1) must take a row below that output's.
ROW_RANK = {1: 0, 6: 1, 4: 2, 5: 3, 7: 4, 8: 5, 2: 6, 3: 7}
V5_X = 7.8                                   # B.Cu 5V riser beside the USB-C pads
V5UP_X = 56.0                                # B.Cu 5V riser to the probe-pad resistor
OS_X = LED_X[9] - ANODE_DX                   # S channel column (cathode of D10)

PLACE = {
    "J1": (J1_X, J1_Y, 180),
    "U1": (U1_X, U1_Y, 270),
    "J2": (3.0, 22.0, 270),    # USB-C, mouth out of the left edge
    "R11": (9.0, 18.6, 90),    # pin 1 (CC1) at the bottom
    "R12": (9.0, 26.4, 270),   # pin 1 (CC2) at the top
    "R13": (32.0, 3.6, 0),
    "Q1": (36.0, 4.55, 0),     # base pad lands on y=3.6, in line with R13
    "R14": (32.0 + R_DX, 7.0, 270),
    "R10": (V5UP_X, 18.0, 90),
    "PAD1": (W - 0.6 - 7.5, 20.0, 0),   # 15x15, 0.6 mm from the right edge
    "H1": (3.5, 3.5, 0), "H2": (W - 3.5, 3.5, 0),
    "H3": (3.5, H - 3.5, 0), "H4": (W - 3.5, H - 3.5, 0),
}
LEDS = ["D9"] + [f"D{i}" for i in range(1, 9)] + ["D10"]
LEDRS = ["R9"] + [f"R{i}" for i in range(1, 9)] + ["R15"]
for k in range(10):
    PLACE[LEDS[k]] = (LED_X[k], LED_Y, 0)
    PLACE[LEDRS[k]] = (LED_X[k] + ANODE_DX, LEDR_Y, 90)   # pin 1 (5V) at the bottom

POWER_NETS = ["/5V", "/GND"]


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def netlist():
    xml = ROOT / "build" / "netlist.xml"
    xml.parent.mkdir(exist_ok=True)
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
                    "-o", str(xml), str(SCH)], check=True, capture_output=True)
    r = ET.parse(xml).getroot()
    comps = {}
    for c in r.find("components"):
        fld = c.find("fields")
        comps[c.get("ref")] = {
            "value": c.findtext("value"),
            "footprint": c.findtext("footprint"),
            "uuid": c.findtext("tstamps"),
            "fields": {f.get("name"): f.text for f in (fld if fld is not None else [])},
        }
    pads = {}
    for n in r.find("nets"):
        for node in n:
            pads[(node.get("ref"), node.get("pin"))] = n.get("name")
    return comps, pads


def write_project():
    d = json.loads(PRO.read_text())
    ns = d["net_settings"]
    base = {"bus_width": 12, "clearance": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
            "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "tuning_profile": "", "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6}
    ns["classes"] = [dict(base, name="Default", priority=2147483647, track_width=0.3),
                     dict(base, name="Power", priority=0, track_width=0.6, via_diameter=0.8,
                          via_drill=0.4)]
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in POWER_NETS]
    ns["netclass_assignments"] = {}
    rules = d["board"]["design_settings"].setdefault("rules", {})
    rules.update({"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
                  "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.4,
                  "min_hole_clearance": 0.25, "min_hole_to_hole": 0.5, "min_silk_clearance": 0.0,
                  "min_text_height": 0.8, "min_text_thickness": 0.15})
    PRO.write_text(json.dumps(d, indent=2) + "\n")


def load_fp(fpid):
    lib, name = fpid.split(":")
    d = LOCALFP if lib == NAME else FPDIR / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(d), name)
    assert fp is not None, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def silk(board, s, x, y, size=1.0, angle=0, layer=pcbnew.F_SilkS, mirror=False, thick=0.15,
         just=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick))
    t.SetTextAngleDegrees(angle)
    if mirror:
        t.SetMirrored(True)
    if just is not None:
        t.SetHorizJustify(just)
    board.Add(t)


def outline(board):
    rad = 2.0
    segs = [((rad, 0), (W - rad, 0)), ((W, rad), (W, H - rad)),
            ((W - rad, H), (rad, H)), ((0, H - rad), (0, rad))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(*a))
        s.SetEnd(pt(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
    for cx, cy, sx, sy in [(rad, rad, 0, rad), (W - rad, rad, W - rad, 0),
                           (W - rad, H - rad, W, H - rad), (rad, H - rad, rad, H)]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetCenter(pt(cx, cy))
        s.SetStart(pt(sx, sy))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)


def place():
    write_project()
    comps, pads = netlist()
    board = pcbnew.NewBoard(str(PCB))
    board.SetCopperLayerCount(2)

    nets = {}
    for name in sorted(set(pads.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    for ref, c in sorted(comps.items()):
        fp = load_fp(c["footprint"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        if c["fields"].get("LCSC"):
            fp.SetField("LCSC", c["fields"]["LCSC"])
            fp.GetField("LCSC").SetVisible(False)
        board.Add(fp)
        x, y, a = PLACE[ref]
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(a)
        for pad in fp.Pads():
            net = pads.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)

    # Assert the geometry the layout depends on, never reason about rotation.
    def padxy(ref, num):
        fp = board.FindFootprintByReference(ref)
        p = [q for q in fp.Pads() if q.GetNumber() == num][0].GetPosition()
        return round(pcbnew.ToMM(p.x) - OX, 3), round(pcbnew.ToMM(p.y) - OY, 3)
    # Pixel's drawing: pin n at 1.27 mm pitch, odd pins on the row nearer the pegs
    # (6.35 mm), even pins 2.54 further (8.89 mm), pegs 11.43 apart, pin 1 1.27 mm
    # inboard of its peg. Rotated 180, so +x runs toward pin 1 and pegs sit above.
    jfp = board.FindFootprintByReference("J1")
    pegs = sorted((round(pcbnew.ToMM(q.GetPosition().x) - OX, 3), round(pcbnew.ToMM(q.GetPosition().y) - OY, 3))
                  for q in jfp.Pads() if abs(pcbnew.ToMM(q.GetDrillSize().x) - 3.25) < 0.01)
    assert len(pegs) == 2 and abs(pegs[1][0] - pegs[0][0] - 11.43) < 0.01, pegs
    p1 = padxy("J1", "1")
    assert abs(p1[0] - (pegs[1][0] - 1.27)) < 0.01 and abs(p1[1] - pegs[0][1] - 6.35) < 0.01, (p1, pegs)
    for n in range(1, 9):
        x, y = padxy("J1", str(n))
        assert abs(x - (p1[0] - 1.27 * (n - 1))) < 0.01, ("J1 pitch", n, x)
        assert abs(y - pegs[0][1] - (6.35 if n % 2 else 8.89)) < 0.01, ("J1 row", n, y)
        ux, uy = padxy("U1", str(n))
        assert abs(ux - x) < 0.01 and uy > y, ("U1 input not under jack pin", n, (ux, uy), (x, y))
        ox, oy = padxy("U1", str(19 - n))
        assert oy > uy, ("U1 output row not below input row", n)
    a5, a12 = padxy("J2", "A5"), padxy("J2", "A12")
    assert a5[0] > 3.0 and a12[0] > 3.0, ("USB-C pads must sit inboard of the mouth", a5, a12)
    print("geometry asserts passed: J1 pegs", pegs, "pin1", p1)

    outline(board)

    # front silk (the case hides it; the lid carries its own labels)
    labels = ["PWR"] + [str(i) for i in range(1, 9)] + ["S"]
    for x, lab in zip(LED_X, labels):
        silk(board, lab, x, LED_Y - 2.3, 1.0, thick=0.18)
    silk(board, "TOUCH WIRE HERE", PLACE["PAD1"][0], PLACE["PAD1"][1] - 8.8, 1.0, thick=0.15)
    silk(board, "5V", 9.5, 15.0, 0.9, thick=0.15)
    silk(board, "RJ45 MAPPER  rev A", 45.0, 22.0, 1.2, thick=0.2)

    # back silk: name, author, date, how it works
    bl = ["RJ45 CABLE MAPPER", "Rix  rev A  2026-10-22", "",
          "Touch a flying wire to the", "pad; the LED for its 8P8C",
          "pin lights. Two shorted", "wires light two LEDs."]
    for i, s in enumerate(bl):
        silk(board, s, 40.0, 14.0 + 2.1 * i, 0.9, layer=pcbnew.B_SilkS, mirror=True, thick=0.15)

    # No rule areas over the SMD parts: one that covers a pad strands it for the router.
    # Pour slivers between pads are handled by the pour minimum width instead.

    # No pour inside the 1.27 mm banks (jack pins -> ULN inputs, ULN outputs -> rows):
    # between two traces at that pitch the fill can only form slivers.
    for x0, y0, x1, y1, layers in [
            (J1_X - 9.6, 11.6, J1_X + 0.75, 23.5, (pcbnew.F_Cu, pcbnew.B_Cu)),
            (U1_X - 6.6, 30.4, J1_X + 0.75, ROW_Y0 + ROW_DY * 7 + 0.5, (pcbnew.F_Cu,)),
            (5.0, 18.6, 10.2, 25.4, (pcbnew.F_Cu,))]:     # USB-C pad row
        k = pcbnew.ZONE(board)
        k.SetIsRuleArea(True)
        k.SetDoNotAllowZoneFills(True)
        k.SetDoNotAllowTracks(False)
        k.SetDoNotAllowVias(False)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        for L in layers:
            ls.AddLayer(L)
        k.SetLayerSet(ls)
        ol = k.Outline()
        ol.NewOutline()
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            ol.Append(mm(OX + x), mm(OY + y))
        board.Add(k)
    route_hand(board, nets, padxy)
    pcbnew.SaveBoard(str(PCB), board)
    print("placed and routed;", PCB)




POWER_W, SIGNAL_W = 0.6, 0.3


def track(board, net, layer, a, b, w):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pt(*a))
    t.SetEnd(pt(*b))
    t.SetLayer(layer)
    t.SetWidth(mm(w))
    t.SetNet(net)
    board.Add(t)


def poly(board, net, layer, pts, w, c=0.5):
    """Polyline with every interior corner cut by a 45-degree chamfer of leg c."""
    out = [pts[0]]
    for a, b, d in zip(pts, pts[1:], pts[2:]):
        la = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        ld = ((d[0] - b[0]) ** 2 + (d[1] - b[1]) ** 2) ** 0.5
        assert la > c and ld > c, ("leg too short to chamfer", a, b, d)
        out.append((b[0] + (a[0] - b[0]) * c / la, b[1] + (a[1] - b[1]) * c / la))
        out.append((b[0] + (d[0] - b[0]) * c / ld, b[1] + (d[1] - b[1]) * c / ld))
    out.append(pts[-1])
    for a, b in zip(out, out[1:]):
        track(board, net, layer, a, b, w)


def via(board, net, x, y, big=False):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(0.8 if big else 0.6))
    v.SetDrill(mm(0.4 if big else 0.3))
    v.SetNet(net)
    board.Add(v)


def route_hand(board, nets, padxy):
    """Every run is scripted: straight segments, 90-degree corners only where two
    straight runs meet at a pad or via, vias where a run changes layer."""
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    n5, gnd = nets["/5V"], nets["/GND"]

    def near(a, b):
        assert abs(a[0] - b[0]) < 0.005 and abs(a[1] - b[1]) < 0.005, (a, b)

    # 1. jack pin n -> ULN input n: one straight F.Cu run each (same x by placement)
    for n in range(1, 9):
        j, u = padxy("J1", str(n)), padxy("U1", str(n))
        near((j[0], 0), (u[0], 0))
        track(board, nets[f"/IN{n}"], F, j, u, SIGNAL_W)
    # ULN GND (pin 9) up to a via into the B.Cu pour
    g9 = padxy("U1", "9")
    track(board, gnd, F, g9, (g9[0], 20.0), POWER_W)
    via(board, gnd, g9[0], 20.0)

    # 2. ULN output n -> LED n cathode: F.Cu down, B.Cu across on its own row, F.Cu down
    for n in range(1, 9):
        net = nets[f"/O{n}"]
        o = padxy("U1", str(19 - n))
        k = padxy(f"D{n}", "1")
        y = ROW_Y0 + ROW_DY * ROW_RANK[n]
        track(board, net, F, o, (o[0], y), SIGNAL_W)
        via(board, net, o[0], y)
        track(board, net, B, (o[0], y), (k[0], y), SIGNAL_W)
        via(board, net, k[0], y)
        track(board, net, F, (k[0], y), k, SIGNAL_W)

    # 3. LED anode -> its resistor (straight down), resistor pin 1 -> 5V bus
    xs = []
    for d, r in zip(LEDS, LEDRS):
        a, r2, r1 = padxy(d, "2"), padxy(r, "2"), padxy(r, "1")
        near((a[0], 0), (r2[0], 0))
        assert r1[1] > r2[1], (r, "pin 1 must be at the bottom")
        assert pads_net(board, r, "2") == pads_net(board, d, "2"), (d, r)
        track(board, nets[pads_net(board, r, "2")], F, a, r2, SIGNAL_W)
        if r != LEDRS[-1]:          # the last one is the bus's own end, below
            track(board, n5, F, r1, (r1[0], BUS_Y), POWER_W)
        xs.append(r1)
    # PWR LED cathode -> GND via to its left
    k9 = padxy("D9", "1")
    track(board, gnd, F, k9, (k9[0] - 1.8, k9[1]), POWER_W)
    via(board, gnd, k9[0] - 1.8, k9[1])

    # 4. 5V: USB-C VBUS pads -> vias -> B.Cu riser -> F.Cu bus
    a9, b9 = padxy("J2", "A9"), padxy("J2", "B9")
    for p in (a9, b9):
        track(board, n5, F, p, (V5_X, p[1]), POWER_W)
        via(board, n5, V5_X, p[1], big=True)
    top = min(a9[1], b9[1])
    track(board, n5, B, (V5_X, top), (V5_X, 44.5), POWER_W)
    via(board, n5, V5_X, 44.5, big=True)
    last = xs[-1]
    poly(board, n5, F, [(V5_X, 44.5), (V5_X, BUS_Y), (last[0], BUS_Y), last], POWER_W)
    # ULN COM (pin 10) off the riser
    c10 = padxy("U1", "10")
    track(board, n5, B, (V5_X, c10[1]), (c10[0] - 1.7, c10[1]), POWER_W)
    via(board, n5, c10[0] - 1.7, c10[1], big=True)
    track(board, n5, F, (c10[0] - 1.7, c10[1]), c10, POWER_W)

    # USB-C GND pads have no pour in the pad row: strap each to its shell stake
    stakes = sorted([(round(pcbnew.ToMM(q.GetPosition().x) - OX, 3),
                      round(pcbnew.ToMM(q.GetPosition().y) - OY, 3))
                     for q in board.FindFootprintByReference("J2").Pads() if q.GetNumber() == "SH"],
                    key=lambda p: -p[0])[:2]           # the two inboard stakes
    for gp in ("B12", "A12"):
        g = padxy("J2", gp)
        st = min(stakes, key=lambda p: abs(p[1] - g[1]))
        assert abs(st[0] - g[0]) < 0.1, (gp, g, st)
        track(board, gnd, F, g, (g[0], st[1]), POWER_W)

    # 5. CC1 / CC2 each to its own 5.1k, the other end of each to a GND via
    for pad, r, gy in (("A5", "R11", 16.2), ("B5", "R12", 28.8)):
        p, r1, r2 = padxy("J2", pad), padxy(r, "1"), padxy(r, "2")
        near((r1[0], 0), (r2[0], 0))
        net = nets[pads_net(board, "J2", pad)]
        poly(board, net, F, [p, (r1[0], p[1]), r1], SIGNAL_W)
        track(board, gnd, F, r2, (r2[0], gy), POWER_W)
        via(board, gnd, r2[0], gy)

    # 6. probe pad: 5V from the bus up a B.Cu riser to R10, R10 -> pad
    r1, r2 = padxy("R10", "1"), padxy("R10", "2")
    assert r1[1] > r2[1], "R10 pin 1 must be at the bottom"
    via(board, n5, V5UP_X, BUS_Y, big=True)
    track(board, n5, B, (V5UP_X, BUS_Y), (V5UP_X, r1[1] + 1.5), POWER_W)
    via(board, n5, V5UP_X, r1[1] + 1.5, big=True)
    track(board, n5, F, (V5UP_X, r1[1] + 1.5), r1, POWER_W)
    pad = padxy("PAD1", "1")
    padnet = nets["/PAD"]
    poly(board, padnet, F, [r2, (r2[0], 16.0), (pad[0] - 6.0, 16.0)], SIGNAL_W)

    # 7. shield channel: both shield tabs -> R13 -> Q1 base, R14 to GND,
    #    emitter to GND, collector -> B.Cu -> D10 cathode
    shl = nets["/SHLD"]
    s1, s2 = sorted([(round(pcbnew.ToMM(q.GetPosition().x) - OX, 3),
                      round(pcbnew.ToMM(q.GetPosition().y) - OY, 3))
                     for q in board.FindFootprintByReference("J1").Pads() if q.GetNumber() == "SH"])
    r13a, r13b = padxy("R13", "1"), padxy("R13", "2")
    near((0, s1[1]), (0, r13a[1]))
    track(board, shl, F, s1, s2, SIGNAL_W)
    track(board, shl, F, s2, r13a, SIGNAL_W)
    qb, qe, qc = padxy("Q1", "1"), padxy("Q1", "2"), padxy("Q1", "3")
    near((0, qb[1]), (0, r13b[1]))
    qbn = nets["/QB"]
    track(board, qbn, F, r13b, qb, SIGNAL_W)
    r14a, r14b = padxy("R14", "1"), padxy("R14", "2")
    near((r14a[0], 0), (r13b[0], 0))
    # R14 tees into the R13-Q1 run with a 45-degree entry, not a right angle at the pad
    tee = (r13b[0] + 0.8, r13b[1])
    track(board, qbn, F, r14a, (r14a[0], tee[1] + 0.8), SIGNAL_W)
    track(board, qbn, F, (r14a[0], tee[1] + 0.8), tee, SIGNAL_W)
    track(board, gnd, F, r14b, (r14b[0], 9.4), POWER_W)
    via(board, gnd, r14b[0], 9.4)
    track(board, gnd, F, qe, (qe[0], 7.3), POWER_W)
    via(board, gnd, qe[0], 7.3)
    os_ = nets["/OS"]
    k10 = padxy("D10", "1")
    track(board, os_, F, qc, (38.6, qc[1]), SIGNAL_W)
    via(board, os_, 38.6, qc[1])
    poly(board, os_, B, [(38.6, qc[1]), (k10[0], qc[1]), (k10[0], 39.5)], SIGNAL_W)
    via(board, os_, k10[0], 39.5)
    track(board, os_, F, (k10[0], 39.5), k10, SIGNAL_W)


def pads_net(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    return [q for q in fp.Pads() if q.GetNumber() == num][0].GetNetname()


def seg_dist(p, a, b):
    ax, ay, bx, by, px, py = a.x, a.y, b.x, b.y, p.x, p.y
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def via_clear(board, x, y, r, clearance):
    p = pt(x, y)
    need = mm(r + clearance)
    for t in board.GetTracks():
        half = t.GetWidth() / 2 if t.GetClass() == "PCB_TRACK" else t.GetWidth(pcbnew.F_Cu) / 2
        if seg_dist(p, t.GetStart(), t.GetEnd()) < need + half:
            return False
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            sz = pad.GetSize(pcbnew.F_Cu)
            if seg_dist(p, pad.GetPosition(), pad.GetPosition()) < need + max(sz.x, sz.y) / 2 + mm(0.1):
                return False
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if bb.GetWidth() and bb.Contains(p) and fp.GetReference() not in ("PAD1",):
            return False
    return True


def finish():
    board = pcbnew.LoadBoard(str(PCB))
    gnd = board.FindNet("/GND")
    assert gnd is not None
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.35))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetIsFilled(False)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(EDGE, EDGE), (W - EDGE, EDGE), (W - EDGE, H - EDGE), (EDGE, H - EDGE)]:
            ol.Append(mm(OX + x), mm(OY + y))
        board.Add(z)
    kept = 0
    for gx in range(6, int(W) - 3, 6):
        for gy in range(6, int(H) - 3, 6):
            if via_clear(board, gx, gy, 0.3, 0.45):
                via(board, gnd, gx, gy)
                kept += 1
    print("stitching vias kept:", kept)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    print("finished;", len(board.GetTracks()), "track/via items")


if __name__ == "__main__":
    {"place": place, "finish": finish}[sys.argv[1]]()
