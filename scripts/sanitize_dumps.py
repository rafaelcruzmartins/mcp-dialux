"""Remove personal data from UI dumps: user paths and file-dialog folder listings.

uv run python scripts/sanitize_dumps.py [dir]   (default: docs/ui-dumps)
"""
import os
import re
import sys
from pathlib import Path

HOME = os.path.expanduser("~")
REPO = str(Path(__file__).resolve().parent.parent)


def sanitize_text(text: str) -> str:
    out = []
    dialog_indent = None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if dialog_indent is not None and indent <= dialog_indent and line.strip():
            dialog_indent = None
        if "cls='#32770'" in line:
            dialog_indent = indent
        elif dialog_indent is not None and re.search(r"\[(ListItem|TreeItem|DataItem)\]", line):
            continue  # folder/file names of the user's disk
        for variant in (REPO, REPO.replace("\\", "\\\\")):
            line = line.replace(variant, "<repo>")
        for variant in (HOME, HOME.replace("\\", "\\\\")):
            line = line.replace(variant, "%USERPROFILE%")
        line = re.sub(r"Users\\{1,2}[^\\']+", r"Users\\<user>", line)
        out.append(line)
    return "\n".join(out)


def main(d: Path) -> None:
    for p in sorted(d.glob("*.txt")):
        t = p.read_text(encoding="utf-8")
        s = sanitize_text(t)
        if s != t:
            p.write_text(s, encoding="utf-8")
            print("sanitized", p.name)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(REPO) / "docs" / "ui-dumps")
