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
    "spaces": ("MenuGotoShowSpaceTool", "SpaceTool", None),
    "luminaires": ("MenuGotoShowLuminaireArrangementTool", "LuminaireArrangementTool", "aid_ArrangementFromSpace"),
    "materials": ("MenuGotoShowMaterialTool", "MaterialTool", "aid_ChangedSpaceSurfaceRho"),
    "output": ("MenuGotoShowOutputTreeTool", "OutputTreeTool", None),
    "calcobjects": ("MenuGotoShowCalculationObjectTool", "CalculationObjectTool", None),
}


def goto(tool: str, timeout: float = 20):
    menu_aid, tab_aid, ready_aid = TOOLS[tool]
    menu("MenuGotoConstructionMode", menu_aid)

    def shown():
        w = M()
        if ready_aid:
            return ui.find(w, aid=ready_aid) is not None
        tab = ui.find(w, aid=tab_aid, ctype="TabItem", visible=None)
        return tab is not None and _is_selected(tab)

    try:
        ui.wait_until(shown, timeout / 3, f"ferramenta {tool}")
        return
    except DialuxUIError:
        pass
    # WPF realizes a tool panel's content only on a selection change: select a
    # sibling tool tab, then the wanted one again.
    tab = ui.find(M(), aid=tab_aid, ctype="TabItem", visible=None)
    if tab is None:
        raise DialuxUIError(f"Aba da ferramenta {tab_aid} não encontrada.")
    sibling = next((t for t in tab.parent().children()
                    if t.element_info.control_type == "TabItem" and t.is_enabled()
                    and t.element_info.automation_id not in (tab_aid, "Separator")), None)
    if sibling is not None:
        sibling.iface_selection_item.Select()
        time.sleep(0.8)
    ui.find(M(), aid=tab_aid, ctype="TabItem", visible=None).iface_selection_item.Select()
    ui.wait_until(shown, timeout * 2 / 3, f"ferramenta {tool}")


def _is_selected(el) -> bool:
    try:
        return bool(el.iface_selection_item.CurrentIsSelected)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- file dialog
def file_dialog_open(path: Path, what: str, timeout: float = 20) -> None:
    dlg = ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window"), timeout, f"diálogo de arquivo ({what})")
    ui.set_text(ui.find(dlg, aid="1148", ctype="Edit"), str(path), "nome do arquivo")
    ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Abrir")
    # dialog must close; an error popup of the shell dialog would keep it open
    ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window") is None, 15, "fechar diálogo de arquivo")


def file_dialog_save(path: Path, what: str, timeout: float = 20) -> None:
    dlg = ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window"), timeout, f"diálogo salvar ({what})")
    edit = ui.find(dlg, aid="1001", ctype="Edit") or ui.find(dlg, aid="1148", ctype="Edit")
    if edit is None:
        raise DialuxUIError("Campo de nome do diálogo Salvar não encontrado.")
    ui.set_text(edit, str(path), "nome do arquivo")
    ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Salvar")
    ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window") is None, 15, "fechar diálogo salvar")


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
def set_field(aid: str, value: str, what: str, commit_to: str | None = None) -> str:
    """Set a WPF TextBox and commit it by moving focus; returns the read-back text."""
    w = M()
    e = ui.find(w, aid=aid, visible=None)
    if e is None:
        raise DialuxUIError(f"Campo {what} ({aid}) não está visível.")
    try:
        e.set_focus()
    except Exception:  # noqa: BLE001
        pass
    e.iface_value.SetValue(value)
    other = ui.find(w, aid=commit_to, visible=None) if commit_to else None
    try:
        (other or ui.find(w, aid="ObjectName", visible=None) or w).set_focus()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    got = ui.get_text(ui.find(M(), aid=aid, visible=None))
    log.info("set_field %s=%r -> %r", aid, value, got)
    return got


def same_number(a: str, b: float, tol: float = 1e-3) -> bool:
    try:
        return abs(float(str(a).replace(",", ".")) - float(b)) <= tol
    except ValueError:
        return False
