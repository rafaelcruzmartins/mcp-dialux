"""MCP server (stdio) that drives DIALux evo through UI Automation."""
from __future__ import annotations

import functools
import json
import threading
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import dialux, report, stf, ui
from .ui import DialuxUIError, log

mcp = FastMCP(
    "dialux",
    instructions=(
        "Opera o DIALux evo nesta máquina por automação de interface. Fluxo típico: stf_generate → "
        "dialux_import_stf → dialux_import_luminaire → dialux_place_luminaires (por ambiente) → "
        "dialux_set_maintenance_factor → dialux_calculate → dialux_export_report → report_read. "
        "Uma ferramenta por vez: a interface do DIALux é única. Nunca sobrescreve .evo existentes."
    ),
)
_lock = threading.Lock()  # one UI operation at a time


def tool(fn):
    """Register a tool: serialize UI access, log, and turn UI errors into clear messages."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            t0 = time.monotonic()
            log.info("TOOL %s %s", fn.__name__, json.dumps(kwargs, ensure_ascii=False, default=str))
            try:
                if fn.__name__ not in ("stf_generate", "report_read"):
                    if ui.session_locked():
                        raise DialuxUIError("A sessão do Windows está bloqueada: com a tela bloqueada o DIALux não "
                                            "aceita valores digitados. Desbloqueie o computador e repita.")
                    ui.ensure_restored()
                out = fn(*args, **kwargs)
            except (DialuxUIError, stf.StfError, FileNotFoundError, ValueError) as e:
                log.error("TOOL %s falhou: %s", fn.__name__, e)
                raise RuntimeError(f"{fn.__name__}: {e}") from e
            except Exception as e:  # noqa: BLE001
                log.exception("TOOL %s erro inesperado", fn.__name__)
                raise RuntimeError(f"{fn.__name__}: erro inesperado {type(e).__name__}: {e}") from e
            log.info("TOOL %s ok em %.1fs", fn.__name__, time.monotonic() - t0)
            return out
    return mcp.tool()(wrapper)


@tool
def dialux_status() -> dict[str, Any]:
    """Estado do DIALux: se está aberto, versão, projeto ativo, alterações não salvas, login e modal aberto."""
    return dialux.status()


@tool
def dialux_open(evo_path: str | None = None) -> dict[str, Any]:
    """Abre o DIALux (se fechado) e, opcionalmente, um projeto .evo existente.

    Alterações não salvas do projeto atual são DESCARTADAS (o servidor nunca salva por cima).
    """
    st = dialux.launch()
    if evo_path:
        st = dialux.open_project(Path(evo_path))
    return st


@tool
def dialux_new() -> dict[str, Any]:
    """Cria um projeto vazio (descarta alterações não salvas do projeto atual)."""
    dialux.launch()
    return dialux.new_project()


@tool
def dialux_save_as(evo_path: str) -> dict[str, Any]:
    """Salva o projeto atual num NOVO arquivo .evo. Recusa se o arquivo já existir."""
    return dialux.save_as(Path(evo_path))


@tool
def stf_generate(project: dict[str, Any], out_path: str, overwrite: bool = False) -> dict[str, Any]:
    """Gera um arquivo .stf (formato DIAL STF 1.0.5) a partir de JSON de ambientes.

    project = {"name": "Projeto", "rooms": [{"name": "Sala 1", "polygon": [[0,0],[6,0],[6,4],[0,4]],
               "height": 2.8, "working_plane": 0.8, "maintenance_factor": 0.8,
               "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2}}]}
    Polígono em metros (sem repetir o ponto inicial); refletâncias em fração 0..1.
    """
    return stf.write(project, out_path, overwrite=overwrite)


@tool
def dialux_import_stf(stf_path: str, project_json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Importa um .stf como projeto novo e confere ambientes, pé-direito, plano de trabalho e FM.

    O DIALux evo aplica um único pé-direito a todas as salas de um STF e ignora as refletâncias do
    arquivo; passe o mesmo JSON usado em stf_generate (project_json) para que pé-direito (conferido na
    interface) e refletâncias (conferir depois com report_read) sejam aplicados por ambiente.
    """
    heights = refl = None
    if project_json:
        spec = stf.parse_project(project_json).rooms
        heights = {r.name: r.height for r in spec}
        norm = lambda v: v / 100 if v > 1 else v  # noqa: E731
        refl = {r.name: (norm(r.r_ceiling), norm(r.r_walls), norm(r.r_floor)) for r in spec}
    res = dialux.import_stf(Path(stf_path), heights, refl)
    if project_json:
        want = {r.name for r in stf.parse_project(project_json).rooms}
        got = {r["name"] for r in res["rooms"]}
        if want != got:
            raise DialuxUIError(f"Ambientes importados {sorted(got)} diferem do JSON {sorted(want)}.")
    return res


@tool
def dialux_import_ifc(ifc_path: str, method: str = "novo", use_dialux_reflectances: bool = True,
                      working_plane: float | None = None, simplify_names: bool = True,
                      workplane_margin: float | None = None) -> dict[str, Any]:
    """Importa um IFC (ex.: exportado do Revit) como projeto novo, criando um ambiente por IfcSpace.

    Fecha o projeto atual descartando alterações não salvas. method: 'novo' (recomendado pelo DIALux)
    ou 'legado'. use_dialux_reflectances=True aplica as refletâncias padrão do DIALux; False mantém as
    do IFC. working_plane (m) define o plano de trabalho de todos os ambientes (padrão do DIALux: 0,80).
    simplify_names transforma 'Sala A - Sala A' (Name - LongName) em 'Sala A'.
    workplane_margin (m): zona marginal do plano de trabalho; o IFC entra com 0,50 m (o STF com 0,00 m).
    Confere: nº de ambientes = nº de IfcSpace; devolve pé-direito, plano de trabalho e FM lidos na interface.
    """
    return dialux.import_ifc(Path(ifc_path), method, use_dialux_reflectances, working_plane, simplify_names,
                             workplane_margin)


@tool
def dialux_set_reflectances(room: str, ceiling: float, walls: float, floor: float) -> dict[str, Any]:
    """Define as refletâncias (fração 0..1) de teto, paredes e piso de um ambiente."""
    return dialux.set_reflectances(room, ceiling, walls, floor)


@tool
def dialux_import_luminaire(file_path: str) -> dict[str, Any]:
    """Importa um arquivo fotométrico LDT/IES para o projeto e o torna a luminária ativa."""
    return dialux.import_luminaire(Path(file_path))


@tool
def dialux_place_luminaires(room: str, luminaire: str, mounting_height: float | None = None,
                            target_lux: float | None = None, count_x: int | None = None,
                            count_y: int | None = None) -> dict[str, Any]:
    """Distribui luminárias em campo num ambiente (Distribuição automática para áreas).

    luminaire: nome (ou início do nome) no catálogo do projeto, ex. o 'catalog_name' de
    dialux_import_luminaire. Use target_lux (iluminância média alvo) OU count_x + count_y (quantidade fixa).
    mounting_height em metros (opcional; padrão = teto).
    """
    return dialux.place_luminaires(room, luminaire, mounting_height, target_lux, count_x, count_y)


@tool
def dialux_set_maintenance_factor(maintenance_factor: float, rooms: list[str] | None = None) -> list[dict[str, Any]]:
    """Define o fator de manutenção (valor fixo) nos ambientes indicados (padrão: todos)."""
    return dialux.set_maintenance_factor(maintenance_factor, rooms)


@tool
def dialux_calculate(timeout_s: float = 1800) -> dict[str, Any]:
    """Calcula todo o projeto e aguarda o fim. Erro se o DIALux registrar falha de cálculo."""
    return dialux.calculate(timeout_s)


@tool
def dialux_export_report(out_pdf: str) -> dict[str, Any]:
    """Gera a documentação completa e exporta para PDF (arquivo novo; recusa sobrescrever)."""
    return dialux.export_report(Path(out_pdf))


@tool
def report_read(pdf_path: str, rooms: list[str] | None = None) -> dict[str, Any]:
    """Lê um relatório PDF do DIALux evo e devolve, por ambiente: Em, Emin, Emax, U0, g2, UGR,
    quantidade e potência de luminárias, área, alturas, FM e refletâncias."""
    return report.read(pdf_path, rooms)


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
