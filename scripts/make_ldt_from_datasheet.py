"""Write an EULUMDAT (.ldt) from datasheet data: dimensions, luminous flux, power, opal 120° optic.

An opal (leitosa) diffuser with a 120° beam is modelled as Lambertian (I = I0*cos g; half intensity at 60°,
i.e. 120° beam). This is an ESTIMATE, not the manufacturer's measured photometry; the luminaire name says so.
Full C-plane matrix (Isym=0): DIALux evo 14 fails to calculate with Isym=1 files.

uv run python scripts/make_ldt_from_datasheet.py out.ldt "Nome" CODIGO "Fabricante" flux_lm watts L_mm W_mm H_mm
"""
import math
import sys
from pathlib import Path


def write_ldt(out: Path, name: str, number: str, maker: str, flux: float, watts: float,
              length: float, width: float, height: float) -> Path:
    gammas = [g * 5 for g in range(37)]  # 0..180
    cplanes = [c * 15 for c in range(24)]
    i0 = 1000 / math.pi  # cd/klm, LOR 100 %
    intens = [round(i0 * math.cos(math.radians(g)), 1) if g <= 90 else 0.0 for g in gammas]
    L = [maker, "1", "0", str(len(cplanes)), "15", str(len(gammas)), "5", "DATASHEET-EST",
         name, number, out.name, "2026-11-27",
         f"{length:g}", f"{width:g}", f"{height:g}", f"{length:g}", f"{width:g}", "0", "0", "0", "0",
         "100", "100", "1", "0", "1", "1", "LED", f"{flux:g}", "4000", "80", f"{watts:g}"]
    L += ["0.5", "0.6", "0.67", "0.72", "0.76", "0.8", "0.84", "0.87", "0.9", "0.92"]
    L += [str(c) for c in cplanes]
    L += [str(g) for g in gammas]
    L += [f"{v:g}" for _ in cplanes for v in intens]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(("\r\n".join(L) + "\r\n").encode("latin-1"))
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    print(write_ldt(Path(a[0]), a[1], a[2], a[3], float(a[4]), float(a[5]), float(a[6]), float(a[7]), float(a[8])))
