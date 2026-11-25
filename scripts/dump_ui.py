"""Dump the UI Automation tree of the running DIALux evo window.

Usage: uv run python scripts/dump_ui.py <label> [max_depth]
Writes docs/ui-dumps/<label>.txt
"""
import sys
from pathlib import Path

from pywinauto import Desktop

label = sys.argv[1] if len(sys.argv) > 1 else "dump"
max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 12

out = Path(__file__).resolve().parent.parent / "docs" / "ui-dumps" / f"{label}.txt"
out.parent.mkdir(parents=True, exist_ok=True)

desk = Desktop(backend="uia")
wins = [w for w in desk.windows() if "DIALux" in (w.window_text() or "")]
lines = []


def walk(el, depth):
    try:
        info = el.element_info
        name = (info.name or "").replace("\n", " ")[:80]
        lines.append(
            f"{'  ' * depth}[{info.control_type}] name={name!r} "
            f"aid={info.automation_id!r} cls={info.class_name!r} "
            f"enabled={info.enabled} rect={info.rectangle}"
        )
    except Exception as e:  # noqa: BLE001
        lines.append(f"{'  ' * depth}<error {e}>")
        return
    if depth >= max_depth:
        return
    try:
        for ch in el.children():
            walk(ch, depth + 1)
    except Exception as e:  # noqa: BLE001
        lines.append(f"{'  ' * depth}  <children error {e}>")


for w in wins:
    lines.append(f"=== WINDOW {w.window_text()!r} pid={w.process_id()} ===")
    walk(w, 0)

out.write_text("\n".join(lines), encoding="utf-8")
print(f"{len(wins)} window(s), {len(lines)} lines -> {out}")
