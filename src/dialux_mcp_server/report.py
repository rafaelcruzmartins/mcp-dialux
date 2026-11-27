"""Parse a DIALux evo 14 PDF report (Portuguese UI) into per-room JSON.

Pages used (header = 2nd line of each page, "<building> · <storey> · <room> [(<scene>)]"):
- "Resumo": area, clear height, reflectances, maintenance factor, mounting and work-plane height
- "Objectos de cálculo" / "Plano de uso (<room>)": Em, Emin, Emax, U0 (g1), g2
- "Lista de luminárias" for the room: quantity, power, flux per luminaire type
- "Resumo" luminaire table, column RUG: UGR when calculated ("–" otherwise)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

NUM = r"(-?\d+(?:[.,]\d+)?)"
SCENE_RE = re.compile(r"\s*\((Cenário de Luz[^)]*)\)\s*$")


def _f(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _room_of(header: str, rooms_hint: set[str] | None) -> tuple[str | None, str | None]:
    scene = None
    m = SCENE_RE.search(header)
    if m:
        scene = m.group(1)
        header = header[: m.start()]
    parts = [p.strip() for p in header.split("·")]
    if len(parts) < 3:
        return None, scene
    room = parts[-1]
    if rooms_hint is not None and room not in rooms_hint:
        return None, scene
    return room, scene


_ROW_UGR = re.compile(rf"^(\d+)\s+(.*?)\s+(–|{NUM})\s+{NUM} W\s+{NUM} lm(?:\s+\S+ lm/W)?\s*$")
_ROW = re.compile(rf"^(\d+)\s+(.*?)\s+{NUM} W\s+{NUM} lm(?:\s+\S+ lm/W)?\s*$")


def _lum_rows(text: str) -> list[dict[str, Any]]:
    """Rows like '4 Philips 9101 WT210C ... [RUG] 39.0 W 3900 lm 100 lm/W' (manufacturer may wrap)."""
    has_ugr = "RUG" in text
    rows = []
    for line in text.splitlines():
        line = line.strip()
        m = _ROW_UGR.match(line) if has_ugr else None
        if m:
            qty, desc, ugr, p, flux = m.group(1), m.group(2), m.group(3), m.group(5), m.group(6)
        else:
            m = _ROW.match(line)
            if not m:
                continue
            qty, desc, p, flux, ugr = m.group(1), m.group(2), m.group(3), m.group(4), None
        rows.append({"quantity": int(qty), "description": desc.strip(), "power_w": _f(p),
                     "flux_lm": _f(flux), "ugr": None if ugr in (None, "–") else _f(ugr)})
    return rows


def read(pdf_path: str | Path, rooms: list[str] | None = None) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    hint = set(rooms) if rooms else None
    out: dict[str, dict[str, Any]] = {}
    project = None

    def room_entry(name: str) -> dict[str, Any]:
        return out.setdefault(name, {
            "room": name, "Em_lx": None, "Emin_lx": None, "Emax_lx": None, "U0": None, "g2": None,
            "UGR": None, "luminaires": [], "luminaire_count": None, "power_w": None,
            "area_m2": None, "clear_height_m": None, "mounting_height_m": None, "workplane_height_m": None,
            "workplane_margin_m": None,
            "maintenance_factor": None, "reflectances_pct": {}, "pages": [],
        })

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for idx, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(lines) < 3:
                continue
            if idx > 1:  # page 1 is the cover
                project = project or lines[0]
            header, title = lines[1], lines[2]

            # Work-plane rows can appear on storey-level pages too: "Plano de uso (<room>) 374 lx 210 lx 467 lx 0.56 0.45"
            for m in re.finditer(rf"Plano de uso \((.+?)\)\s+{NUM} lx\s+{NUM} lx\s+{NUM} lx\s+{NUM}\s+{NUM}", text):
                name = m.group(1)
                if hint is not None and name not in hint:
                    continue
                r = room_entry(name)
                r["Em_lx"], r["Emin_lx"], r["Emax_lx"] = _f(m.group(2)), _f(m.group(3)), _f(m.group(4))
                r["U0"], r["g2"] = _f(m.group(5)), _f(m.group(6))

            room, _scene = _room_of(header, hint)
            if room is None:
                continue
            r = room_entry(room)
            r["pages"].append(idx)

            if title == "Resumo":
                if (m := re.search(rf"Superfície básica {NUM} m²", text)):
                    r["area_m2"] = _f(m.group(1))
                if (m := re.search(rf"Pé direito livre {NUM} m", text)):
                    r["clear_height_m"] = _f(m.group(1))
                if (m := re.search(rf"Altura de montagem {NUM} m", text)):
                    r["mounting_height_m"] = _f(m.group(1))
                if (m := re.search(rf"Altura Plano de uso {NUM} m", text)):
                    r["workplane_height_m"] = _f(m.group(1))
                if (m := re.search(rf"Zona marginal Plano de uso {NUM} m", text)):
                    r["workplane_margin_m"] = _f(m.group(1))
                if (m := re.search(rf"Factor de manutenção {NUM}", text)):
                    r["maintenance_factor"] = _f(m.group(1))
                for key, label in (("ceiling", "Tecto"), ("walls", "Paredes"), ("floor", "Solo")):
                    if (m := re.search(rf"{label}: {NUM} %", text)):
                        r["reflectances_pct"][key] = _f(m.group(1))
                if "RUG" in text:
                    ugrs = [x["ugr"] for x in _lum_rows(text) if x["ugr"] is not None]
                    if ugrs:
                        r["UGR"] = max(ugrs)
            elif title == "Lista de luminárias":
                rows = _lum_rows(text)
                if rows:
                    r["luminaires"] = rows
                    r["luminaire_count"] = sum(x["quantity"] for x in rows)
                    r["power_w"] = round(sum(x["quantity"] * (x["power_w"] or 0) for x in rows), 2)

    rooms_out = list(out.values())
    for r in rooms_out:
        r["complete"] = all(r[k] is not None for k in ("Em_lx", "Emin_lx", "Emax_lx", "U0", "luminaire_count"))
    return {"pdf": str(pdf_path.resolve()), "project": project, "pages": n_pages, "rooms": rooms_out,
            "notes": ["UGR fica null quando o DIALux não o calcula (coluna RUG com '–').",
                      "clear_height_m fica null para ambientes importados de IFC (o relatório não traz essa linha)."]}
