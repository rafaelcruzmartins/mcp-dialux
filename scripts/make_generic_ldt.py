"""Write a generic EULUMDAT (.ldt): 600x600 LED panel, Lambertian, rotationally symmetric.

Lambertian: I(g) = I0*cos(g) for g<=90, 0 above; flux = pi*I0  ->  I0 = 1000*LOR/pi cd/klm.
uv run python scripts/make_generic_ldt.py [out.ldt] [flux_lm] [watts]
"""
import math
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/luminarias/generico_painel_4000lm_32W.ldt")
flux = float(sys.argv[2]) if len(sys.argv) > 2 else 4000
watts = float(sys.argv[3]) if len(sys.argv) > 3 else 32
lor = 100.0
gammas = [g * 5 for g in range(37)]  # 0..180 step 5
i0 = 1000 * lor / 100 / math.pi
intens = [round(i0 * math.cos(math.radians(g)), 1) if g <= 90 else 0.0 for g in gammas]
name = f"Generico Painel LED {int(flux)}lm {int(watts)}W"
L = [
    "dialux-mcp-server (generico)",  # 1 company
    "1",            # 2 Ityp point source, vertical symmetry
    "1",            # 3 Isym symmetric about vertical axis
    "36",           # 4 Mc
    "10",           # 5 Dc
    str(len(gammas)),  # 6 Ng
    "5",            # 7 Dg
    "GEN-001",      # 8 measurement report
    name,           # 9 luminaire name
    "GEN-PNL-600",  # 10 luminaire number
    out.name,       # 11 file name
    "2026-11-25",   # 12 date/user
    "600", "600", "50",  # 13-15 luminaire L, W, H (mm)
    "600", "600",   # 16-17 luminous area L, W
    "0", "0", "0", "0",  # 18-21 luminous area heights C0/C90/C180/C270
    "100",          # 22 DFF %
    f"{lor:g}",     # 23 LORL %
    "1",            # 24 conversion factor
    "0",            # 25 tilt
    "1",            # 26 number of lamp sets
    "1",            # 26a number of lamps
    "LED",          # 26b lamp type
    f"{flux:g}",    # 26c total lamp flux
    "4000",         # 26d CCT
    "80",           # 26e CRI group/Ra
    f"{watts:g}",   # 26f wattage incl. gear
]
L += ["0.5", "0.6", "0.67", "0.72", "0.76", "0.8", "0.84", "0.87", "0.9", "0.92"]  # 27 direct ratios
L += [str(c * 10) for c in range(36)]  # 28 C angles
L += [str(g) for g in gammas]          # 29 gamma angles
L += [f"{v:g}" for v in intens]        # 30 intensities (one plane, Isym=1)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(("\r\n".join(L) + "\r\n").encode("latin-1"))
print(out.resolve())
