#!/usr/bin/env python3
"""Generate rj45-mapper.kicad_sch.

Stock KiCad symbols are extracted and embedded; the probe pad uses a local
symbol. Connectivity is carried by net labels on short pin stubs, so the gate
is ERC plus the netlist checks in check_netlist.py, not drawn wires.
"""
import math
import re
import sys
import uuid as uuidlib
from pathlib import Path

SYMDIR = Path("/usr/share/kicad/symbols")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "rj45-mapper.kicad_sch"
ROOT_UUID = "a2d7f6c1-4b3e-4a90-8c21-0e5d7b9a1c33"

# ---- symbol extraction (same approach as ps1-port-tap) ----


def uid():
    return str(uuidlib.uuid4())


def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def extract_symbol(lib, name):
    text = (SYMDIR / f"{lib}.kicad_sym").read_text()
    m = re.search(r'\n\t\(symbol "%s"\n' % re.escape(name), text)
    if not m:
        sys.exit(f"symbol {lib}:{name} not found")
    start = m.start() + 2
    depth = 0
    i = start
    in_str = False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = text[start:i + 1]
    assert body.startswith(f'(symbol "{name}"'), body[:60]
    body = body.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
    pins = {}
    for pm in re.finditer(
        r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)\s*\(length [-\d.]+\)'
        r'(?:\s*\(hide yes\))?\s*\(name "[^"]*"(?:.|\n)*?\(number "([^"]+)"', body):
        pins[pm[4]] = (float(pm[1]), float(pm[2]), float(pm[3]))
    return body, pins


LIBID = {
    "USB_C_Receptacle_PowerOnly_6P": "Connector:USB_C_Receptacle_PowerOnly_6P",
    "ULN2803A": "Transistor_Array:ULN2803A",
    "LED": "Device:LED",
    "R": "Device:R",
    "8P8C": "Connector:8P8C",
    "Conn_01x01": "Connector_Generic:Conn_01x01",
    "MountingHole": "Mechanical:MountingHole",
    "PWR_FLAG": "power:PWR_FLAG",
}
LIBS = {
    "USB_C_Receptacle_PowerOnly_6P": extract_symbol("Connector", "USB_C_Receptacle_PowerOnly_6P"),
    "ULN2803A": extract_symbol("Transistor_Array", "ULN2803A"),
    "LED": extract_symbol("Device", "LED"),
    "R": extract_symbol("Device", "R"),
    "8P8C": extract_symbol("Connector", "8P8C"),
    "Conn_01x01": extract_symbol("Connector_Generic", "Conn_01x01"),
    "MountingHole": extract_symbol("Mechanical", "MountingHole"),
    "PWR_FLAG": extract_symbol("power", "PWR_FLAG"),
}

items = []


