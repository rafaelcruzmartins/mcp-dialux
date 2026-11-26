"""Offline tests (no DIALux needed): STF writer, title parsing, report parser on synthetic text."""
import datetime as dt

import pytest

from dialux_mcp_server import report, stf
from dialux_mcp_server.dialux import parse_title

PROJ = {
    "name": "Teste",
    "rooms": [
        {"name": "Sala A", "polygon": [[0, 0], [0, 4], [6, 4], [6, 0], [0, 0]], "height": 2.8,
         "working_plane": 0.75, "maintenance_factor": 0.67,
         "reflectances": {"ceiling": 0.73, "walls": 0.52, "floor": 0.21}},
        {"name": "Sala B", "polygon": [[6, 0], [11, 0], [11, 4], [6, 4]], "height": 3},
    ],
}


def test_stf_layout():
    txt = stf.render(stf.parse_project(PROJ), date=dt.date(2026, 1, 2))
    lines = txt.split("\r\n")
    assert lines[:4] == ["[VERSION]", "STFF=1.0.5", "Progname=dialux-mcp-server", "Progvers=0.1"]
    assert "Date=2026-01-02" in lines and "NrRooms=2" in lines
    assert "Room1=ROOM.R1" in lines and "Room2=ROOM.R2" in lines
    r1 = lines[lines.index("[ROOM.R1]"):lines.index("[ROOM.R2]")]
    assert "Height=2.8" in r1 and "WorkingPlane=0.75" in r1 and "NrPoints=4" in r1
    # closing point dropped, clockwise input turned counter-clockwise
    assert r1[r1.index("NrPoints=4") + 1:r1.index("NrPoints=4") + 5] == [
        "Point1=6 0", "Point2=6 4", "Point3=0 4", "Point4=0 0"]
    assert "R_Ceiling=73" in r1 and "R_Floor=21" in r1 and "R_Wall4=52" in r1 and "MF=0.67" in r1
    assert txt.endswith("\r\n")


@pytest.mark.parametrize("bad, msg", [
    ({"rooms": [{"name": "X", "polygon": [[0, 0], [1, 0]], "height": 3}]}, "3 vértices"),
    ({"rooms": [{"name": "X", "polygon": [[0, 0], [2, 2], [2, 0], [0, 2]], "height": 3}]}, "auto-intercepta"),
    ({"rooms": [{"name": "X=1", "polygon": [[0, 0], [1, 0], [1, 1]], "height": 3}]}, "proibido"),
    ({"rooms": [{"name": "X", "polygon": [[0, 0], [1, 0], [1, 1]], "height": 3, "working_plane": 3}]}, "plano"),
    ({"rooms": [{"name": "X", "polygon": [[0, 0], [1, 0], [1, 1]], "height": 3, "maintenance_factor": 0}]}, "manutenção"),
])
def test_stf_validation(bad, msg):
    with pytest.raises(stf.StfError, match=msg):
        stf.parse_project(bad)


def test_stf_no_overwrite(tmp_path):
    p = tmp_path / "a.stf"
    stf.write(PROJ, p)
    with pytest.raises(stf.StfError, match="já existe"):
        stf.write(PROJ, p)


def test_parse_title():
    t = parse_title(r"C:\x\proj.evo* - DIALux evo 14.0  (64-Bit)")
    assert t == {"project": r"C:\x\proj.evo", "unsaved": True, "version": "14.0"}
    assert parse_title("DIALux evo 14.0  (64-Bit)")["project"] is None


def test_lum_rows():
    rows = report._lum_rows("Un. Fabricante N° do artigo Nome do artigo RUG P Φ Rendimento luminoso\n"
                            "4 dialux-mcp- GEN-PNL- Generico Painel LED 4000lm 33W – 33.0 W 3996 lm 121.1 lm/W\n"
                            "2 Philips 9101 WT210C 19.2 39.0 W 3900 lm 100.0 lm/W")
    assert rows[0]["quantity"] == 4 and rows[0]["power_w"] == 33.0 and rows[0]["ugr"] is None
    assert rows[1]["ugr"] == 19.2 and rows[1]["flux_lm"] == 3900
    rows = report._lum_rows("4 dialux-mcp- GEN-PNL- Generico Painel LED 4000lm 33W 33.0 W 3996 lm 121.1 lm/W")
    assert rows[0]["power_w"] == 33.0 and rows[0]["description"].endswith("33W")
