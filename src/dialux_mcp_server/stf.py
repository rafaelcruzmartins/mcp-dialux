"""STF (DIAL "Standard Transfer Format") writer.

DIAL does not publish the STF specification (it is sent on request to CAD
vendors). The layout below follows the two public exporters DIAL itself
points to / that are known to import into DIALux evo:

* kmorin/STF-Exporter (Revit -> STF, listed by DIAL as third-party exporter)
* BHoM/DIALux_Toolkit (Buro Happold)

Both write ``STFF=1.0.5``, an INI-like file with sections ``[VERSION]``,
``[PROJECT]`` and one ``[ROOM.Rn]`` per room, numbers with a dot as decimal
separator (en-US), lengths in metres and the room contour as ``x y`` pairs.
Details that differ between sources (reflectance scale, wall keys) were
settled by importing test files into DIALux evo 14 and reading the values
back; see docs/stf-format.md.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STF_VERSION = "1.0.5"
PROGNAME = "dialux-mcp-server"
PROGVERS = "0.1"

# How reflectances are written. DIALux evo 14 reads them as percent
# (verified on import, see docs/stf-format.md).
REFLECTANCE_AS_PERCENT = True


class StfError(ValueError):
    """Invalid input for the STF writer."""


@dataclass
class RoomSpec:
    name: str
    polygon: list[tuple[float, float]]
    height: float
    working_plane: float = 0.8
    r_ceiling: float = 0.7
    r_walls: float = 0.5
    r_floor: float = 0.2
    maintenance_factor: float | None = None


@dataclass
class ProjectSpec:
    name: str
    rooms: list[RoomSpec] = field(default_factory=list)
    operator: str = ""


def _num(v: float) -> str:
    """en-US number, no exponent, trimmed trailing zeros."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _check_label(field_name: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise StfError(f"{field_name} vazio")
    if any(c in value for c in "\r\n=[]"):
        raise StfError(f"{field_name} {value!r} contém caractere proibido no STF (= [ ] ou quebra de linha)")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as e:
        raise StfError(f"{field_name} {value!r} não cabe em Latin-1 (codificação do STF)") from e
    return value


def _signed_area(poly: list[tuple[float, float]]) -> float:
    a = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def normalize_polygon(points: list[Any]) -> list[tuple[float, float]]:
    """Validate a simple polygon; drop closing duplicate; return counter-clockwise."""
    try:
        poly = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError) as e:
        raise StfError("polígono deve ser lista de pares [x, y] em metros") from e
    if len(poly) > 1 and abs(poly[0][0] - poly[-1][0]) < 1e-9 and abs(poly[0][1] - poly[-1][1]) < 1e-9:
        poly = poly[:-1]
    # drop consecutive duplicates
    clean: list[tuple[float, float]] = []
    for p in poly:
        if not clean or abs(clean[-1][0] - p[0]) > 1e-6 or abs(clean[-1][1] - p[1]) > 1e-6:
            clean.append(p)
    if len(clean) < 3:
        raise StfError("polígono precisa de pelo menos 3 vértices distintos")
    n = len(clean)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) in (1, n - 1):
                continue
            if _segments_intersect(clean[i], clean[(i + 1) % n], clean[j], clean[(j + 1) % n]):
                raise StfError("polígono se auto-intercepta")
    area = _signed_area(clean)
    if abs(area) < 0.01:
        raise StfError("polígono com área ~0")
    if area < 0:
        clean.reverse()
    return clean


def _refl(name: str, v: float) -> str:
    v = float(v)
    if v > 1.0:  # accept percent input too
        v = v / 100.0
    if not 0.0 <= v <= 1.0:
        raise StfError(f"refletância {name}={v} fora de 0..1")
    return _num(v * 100.0) if REFLECTANCE_AS_PERCENT else _num(v)