def place(kind, ref, value, footprint, x, y, nets, angle=0, fields_extra=(), mirror=False):
    x = round(x / 1.27) * 1.27   # keep origins (and thus pin stubs) on the 1.27 mm grid
    y = round(y / 1.27) * 1.27
    _, pins = LIBS[kind]
    su = uid()
    pin_uuids = "".join(f'\n\t\t(pin "{n}"\n\t\t\t(uuid "{uid()}")\n\t\t)' for n in pins)
    extra = "".join(
        f'\n\t\t(property "{k}" "{v}"\n\t\t\t(at {fmt(x)} {fmt(y)} 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)'
        for k, v in fields_extra)
    in_bom = "no" if kind in ("MountingHole", "PWR_FLAG") or ref.startswith("PAD") else "yes"
    mir = "\n\t\t(mirror y)" if mirror else ""
    items.append(f'''	(symbol
		(lib_id "{LIBID[kind]}")
		(at {fmt(x)} {fmt(y)} {fmt(angle)}){mir}
		(unit 1)
		(exclude_from_sim no)
		(in_bom {in_bom})
		(on_board yes)
		(dnp no)
		(uuid "{su}")
		(property "Reference" "{ref}"
			(at {fmt(x + 5.08)} {fmt(y - 3.81)} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
		(property "Value" "{value}"
			(at {fmt(x + 5.08)} {fmt(y + 3.81)} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
		(property "Footprint" "{footprint}"
			(at {fmt(x)} {fmt(y)} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		)
		(property "Datasheet" ""
			(at {fmt(x)} {fmt(y)} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
				(hide yes)
			)
		){extra}{pin_uuids}
		(instances
			(project "rj45-mapper"
				(path "/{ROOT_UUID}"
					(reference "{ref}")
					(unit 1)
				)
			)
		)
	)''')
    # schematic y is down and KiCad symbol angles are counter-clockwise on screen,
    # so the on-sheet rotation is by -angle
    ca, sa = math.cos(math.radians(-angle)), math.sin(math.radians(-angle))
    for num, net in nets.items():
        px, py, pa = pins[num]
        # rotate pin position by the symbol angle; KiCad schematic y is down, so
        # the library y (up) is negated, then the standard 2D rotation applies.
        lx, ly = px, -py
        if mirror:
            lx = -lx
        rx = lx * ca - ly * sa
        ry = lx * sa + ly * ca
        sx, sy = x + rx, y + ry
        # pin direction in library frame points OUT of the body at angle pa
        da = pa + angle + (180 if mirror else 0)
        dx, dy = -math.cos(math.radians(da)), math.sin(math.radians(da))
        ex, ey = sx + 2.54 * dx, sy + 2.54 * dy
        items.append(f'''	(wire
		(pts
			(xy {fmt(sx)} {fmt(sy)}) (xy {fmt(ex)} {fmt(ey)})
		)
		(stroke
			(width 0)
			(type default)
		)
		(uuid "{uid()}")
	)''')
        if abs(dx) > 0.5:
            lang, just = (180, "right") if dx < 0 else (0, "left")
        else:
            lang, just = (90, "left") if dy < 0 else (270, "right")
        items.append(f'''	(label "{net}"
		(at {fmt(ex)} {fmt(ey)} {lang})
		(effects
			(font
				(size 1.27 1.27)
			)
			(justify {just} bottom)
		)
		(uuid "{uid()}")
	)''')


def text(s, x, y, size=1.27):
    s = s.replace('"', '\\"').replace("\n", "\\n")
    items.append(f'''	(text "{s}"
		(exclude_from_sim no)
		(at {fmt(x)} {fmt(y)} 0)
		(effects
			(font
				(size {size} {size})
			)
			(justify left bottom)
		)
		(uuid "{uid()}")
	)''')


# ---- footprints and part numbers ----
F_USBC = "Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal"
F_ULN = "Package_SO:SOIC-18W_7.5x11.6mm_P1.27mm"
F_LED = "LED_SMD:LED_1206_3216Metric"
F_R = "Resistor_SMD:R_0805_2012Metric"
F_RJ = "rj45-mapper:RJ45_8P8C_RightAngle"   # Pixel's drawing; he supplies the jack
F_PAD = "rj45-mapper:ProbePad_15x15"
F_MH = "MountingHole:MountingHole_3.2mm_M3"

LCSC_R330 = "C17630"
LCSC_R1K = "C17513"
LCSC_R51K = "C27834"
LCSC_LED = "C84270"
LCSC_ULN = "C845537"
LCSC_USBC = "C3151650"


def lc(code):
    return (("LCSC", code),)


# ---- schematic layout (label-based; positions chosen for a legible PDF) ----
# RJ45 jack, inputs to the ULN
place("8P8C", "J1", "TE 5555164-1 or equal, RA unshielded", F_RJ, 38.1, 50.8, {str(n): f"IN{n}" for n in range(1, 9)})

# ULN2803A: in1..in8 = IN1..IN8, out On on pins 18..11, pin9 GND, pin10 COM=5V
uln_nets = {str(n): f"IN{n}" for n in range(1, 9)}
uln_nets["9"] = "GND"
uln_nets["10"] = "5V"
for n in range(1, 9):
    uln_nets[str(19 - n)] = f"O{n}"   # O1 -> pin18 ... O8 -> pin11
