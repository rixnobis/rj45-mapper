#!/bin/sh
# Copper/silk layer plots and 3D renders (top, bottom, iso) of the board.
# usage: tools/render.sh [outdir]
set -e
cd "$(dirname "$0")/.."
out=${1:-renders}
mkdir -p "$out"
pcb=rj45-mapper.kicad_pcb
plot() {  # name layers [extra args]
    name=$1; layers=$2; shift 2
    kicad-cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet \
        --page-size-mode 2 --layers "$layers" "$@" -o "$out/$name.svg" "$pcb" >/dev/null
    rsvg-convert -b white -w 1600 "$out/$name.svg" -o "$out/$name.png"
    rm "$out/$name.svg"
}
plot F.Cu        F.Cu,Edge.Cuts
plot B.Cu        B.Cu,Edge.Cuts --mirror
plot F.SilkS     F.SilkS,F.Mask,Edge.Cuts
plot B.SilkS     B.SilkS,B.Mask,Edge.Cuts --mirror
r() { kicad-cli pcb render --quality high -w 1600 -h 1100 "$@" "$pcb" >/dev/null; }
r --side top -o "$out/3d-top.png"
r --side bottom -o "$out/3d-bottom.png"
r --side top --rotate '-50,0,25' -o "$out/3d-iso.png"
ls -l "$out"
