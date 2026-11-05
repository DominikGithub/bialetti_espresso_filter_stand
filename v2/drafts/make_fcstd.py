"""Wrap every draft STL in this folder into a FreeCAD document together with
a dummy of the funnel in its resting position (run with FreeCAD's Python):

    ~/Applications/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd make_fcstd.py
"""
import glob
import json
import os

import FreeCAD as App
import Mesh
import Part

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
V = App.Vector


def funnel_shape(zt, f):
    zb = zt - f["basket_h"]
    rs, rb = f["stem_d"] / 2, f["basket_d_bottom"] / 2
    pts = [(0, zb - f["stem_len"]), (rs, zb - f["stem_len"]), (rs, zb - 1.0),
           (rb - 1.5, zb), (rb, zb + 1.5), (f["basket_d"] / 2, zt), (f["flange_d"] / 2, zt),
           (f["flange_d"] / 2, zt + f["flange_t"]), (0, zt + f["flange_t"])]
    poly = Part.makePolygon([V(x, 0, z) for x, z in pts] + [V(pts[0][0], 0, pts[0][1])])
    return Part.Face(poly).revolve(V(0, 0, 0), V(0, 0, 1), 360)


for stl in sorted(glob.glob(os.path.join(HERE, "*.stl"))):
    name = os.path.splitext(os.path.basename(stl))[0]
    meta_path = os.path.join(HERE, name + ".json")
    if not os.path.exists(meta_path):
        continue
    meta = json.load(open(meta_path))
    doc = App.newDocument(name)
    holder = doc.addObject("Mesh::Feature", "Holder")
    holder.Mesh = Mesh.Mesh(stl)
    funnel = doc.addObject("Part::Feature", "FunnelDummy")
    funnel.Shape = funnel_shape(meta["z_top"], meta["funnel"])
    doc.recompute()
    path = os.path.join(HERE, name + ".FCStd")
    if os.path.exists(path):
        os.remove(path)
    doc.saveAs(path)
    print(f"{path}: mesh {holder.Mesh.CountFacets} facets, solid {holder.Mesh.isSolid()}, "
          f"non-manifold {holder.Mesh.hasNonManifolds()}")
    App.closeDocument(doc.Name)
