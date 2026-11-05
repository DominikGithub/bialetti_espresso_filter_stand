"""Shared pieces for the v2 drafts: funnel dimensions, the precise seat,
geometry helpers, export and a small numpy preview renderer.

Run inside FreeCAD's Python (freecadcmd). All lengths in mm.
"""
import math
import os

import FreeCAD as App
import MeshPart
import Part
import numpy as np

V = App.Vector

# --- The one funnel this stand is made for -------------------------------
# Only FLANGE_D is carried over from v1; the rest are PLACEHOLDERS until measured.
FUNNEL = dict(
    flange_d=60.0,   # outer diameter of the flat top rim (flange)
    flange_t=1.0,    # flange sheet thickness
    basket_d=54.0,   # outer diameter of the basket directly under the flange
    basket_d_bottom=51.0,  # outer diameter at the basket bottom (taper)
    basket_h=22.0,   # flange underside -> basket bottom
    stem_d=11.0,     # outer diameter of the stem tube
    stem_len=40.0,   # basket bottom -> stem tip
)

# --- Fit ------------------------------------------------------------------
FIT = 0.20       # radial clearance between basket wall and seat faces
SEAT_H = 5.0     # height of the precise contact faces on the basket wall
STEM_GAP = 6.0   # air under the stem tip

# PLA / Anycubic i3 Mega limits used by the checks
BED = (210.0, 210.0, 205.0)
MAX_OVERHANG = 45.0  # degrees from vertical


def z_top(floor=0.0):
    """Height of the seat plane (flange underside rests here)."""
    f = FUNNEL
    return floor + STEM_GAP + f["stem_len"] + f["basket_h"]


def seat_r():
    return FUNNEL["basket_d"] / 2 + FIT


def basket_r_at(z, zt):
    """Basket outer radius at height z (linear taper), None outside the basket."""
    f = FUNNEL
    zb = zt - f["basket_h"]
    if z < zb or z > zt:
        return None
    t = (z - zb) / f["basket_h"]
    return f["basket_d_bottom"] / 2 + t * (f["basket_d"] - f["basket_d_bottom"]) / 2


def funnel_shape(zt):
    """Dummy of the funnel, resting with its flange underside on z = zt."""
    f = FUNNEL
    zb = zt - f["basket_h"]
    rs = f["stem_d"] / 2
    pts = [
        (0, zb - f["stem_len"]), (rs, zb - f["stem_len"]), (rs, zb - 1.0),
        (f["basket_d_bottom"] / 2 - 1.5, zb), (f["basket_d_bottom"] / 2, zb + 1.5),
        (f["basket_d"] / 2, zt), (f["flange_d"] / 2, zt),
        (f["flange_d"] / 2, zt + f["flange_t"]), (0, zt + f["flange_t"]),
    ]
    poly = Part.makePolygon([V(x, 0, z) for x, z in pts] + [V(pts[0][0], 0, pts[0][1])])
    return Part.Face(poly).revolve(V(0, 0, 0), V(0, 0, 1), 360)


def seat_finish(shape, zt):
    """Make the contact precise: flat flange rest at zt, cylindrical basket
    contact faces of height SEAT_H, nothing below the bed."""
    big = 400.0
    above = Part.makeBox(big, big, 200, V(-big / 2, -big / 2, zt))
    below = Part.makeBox(big, big, 50, V(-big / 2, -big / 2, -50))
    bore = Part.makeCylinder(seat_r(), 200, V(0, 0, zt - SEAT_H))
    return shape.cut(above.fuse(below).fuse(bore)).removeSplitter()


# --- Geometry helpers -----------------------------------------------------
def closed_spline(points):
    c = Part.BSplineCurve()
    c.interpolate([V(*p) for p in points], PeriodicFlag=True)
    return Part.Wire(c.toShape())


def spline_edge(points):
    c = Part.BSplineCurve()
    c.interpolate([V(*p) for p in points])
    return c


