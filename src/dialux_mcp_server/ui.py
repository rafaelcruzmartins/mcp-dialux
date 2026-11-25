"""Low-level UI Automation helpers for DIALux evo (pywinauto, backend "uia").

Rules: controls are found by AutomationId / name / control type only (never by
screen coordinates); every wait is a polled condition with a timeout.
"""
from __future__ import annotations

import logging
import os
import time
import warnings
from pathlib import Path
from typing import Callable, Iterable

warnings.filterwarnings("ignore", category=SyntaxWarning)  # pywinauto 0.6.9 on py3.12

from pywinauto import Application, Desktop  # noqa: E402
from pywinauto.base_wrapper import BaseWrapper  # noqa: E402

DIALUX_EXE = os.environ.get("DIALUX_EXE", r"C:\Program Files\DIAL GmbH\DIALux\DIALux_x64.exe")
MAIN_AID = "MainWindow"
LOG_DIR = Path(os.environ.get("DIALUX_MCP_LOG_DIR", Path.home() / ".dialux-mcp" / "logs"))

LOG_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("dialux_mcp")
if not log.handlers:
    h = logging.FileHandler(LOG_DIR / "dialux-mcp.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


class DialuxUIError(RuntimeError):
    """The DIALux UI is not in the expected state."""


def wait_until(cond: Callable[[], object], timeout: float, what: str, interval: float = 0.25):
    """Poll ``cond`` until truthy; raise DialuxUIError with ``what`` on timeout."""
    end = time.monotonic() + timeout
    last_exc: Exception | None = None
    while True:
        try:
            v = cond()
            if v:
                return v
        except Exception as e:  # noqa: BLE001 - UIA throws transient COM errors
            last_exc = e
        if time.monotonic() >= end:
            extra = f" (último erro: {last_exc})" if last_exc else ""
            raise DialuxUIError(f"Tempo esgotado ({timeout:.0f}s) esperando: {what}{extra}")
        time.sleep(interval)


def _process_ids() -> list[int]:
    import subprocess

    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq DIALux_x64.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, creationflags=0x08000000,
    ).stdout
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower().startswith("dialux_x64"):
            pids.append(int(parts[1]))
    return pids


def main_window(timeout: float = 0) -> BaseWrapper:
    """Return the DIALux main window wrapper or raise."""
    def find():
        for pid in _process_ids():
            for w in Desktop(backend="uia").windows(process=pid):
                if w.element_info.automation_id == MAIN_AID:
                    return w
        return None

    if timeout <= 0:
        w = find()
        if w is None:
            raise DialuxUIError("DIALux evo não está aberto (janela principal não encontrada).")
        return w
    return wait_until(find, timeout, "janela principal do DIALux")


def app() -> Application:
    pids = _process_ids()
    if not pids:
        raise DialuxUIError("DIALux evo não está aberto.")
    return Application(backend="uia").connect(process=pids[0])


def find(parent: BaseWrapper, aid: str | None = None, name: str | None = None,
         ctype: str | None = None, cls: str | None = None, visible: bool | None = True) -> BaseWrapper | None:
    """First descendant matching all given criteria, or None."""
    for el in find_all(parent, aid=aid, name=name, ctype=ctype, cls=cls):
        try:
            if visible is None or el.is_visible() == visible:
                return el
        except Exception:  # noqa: BLE001
            continue
    return None


def find_all(parent: BaseWrapper, aid: str | None = None, name: str | None = None,
             ctype: str | None = None, cls: str | None = None) -> list[BaseWrapper]:
    """All descendants matching the given criteria (exact match)."""
    kw = {"control_type": ctype} if ctype else {}
    try:
        cands = parent.descendants(**kw)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for el in cands:
        try:
            i = el.element_info
            if aid is not None and i.automation_id != aid:
                continue
            if name is not None and (i.name or "") != name:
                continue
            if cls is not None and i.class_name != cls:
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(el)
    return out


def wait_find(parent_fn: Callable[[], BaseWrapper], timeout: float, what: str, **crit) -> BaseWrapper:
    return wait_until(lambda: find(parent_fn(), **crit), timeout, what)


def invoke(el: BaseWrapper, what: str) -> None:
    """Invoke a button/menu item through UIA patterns (no mouse coordinates)."""
    log.info("invoke %s [aid=%s name=%s]", what, el.element_info.automation_id, el.element_info.name)
    if not el.is_enabled():
        raise DialuxUIError(f"Controle '{what}' está desabilitado.")
    iface = el.iface_invoke if _has(el, "iface_invoke") else None
    if iface is not None:
        iface.Invoke()
        return
    if _has(el, "iface_toggle"):
        el.iface_toggle.Toggle()
        return
    if _has(el, "iface_selection_item"):
        el.iface_selection_item.Select()
        return
    if _has(el, "iface_expand_collapse"):
        el.iface_expand_collapse.Expand()
        return
    raise DialuxUIError(f"Controle '{what}' não expõe padrão UIA de acionamento (Invoke/Toggle/Select).")


def _has(el: BaseWrapper, iface: str) -> bool:
    try:
        return getattr(el, iface) is not None
    except Exception:  # noqa: BLE001
        return False


def set_text(el: BaseWrapper, text: str, what: str) -> None:
    log.info("set_text %s = %r", what, text)
    if _has(el, "iface_value"):
        el.iface_value.SetValue(text)
    else:
        raise DialuxUIError(f"Campo '{what}' não aceita ValuePattern.")
    got = get_text(el)
    if got.strip() != text.strip():
        raise DialuxUIError(f"Campo '{what}': escrevi {text!r} mas li {got!r}.")


def get_text(el: BaseWrapper) -> str:
    if _has(el, "iface_value"):
        try:
            return el.iface_value.CurrentValue or ""
        except Exception:  # noqa: BLE001
            pass
    return el.window_text() or ""


def windows_of_dialux() -> list[BaseWrapper]:
    out = []
    for pid in _process_ids():
        out.extend(Desktop(backend="uia").windows(process=pid))
    return out


def dump(el: BaseWrapper, max_depth: int = 12) -> list[str]:
    lines: list[str] = []

    def walk(e, d):
        i = e.element_info
        lines.append(f"{'  ' * d}[{i.control_type}] name={(i.name or '')[:80]!r} aid={i.automation_id!r} "
                     f"cls={i.class_name!r} enabled={i.enabled}")
        if d < max_depth:
            try:
                for c in e.children():
                    walk(c, d + 1)
            except Exception:  # noqa: BLE001
                pass

    walk(el, 0)
    return lines


def texts(el: BaseWrapper) -> Iterable[str]:
    for t in find_all(el, ctype="Text"):
        n = t.element_info.name
        if n:
            yield n