def parse_project(data: dict[str, Any]) -> ProjectSpec:
    """Build a ProjectSpec from the tool's JSON input."""
    if not isinstance(data, dict):
        raise StfError("entrada deve ser um objeto JSON")
    rooms_in = data.get("rooms") or data.get("ambientes")
    if not rooms_in:
        raise StfError("nenhum ambiente em 'rooms'")
    proj = ProjectSpec(name=_check_label("project name", data.get("name") or data.get("project") or "Projeto"),
                       operator=str(data.get("operator", "")))
    seen = set()
    for i, r in enumerate(rooms_in, 1):
        name = _check_label(f"rooms[{i}].name", r.get("name", ""))
        if name in seen:
            raise StfError(f"nome de ambiente repetido: {name}")
        seen.add(name)
        height = float(r.get("height", 0))
        wp = float(r.get("working_plane", 0.8))
        if height <= 0:
            raise StfError(f"{name}: pé-direito (height) deve ser > 0")
        if not 0 <= wp < height:
            raise StfError(f"{name}: plano de trabalho deve estar entre 0 e o pé-direito")
        refl = r.get("reflectances", {}) or {}
        mf = r.get("maintenance_factor")
        if mf is not None and not 0.01 < float(mf) <= 1:
            raise StfError(f"{name}: fator de manutenção deve estar em (0.01, 1]")
        proj.rooms.append(RoomSpec(
            name=name,
            polygon=normalize_polygon(r.get("polygon") or r.get("contour") or []),
            height=height,
            working_plane=wp,
            r_ceiling=refl.get("ceiling", r.get("r_ceiling", 0.7)),
            r_walls=refl.get("walls", r.get("r_walls", 0.5)),
            r_floor=refl.get("floor", r.get("r_floor", 0.2)),
            maintenance_factor=None if mf is None else float(mf),
        ))
    return proj


def render(proj: ProjectSpec, date: _dt.date | None = None) -> str:
    date = date or _dt.date.today()
    L: list[str] = [
        "[VERSION]",
        f"STFF={STF_VERSION}",
        f"Progname={PROGNAME}",
        f"Progvers={PROGVERS}",
        "[PROJECT]",
        f"Name={proj.name}",
        f"Date={date.isoformat()}",
        f"Operator={proj.operator}",
        f"NrRooms={len(proj.rooms)}",
    ]
    L += [f"Room{i}=ROOM.R{i}" for i in range(1, len(proj.rooms) + 1)]
    for i, r in enumerate(proj.rooms, 1):
        L += [
            f"[ROOM.R{i}]",
            f"Name={r.name}",
            f"Height={_num(r.height)}",
            f"WorkingPlane={_num(r.working_plane)}",
            f"NrPoints={len(r.polygon)}",
        ]
        L += [f"Point{k}={_num(x)} {_num(y)}" for k, (x, y) in enumerate(r.polygon, 1)]
        L.append(f"R_Ceiling={_refl('ceiling', r.r_ceiling)}")
        L.append(f"R_Floor={_refl('floor', r.r_floor)}")
        w = _refl("walls", r.r_walls)
        L += [f"R_Wall{k}={w}" for k in range(1, len(r.polygon) + 1)]
        if r.maintenance_factor is not None:
            L.append(f"MF={_num(r.maintenance_factor)}")
        L += ["NrLums=0", "NrStruct=0", "NrFurns=0"]
    return "\r\n".join(L) + "\r\n"


def write(data: dict[str, Any], out_path: str | Path, overwrite: bool = False) -> dict[str, Any]:
    proj = parse_project(data)
    out = Path(out_path).expanduser().resolve()
    if out.suffix.lower() != ".stf":
        raise StfError("arquivo de saída deve ter extensão .stf")
    if out.exists() and not overwrite:
        raise StfError(f"{out} já existe (use overwrite=true para substituir)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(render(proj).encode("latin-1"))
    return {
        "path": str(out),
        "rooms": [
            {"name": r.name, "area_m2": round(_signed_area(r.polygon), 3), "vertices": len(r.polygon),
             "height": r.height, "working_plane": r.working_plane}
            for r in proj.rooms
        ],
    }
