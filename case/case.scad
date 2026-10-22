// rj45-mapper case: a base tray and a lid, held together by four M3 screws that
// pass through the lid bosses and the board's mounting holes into the base standoffs.
//
// Frame: the board STL frame from `kicad-cli pcb export stl --user-origin 100x100mm`
// (x right, y up, board spans x 0..75, y -50..0, board top at z = 0 in that file).
// Every component dimension below was measured from that STL (see case/README.md),
// not from a datasheet.
//
// part = "base" | "lid" | "assembly" | "assembly_closed" | "section_jack" | "section_usb" | "fit_base" | "fit_lid"
part = "assembly";

$fn = 48;
BW = 75; BH = 50; BT = 1.6;         // board
C  = 0.5;                            // board edge to inner wall
T  = 2.0;                            // wall
FLOOR = 2.0;
STANDOFF = 5.0;                      // floor to board bottom; clears THT pin tails
Z_BB = FLOOR + STANDOFF;             // board bottom
Z_BT = Z_BB + BT;                    // board top
TALLEST = 12.59;                     // RJ45 body top above board (measured)
CEIL = Z_BT + TALLEST + 0.8;         // lid underside
TOP = CEIL + T;                      // lid top
HOLES = [[3.5, -3.5], [71.5, -3.5], [3.5, -46.5], [71.5, -46.5]];
BOSS_D = 8.0; SCREW_D = 3.4; HEAD_D = 6.0; HEAD_H = 2.5;
PILOT_D = 2.6;                       // M3 self-tapping; 4.0 for a heat-set insert

// RJ45 right-angle body (TE 5555164 model), measured: x 12.28..27.72, plug face flush with
// the board edge at y 0, top 12.59. Its plug cavity is open at the face from 1 to 10 mm.
JACK = [12.28, 27.72]; JACK_CL = 0.6;
// USB-C: receptacle centred on y -22.0, measured z 0.59..4.86 above board top.
// Window sized for a USB-C overmold (12.35 x 6.5 max) so the plug seats fully.
USB_Y = -22.0; USB_ZC = (0.59 + 4.86) / 2; USB_W = 13.0; USB_H = 7.5;
// probe pad (copper): x 59.4..74.4, y -27.5..-12.5; window 1 mm larger, open to the east
PAD = [59.4, 74.4, -27.5, -12.5]; PAD_M = 1.0;
// indicator LEDs: board y -41, x per channel; tubes stop above the measured 2.69 mm
LED_Y = -41.0;
LED_X = [for (i = [0:8]) 9.0 + 5.5 * i];
LED_LBL = ["P", "1", "2", "3", "4", "5", "6", "7", "8"];
TUBE_ID = 3.2; TUBE_OD = 5.0; TUBE_GAP = 2.69 + 0.5;

module outer(z0, z1, r = 3) {
    translate([-C - T, -BH - C - T, z0])
        linear_extrude(z1 - z0)
            offset(r = r) offset(delta = -r)
                square([BW + 2 * (C + T), BH + 2 * (C + T)]);
}
module inner(z0, z1, r = 1) {
    translate([-C, -BH - C, z0])
        linear_extrude(z1 - z0)
            offset(r = r) offset(delta = -r)
                square([BW + 2 * C, BH + 2 * C]);
}

module cutouts() {
    // RJ45 face, through the north wall
    translate([JACK[0] - JACK_CL, -1, Z_BT - 0.3])
        cube([JACK[1] - JACK[0] + 2 * JACK_CL, C + T + 2, TALLEST + 0.6]);
    // USB-C, through the west wall
    translate([-C - T - 1, USB_Y, Z_BT + USB_ZC])
        rotate([0, 90, 0])
            linear_extrude(C + T + 2)
                offset(r = 1.5) offset(delta = -1.5) square([USB_H, USB_W], center = true);
    // probe pad: window in the lid top and the east wall, open down to the board top
    translate([PAD[0] - PAD_M, PAD[2] - PAD_M, Z_BT - 0.2])
        cube([BW + C + T + 1 - (PAD[0] - PAD_M), PAD[3] - PAD[2] + 2 * PAD_M, TOP]);
}

