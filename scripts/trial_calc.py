"""Experiment: import STF (discarding current changes), pick catalog luminaire, arrange, calculate.
uv run python scripts/trial_calc.py <stf> <catalog item aid prefix> [lux]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dialux_mcp_server import dialux as d, ui  # noqa: E402

stf, lum = Path(sys.argv[1]).resolve(), sys.argv[2]
lux = sys.argv[3] if len(sys.argv) > 3 else "300"

d.menu("File", "Import", "ImportStf")
d.file_dialog_open(stf, "STF") if False else None
dlg = ui.wait_until(lambda: ui.find(d.M(), cls="#32770", ctype="Window"), 15, "dialogo STF")
ui.set_text(ui.find(dlg, aid="1148", ctype="Edit"), str(stf), "nome")
ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Abrir")
ui.wait_until(lambda: (d.dismiss_modals() or True) and stf.stem in d.M().window_text()
              and ui.find(d.M(), aid="ModeSelectionTabControl") is not None, 90, "projeto importado")
time.sleep(3)
rooms = d.rooms()
print("ambientes:", list(rooms))
d.menu("MenuGotoConstructionMode", "MenuGotoShowLuminaireCatalogPopup")
item = ui.wait_until(lambda: next((i for i in ui.find_all(d.M(), ctype="ListItem")
                                    if (i.element_info.automation_id or "").startswith(lum)), None), 10, "item catalogo")
ui.invoke(item, "luminaria")
time.sleep(1)
for name in rooms:
    d.select_room(name)
    d.goto("luminaires")
    print("ativa:", list(ui.texts(ui.find(d.M(), aid="ToolPartLuminaireType", visible=None)))[:2])
    ui.invoke(ui.find(d.M(), aid="aid_ArrangementFromSpace"), "arranjo")
    ui.wait_until(lambda: ui.find(d.M(), aid="TargetIlluminance", visible=None), 15, "painel")
    d.set_field("TargetIlluminance", lux, "alvo", commit_to="EstimatedIlluminance")
    ui.invoke(ui.find(d.M(), aid="ResetFieldToPlanningTarget", visible=None), "reaplicar")
    time.sleep(1.5)
    w = d.M()
    print(name, {a: ui.get_text(ui.find(w, aid=a, visible=None)) for a in
                 ("ElementCountX", "ElementCountY", "EstimatedIlluminance", "MountingHeight_Value")})

msgs0 = ui.find(d.M(), aid="TextBlockNumberNewMessages", visible=None).element_info.name
ui.invoke(ui.find(d.M(), aid="CalculationButtonStart", visible=None), "calcular")
t0 = time.time()
while time.time() - t0 < 300:
    d.dismiss_modals()
    w = d.M()
    disc = ui.find(w, aid="DiscardResultsButton", visible=None).is_enabled()
    m = ui.find(w, aid="TextBlockNumberNewMessages", visible=None).element_info.name
    if disc or m != msgs0:
        break
    time.sleep(2)
print(f"{time.time() - t0:.0f}s discard={disc} msgs={m}")
