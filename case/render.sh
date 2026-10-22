#!/bin/sh
# STLs for printing, plus assembled, part and section renders, into renders/case/.
set -e
cd "$(dirname "$0")"
out=../renders/case
mkdir -p "$out"
for p in base lid; do openscad -q -D "part=\"$p\"" -o "$p.stl" case.scad; done
python3 fit_check.py 0.2
shot() {  # part out eye(x,y,z) center(x,y,z) [ortho]
    xvfb-run -a openscad -q -D "part=\"$1\"" --camera="$3,$4" ${5:+--projection=ortho} \
        --imgsize=1600,1100 --colorscheme=Tomorrow -o "$out/$2.png" case.scad
}
shot assembly     assembly     -60,-150,110  37,-25,10
shot lid          lid           -60,-150,130  37,-25,10
shot base         base          -60,-150,110  37,-25,5
shot section_jack section-jack -120,-25,12    20,-25,12  ortho
kicad-cli pcb export stl --board-only --force --user-origin 100x100mm \
    -o ../build/board-only.stl ../rj45-mapper.kicad_pcb >/dev/null
shot jack_view    jack-side     45,60,30    20,0,12
shot section_usb  section-usb    37,90,12     37,-22,12  ortho
ls -l "$out"
