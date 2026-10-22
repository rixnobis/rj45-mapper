#!/bin/sh
# Gerbers + drill zip, BOM and CPL for JLCPCB assembly, STEP, into fab/.
# The RJ45 jack (J1) is through-hole and hand-soldered, so it is left out of the
# assembly BOM and CPL and listed in fab/hand-solder.csv instead.
set -e
cd "$(dirname "$0")/.."
pcb=rj45-mapper.kicad_pcb; sch=rj45-mapper.kicad_sch
rm -rf fab; mkdir -p fab/gerbers
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
    --subtract-soldermask --no-protel-ext -o fab/gerbers/ "$pcb" >/dev/null
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm \
    --generate-map --map-format gerberx2 -o fab/gerbers/ "$pcb" >/dev/null
(cd fab/gerbers && zip -q ../rj45-mapper-gerbers.zip *)
kicad-cli sch export bom --fields 'Value,Reference,Footprint,LCSC' \
    --labels 'Comment,Designator,Footprint,LCSC Part #' --group-by 'Value,Footprint,LCSC' \
    --ref-range-delimiter '' --exclude-dnp -o fab/bom-all.csv "$sch" >/dev/null
{ head -1 fab/bom-all.csv; grep '"C[0-9]' fab/bom-all.csv | grep -v '"J1"'; } > fab/rj45-mapper-bom.csv
{ head -1 fab/bom-all.csv; grep '"J1"' fab/bom-all.csv; } > fab/hand-solder.csv
rm fab/bom-all.csv
# every placed part except holes, the probe pad and the hand-soldered jack must be in the BOM
python3 - <<'PY2'
import csv, re, subprocess
bom = {r.strip() for row in csv.DictReader(open("fab/rj45-mapper-bom.csv"))
       for r in row["Designator"].split(",")}
sch = open("rj45-mapper.kicad_sch").read()
refs = set(re.findall(r'\(reference "([^"#]+)"\)', sch))
need = {r for r in refs if not re.match(r"^(H\d|PAD\d|J1)$", r)}
missing = sorted(need - bom)
print("BOM covers", len(bom), "of", len(need), "assembled parts")
assert not missing, ("missing from BOM", missing)
PY2
kicad-cli pcb export pos --format csv --units mm --side front --smd-only -o fab/pos.csv "$pcb" >/dev/null
python3 - <<'PY'
import csv, math
# JLC places its own (EasyEDA) model, whose origin and zero rotation can differ from the
# KiCad footprint's. Corrections per KiCad footprint, read off the EasyEDA footprints of
# the BOM's own LCSC parts (easyeda2kicad --footprint), and confirmed in JLC's preview:
#   (dx, dy) = where the EasyEDA origin sits in KiCad footprint-local mm (y down),
#   drot     = degrees added to KiCad's rotation (KiCad and JLC both count CCW).
# SOIC-18W: EasyEDA has pin 1 bottom-left with pins 1-9 along the bottom row; KiCad has
# pin 1 top-left down the left column, so EasyEDA = KiCad turned 90 CCW -> drot -90.
# USB4125: EasyEDA's origin is 1.15 mm toward the SMD pads from KiCad's.
JLC = {
    "Package_SO:SOIC-18W_7.5x11.6mm_P1.27mm": (0.0, 0.0, -90.0),
    "Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal": (0.0, -1.15, 0.0),
}
fps = {}
import re
for m in re.finditer(r'\(footprint "([^"]+)"[\s\S]*?\(property "Reference" "([^"]+)"', open("rj45-mapper.kicad_pcb").read()):
    fps[m.group(2)] = m.group(1)
rows = [r for r in csv.DictReader(open("fab/pos.csv")) if not r["Ref"].startswith(("PAD", "J1"))]
with open("fab/rj45-mapper-cpl.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    fixed = 0
    for r in rows:
        x, y, rot = float(r["PosX"]), float(r["PosY"]), float(r["Rot"])   # pos: y up
        dx, dy, drot = JLC.get(fps.get(r["Ref"], ""), (0.0, 0.0, 0.0))
        if (dx, dy, drot) != (0.0, 0.0, 0.0):
            t = math.radians(rot)
            # footprint-local (y down) -> board (y down): CCW-visual rotation by rot
            bx = dx * math.cos(t) + dy * math.sin(t)
            by = -dx * math.sin(t) + dy * math.cos(t)
            x, y = x + bx, y - by                                           # pos y is up
            rot = (rot + drot + 180.0) % 360.0 - 180.0
            fixed += 1
        w.writerow([r["Ref"], f"{x:.4f}mm", f"{y:.4f}mm", "Top", f"{rot:.1f}"])
assert fixed == len([r for r in rows if fps.get(r["Ref"]) in JLC]) == 2, fixed
print(len(rows), "placements,", fixed, "with JLC model corrections")
PY
rm fab/pos.csv
kicad-cli pcb export step --subst-models --force -o fab/rj45-mapper.step "$pcb" >/dev/null
ls -l fab
