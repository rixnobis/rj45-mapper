#!/bin/sh
# Zoomed F.Cu | B.Cu crops (60 px/mm) of the dense regions, for routing detail the
# board-scale plots hide. B.Cu is NOT mirrored, so both halves share coordinates.
# usage: tools/crops.sh [outdir]
set -e
cd "$(dirname "$0")/.."
pcb=rj45-mapper.kicad_pcb
out=${1:-renders/crops}
PXMM=60
mkdir -p "$out"
tmp=$(mktemp -d)
for L in F.Cu B.Cu; do
    kicad-cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet \
        --page-size-mode 2 --layers "$L,Edge.Cuts" -o "$tmp/$L.svg" "$pcb" >/dev/null
    rsvg-convert -b white -w $((75 * PXMM)) "$tmp/$L.svg" -o "$tmp/$L.png"
done
crop() {  # name x0 y0 w h (mm, board coordinates)
    g="$(($4 * PXMM))x$(($5 * PXMM))+$(($2 * PXMM))+$(($3 * PXMM))"
    magick "$tmp/F.Cu.png" -crop "$g" +repage -bordercolor black -border 4 "$tmp/f.png"
    magick "$tmp/B.Cu.png" -crop "$g" +repage -bordercolor black -border 4 "$tmp/b.png"
    magick "$tmp/f.png" "$tmp/b.png" +append "$out/$1.png"
}
crop usb        0 14 14 18
crop jack-uln  11  0 16 34
crop rows      10 30 16 12
crop shield    26  0 16 12
crop leds-r    20 37 16 13
rm -r "$tmp"
ls "$out"