place("ULN2803A", "U1", "ULN2803A", F_ULN, 88.9, 48.26, uln_nets, fields_extra=lc(LCSC_ULN))

# indicator LEDs 1..8 and their 330R series resistors, one per channel
for n in range(1, 9):
    y = 25.4 + 10.16 * (n - 1)
    place("R", f"R{n}", "330", F_R, 127.0, y, {"1": "5V", "2": f"LEDA{n}"},
          angle=90, fields_extra=lc(LCSC_R330))
    place("LED", f"D{n}", "RED", F_LED, 147.32, y, {"2": f"LEDA{n}", "1": f"O{n}"},
          fields_extra=lc(LCSC_LED))

# power-good LED
place("R", "R9", "1k", F_R, 127.0, 113.0, {"1": "5V", "2": "PWRA"}, angle=90,
      fields_extra=lc(LCSC_R1K))
place("LED", "D9", "RED", F_LED, 147.32, 113.0, {"2": "PWRA", "1": "GND"},
      fields_extra=lc(LCSC_LED))

# probe pad fed from 5V through 1k
place("R", "R10", "1k", F_R, 38.1, 95.25, {"1": "5V", "2": "PAD"}, angle=90,
      fields_extra=lc(LCSC_R1K))
place("Conn_01x01", "PAD1", "PROBE_PAD", F_PAD, 58.42, 95.25, {"1": "PAD"})

# power flags so ERC sees the rails driven (USB-C power pins are inputs)
place("PWR_FLAG", "#FLG1", "PWR_FLAG", "", 198.12, 60.96, {"1": "5V"})
place("PWR_FLAG", "#FLG2", "PWR_FLAG", "", 205.74, 60.96, {"1": "GND"})

# USB-C power in, each CC with its own 5.1k
place("USB_C_Receptacle_PowerOnly_6P", "J2", "USB-C_5V", F_USBC, 190.5, 48.26,
      {"A9": "5V", "B9": "5V", "A12": "GND", "B12": "GND", "A5": "CC1", "B5": "CC2",
       "SH": "GND"}, fields_extra=lc(LCSC_USBC))
place("R", "R11", "5.1k", F_R, 215.9, 38.1, {"1": "CC1", "2": "GND"}, angle=90,
      fields_extra=lc(LCSC_R51K))
place("R", "R12", "5.1k", F_R, 236.22, 38.1, {"1": "CC2", "2": "GND"}, angle=90,
      fields_extra=lc(LCSC_R51K))

# mounting holes
for i in range(4):
    place("MountingHole", f"H{i + 1}", "M3", F_MH, 190.5 + 10.16 * i, 90.0, {})

text("RJ45 CABLE MAPPER  rev A  rixnobis", 25.4, 15.24, 2.54)
text("Touch a flying wire to PAD1; the LED for its 8P8C pin lights. ULN2803A sinks each\\n"
     "LED. PAD at 5V through 1k, so a wire grounded at the far end draws 5 mA, not a short.\\n"
     "A finger bridging pad and wire (~1 Mohm) holds the ULN input under 0.1 V, far below the\\n"
     "two-VBE turn-on, so only metal-to-metal contact lights an LED. Two shorted wires light two.",
     25.4, 19.0, 1.27)
text("The RJ45 jack is the only through-hole part: an unshielded right-angle 8P8C on the\\n"
     "TE 5555164 / Amphenol 54602 land pattern, supplied and hand-soldered by the builder.\\n"
     "Everything else is SMD, JLC-assembled.",
     127.0, 134.62, 1.27)

lib_symbols = "\n".join("\t\t" + LIBS[k][0].replace("\n", "\n\t") for k in LIBS)

OUT.write_text(f'''(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{ROOT_UUID}")
	(paper "A3")
	(title_block
		(title "rj45-mapper")
		(rev "A")
		(company "rixnobis")
	)
	(lib_symbols
{lib_symbols}
	)
{chr(10).join(items)}
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(embedded_fonts no)
)
''')
print("wrote", OUT)
