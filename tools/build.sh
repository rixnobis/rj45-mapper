#!/bin/sh
# Full pipeline: schematic -> ERC -> netlist checks -> placement + scripted route ->
# pours -> DRC with schematic parity -> geometry check -> renders, crops -> fab.
# Stops on any ERC, netlist, DRC or geometry finding.
set -e
cd "$(dirname "$0")/.."
mkdir -p build
python3 tools/gen_sch.py
kicad-cli sch erc --exit-code-violations -o build/erc.rpt rj45-mapper.kicad_sch
python3 tools/check_netlist.py
python3 tools/build_pcb.py place
python3 tools/build_pcb.py finish
kicad-cli pcb drc --schematic-parity --severity-all --exit-code-violations \
    -o build/drc.rpt rj45-mapper.kicad_pcb
python3 tools/check_geometry.py rj45-mapper.kicad_pcb
kicad-cli sch export pdf -o schematic.pdf rj45-mapper.kicad_sch >/dev/null
tools/render.sh renders >/dev/null
tools/crops.sh renders/crops >/dev/null
tools/fab.sh
echo BUILD-OK
