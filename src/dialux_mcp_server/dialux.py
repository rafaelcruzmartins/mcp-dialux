"""High-level DIALux evo 14 operations built on ui.py (see docs/ui-map.md)."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from . import ui
from .ui import DialuxUIError, log

M = ui.main_window
TITLE_RE = re.compile(r"^(?:(?P<path>.+?)(?P<dirty>\*)? - )?DIALux evo (?P<ver>[\d.]+)")
ROOMS_NODE = "_Salas e espaços_"  # localized (pt) tree node holding rooms


# ---------------------------------------------------------------- state / modals
def parse_title(title: str) -> dict:
    m = TITLE_RE.match(title or "")
    if not m:
        return {"project": None, "unsaved": None, "version": None}
    return {"project": m.group("path"), "unsaved": bool(m.group("dirty")), "version": m.group("ver")}


def info_box_text(box) -> str:
    e = ui.find(box, ctype="Edit", visible=None)
    return ui.get_text(e) if e else ""


_ALLOW_INVALIDATE = False


class modifying:
    """Context manager: inside it, "Os resultados tornam-se inválidos. Continuar?" is answered Sim."""

    def __enter__(self):
        global _ALLOW_INVALIDATE
        _ALLOW_INVALIDATE = True

    def __exit__(self, *exc):
        global _ALLOW_INVALIDATE
        _ALLOW_INVALIDATE = False


def dismiss_modals(timeout: float = 0.0) -> list[str]:
    """Answer known modal prompts safely. Never saves. Raises on license walls.

    - "Guardar alterações em ...?" / "não foi guardado ... Guardar agora?" -> Não
    - ProVersionAdvertisingWindow -> close and raise DialuxUIError
    """
    handled = []
    end = time.monotonic() + timeout
    while True:
        w = M()
        box = ui.find(w, aid="InformationBox", visible=None)
        if box is not None:
            txt = info_box_text(box)
            if "Guardar" in txt or "guardado" in txt:
                ui.invoke(ui.find(box, aid="No"), f"Não (prompt: {txt!r})")
                handled.append(txt)
                time.sleep(0.4)
                continue
            if "inválidos" in txt:
                if not _ALLOW_INVALIDATE:
                    raise DialuxUIError(f"DIALux pede confirmação: {txt!r} (operação de leitura não altera o projeto).")
                ui.invoke(ui.find(box, aid="Yes"), f"Sim (prompt: {txt!r})")
                handled.append(txt)
                time.sleep(0.4)
                continue
            raise DialuxUIError(f"DIALux mostra uma mensagem inesperada: {txt!r}")
        adv = ui.find(w, aid="ProVersionAdvertisingWindow", visible=None)
        if adv is not None:
            t = ui.find(adv, aid="TextBlockAdvertisingTitle", visible=None)
            msg = ui.get_text(t) if t else ""
            ui.invoke(ui.find(adv, aid="ButtonClose", visible=None), "fechar aviso de licença")
            raise DialuxUIError(f"Recurso bloqueado pela licença do DIALux: {msg}")
        if time.monotonic() >= end:
            return handled
        time.sleep(0.3)


def status() -> dict:
    pids = ui._process_ids()
    if not pids:
        return {"running": False}
    try:
        w = M()
    except DialuxUIError:
        return {"running": True, "main_window": False, "pids": pids}
    st = parse_title(w.window_text())
    logged = ui.find(w, aid="LoginModeControlLogin", visible=None) is None
    start_screen = ui.find(w, aid="StartNewProject", visible=None) is not None
    sb = ui.find(w, aid="MainStatusBar", visible=None)
    return {
        "running": True,
        "version": st["version"],
        "exe_version": exe_version(),
        "project": st["project"],
        "unsaved_changes": st["unsaved"],
        "logged_in": logged,
        "start_screen": start_screen,
        "status_bar": [t for t in ui.texts(sb)] if sb else [],
        "modal": info_box_text(b) if (b := ui.find(w, aid="InformationBox", visible=None)) else None,
    }


def exe_version() -> str | None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-Item '{ui.DIALUX_EXE}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=15, creationflags=0x08000000,
        ).stdout.strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- launching
def launch(timeout: float = 180) -> dict:
    if not ui._process_ids():
        log.info("launch %s", ui.DIALUX_EXE)
        subprocess.Popen([ui.DIALUX_EXE], creationflags=0x00000008)  # DETACHED_PROCESS
    ui.wait_until(lambda: _ready(), timeout, "DIALux pronto (tela inicial, projeto ou login)")
    w = M()
    if ui.find(w, aid="LoginModeControlLogin", visible=None) is not None:
        raise DialuxUIError("DIALux abriu na tela de login do DIALux ID. Faça login manualmente "
                            "(marque 'Lembrar senha') e chame a ferramenta de novo.")
    return status()


def _ready():
    w = M()
    return any(ui.find(w, aid=a, visible=None) is not None
               for a in ("StartNewProject", "LoginModeControlLogin", "ModeSelectionTabControl"))


# ---------------------------------------------------------------- menus & navigation
def _find_menu_item(aid: str):
    e = ui.find(M(), aid=aid, ctype="MenuItem", visible=None)  # menu popups live under the main window
    if e is not None:
        return e
    for win in ui.windows_of_dialux():
        e = ui.find(win, aid=aid, ctype="MenuItem", visible=None)
        if e is not None:
            return e
    return None


def menu(*path: str) -> None:
    """Open a menu path by AutomationIds, e.g. menu('File','Import','ImportStf')."""
    dismiss_modals()
    for aid in path[:-1]:
        item = ui.wait_until(lambda a=aid: _find_menu_item(a), 10, f"menu {aid}")
        item.iface_expand_collapse.Expand()
        time.sleep(0.3)
    last = ui.wait_until(lambda: _find_menu_item(path[-1]), 10, f"menu {path[-1]}")
    if not last.is_enabled():
        raise DialuxUIError(f"Item de menu {path[-1]} está desabilitado neste estado.")
    ui.invoke(last, "menu " + "/".join(path))


TOOLS = {
    # goto menu aid, tool tab aid, control that proves the panel is shown
    "tree": ("MenuGotoShowProjectTreeTool", "ProjectTreeTool", "ProjectTreeToolSearch"),
    "spaces": ("MenuGotoShowSpaceTool", "SpaceTool", "WorkplaneHeightDoubleBox"),
    "luminaires": ("MenuGotoShowLuminaireArrangementTool", "LuminaireArrangementTool", "aid_ArrangementFromSpace"),
    "materials": ("MenuGotoShowMaterialTool", "MaterialTool", "aid_ChangedSpaceSurfaceRho"),
    "output": ("MenuGotoShowOutputTreeTool", "OutputTreeTool", "aid_RenderProjectDocument"),
    "calcobjects": ("MenuGotoShowCalculationObjectTool", "CalculationObjectTool", None),
}


def _tab(aid: str):
    return ui.find(M(), aid=aid, ctype="TabItem", visible=None)


def goto(tool: str, timeout: float = 20, ready: bool = True):
    """Show a tool panel.

    Inside the current mode the tool tab is selected directly: the Goto menu (and other
    tools) drop the current object selection. The Goto menu is used only to switch modes.
    WPF builds a panel's content only on a selection change, so an already-selected tab
    with empty content is re-selected via the project-tree tab (which keeps the selection).
    """
    menu_aid, tab_aid, ready_aid = TOOLS[tool]

    def shown():
        if not ready or not ready_aid:
            t = _tab(tab_aid)
            return t is not None and _is_selected(t)
        return ui.find(M(), aid=ready_aid) is not None

    if _tab(tab_aid) is None:  # tool belongs to another mode
        menu("MenuGotoConstructionMode", menu_aid)
        ui.wait_until(lambda: _tab(tab_aid) is not None, timeout / 2, f"modo da ferramenta {tool}")
    if shown():
        return
    t = _tab(tab_aid)
    if _is_selected(t) and tab_aid != "ProjectTreeTool" and _tab("ProjectTreeTool") is not None:
        _tab("ProjectTreeTool").iface_selection_item.Select()
        time.sleep(0.8)
    _tab(tab_aid).iface_selection_item.Select()
    ui.wait_until(shown, timeout, f"ferramenta {tool}")


def _is_selected(el) -> bool:
    try:
        return bool(el.iface_selection_item.CurrentIsSelected)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- file dialog
def file_dialog_open(path: Path, what: str, timeout: float = 20) -> None:
    dlg = ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window"), timeout, f"diálogo de arquivo ({what})")
    _dialog_filename(dlg, path, ("1148",))
    ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Abrir")
    # dialog must close; an error popup of the shell dialog would keep it open
    ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window") is None, 15, "fechar diálogo de arquivo")


def file_dialog_save(path: Path, what: str, timeout: float = 20) -> None:
    dlg = ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window"), timeout, f"diálogo salvar ({what})")
    _dialog_filename(dlg, path, ("1001", "1148"))
    ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Salvar")
    ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window") is None, 15, "fechar diálogo salvar")


def _dialog_filename(dlg, path: Path, aids: tuple[str, ...]) -> None:
    """Put the file name into a Windows file dialog without keyboard or focus (WM_SETTEXT).

    ValuePattern.SetValue is ignored by some of these dialogs (they keep their default name).
    """
    edit = next((e for a in aids if (e := ui.find(dlg, aid=a, ctype="Edit", visible=None)) is not None), None)
    if edit is None:
        raise DialuxUIError("Campo de nome do diálogo de arquivo não encontrado.")
    ui.set_text_win32(edit, str(path), "nome do arquivo")


def _escape_keys(s: str) -> str:
    """Escape pywinauto send_keys specials."""
    return "".join("{" + c + "}" if c in "+^%~(){}[]" else c for c in s)


# ---------------------------------------------------------------- project tree
def tree_items() -> list[str]:
    goto("tree")
    return [i.element_info.automation_id for i in ui.find_all(M(), ctype="ListItem")
            if i.element_info.automation_id]


def rooms() -> dict[str, str]:
    """room name -> tree AutomationId."""
    out = {}
    for aid in tree_items():
        if ROOMS_NODE in aid:
            name = aid.split(ROOMS_NODE, 1)[1]
            if "_" not in name:  # direct children only
                out[name] = aid
    return out


def select_room(name: str) -> None:
    rs = rooms()
    if name not in rs:
        raise DialuxUIError(f"Ambiente {name!r} não existe no projeto. Ambientes: {sorted(rs)}")
    item = ui.find(M(), aid=rs[name], ctype="ListItem")
    ui.invoke(item, f"selecionar ambiente {name}")
    ui.wait_until(lambda: _is_selected(ui.find(M(), aid=rs[name], ctype="ListItem")), 5,
                  f"ambiente {name} selecionado")


# ---------------------------------------------------------------- edits
def _commit_attempt(aid: str, value: str, commit_to: str | None) -> None:
    w = M()
    e = ui.find(w, aid=aid, visible=None)
    if e is None:
        raise DialuxUIError(f"Campo {aid} não está visível.")
    try:
        e.set_focus()
    except Exception:  # noqa: BLE001
        pass
    e.iface_value.SetValue(value)
    other = ui.find(w, aid=commit_to, visible=None) if commit_to else None
    try:  # WPF commits the binding when the box loses focus
        (other or ui.find(w, aid="ObjectName", visible=None) or w).set_focus()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    dismiss_modals()


def _rerender_tool_panel() -> None:
    """Rebuild the current tool panel (tree tab and back; keeps the selection) to read committed values."""
    tabs = [t for t in ui.find_all(M(), ctype="TabItem") if _is_selected(t)
            and (t.element_info.automation_id or "") not in ("", "ProjectTreeTool")
            and t.element_info.class_name == "TabItem" and (t.element_info.name or "").startswith(
                "Dial.Dialux.InteractionTools")]
    tree = _tab("ProjectTreeTool")
    if not tabs or tree is None:
        return
    cur = tabs[0].element_info.automation_id
    tree.iface_selection_item.Select()
    time.sleep(0.6)
    _tab(cur).iface_selection_item.Select()
    time.sleep(0.8)


def _matches(got: str, value: str) -> bool:
    try:
        return same_number(got, float(value.replace(",", ".")))
    except ValueError:
        return got.strip() == value.strip()


def set_field(aid: str, value: str, what: str, commit_to: str | None = None, verify: bool = True) -> str:
    """Set a WPF TextBox, commit it by moving focus and (verify=True) read it back from a rebuilt panel.

    A value that only shows in the box but was not committed (e.g. focus could not move) is detected
    here; one retry is made with DIALux brought to the front, then a clear error is raised.
    """
    for attempt in (1, 2):
        _commit_attempt(aid, value, commit_to)
        if not verify:
            got = ui.get_text(ui.find(M(), aid=aid, visible=None))
            log.info("set_field %s=%r -> %r (sem releitura)", aid, value, got)
            return got
        _rerender_tool_panel()
        el = ui.wait_until(lambda: ui.find(M(), aid=aid, visible=None), 10, f"campo {what} após redesenhar")
        got = ui.get_text(el)
        log.info("set_field %s=%r -> %r (tentativa %d, relido)", aid, value, got, attempt)
        if _matches(got, value):
            return got
        if ui.session_locked():
            raise DialuxUIError(f"{what}: valor não gravado porque a sessão do Windows está bloqueada.")
        try:  # second try with DIALux in front (focus changes are more reliable there)
            M().set_focus()
        except Exception:  # noqa: BLE001
            pass
    raise DialuxUIError(f"{what}: escrevi {value!r} mas o DIALux manteve {got!r} (valor não confirmado).")


def same_number(a: str, b: float, tol: float = 1e-3) -> bool:
    try:
        return abs(float(str(a).replace(",", ".")) - float(b)) <= tol
    except ValueError:
        return False


# ================================================================ operations
def _wait_project_loaded(expect_in_title: str | None, timeout: float = 120) -> dict:
    def ok():
        dismiss_modals()
        w = M()
        if expect_in_title and expect_in_title.lower() not in w.window_text().lower():
            return False
        return ui.find(w, aid="ModeSelectionTabControl") is not None and \
            ui.find(w, aid="CalculationButtonStart", visible=None) is not None
    ui.wait_until(ok, timeout, f"projeto carregado ({expect_in_title or 'novo'})")
    time.sleep(1.5)
    return status()


def new_project() -> dict:
    w = M()
    if ui.find(w, aid="StartNewProject", visible=None) is not None:
        ui.invoke(ui.find(w, aid="StartNewProject", visible=None), "novo projeto (tela inicial)")
    else:
        menu("File", "New")
    return _wait_project_loaded(None)


def open_project(path: Path) -> dict:
    path = Path(path).resolve()
    if not path.exists() or path.suffix.lower() != ".evo":
        raise DialuxUIError(f"Arquivo .evo não encontrado: {path}")
    menu("File", "OpenProject")
    dismiss_modals(1.0)
    file_dialog_open(path, "abrir .evo")
    return _wait_project_loaded(path.stem)


def save_as(path: Path) -> dict:
    """Save the project under a NEW name (never overwrites)."""
    path = Path(path).resolve()
    if path.suffix.lower() != ".evo":
        raise DialuxUIError("O arquivo deve ter extensão .evo")
    if path.exists():
        raise DialuxUIError(f"{path} já existe; escolha outro nome (o servidor nunca sobrescreve .evo).")
    path.parent.mkdir(parents=True, exist_ok=True)
    menu("File", "SaveAs")
    file_dialog_save(path, "salvar .evo")
    ui.wait_until(lambda: path.exists(), 120, f"arquivo {path.name} gravado")
    ui.wait_until(lambda: (st := parse_title(M().window_text()))["project"] and
                  Path(st["project"]).resolve() == path and not st["unsaved"], 60, "título com o novo arquivo")
    return status()


def import_stf(path: Path, heights: dict[str, float] | None = None,
               reflectances: dict[str, tuple[float, float, float]] | None = None) -> dict:
    """Import STF as a new project, then fix per-room heights (evo applies one height to all)
    and reflectances (evo 14 ignores the STF reflectance keys)."""
    with modifying():
        res = _import_stf(path, heights)
        for name, (c, w, f) in (reflectances or {}).items():
            res.setdefault("reflectances", []).append(set_reflectances(name, c, w, f))
        return res


def _import_stf(path: Path, heights: dict[str, float] | None = None) -> dict:
    path = Path(path).resolve()
    if not path.exists():
        raise DialuxUIError(f"STF não encontrado: {path}")
    menu("File", "Import", "ImportStf")
    dismiss_modals(1.0)
    file_dialog_open(path, "STF")
    _wait_project_loaded(path.stem)
    rs = rooms()
    result = {"project": status()["project"], "rooms": []}
    for name in rs:
        info = room_properties(name)
        want = (heights or {}).get(name)
        if want is not None and not same_number(info["height"], want):
            got = set_field("Height", f"{want:.3f}", f"pé-direito {name}", commit_to="ObjectName")
            if not same_number(got, want):
                raise DialuxUIError(f"{name}: pé-direito ficou {got} em vez de {want}.")
            info = room_properties(name)
        result["rooms"].append(info)
    return result


def set_reflectances(name: str, ceiling: float, walls: float, floor: float) -> dict:
    """Room surface reflectances (fractions 0..1) via Materiais > 'Alterar graus de reflexão...'.

    The panel acts on the active room context; it does not read back the room's state, so
    the final check is the PDF report (report_read -> reflectances_pct).
    """
    vals = {"CeilingRho_Value": ceiling, "WallRho_Value": walls, "FloorRho_Value": floor}
    for k, v in vals.items():
        if not 0 <= v <= 1:
            raise DialuxUIError(f"refletância {k}={v} fora de 0..1")
    with modifying():
        set_room_context(name)
        goto("materials")
        ui.invoke(ui.find(M(), aid="aid_ChangedSpaceSurfaceRho"), "alterar graus de reflexão do ambiente")
        ui.wait_until(lambda: ui.find(M(), aid="CeilingRho_Value"), 10, "painel de refletâncias")
        order = list(vals)
        for i, (aid, v) in enumerate(vals.items()):
            got = set_field(aid, f"{v * 100:.1f}", aid, commit_to=order[(i + 1) % len(order)], verify=False)
            if not same_number(got, v * 100, 0.05):
                raise DialuxUIError(f"{name}: {aid} ficou {got} em vez de {v * 100:.1f}.")
        ui.invoke(ui.wait_until(lambda: (b := ui.find(M(), aid="ApplyRhoButton")) and b.is_enabled() and b,
                                5, "botão Aplicar habilitado"), f"aplicar refletâncias {name}")
        time.sleep(1.0)
        dismiss_modals(1.0)
    out = {"room": name, "walls_pct": walls * 100, "verify": "conferir em report_read (reflectances_pct)",
           "warnings": []}
    # Verified in evo 14 (report): this command changes only the room's walls. Ceiling and floor of
    # STF rooms are storey slabs; their reflectance is only editable by painting in the 3D view.
    if abs(ceiling - DEFAULT_CEILING) > 1e-6 or abs(floor - DEFAULT_FLOOR) > 1e-6:
        out["warnings"].append(
            f"Teto/piso pedidos {ceiling * 100:.0f}/{floor * 100:.0f} % NÃO foram aplicados: no DIALux evo 14 só "
            f"se alteram pintando superfícies na vista 3D (não automatizável). Ficam no padrão "
            f"{DEFAULT_CEILING * 100:.0f}/{DEFAULT_FLOOR * 100:.0f} %.")
    out["warnings"].append("Paredes compartilhadas entre ambientes ficam com o último valor aplicado.")
    return out


DEFAULT_CEILING, DEFAULT_FLOOR = 0.70, 0.20


def room_properties(name: str) -> dict:
    select_room(name)
    goto("spaces")
    w = M()
    get = lambda a: ui.get_text(e) if (e := ui.find(w, aid=a, visible=None)) else None  # noqa: E731
    if get("ObjectName") != name:
        raise DialuxUIError(f"Painel de espaço mostra {get('ObjectName')!r}, esperado {name!r}.")
    return {"name": name, "height": get("Height"), "working_plane": get("WorkplaneHeightDoubleBox"),
            "workplane_margin": get("WorkplaneMarginDoubleBox"), "maintenance_factor": get("MaintenanceFactor")}


def set_maintenance_factor(mf: float, room_names: list[str] | None = None) -> list[dict]:
    if not 0.01 < mf <= 1:
        raise DialuxUIError("Fator de manutenção deve estar em (0.01, 1].")
    out = []
    with modifying():
        for name in room_names or list(rooms()):
            room_properties(name)
            got = set_field("MaintenanceFactor", f"{mf:.2f}", f"FM {name}", commit_to="ObjectName")
            dismiss_modals(1.0)
            if not same_number(got, mf, 0.005):
                raise DialuxUIError(f"{name}: FM ficou {got} em vez de {mf}.")
            out.append(room_properties(name))
    return out


def ldt_identity(path: Path) -> dict:
    """Name / number from an EULUMDAT (lines 9-10) or IES ([LUMINAIRE]/[LUMCAT])."""
    raw = Path(path).read_bytes().decode("latin-1", errors="replace").splitlines()
    if Path(path).suffix.lower() == ".ldt":
        return {"manufacturer": raw[0].strip(), "name": raw[8].strip(), "number": raw[9].strip()}
    kw = {}
    for line in raw:
        m = re.match(r"\[(\w+)\]\s*(.*)", line.strip())
        if m:
            kw[m.group(1).upper()] = m.group(2).strip()
    return {"manufacturer": kw.get("MANUFAC", ""), "name": kw.get("LUMINAIRE", ""), "number": kw.get("LUMCAT", "")}


def catalog_items() -> list[str]:
    menu("MenuGotoConstructionMode", "MenuGotoShowLuminaireCatalogPopup")
    # the popup is a child of the main window or a separate top-level window, depending on the project
    pop = ui.wait_until(lambda: ui.find_any(aid="LuminairePopupControl", visible=None), 20, "catálogo de luminárias")
    # ProjectLuminaireFilterToggleButton: state 1 lists recent/imported luminaires, 0 only placed ones
    flt = ui.find(pop, aid="ProjectLuminaireFilterToggleButton", visible=None)
    if flt is not None and flt.iface_toggle.CurrentToggleState != 1:
        flt.iface_toggle.Toggle()
    time.sleep(1.0)
    return [i.element_info.automation_id[: -len("_LuminaireCatalogItem")] for i in ui.find_all(pop, ctype="ListItem")
            if (i.element_info.automation_id or "").endswith("_LuminaireCatalogItem")]


def activate_luminaire(name: str) -> str:
    """Pick a luminaire from the catalog popup by (prefix of) its catalog name; returns full name."""
    items = catalog_items()
    match = [i for i in items if i == name] or [i for i in items if i.startswith(name)]
    if not match:
        raise DialuxUIError(f"Luminária {name!r} não está no catálogo. Disponíveis: {items}")
    if len(set(match)) > 1:
        raise DialuxUIError(f"Nome {name!r} ambíguo no catálogo: {sorted(set(match))}. Use o nome completo.")
    if len(match) > 1:
        log.warning("catálogo tem %d itens chamados %r; usando o primeiro (mais recente)", len(match), match[0])
    # first match = most recent (the list is ordered by last use)
    el = next(i for i in ui.find_all_any(ctype="ListItem")
              if i.element_info.automation_id == match[0] + "_LuminaireCatalogItem")
    ui.invoke(el, f"luminária {match[0]}")
    ui.wait_until(lambda: _is_selected(el), 5, f"luminária {match[0]} selecionada no catálogo")
    try:  # the popup stays open until the main window gets focus; harmless either way
        ui.find(M(), aid="ModeSelectionTabControl").set_focus()
    except Exception:  # noqa: BLE001
        pass
    return match[0]


def import_luminaire(path: Path) -> dict:
    path = Path(path).resolve()
    if path.suffix.lower() not in (".ldt", ".ies") or not path.exists():
        raise DialuxUIError(f"Arquivo LDT/IES não encontrado: {path}")
    ident = ldt_identity(path)
    with modifying():
        return _import_luminaire(path, ident)


def _import_luminaire(path: Path, ident: dict) -> dict:
    menu("File", "Import", "ImportLuminaire")
    dismiss_modals(1.0)
    file_dialog_open(path, "luminária")
    time.sleep(1.5)
    dismiss_modals(1.0)
    items = catalog_items()
    hits = [i for i in items if ident["name"] and i.startswith(ident["name"])]
    if not hits:
        raise DialuxUIError(f"Luminária {ident['name']!r} não apareceu no catálogo após importar. Catálogo: {items}")
    full = activate_luminaire(hits[0])
    return {"catalog_name": full, **ident}


def _arr_get(aid: str) -> str:
    e = ui.find(M(), aid=aid, visible=None)
    return ui.get_text(e) if e else ""


def place_luminaires(room: str, luminaire: str, mounting_height: float | None = None,
                     target_lux: float | None = None, count_x: int | None = None,
                     count_y: int | None = None) -> dict:
    if (target_lux is None) == (count_x is None or count_y is None):
        raise DialuxUIError("Informe target_lux OU count_x e count_y.")
    with modifying():
        return _place(room, luminaire, mounting_height, target_lux, count_x, count_y)


def set_room_context(name: str) -> None:
    """Make `name` the active room context (used by 'Distribuição automática' and room reflectances)."""
    dismiss_modals()
    btn = ui.find(M(), aid="ToggleButton_RoomContextSelectionButton", visible=None)
    if btn is None:  # e.g. in Documentation mode: go back to a mode with the CAD view
        goto("luminaires", ready=False)
        btn = ui.wait_until(lambda: ui.find(M(), aid="ToggleButton_RoomContextSelectionButton", visible=None),
                            15, "seletor de contexto de ambiente")
    mi = ui.find(btn, aid="_menuItemControl", visible=None)
    mi.iface_expand_collapse.Expand()

    def item():
        for x in ui.find_all(M(), ctype="MenuItem"):
            if (x.element_info.automation_id or "").startswith("MenuItem_ToggleButton_RoomContextSelectionButton_") \
                    and any(t.element_info.name == name for t in ui.walk(x)):
                return x
        return None

    it = ui.wait_until(item, 5, f"ambiente {name} no seletor de contexto")
    ui.invoke(it, f"contexto {name}")
    time.sleep(1.0)
    dismiss_modals()


def _place(room, luminaire, mounting_height, target_lux, count_x, count_y) -> dict:
    goto("luminaires", ready=False)  # switch to Light mode first (drops selection)
    room_h = float(room_properties(room)["height"])
    full = activate_luminaire(luminaire)
    set_room_context(room)
    goto("luminaires")
    active = list(ui.texts(ui.find(M(), aid="ToolPartLuminaireType", visible=None)))
    if not any(full.startswith(t) or t.startswith(full.split(" (")[0]) for t in active if t):
        raise DialuxUIError(f"Luminária ativa não é {full!r}: {active[:3]}")
    ui.invoke(ui.find(M(), aid="aid_ArrangementFromSpace"), f"distribuição automática em {room}")
    dismiss_modals(1.5)
    ui.wait_until(lambda: ui.find(M(), aid="TargetIlluminance", visible=None), 15, "painel do arranjo")
    # a new field arrangement takes the context room's ceiling as mounting height
    default_h = _arr_get("MountingHeight_Value")
    if not same_number(default_h, room_h, 0.002):
        raise DialuxUIError(f"Arranjo parece ter sido criado em outro ambiente: altura padrão {default_h} m, "
                            f"pé-direito de {room} = {room_h} m. Desfaça (Ctrl+Z) e verifique o contexto.")
    if mounting_height is not None:
        got = set_field("MountingHeight_Value", f"{mounting_height:.3f}", "altura de montagem",
                        commit_to="ArrangementObjectName")
        if not same_number(got, mounting_height):
            raise DialuxUIError(f"Altura de montagem ficou {got} em vez de {mounting_height}.")
    if target_lux is not None:
        set_field("TargetIlluminance", f"{target_lux:g}", "iluminância alvo", commit_to="EstimatedIlluminance")
        ui.invoke(ui.find(M(), aid="ResetFieldToPlanningTarget", visible=None), "reaplicar alvo")
        time.sleep(1.5)
        if not same_number(_arr_get("TargetIlluminance"), target_lux, 0.5):
            raise DialuxUIError(f"Alvo ficou {_arr_get('TargetIlluminance')} lx.")
    else:
        for aid, v in (("ElementCountX", count_x), ("ElementCountY", count_y)):
            got = set_field(aid, str(v), aid, commit_to="ArrangementObjectName")
            if not same_number(got, v):
                raise DialuxUIError(f"{aid} ficou {got} em vez de {v}.")
    time.sleep(0.8)
    w = M()
    cnt_txt = ui.find(w, aid="NumberOfCurrentLuminairesObjectsTextBlock", visible=None).element_info.name
    n = int(re.search(r"\d+", cnt_txt).group()) if re.search(r"\d+", cnt_txt) else None
    res = {"room": room, "luminaire": full, "count": n,
           "count_x": _arr_get("ElementCountX"), "count_y": _arr_get("ElementCountY"),
           "estimated_lux": _arr_get("EstimatedIlluminance"),
           "mounting_height": _arr_get("MountingHeight_Value"),
           "flux_lm": _arr_get("TotalLuminaireFlux_1"), "power_w": _arr_get("Load_1")}
    if not n:
        raise DialuxUIError(f"Arranjo sem luminárias: {res}")
    return res


def _messages() -> list[str]:
    ui.invoke(ui.find(M(), aid="ToggleButtonShowUserLogPopup", visible=None), "abrir mensagens")
    lb = ui.wait_until(lambda: ui.find(M(), aid="_listBox", ctype="List", visible=None), 5, "lista de mensagens")
    msgs = [" ".join(t.element_info.name for t in ui.walk(it) if t.element_info.control_type == "Text"
                     and t.element_info.name.strip()) for it in lb.children()]
    _close_messages()
    return [m for m in msgs if m and m != "Não há mensagens" and not m.startswith("mensagens mais antigas")]


def _close_messages() -> None:
    def win():
        return ui.find(M(), aid="_listBox", ctype="List", visible=None)

    for _ in range(3):
        if win() is None:
            return
        c = ui.find(M(), aid="Close", ctype="Button", visible=None)
        if c is not None:
            ui.invoke(c, "fechar mensagens")
        else:
            ui.invoke(ui.find(M(), aid="ToggleButtonShowUserLogPopup", visible=None), "alternar mensagens")
        time.sleep(0.6)
    if win() is not None:
        raise DialuxUIError("Não consegui fechar a janela de mensagens do DIALux.")


def calculate(timeout: float = 1800) -> dict:
    w = M()
    start = ui.find(w, aid="CalculationButtonStart", visible=None)
    if start is None or not start.is_enabled():
        raise DialuxUIError("Botão de cálculo indisponível (há luminárias no projeto?).")
    before = _messages()
    t0 = time.monotonic()
    ui.invoke(start, "calcular")

    def done():
        dismiss_modals()
        w = M()
        if ui.find(w, aid="DiscardResultsButton", visible=None).is_enabled():
            return "ok"
        txt = ui.find(w, aid="TextBlockNumberNewMessages", visible=None).element_info.name
        if not txt.startswith("0 "):
            return "msg"
        return None

    r = ui.wait_until(done, timeout, "fim do cálculo", interval=2)
    new = [m for m in _messages() if m not in before]
    errors = [m for m in new if "erro" in m.lower()]
    if errors or r != "ok":
        if r == "msg" and not errors:
            r = ui.wait_until(lambda: "ok" if ui.find(M(), aid="DiscardResultsButton", visible=None).is_enabled()
                              else None, timeout, "fim do cálculo", interval=2)
        else:
            raise DialuxUIError(f"Cálculo falhou: {errors or new}")
    return {"seconds": round(time.monotonic() - t0, 1), "messages": new}


def export_report(out_path: Path, timeout: float = 600) -> dict:
    out_path = Path(out_path).resolve()
    if out_path.suffix.lower() != ".pdf":
        raise DialuxUIError("Saída deve ser .pdf")
    if out_path.exists():
        raise DialuxUIError(f"{out_path} já existe; escolha outro nome.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    menu("View", "ShowOutputMode")
    btn = ui.wait_until(lambda: ui.find(M(), aid="aid_RenderProjectDocument", visible=None), 30, "modo Documentação")
    ui.invoke(btn, "exibir toda a documentação")

    def pages():
        e = ui.find(M(), aid="buttonPageGoTo", visible=None)
        m = re.search(r"de (\d+)", e.element_info.name) if e else None
        return int(m.group(1)) if m else 0

    last, stable_since = -1, time.monotonic()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        dismiss_modals()
        n = pages()
        if n != last:
            last, stable_since = n, time.monotonic()
        elif n > 2 and time.monotonic() - stable_since > 6:
            break
        time.sleep(1)
    else:
        raise DialuxUIError("Documento não terminou de ser gerado.")
    item = ui.find(ui.find(M(), aid="MenuSaveAs", visible=None), ctype="MenuItem", visible=None)
    item.iface_expand_collapse.Expand()
    time.sleep(0.6)
    pdf_item = ui.wait_until(lambda: _find_menu_item("ExportFormatMenuItem_Pdf"), 10, "opção PDF")
    ui.invoke(pdf_item, "exportar PDF")
    cfg = ui.wait_until(lambda: next((x for x in ui.find_all(M(), ctype="Window")
                                      if ui.find(x, aid="checkBoxOpenAfterExport", visible=None)), None),
                        20, "configuração de exportação PDF")
    cb = ui.find(cfg, aid="checkBoxOpenAfterExport", visible=None)
    if cb.iface_toggle.CurrentToggleState == 1:
        cb.iface_toggle.Toggle()
    ui.invoke(ui.find(cfg, aid="buttonOk", visible=None), "OK exportação")
    file_dialog_save(out_path, "PDF")
    ui.wait_until(lambda: out_path.exists() and out_path.stat().st_size > 1000, timeout, f"PDF {out_path.name}")
    size = -1
    while out_path.stat().st_size != size:  # wait until the writer finishes
        size = out_path.stat().st_size
        time.sleep(1.5)
    return {"pdf": str(out_path), "pages": last, "bytes": size}


# ---------------------------------------------------------------- IFC
def _ifc_space_names(path: Path) -> list[str]:
    """Names of IfcSpace entities, read from the STEP text (no extra dependency)."""
    txt = Path(path).read_bytes().decode("latin-1", errors="replace")
    names = []
    for m in re.finditer(r"=\s*IFCSPACE\s*\((.*?)\);", txt, re.S | re.I):
        # GlobalId, OwnerHistory(#), Name, ... -> quoted strings in order: GlobalId, Name, ...
        # (approximate when Name is $; only used to count spaces and report names)
        quoted = re.findall(r"'((?:[^']|'')*)'", m.group(1))
        names.append(quoted[1] if len(quoted) > 1 else "")
    return names


def import_ifc(path: Path, method: str = "novo", use_dialux_reflectances: bool = True,
               working_plane: float | None = None, simplify_names: bool = True,
               workplane_margin: float | None = None, timeout: float = 600) -> dict:
    """Import an IFC as a new project through the start screen and the 2-page import wizard."""
    path = Path(path).resolve()
    if not path.exists() or path.suffix.lower() != ".ifc":
        raise DialuxUIError(f"Arquivo .ifc não encontrado: {path}")
    if method not in ("novo", "legado"):
        raise DialuxUIError("method deve ser 'novo' ou 'legado'")
    expected = _ifc_space_names(path)
    with modifying():
        # The import asks "Guardar alterações?" when a changed project is open, and answering
        # Não silently aborts it; closing the project first (discarding, like the other tools) avoids that.
        if ui.find(M(), aid="StartImportIfc", visible=None) is None:
            menu("File", "CloseProject")
            dismiss_modals(2.0)
        start = ui.wait_until(lambda: ui.find(M(), aid="StartImportIfc", visible=None), 30, "tela inicial")
        ui.invoke(start, "importar IFC (tela inicial)")
        file_dialog_open(path, "IFC")
        # page 1: IFC content (all checked by default)
        nxt = ui.wait_until(lambda: ui.find(M(), aid="NextPage", visible=None), timeout, "assistente IFC: conteúdo")
        ui.invoke(nxt, "Continuar")
        ui.wait_until(lambda: ui.find(M(), aid="FinishPage", visible=None), 60, "assistente IFC: definições")
        # page 2: settings
        radio = ui.find(M(), aid=f"RadioButton_GeometryImportOption_{'True' if method == 'novo' else 'False'}",
                        visible=None)
        radio.iface_selection_item.Select()
        ui.wait_until(lambda: radio.iface_selection_item.CurrentIsSelected, 5, f"método {method}")
        cb = ui.find(M(), aid="CheckBox_IfcReflectance", visible=None)
        if (cb.iface_toggle.CurrentToggleState == 1) != use_dialux_reflectances:
            cb.iface_toggle.Toggle()
        ui.wait_until(lambda: (cb.iface_toggle.CurrentToggleState == 1) == use_dialux_reflectances, 5,
                      "opção de refletâncias")
        ui.invoke(ui.find(M(), aid="FinishPage", visible=None), "Terminar")
        ui.wait_until(lambda: ui.find(M(), aid="FinishPage", visible=None) is None, timeout, "importação IFC")
        time.sleep(2)
        dismiss_modals(1.0)
        rs = ui.wait_until(lambda: rooms() or None, 60, "ambientes importados")
        if len(rs) != len(expected):
            raise DialuxUIError(f"O IFC tem {len(expected)} IfcSpace ({expected}) mas o DIALux criou "
                                f"{len(rs)} ambientes ({sorted(rs)}).")
        out_rooms = []
        for name in list(rs):
            final = name
            parts = name.split(" - ")
            if simplify_names and len(parts) == 2 and parts[0] == parts[1]:
                room_properties(name)
                got = set_field("ObjectName", parts[0], f"nome {name}", commit_to="ObjectDescription")
                if got != parts[0]:
                    raise DialuxUIError(f"Renomear {name!r}: ficou {got!r}.")
                final = parts[0]
            if working_plane is not None:
                room_properties(final)
                got = set_field("WorkplaneHeightDoubleBox", f"{working_plane:.3f}", f"plano de trabalho {final}",
                                commit_to="ObjectName")
                if not same_number(got, working_plane):
                    raise DialuxUIError(f"{final}: plano de trabalho ficou {got}.")
            if workplane_margin is not None:
                room_properties(final)
                got = set_field("WorkplaneMarginDoubleBox", f"{workplane_margin:.3f}", f"zona marginal {final}",
                                commit_to="ObjectName")
                if not same_number(got, workplane_margin):
                    raise DialuxUIError(f"{final}: zona marginal ficou {got}.")
            out_rooms.append(room_properties(final))
    return {"ifc": str(path), "ifc_spaces": expected, "method": method,
            "use_dialux_reflectances": use_dialux_reflectances, "rooms": out_rooms,
            "project": status()["project"]}
