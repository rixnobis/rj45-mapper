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
import csv
rows = [r for r in csv.DictReader(open("fab/pos.csv")) if not r["Ref"].startswith(("PAD", "J1"))]
with open("fab/rj45-mapper-cpl.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in rows:
        w.writerow([r["Ref"], r["PosX"] + "mm", r["PosY"] + "mm", "Top", r["Rot"]])
print(len(rows), "placements")
PY
rm fab/pos.csv
kicad-cli pcb export step --subst-models --force -o fab/rj45-mapper.step "$pcb" >/dev/null
ls -l fab