def tube(points, radii, samples=24):
    """Tapered round tube along a smooth spline through `points`.
    radii: one value per sample along the path (or a callable t -> r)."""
    curve = spline_edge(points)
    a, b = curve.FirstParameter, curve.LastParameter
    wires = []
    for i in range(samples + 1):
        t = i / samples
        u = a + t * (b - a)
        p = curve.value(u)
        d = curve.tangent(u)[0]
        r = radii(t) if callable(radii) else radii
        wires.append(Part.Wire(Part.makeCircle(r, p, d)))
    return Part.makeLoft(wires, True, False)


def path_min_angle(points, n=400):
    """Smallest angle from horizontal along a spline path (degrees)."""
    curve = spline_edge(points)
    a, b = curve.FirstParameter, curve.LastParameter
    worst = 90.0
    for i in range(n + 1):
        d = curve.tangent(a + (b - a) * i / n)[0]
        h = math.hypot(d.x, d.y)
        worst = min(worst, math.degrees(math.atan2(abs(d.z), h)))
    return worst


def polar(r, deg, z):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a), z)


# --- Checks & export ------------------------------------------------------
def report(name, shape, zt):
    bb = shape.BoundBox
    clash = shape.common(funnel_shape(zt)).Volume
    print(f"[{name}] size {bb.XLength:.1f} x {bb.YLength:.1f} x {bb.ZLength:.1f} mm, "
          f"volume {shape.Volume / 1000:.1f} cm3 (~{shape.Volume / 1000 * 1.24:.0f} g PLA solid), "
          f"solids {len(shape.Solids)}, valid {shape.isValid()}, funnel clash {clash:.3f} mm3")
    assert bb.XLength < BED[0] and bb.YLength < BED[1] and bb.ZLength < BED[2]


def save(name, shape, zt, out_dir, extra=()):
    """Write <name>.FCStd (holder + funnel dummy) and <name>.stl."""
    doc = App.newDocument(name)
    holder = doc.addObject("Part::Feature", "Holder")
    holder.Shape = shape
    funnel = doc.addObject("Part::Feature", "FunnelDummy")
    funnel.Shape = funnel_shape(zt)
    for label, shp in extra:
        o = doc.addObject("Part::Feature", label)
        o.Shape = shp
        o.Visibility = False
    doc.recompute()
    fcstd = os.path.join(out_dir, f"{name}.FCStd")
    if os.path.exists(fcstd):
        os.remove(fcstd)
    doc.saveAs(fcstd)
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.02,
                                  AngularDeflection=math.radians(4), Relative=False)
    mesh.write(os.path.join(out_dir, f"{name}.stl"))
    print(f"[{name}] mesh facets {mesh.CountFacets}, solid {mesh.isSolid()}, "
          f"non-manifold {mesh.hasNonManifolds()}")
    App.closeDocument(doc.Name)


# --- Preview renderer -----------------------------------------------------
def _tess(shape, tol=0.08):
    pts, tris = shape.tessellate(tol)
    P = np.array([[p.x, p.y, p.z] for p in pts], float)
    T = np.array(tris, int)
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    vn = np.zeros_like(P)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    return P, T, vn


