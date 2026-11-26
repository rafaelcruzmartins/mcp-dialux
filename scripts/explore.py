"""Exploration helper: invoke controls by AutomationId/name and dump all DIALux windows.

uv run python scripts/explore.py dump <label> [depth]
uv run python scripts/explore.py invoke <aid> [name] [--then-dump label]
uv run python scripts/explore.py open-menu <menu aid>  (expands, dumps the popup)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dialux_mcp_server import ui  # noqa: E402

DUMPS = Path(__file__).resolve().parent.parent / "docs" / "ui-dumps"
DUMPS.mkdir(parents=True, exist_ok=True)


def dump_all(label, depth=14):
    from pywinauto import Desktop
    lines = []
    pids = ui._process_ids()
    for w in Desktop(backend="uia").windows():
        try:
            if w.process_id() in pids:
                lines.append(f"=== WINDOW {w.window_text()!r} aid={w.element_info.automation_id!r} cls={w.element_info.class_name!r}")
                lines += ui.dump(w, depth)
        except Exception as e:  # noqa: BLE001
            lines.append(f"<err {e}>")
    from sanitize_dumps import sanitize_text
    p = DUMPS / f"{label}.txt"
    p.write_text(sanitize_text("\n".join(lines)), encoding="utf-8")
    print(f"{len(lines)} lines -> {p}")


cmd = sys.argv[1]
if cmd == "dump":
    dump_all(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 14)
elif cmd == "invoke":
    aid = sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None
    w = ui.main_window()
    crit = {}
    if aid != "-":
        crit["aid"] = aid
    if name:
        crit["name"] = name
    el = ui.find(w, **crit)
    if el is None:
        sys.exit(f"not found: {crit}")
    ui.invoke(el, f"{aid}/{name}")
    print("invoked", crit)
    if "--then-dump" in sys.argv:
        time.sleep(2)
        dump_all(sys.argv[sys.argv.index("--then-dump") + 1])
elif cmd == "open-menu":
    w = ui.main_window()
    el = ui.find(w, aid=sys.argv[2], ctype="MenuItem")
    el.iface_expand_collapse.Expand()
    time.sleep(1)
    dump_all(sys.argv[3] if len(sys.argv) > 3 else f"menu-{sys.argv[2]}", 8)
