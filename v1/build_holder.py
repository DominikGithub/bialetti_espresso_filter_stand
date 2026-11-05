"""Parametric stand for a Bialetti moka pot funnel (filter basket).

The funnel rests in a 45 degree conical seat, so it centres itself and works
for a range of funnel sizes; the stem hangs into a closed shaft that also
catches stray grounds. The octagonal hourglass body echoes the Moka Express.

Build the FreeCAD model and the STL (headless):

    ~/Applications/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd build_holder.py

Every dimension lives in the "Parameters" spreadsheet of funnel_holder.FCStd,
so it can also be changed in the FreeCAD GUI: edit funnel_d / stem_len,
press Recompute (Ctrl+R), select "FunnelHolder" and File > Export as .stl.
Usually only the two measured values at the top of PARAMS need changing.
"""
import math
import os

import FreeCAD as App
import MeshPart
import Part  # noqa: F401  registers the Part feature types

OUT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
NAME = "funnel_holder"
SHEET = "Parameters"

# (alias, value or =formula, description). Lengths in mm, angles in degrees.
PARAMS = [
    ("funnel_d", "60", "MEASURED: outer diameter of the funnel's top rim"),
    ("stem_len", "50", "MEASURED: stem length below the basket (generous guess)"),
    ("stem_hole_d", "18", "Hole for the stem (Bialetti stems are ~10-12 mm)"),
    ("seat_angle", "45", "Slope of the conical seat, degrees from horizontal"),
    ("floor", "3", "Thickness of the closed bottom"),
    ("bevel", "1", "Chamfer on the bottom and top outer edges"),
    ("groove_depth", "1", "Depth of the decorative groove at the waist"),
    ("groove_h", "2", "Height of the decorative groove"),
    # Derived values below: change only if you want different proportions.
    ("seat_d", "=funnel_d + 12", "Opening of the conical seat"),
    ("height", "=stem_len + 30", "Total height"),
    ("top_af", "=seat_d + 12", "Octagon across flats at the top"),
    ("waist_af", "=top_af - 24", "Octagon across flats at the waist"),
    ("base_af", "=top_af + 8", "Octagon across flats at the foot"),
    ("plinth_h", "6", "Height of the vertical foot band"),
    ("waist_z", "=height * 0.55", "Height of the waist"),
    ("seat_depth", "=(seat_d - stem_hole_d) / 2 * tan(seat_angle)", "Depth of the cone"),
]

# Outer octagon sections (height expr, across-flats expr), bottom to top.
SECTIONS = [
    ("0", "base_af - 2 * bevel"),
    ("bevel", "base_af"),
    ("plinth_h", "base_af"),
    ("waist_z", "waist_af"),
    ("height - bevel", "top_af"),
    ("height", "top_af - 2 * bevel"),
]

# Flats (not corners) face front, like the Moka Express.
OCTAGON_ROT = App.Rotation(App.Vector(0, 0, 1), 22.5)


def p(alias):
    return f"{SHEET}.{alias}"


def circumradius(af_expr):
    """Across-flats expression -> octagon circumradius expression."""
    af = " ".join(p(t) if t.isidentifier() else t for t in af_expr.split())
    return f"({af}) / 2 / cos(22.5)"


def z_expr(expr):
    return " ".join(p(t) if t.isidentifier() else t for t in expr.split())


def build():
    doc = App.newDocument(NAME)

    sheet = doc.addObject("Spreadsheet::Sheet", SHEET)
    sheet.set("A1", "Parameter")
    sheet.set("B1", "Value")
    sheet.set("C1", "Description")
    for row, (alias, value, desc) in enumerate(PARAMS, start=2):
        sheet.set(f"A{row}", alias)
        sheet.set(f"B{row}", value)
        sheet.setAlias(f"B{row}", alias)
        sheet.set(f"C{row}", desc)
    sheet.setColumnWidth("C", 420)
    doc.recompute()

    sections = []
    for i, (z, af) in enumerate(SECTIONS):
        sec = doc.addObject("Part::RegularPolygon", f"Section{i}")
        sec.Polygon = 8
        sec.setExpression("Circumradius", circumradius(af))
        sec.Placement.Rotation = OCTAGON_ROT
        sec.setExpression(".Placement.Base.z", z_expr(z))
        sections.append(sec)

    body = doc.addObject("Part::Loft", "Body")
    body.Sections = sections
    body.Solid = True
    body.Ruled = True

    # The cone overshoots the top by 1 mm so the cut leaves a clean edge.
    seat = doc.addObject("Part::Cone", "Seat")
    seat.setExpression("Radius1", f"{p('stem_hole_d')} / 2")
    seat.setExpression("Radius2", f"{p('seat_d')} / 2 + 1 / tan({p('seat_angle')})")
    seat.setExpression("Height", f"{p('seat_depth')} + 1")
    seat.setExpression(".Placement.Base.z", f"{p('height')} - {p('seat_depth')}")

    shaft = doc.addObject("Part::Cylinder", "StemShaft")
    shaft.setExpression("Radius", f"{p('stem_hole_d')} / 2")
    shaft.setExpression("Height", f"{p('height')} - {p('floor')}")
    shaft.setExpression(".Placement.Base.z", p("floor"))

    groove_outer = doc.addObject("Part::Prism", "GrooveOuter")
    groove_inner = doc.addObject("Part::Prism", "GrooveInner")
    for prism, af in ((groove_outer, "base_af + 10"), (groove_inner, "waist_af - 2 * groove_depth")):
        prism.Polygon = 8
        prism.setExpression("Circumradius", circumradius(af))
        prism.setExpression("Height", p("groove_h"))
        prism.Placement.Rotation = OCTAGON_ROT
        prism.setExpression(".Placement.Base.z", f"{p('waist_z')} - {p('groove_h')} / 2")
    groove = doc.addObject("Part::Cut", "Groove")
    groove.Base = groove_outer
    groove.Tool = groove_inner

    cutters = doc.addObject("Part::MultiFuse", "Cutters")
    cutters.Shapes = [seat, shaft, groove]

    holder = doc.addObject("Part::Cut", "FunnelHolder")
    holder.Base = body
    holder.Tool = cutters
    holder.Refine = True

    doc.recompute()
    for obj in doc.Objects:
        if obj is not holder and obj is not sheet:
            obj.Visibility = False
    broken = [o.Name for o in doc.Objects if "Invalid" in o.State or "Error" in o.State]
    if broken:
        raise RuntimeError(f"Recompute failed for: {broken}")
    return doc, holder


def main():
    doc, holder = build()
    shape = holder.Shape
    assert shape.isValid() and len(shape.Solids) == 1, "holder is not a single valid solid"

    fcstd = os.path.join(OUT_DIR, f"{NAME}.FCStd")
    if os.path.exists(fcstd):
        os.remove(fcstd)  # otherwise FreeCAD leaves a .FCBak copy on every rebuild
    doc.saveAs(fcstd)
    mesh = MeshPart.meshFromShape(
        Shape=shape, LinearDeflection=0.02, AngularDeflection=math.radians(4), Relative=False
    )
    mesh.write(os.path.join(OUT_DIR, f"{NAME}.stl"))

    bb = shape.BoundBox
    print(f"size: {bb.XLength:.1f} x {bb.YLength:.1f} x {bb.ZLength:.1f} mm")
    print(f"volume: {shape.Volume / 1000:.1f} cm3, mesh facets: {mesh.CountFacets}, "
          f"solid: {mesh.isSolid()}, non-manifold: {mesh.hasNonManifolds()}")


main()