def render(items, elev=22, azim=-55, size=760, margin=0.08, bounds=None):
    """items: [(shape, rgb)], orthographic z-buffer render -> HxWx3 float."""
    e, a = math.radians(elev), math.radians(azim)
    fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    right = np.cross([0, 0, 1], fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    meshes = []
    for shape, rgb in items:
        P, T, N = _tess(shape)
        meshes.append((P @ np.c_[right, up, fwd], T, N, np.array(rgb, float)))
    allp = np.vstack([m[0] for m in meshes]) if bounds is None else bounds
    lo, hi = allp[:, :2].min(0), allp[:, :2].max(0)
    scale = size * (1 - 2 * margin) / max(hi - lo)
    off = (size - (hi - lo) * scale) / 2
    zbuf = np.full((size, size), -np.inf)
    nbuf = np.zeros((size, size, 3))
    cbuf = np.ones((size, size, 3))
    for Q, T, N, rgb in meshes:
        xy = (Q[:, :2] - lo) * scale + off
        xy[:, 1] = size - xy[:, 1]
        for tri in T:
            p = xy[tri]
            x0, y0 = np.floor(p.min(0)).astype(int)
            x1, y1 = np.ceil(p.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, size - 1), min(y1, size - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = p
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12:
                continue
            w0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            w1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not m.any():
                continue
            d = w0 * Q[tri[0], 2] + w1 * Q[tri[1], 2] + w2 * Q[tri[2], 2]
            sub = zbuf[y0:y1 + 1, x0:x1 + 1]
            m &= d > sub
            if not m.any():
                continue
            sub[m] = d[m]
            n = (w0[..., None] * N[tri[0]] + w1[..., None] * N[tri[1]]
                 + w2[..., None] * N[tri[2]])
            nbuf[y0:y1 + 1, x0:x1 + 1][m] = n[m]
            cbuf[y0:y1 + 1, x0:x1 + 1][m] = rgb
    hit = np.isfinite(zbuf)
    n = nbuf / (np.linalg.norm(nbuf, axis=2, keepdims=True) + 1e-12)
    n_cam = np.stack([n @ right, n @ up, n @ fwd], axis=2)
    n_cam[n_cam[..., 2] < 0] *= -1  # light both sides of open sections
    l1 = np.array([-0.45, 0.55, 0.70]); l1 /= np.linalg.norm(l1)
    l2 = np.array([0.6, -0.1, 0.8]); l2 /= np.linalg.norm(l2)
    diff = 0.62 * np.clip(n_cam @ l1, 0, 1) + 0.22 * np.clip(n_cam @ l2, 0, 1)
    h = l1 + np.array([0, 0, 1.0]); h /= np.linalg.norm(h)
    spec = 0.18 * np.clip(n_cam @ h, 0, 1) ** 30
    img = cbuf * (0.30 + diff)[..., None] + spec[..., None]
    # outline from depth discontinuities
    z = np.where(hit, zbuf, zbuf[hit].min() - 20 if hit.any() else 0)
    edge = np.zeros_like(z, bool)
    thr = 1.2 / scale * 6
    edge[1:, :] |= np.abs(np.diff(z, axis=0)) > thr
    edge[:, 1:] |= np.abs(np.diff(z, axis=1)) > thr
    img[edge] *= 0.35
    img[~hit & ~edge] = 1.0
    return np.clip(img, 0, 1)


def preview_sheet(path, title, holder, zt, notes=""):
    """2x2 sheet: holder, with funnel, side view, cutaway."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    clay = (0.86, 0.80, 0.70)
    steel = (0.66, 0.70, 0.76)
    funnel = funnel_shape(zt)
    half = Part.makeBox(300, 300, 300, V(-150, 0, -50))
    both = np.vstack([np.array([[v.x, v.y, v.z] for v in s.Vertexes] +
                               [[s.BoundBox.XMin, s.BoundBox.YMin, s.BoundBox.ZMin],
                                [s.BoundBox.XMax, s.BoundBox.YMax, s.BoundBox.ZMax]])
                      for s in (holder, funnel)])
    views = [
        ("Holder", render([(holder, clay)], 24, -60)),
        ("With funnel (dummy)", render([(holder, clay), (funnel, steel)], 24, -60)),
        ("Side", render([(holder, clay)], 0, -90)),
        ("Cutaway with funnel", render([(holder.cut(half), clay), (funnel.cut(half), steel)], 8, -90)),
    ]
    fig, axs = plt.subplots(2, 2, figsize=(10, 10.6), dpi=110)
    for ax, (t, im) in zip(axs.ravel(), views):
        ax.imshow(im)
        ax.set_title(t, fontsize=10, loc="left", color="#444")
        ax.axis("off")
    fig.suptitle(title, fontsize=15, x=0.03, ha="left", y=0.985)
    if notes:
        fig.text(0.03, 0.945, notes, fontsize=9, color="#555", ha="left", va="top")
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.92, wspace=0.02, hspace=0.06)
    fig.savefig(path)
    plt.close(fig)
    print(f"preview -> {path}")
