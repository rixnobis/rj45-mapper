#!/usr/bin/env python3
"""Check the schematic netlist against the intended circuit, pin by pin.

ERC passes a label-based schematic with a wrong pin number, so this is the gate
that says jack pin n reaches ULN input n, ULN output n reaches LED n, and so on.
ULN2803A pins checked against the UTC and UMW datasheets: IN n = pin n,
OUT n = pin 19-n, GND = 9, COM = 10. MMBT3904 SOT-23: 1 B, 2 E, 3 C.
Exits 1 on any mismatch; prints the count of checks run.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCH = ROOT / "rj45-mapper.kicad_sch"
xml = ROOT / "build" / "netlist.xml"
xml.parent.mkdir(exist_ok=True)
subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml", "-o", str(xml),
                str(SCH)], check=True, capture_output=True)
r = ET.parse(xml).getroot()
net_of = {}
for n in r.find("nets"):
    for node in n:
        net_of[(node.get("ref"), node.get("pin"))] = n.get("name")

expect = []   # groups of (ref, pin) that must share one net, plus a required net name or None
for n in range(1, 9):
    expect.append(([("J1", str(n)), ("U1", str(n))], None))            # jack pin n -> input n
    expect.append(([("U1", str(19 - n)), (f"D{n}", "1")], None))        # output n -> LED n cathode
    expect.append(([(f"D{n}", "2"), (f"R{n}", "2")], None))             # LED n anode -> its R
    expect.append(([(f"R{n}", "1")], "/5V"))
expect += [
    ([("U1", "9")], "/GND"), ([("U1", "10")], "/5V"),
    ([("J2", "A9"), ("J2", "B9")], "/5V"),
    ([("J2", "A12"), ("J2", "B12")], "/GND"),
    ([("J2", "A5"), ("R11", "1")], None), ([("R11", "2")], "/GND"),
    ([("J2", "B5"), ("R12", "1")], None), ([("R12", "2")], "/GND"),
    ([("R10", "1")], "/5V"), ([("R10", "2"), ("PAD1", "1")], None),
    ([("R9", "1")], "/5V"), ([("R9", "2"), ("D9", "2")], None), ([("D9", "1")], "/GND"),
    ([("J1", "SH"), ("R13", "1")], None), ([("R13", "2"), ("R14", "1"), ("Q1", "1")], None),
    ([("R14", "2"), ("Q1", "2")], "/GND"), ([("Q1", "3"), ("D10", "1")], None),
    ([("D10", "2"), ("R15", "2")], None), ([("R15", "1")], "/5V"),
]
bad = 0
for group, name in expect:
    nets = {net_of.get(p) for p in group}
    if None in nets or len(nets) != 1 or (name and nets != {name}):
        print("MISMATCH", group, "->", sorted(str(x) for x in nets), "want", name or "one net")
        bad += 1
# the CC pins must NOT share a resistor
if net_of.get(("J2", "A5")) == net_of.get(("J2", "B5")):
    print("MISMATCH CC1 and CC2 share a net")
    bad += 1
# the shield must not be grounded, or the S channel can never light
if net_of.get(("J1", "SH")) in ("/GND", "/5V"):
    print("MISMATCH jack shield tied to a rail")
    bad += 1
print(f"check_netlist: {len(expect) + 2} checks, {bad} mismatches")
sys.exit(1 if bad else 0)