module base() {
    difference() {
        union() {
            difference() {
                outer(0, Z_BB);
                inner(FLOOR, Z_BB + 1);
            }
            for (h = HOLES) translate([h[0], h[1], 0]) cylinder(d = BOSS_D, h = Z_BB);
        }
        for (h = HOLES) translate([h[0], h[1], FLOOR * 0.5]) cylinder(d = PILOT_D, h = Z_BB);
        cutouts();
    }
}

module lid() {
    difference() {
        union() {
            difference() {
                outer(Z_BB, TOP);
                inner(Z_BB - 1, CEIL);
            }
            // bosses clamp the board down onto the standoffs
            for (h = HOLES) translate([h[0], h[1], Z_BT]) cylinder(d = BOSS_D, h = CEIL - Z_BT + 0.01);
            // light tubes: one per LED, so a lit channel does not bleed into its neighbour
            for (x = LED_X) translate([x, LED_Y, Z_BT + TUBE_GAP]) cylinder(d = TUBE_OD, h = CEIL - Z_BT - TUBE_GAP + 0.01);
        }
        for (h = HOLES) {
            translate([h[0], h[1], Z_BT - 1]) cylinder(d = SCREW_D, h = TOP);
            translate([h[0], h[1], TOP - HEAD_H]) cylinder(d = HEAD_D, h = HEAD_H + 1);
        }
        for (x = LED_X) translate([x, LED_Y, Z_BT]) cylinder(d = TUBE_ID, h = TOP);
        // channel labels and title, debossed 0.6 mm into the lid top
        for (i = [0:8]) translate([LED_X[i], LED_Y + 4.6, TOP - 0.6])
            linear_extrude(1) text(LED_LBL[i], size = 3.2, halign = "center", valign = "center",
                                   font = "Liberation Sans:style=Bold");
        for (l = [["RJ45", -16], ["MAPPER", -24]]) translate([44, l[1], TOP - 0.6]) linear_extrude(1)
            text(l[0], size = 5, halign = "center", valign = "center",
                 font = "Liberation Sans:style=Bold");
        translate([(PAD[0] + PAD[1]) / 2, PAD[2] - PAD_M - 3.0, TOP - 0.6]) linear_extrude(1)
            text("TOUCH", size = 3.0, halign = "center", valign = "center",
                 font = "Liberation Sans:style=Bold");
        cutouts();
    }
}

module board() { translate([0, 0, Z_BT]) import("../build/board.stl", convexity = 6); }

if (part == "base") base();
else if (part == "lid") lid();
else if (part == "assembly") {
    color("dimgray") base();
    color("green") board();
    color("lightsteelblue", 0.45) lid();
}
else if (part == "assembly_closed") {
    color("dimgray") base();
    color("green") board();
    color("lightsteelblue") lid();
}
else if (part == "jack_view") {
    color("dimgray") base();
    color("lightsteelblue") lid();
    color("green") translate([0, 0, Z_BT]) import("../build/board-only.stl", convexity = 4);
    color([0.12, 0.12, 0.12]) translate([0, 0, Z_BT]) import("../build/jack.stl", convexity = 6);
}
else if (part == "section_jack") intersection() {
    union() { color("dimgray") base(); color("green") board(); color("lightsteelblue") lid(); }
    translate([20, -60, -1]) cube([60, 70, 40]);          // cut at x = 20 (jack centre)
}
else if (part == "section_usb") intersection() {
    union() { color("dimgray") base(); color("green") board(); color("lightsteelblue") lid(); }
    translate([-10, -60, -1]) cube([100, 38, 40]);        // cut at y = -22 (USB-C centre)
}
else if (part == "fit_base") intersection() { base(); board(); }
else if (part == "fit_lid") intersection() { lid(); board(); }
