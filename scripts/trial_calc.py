"""Experiment: import STF (discarding current changes), pick catalog luminaire, arrange, calculate.
uv run python scripts/trial_calc.py <stf> <catalog item aid prefix> [lux]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dialux_mcp_server import ui  # noqa: E402

stf, lum = sys.argv[1], sys.argv[2]
lux = sys.argv[3] if len(sys.argv) > 3 else "300"
M = ui.main_window


def menu(*path):
    w = M()
    first = ui.find(w, aid=path[0], ctype="MenuItem")
    first.iface_expand_collapse.Expand()
    time.sleep(0.5)
    for aid in path[1:-1]:
        for win in ui.windows_of_dialux():
            e = ui.find(win, aid=aid, ctype="MenuItem", visible=None)
            if e:
                e.iface_expand_collapse.Expand()
                break
        time.sleep(0.6)
    for win in ui.windows_of_dialux():
        e = ui.find(win, aid=path[-1], ctype="MenuItem", visible=None)
        if e:
            ui.invoke(e, path[-1])
            return
    raise SystemExit(f"menu {path} not found")


menu("File", "Import", "ImportStf")
dlg = ui.wait_until(lambda: ui.find(M(), cls="#32770", ctype="Window"), 15, "dialogo STF")
ui.set_text(ui.find(dlg, aid="1148", ctype="Edit"), str(Path(stf).resolve()), "nome")
ui.invoke(ui.find(dlg, aid="1", ctype="Button"), "Abrir")
stem = Path(stf).stem
end = time.time() + 60
while time.time() < end:
    w = M()
    box = ui.find(w, aid="InformationBox", visible=None)
    if box:
        ui.invoke(ui.find(box, aid="No"), "nao salvar")
    if stem in w.window_text():
        break
    time.sleep(0.5)
print("projeto:", M().window_text())
time.sleep(2)

menu("MenuGotoConstructionMode", "MenuGotoShowProjectTreeTool")
time.sleep(1.5)
rooms = [i for i in ui.find_all(M(), ctype="ListItem") if "_Salas e espaços_" in (i.element_info.automation_id or "")]
print("ambientes:", [r.element_info.automation_id.rsplit("_", 1)[-1] for r in rooms])
menu("MenuGotoConstructionMode", "MenuGotoShowLuminaireCatalogPopup")
item = ui.wait_until(lambda: next((i for i in ui.find_all(M(), ctype="ListItem")
                                    if (i.element_info.automation_id or "").startswith(lum)), None), 10, "item catalogo")
ui.invoke(item, "luminaria")
time.sleep(1)
for r in rooms:
    menu("MenuGotoConstructionMode", "MenuGotoShowProjectTreeTool")
    time.sleep(1)
    ui.invoke(ui.find(M(), aid=r.element_info.automation_id, ctype="ListItem"), "ambiente")
    time.sleep(0.8)
    menu("MenuGotoConstructionMode", "MenuGotoShowLuminaireArrangementTool")
    time.sleep(1.5)
    print("ativa:", list(ui.texts(ui.find(M(), aid="ToolPartLuminaireType", visible=None)))[:2])
    ui.invoke(ui.find(M(), aid="aid_ArrangementFromSpace", visible=None), "arranjo")
    t = ui.wait_until(lambda: ui.find(M(), aid="TargetIlluminance", visible=None), 15, "painel")
    t.set_focus()
    t.iface_value.SetValue(lux)
    ui.find(M(), aid="EstimatedIlluminance", visible=None).set_focus()
    time.sleep(0.3)
    ui.invoke(ui.find(M(), aid="ResetFieldToPlanningTarget", visible=None), "reaplicar")
    time.sleep(1.5)
    w = M()
    print(r.element_info.automation_id.rsplit("_", 1)[-1],
          {a: ui.get_text(ui.find(w, aid=a, visible=None)) for a in
           ("ElementCountX", "ElementCountY", "EstimatedIlluminance", "MountingHeight_Value")})

msgs0 = ui.find(M(), aid="TextBlockNumberNewMessages", visible=None).element_info.name
ui.invoke(ui.find(M(), aid="CalculationButtonStart", visible=None), "calcular")
t0 = time.time()
while time.time() - t0 < 300:
    w = M()
    d = ui.find(w, aid="DiscardResultsButton", visible=None).is_enabled()
    m = ui.find(w, aid="TextBlockNumberNewMessages", visible=None).element_info.name
    if d or m != msgs0:
        break
    time.sleep(2)
print(f"{time.time() - t0:.0f}s discard={d} msgs={m}")
