"""End-to-end test through the MCP protocol (stdio): 2 rooms, generic LDT, 300 lx, report -> JSON.

Requires DIALux evo open and logged in. Run:  uv run python tests/live/e2e.py [--from N]
Each step calls one tool; the run stops at the first error.
"""
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / f"e2e-{dt.datetime.now():%Y%m%d-%H%M%S}"
PROJECT = json.loads((ROOT / "examples" / "duas-salas.json").read_text(encoding="utf-8-sig"))
LDT = ROOT / "examples" / "luminarias" / "generico_painel_4000lm_32W.ldt"
TARGET = 300

IFC_MODE = "--ifc" in sys.argv  # same 2 rooms from examples/ifc/duas-salas.ifc (scripts/make_test_ifc.py)
IFC = ROOT / "examples" / "ifc" / "duas-salas.ifc"
if IFC_MODE:
    OUT = OUT.with_name(OUT.name + "-ifc")
    for _r in PROJECT["rooms"]:  # what the IFC import is expected to produce
        _r["working_plane"] = 0.75
        _r["reflectances"] = {"ceiling": 0.7, "walls": 0.5, "floor": 0.2}  # DIALux defaults

IMPORT_STEPS = [
    ("dialux_import_ifc", lambda r: {"ifc_path": str(IFC), "working_plane": 0.75, "workplane_margin": 0.0}),
] if IFC_MODE else [
    ("stf_generate", lambda r: {"project": PROJECT, "out_path": str(OUT / "duas-salas.stf")}),
    ("dialux_import_stf", lambda r: {"stf_path": r["stf_generate"]["path"], "project_json": PROJECT}),
]

STEPS = [
    ("dialux_status", lambda r: {}),
    ("dialux_open", lambda r: {}),
    *IMPORT_STEPS,
    ("dialux_import_luminaire", lambda r: {"file_path": str(LDT)}),
    *[(f"dialux_place_luminaires#{room['name']}",
       (lambda name: lambda r: {"room": name, "luminaire": r["dialux_import_luminaire"]["catalog_name"],
                                "target_lux": TARGET})(room["name"]))
      for room in PROJECT["rooms"]],
    ("dialux_set_maintenance_factor", lambda r: {"maintenance_factor": 0.8}),
    ("dialux_calculate", lambda r: {}),
    ("dialux_export_report", lambda r: {"out_pdf": str(OUT / "relatorio.pdf")}),
    ("report_read", lambda r: {"pdf_path": r["dialux_export_report"]["pdf"]}),
    ("dialux_save_as", lambda r: {"evo_path": str(OUT / "duas-salas.evo")}),
]


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=["-m", "dialux_mcp_server"], cwd=str(ROOT),
                                   env={"PYTHONPATH": str(ROOT / "src")})
    results = {}
    async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
        await s.initialize()
        for step, args_fn in STEPS:
            name = step.split("#")[0]
            args = args_fn(results)
            print(f"\n>>> {step} {json.dumps(args, ensure_ascii=False)[:200]}", flush=True)
            res = await s.call_tool(name, args)
            text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
            if res.isError:
                print("ERRO:", text)
                sys.exit(1)
            data = res.structuredContent.get("result", res.structuredContent) if res.structuredContent else json.loads(text)
            results[step.split("#")[0] if "#" not in step else step] = data
            results[name] = data
            print(json.dumps(data, ensure_ascii=False, indent=1)[:3000])
    (OUT / "resultado.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = results["report_read"]
    print("\n=== RESUMO ===")
    for r in rep["rooms"]:
        print(f"{r['room']}: Em={r['Em_lx']} Emin={r['Emin_lx']} Emax={r['Emax_lx']} U0={r['U0']} "
              f"UGR={r['UGR']} lum={r['luminaire_count']} P={r['power_w']} W refl={r['reflectances_pct']} "
              f"h={r['clear_height_m']} FM={r['maintenance_factor']}")
    print("saída:", OUT)

    # checks against the input JSON
    fails = []
    by = {r["room"]: r for r in rep["rooms"]}
    for spec in PROJECT["rooms"]:
        r = by.get(spec["name"])
        if r is None:
            fails.append(f"{spec['name']}: ausente no relatório")
            continue
        refl = spec.get("reflectances", {})
        checks = [
            ("luminárias > 0", (r["luminaire_count"] or 0) > 0),
            (f"Em >= {TARGET} lx", (r["Em_lx"] or 0) >= TARGET),
            ("pé-direito", (r["clear_height_m"] if r["clear_height_m"] is not None else
                            float(next(x["height"] for x in results["dialux_import_ifc"]["rooms"]
                                       if x["name"] == spec["name"]))) == spec["height"]),
            ("zona marginal 0", r["workplane_margin_m"] == 0.0),
            ("plano de trabalho", r["workplane_height_m"] == spec["working_plane"]),
            ("FM 0.8", r["maintenance_factor"] == 0.8),
            ("refletâncias", r["reflectances_pct"] == {"ceiling": round(refl["ceiling"] * 100, 1),
                                                      "walls": round(refl["walls"] * 100, 1),
                                                      "floor": round(refl["floor"] * 100, 1)}),
        ]
        for label, ok in checks:
            print(f"  [{'ok' if ok else 'FALHA'}] {spec['name']}: {label}")
            if not ok:
                fails.append(f"{spec['name']}: {label}")
    if fails:
        print("FALHAS:", fails)
        sys.exit(2)
    print("TODAS AS CONFERÊNCIAS OK")


asyncio.run(main())
