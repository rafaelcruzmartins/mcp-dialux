"""Generate a small IFC4 test model: 2 rooms (IfcSpace) with walls, floor slab and ceilings.

Sala A: 6 x 4 m (axes), ceiling 2.8 m; Sala B: 5 x 4 m, ceiling 3.0 m; walls 0.15 m on the axes.
uv run python scripts/make_test_ifc.py [out.ifc]
"""
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.shape_builder as sb

out = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/ifc/duas-salas.ifc")
SCHEMA = sys.argv[2] if len(sys.argv) > 2 else "IFC2X3"  # Revit default; DIALux evo 14 ignored our IFC4 file
T = 0.15  # wall thickness
WALL_H = 3.2
ROOMS = [("Sala A", (0.0, 0.0, 6.0, 4.0), 2.8), ("Sala B", (6.0, 0.0, 11.0, 4.0), 3.0)]

f = ifcopenshell.api.run("project.create_file", version=SCHEMA)
if SCHEMA == "IFC2X3":  # IfcOwnerHistory is mandatory in IFC2X3
    import ifcopenshell.api.owner.settings as own
    person = f.createIfcPerson(FamilyName="dialux-mcp-server")
    org = f.createIfcOrganization(Name="dialux-mcp-server")
    user = f.createIfcPersonAndOrganization(person, org)
    app = f.createIfcApplication(org, "0.1", "dialux-mcp-server", "dialux-mcp-server")
    own.get_user = lambda ifc: user
    own.get_application = lambda ifc: app
project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Exemplo IFC 2 salas")
ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})  # default would be mm
ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                            target_view="MODEL_VIEW", parent=ctx)
site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
bldg = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[bldg])
ifcopenshell.api.run("aggregate.assign_object", f, relating_object=bldg, products=[storey])
for el in (site, bldg, storey):
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=el)
builder = sb.ShapeBuilder(f)


def prism(points, z0, height):
    profile = builder.polyline([(x, y) for x, y in points], closed=True)
    solid = builder.extrude(builder.profile(profile), height, position=(0.0, 0.0, z0))
    return builder.get_representation(body, [solid])


def add(ifc_class, name, rep, predefined=None, container=storey):
    kw = {"predefined_type": predefined} if predefined else {}
    el = ifcopenshell.api.run("root.create_entity", f, ifc_class=ifc_class, name=name, **kw)
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=el)
    ifcopenshell.api.run("geometry.assign_representation", f, product=el, representation=rep)
    if ifc_class == "IfcSpace":
        ifcopenshell.api.run("aggregate.assign_object", f, relating_object=storey, products=[el])
    else:
        ifcopenshell.api.run("spatial.assign_container", f, relating_structure=container, products=[el])
    return el


h = T / 2
for name, (x0, y0, x1, y1), ch in ROOMS:
    inner = [(x0 + h, y0 + h), (x1 - h, y0 + h), (x1 - h, y1 - h), (x0 + h, y1 - h)]
    sp = add("IfcSpace", name, prism(inner, 0.0, ch), "INTERNAL")
    sp.LongName = name
    if SCHEMA == "IFC2X3":
        sp.InteriorOrExteriorSpace = "INTERNAL"
    add("IfcCovering", f"Forro {name}", prism(inner, ch, 0.02), "CEILING")

# walls on the axes (centre lines), as rectangles of thickness T
axes = [((0, 0), (11, 0)), ((0, 4), (11, 4)), ((0, 0), (0, 4)), ((6, 0), (6, 4)), ((11, 0), (11, 4))]
for i, ((ax, ay), (bx, by)) in enumerate(axes, 1):
    if ay == by:
        pts = [(ax - h, ay - h), (bx + h, ay - h), (bx + h, ay + h), (ax - h, ay + h)]
    else:
        pts = [(ax - h, ay + h), (ax + h, ay + h), (bx + h, by - h), (bx - h, by - h)]
    add("IfcWall", f"Parede {i}", prism(pts, 0.0, WALL_H), "STANDARD")

add("IfcSlab", "Laje piso", prism([(-h, -h), (11 + h, -h), (11 + h, 4 + h), (-h, 4 + h)], -0.2, 0.2), "FLOOR")

out.parent.mkdir(parents=True, exist_ok=True)
f.write(str(out))
print(out.resolve(), "spaces:", [s.Name for s in f.by_type("IfcSpace")])
