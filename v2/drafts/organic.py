"""Shared toolkit for the v2 drafts of the Bialetti funnel stand.

Organic forms are modelled as signed distance fields (tubes, revolved shells,
smooth unions), meshed with marching cubes. Everything that touches the funnel
is then cut with exact solids (manifold3d), so the fit does not depend on the
voxel size.
"""
import math
import os

import manifold3d as mf
import numpy as np
import trimesh
from scipy.ndimage import map_coordinates
from skimage.measure import marching_cubes

# --- The one funnel this stand is made for ----------------------------------
# Only flange_d comes from v1 (measured); the rest are PLACEHOLDERS.
FUNNEL = dict(
    flange_d=60.0,         # outer diameter of the flat top rim (flange)
    flange_t=1.0,          # flange sheet thickness
    basket_d=54.0,         # basket outer diameter right under the flange
    basket_d_bottom=51.0,  # basket outer diameter at its bottom
    basket_h=22.0,         # flange underside -> basket bottom
    stem_d=11.0,           # stem tube outer diameter
    stem_len=40.0,         # basket bottom -> stem tip
)
FIT = 0.20      # radial clearance on the precise contact faces (PLA, i3 Mega)
SEAT_H = 5.0    # height of the contact faces on the basket wall
STEM_GAP = 6.0  # air under the stem tip

BED = (210.0, 210.0, 205.0)   # Anycubic i3 Mega build volume
CIRC = 720                    # segments for exact cylinders (0.0003 mm error)


def z_top(floor=0.0):
    """Seat plane: the flange underside rests here."""
    f = FUNNEL
    return floor + STEM_GAP + f["stem_len"] + f["basket_h"]


def seat_r():
    return FUNNEL["basket_d"] / 2 + FIT


def pocket_r():
    return FUNNEL["flange_d"] / 2 + FIT


# --- Signed distance field on a grid --------------------------------------------
class Field:
    """Regular grid holding a signed distance (negative = inside)."""

    def __init__(self, lo, hi, h):
        self.h = float(h)
        self.lo = np.asarray(lo, float)
        self.n = np.ceil((np.asarray(hi, float) - self.lo) / h).astype(int) + 1
        self.d = np.full(self.n, 1e3, np.float32)

    def block(self, bmin, bmax):
        i0 = np.clip(np.floor((np.asarray(bmin) - self.lo) / self.h).astype(int), 0, self.n - 1)
        i1 = np.clip(np.ceil((np.asarray(bmax) - self.lo) / self.h).astype(int) + 1, 0, self.n)
        sl = tuple(slice(a, b) for a, b in zip(i0, i1))
        ax = [self.lo[k] + self.h * np.arange(i0[k], i1[k]) for k in range(3)]
        return sl, ax

    def coords(self, sl=None):
        sl = sl or tuple(slice(0, n) for n in self.n)
        ax = [self.lo[k] + self.h * np.arange(sl[k].start, sl[k].stop) for k in range(3)]
        return np.meshgrid(*ax, indexing="ij")

    def combine(self, sl, values, k=0.0, op="union"):
        cur = self.d[sl]
        if op == "union":
            self.d[sl] = smin(cur, values, k)
        elif op == "cut":
            self.d[sl] = -smin(-cur, values, k)
        else:
            raise ValueError(op)


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    hh = np.clip(k - np.abs(a - b), 0, None) / k
    return np.minimum(a, b) - hh * hh * k * 0.25


def sample_path(points, n=None, step=0.6):
    """Smooth Catmull-Rom path through control points -> dense (N, 3)."""
    p = np.asarray(points, float)
    p = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        m = max(int(np.linalg.norm(p2 - p1) / step), 2)
        t = np.linspace(0, 1, m, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(p[-2][None])
    return np.vstack(out)


def path_min_angle(path):
    """Flattest direction along a dense path, degrees from horizontal."""
    d = np.diff(np.asarray(path, float), axis=0)
    return float(np.degrees(np.arctan2(np.abs(d[:, 2]), np.hypot(d[:, 0], d[:, 1]))).min())


def polar(r, deg, z):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a), z)


def closed_path(points, step=0.6):
    p = np.asarray(points, float)
    ext = np.vstack([p[-1], p, p[0], p[1]])
    dense = sample_path(ext, step=step)
    # drop the extension segments (first and last control intervals)
    seg0 = np.linalg.norm(ext[1] - ext[0])
    seg1 = np.linalg.norm(ext[-1] - ext[-2])
    n0 = max(int(seg0 / step), 2)
    n1 = max(int(seg1 / step), 2)
    return dense[n0:len(dense) - n1]


def add_tube(field, path, radii, k=0.0, margin=None):
    """Union a tapered round tube along a dense path (N, 3), radii (N,)."""
    path = np.asarray(path, float)
    radii = np.broadcast_to(np.asarray(radii, float), (len(path),))
    margin = (k + 2 * field.h) if margin is None else margin
    rmax = radii.max() + margin
    sl, _ = field.block(path.min(0) - rmax, path.max(0) + rmax)
    local = np.full(tuple(s.stop - s.start for s in sl), 1e3, np.float32)
    origin = np.array([s.start for s in sl])
    for i in range(len(path) - 1):
        a, b, ra, rb = path[i], path[i + 1], radii[i], radii[i + 1]
        r = max(ra, rb) + margin
        ssl, ax = field.block(np.minimum(a, b) - r, np.maximum(a, b) + r)
        X, Y, Z = np.meshgrid(*ax, indexing="ij")
        ab = b - a
        L2 = max(ab @ ab, 1e-12)
        t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1] + (Z - a[2]) * ab[2]) / L2, 0, 1)
        dx, dy, dz = X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]), Z - (a[2] + t * ab[2])
        d = np.sqrt(dx * dx + dy * dy + dz * dz) - (ra + t * (rb - ra))
        lsl = tuple(slice(s.start - o, s.stop - o) for s, o in zip(ssl, origin))
        np.minimum(local[lsl], d, out=local[lsl])
    field.combine(sl, local, k)


def sdf_polygon_2d(poly, P):
    """Signed distance from points P (M, 2) to a closed polygon (negative inside)."""
    poly = np.asarray(poly, float)
    d2 = np.full(len(P), np.inf)
    inside = np.zeros(len(P), bool)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        e = b - a
        w = P - a
        t = np.clip((w @ e) / max(e @ e, 1e-12), 0, 1)
        q = w - t[:, None] * e
        d2 = np.minimum(d2, (q * q).sum(1))
        c1 = (a[1] <= P[:, 1]) & (b[1] > P[:, 1])
        c2 = (a[1] > P[:, 1]) & (b[1] <= P[:, 1])
        cross = e[0] * w[:, 1] - e[1] * w[:, 0]
        inside ^= (c1 & (cross > 0)) | (c2 & (cross < 0))
    d = np.sqrt(d2)
    return np.where(inside, -d, d)


class RZField:
    """A signed distance in the (r, z) half plane, tabulated finely so that it
    can be sampled for millions of 3D points (solids of revolution)."""

    def __init__(self, poly, h=0.1, pad=4.0):
        poly = np.asarray(poly, float)
        self.lo = poly.min(0) - pad
        self.lo[0] = 0.0
        hi = poly.max(0) + pad
        self.h = h
        nr, nz = (np.ceil((hi - self.lo) / h).astype(int) + 1)
        R, Z = np.meshgrid(self.lo[0] + h * np.arange(nr), self.lo[1] + h * np.arange(nz),
                           indexing="ij")
        self.table = sdf_polygon_2d(poly, np.c_[R.ravel(), Z.ravel()]).reshape(nr, nz)

    def __call__(self, r, z):
        ir = (r - self.lo[0]) / self.h
        iz = (z - self.lo[1]) / self.h
        return map_coordinates(self.table, [ir.ravel(), iz.ravel()], order=1,
                               mode="nearest").reshape(r.shape)


# --- Meshing and exact finishing -------------------------------------------------
def to_manifold(field):
    # pad with an "outside" layer so the surface is always closed
    vol = np.pad(field.d, 1, constant_values=1e3)
    verts, faces, _, _ = marching_cubes(vol, level=0.0, spacing=(field.h,) * 3)
    verts += field.lo - field.h
    t = trimesh.Trimesh(verts, faces, process=True)   # merges duplicates, drops degenerate faces
    verts, faces = np.asarray(t.vertices), np.asarray(t.faces)
    mesh = mf.Mesh(vert_properties=verts.astype(np.float32), tri_verts=faces.astype(np.uint32))
    m = mf.Manifold(mesh)
    if m.status() != mf.Error.NoError or m.is_empty():
        raise RuntimeError(f"marching cubes mesh is not manifold: {m.status()}")
    if m.volume() < 0:
        m = mf.Manifold(mf.Mesh(vert_properties=verts.astype(np.float32),
                                tri_verts=faces[:, ::-1].astype(np.uint32)))
    return m


def _apply_cuts(field, cut):
    """d = max(d, -cut) slab by slab; `cut(r, z)` is the SDF of what to remove."""
    nz = field.n[2]
    for z0 in range(0, nz, 32):
        sl = (slice(0, field.n[0]), slice(0, field.n[1]), slice(z0, min(z0 + 32, nz)))
        X, Y, Z = field.coords(sl)
        field.d[sl] = np.maximum(field.d[sl], -cut(np.hypot(X, Y), Z))


def finish_basket_seat(field, zt):
    """Flat bed, flat flange rest at zt and cylindrical contact faces on the
    basket wall (radius basket_d / 2 + FIT) from zt - SEAT_H up.
    The cuts are exact distance functions applied before meshing, so the faces
    land within ~0.001 mm and the mesh stays clean."""
    rs, z0 = seat_r(), zt - SEAT_H

    def cut(r, z):
        bed, top = z, zt - z                       # outside of the slab 0 < z < zt
        bore = np.maximum(r - rs, z0 - z)          # r < rs and z > z0
        return np.minimum(np.minimum(bed, top), bore)
    _apply_cuts(field, cut)


def finish_flange_seat(field, zt, ztip):
    """Flat bed; the flange rests on ledges at zt and its rim is located by
    cylindrical faces (radius flange_d / 2 + FIT); tips may rise to ztip."""
    rp = pocket_r()

    def cut(r, z):
        bed, top = z, ztip - z
        pocket = np.maximum(r - rp, zt - z)
        return np.minimum(np.minimum(bed, top), pocket)
    _apply_cuts(field, cut)


def funnel(zt, segments=180):
    """Dummy of the funnel resting with its flange underside on z = zt."""
    f = FUNNEL
    zb = zt - f["basket_h"]
    rs = f["stem_d"] / 2
    rb = f["basket_d_bottom"] / 2
    pts = [(0, zb - f["stem_len"]), (rs, zb - f["stem_len"]), (rs, zb - 1.0),
           (rb - 1.5, zb), (rb, zb + 1.5), (f["basket_d"] / 2, zt),
           (f["flange_d"] / 2, zt), (f["flange_d"] / 2, zt + f["flange_t"]),
           (0, zt + f["flange_t"])]
    return mf.Manifold.revolve(mf.CrossSection([pts]), segments)


# --- Checks and export ------------------------------------------------------------
def to_trimesh(m):
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts),
                           process=False)


def overhang_report(m, zt, limit=45.0, ignore_below=0.4):
    """Area of downward faces flatter than `limit` deg from vertical (bed excluded)."""
    t = to_trimesh(m)
    n = t.face_normals
    c = t.triangles_center
    a = t.area_faces
    thresh = -math.sin(math.radians(90 - limit))   # n_z below this = too flat
    bad = (n[:, 2] < thresh) & (c[:, 2] > ignore_below)
    return a[bad].sum(), (c[bad] if bad.any() else np.zeros((0, 3)))


def report(name, m, zt):
    bb = m.bounding_box()
    size = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
    parts = len(m.decompose())
    clash = (m ^ funnel(zt)).volume()
    gap = m.min_gap(funnel(zt), 3.0)
    over, where = overhang_report(m, zt)
    print(f"[{name}] size {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm, "
          f"volume {m.volume() / 1000:.1f} cm3 (~{m.volume() / 1000 * 1.24:.0f} g PLA if solid), "
          f"parts {parts}, triangles {m.num_tri()}")
    print(f"[{name}] funnel clash {clash:.3f} mm3, min gap to funnel {gap:.3f} mm, "
          f"overhang > 45deg: {over:.1f} mm2"
          + (f" (z {where[:, 2].min():.1f}..{where[:, 2].max():.1f})" if len(where) else ""))
    assert parts == 1, "stand is not one connected part"
    assert clash < 0.05, "stand intersects the funnel"  # mm3, numerical contact at the seat
    assert all(s < b for s, b in zip(size, BED)), "does not fit the i3 Mega"


def export_stl(m, path, zt=None):
    """Write the STL (lightly simplified, max 0.01 mm deviation) and a small
    JSON sidecar that make_fcstd.py uses to place the funnel dummy."""
    m = m.simplify(0.01)
    to_trimesh(m).export(path)
    back = trimesh.load(path)   # what a slicer sees: vertices merged by position
    assert back.is_watertight and back.is_volume, f"{path} is not a clean closed mesh"
    if zt is not None:
        import json
        with open(os.path.splitext(path)[0] + ".json", "w") as fh:
            json.dump(dict(z_top=zt, funnel=FUNNEL, fit=FIT, seat_h=SEAT_H), fh, indent=1)
    print(f"stl -> {path} ({m.num_tri()} triangles)")


# --- Preview renderer --------------------------------------------------------------
def _camera(elev, azim):
    e, a = math.radians(elev), math.radians(azim)
    fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    right = np.cross([0, 0, 1], fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    return right, up, fwd


def render(items, elev=22, azim=-60, size=800, margin=0.06, frame=None):
    """items: [(manifold, rgb)] -> HxWx3 image (orthographic, z-buffer, smooth)."""
    right, up, fwd = _camera(elev, azim)
    M = np.c_[right, up, fwd]
    meshes = []
    for m, rgb in items:
        t = to_trimesh(m).smooth_shaded   # split sharp edges so cut faces shade flat
        meshes.append((t.vertices @ M, t.faces, t.vertex_normals, np.array(rgb, float)))
    pts = np.vstack([q for q, *_ in meshes]) if frame is None else frame @ M
    lo, hi = pts[:, :2].min(0), pts[:, :2].max(0)
    scale = size * (1 - 2 * margin) / max(hi - lo)
    off = (size - (hi - lo) * scale) / 2
    pix_all, dep_all, nrm_all, col_all = [], [], [], []
    for Q, F, N, rgb in meshes:
        xy = (Q[:, :2] - lo) * scale + off
        xy[:, 1] = size - xy[:, 1]
        tri = xy[F]                                  # (T, 3, 2)
        bmin = np.floor(tri.min(1)).astype(int)
        span = (np.ceil(tri.max(1)).astype(int) - bmin).max(1) + 1
        for s in np.unique(span):
            sel = np.where(span == s)[0]
            for chunk in np.array_split(sel, max(1, len(sel) * s * s // 4_000_000 + 1)):
                if not len(chunk):
                    continue
                g = np.arange(s)
                gx = bmin[chunk, 0, None, None] + g[None, None, :] + 0.5
                gy = bmin[chunk, 1, None, None] + g[None, :, None] + 0.5
                gx, gy = np.broadcast_arrays(gx, gy)
                a, b, c = tri[chunk, 0], tri[chunk, 1], tri[chunk, 2]
                den = ((b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1]))
                ok = np.abs(den) > 1e-12
                den = np.where(ok, den, 1)[:, None, None]
                w0 = ((b[:, 1, None, None] - c[:, 1, None, None]) * (gx - c[:, 0, None, None])
                      + (c[:, 0, None, None] - b[:, 0, None, None]) * (gy - c[:, 1, None, None])) / den
                w1 = ((c[:, 1, None, None] - a[:, 1, None, None]) * (gx - c[:, 0, None, None])
                      + (a[:, 0, None, None] - c[:, 0, None, None]) * (gy - c[:, 1, None, None])) / den
                w2 = 1 - w0 - w1
                inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4) & ok[:, None, None]
                inside &= (gx >= 0) & (gx < size) & (gy >= 0) & (gy < size)
                ti, yi, xi = np.nonzero(inside)
                if not len(ti):
                    continue
                f = F[chunk[ti]]
                W = np.stack([w0[ti, yi, xi], w1[ti, yi, xi], w2[ti, yi, xi]], 1)
                dep = (W * Q[f, 2]).sum(1)
                nrm = (W[:, :, None] * N[f]).sum(1)
                px = (gy[ti, yi, xi].astype(int)) * size + gx[ti, yi, xi].astype(int)
                pix_all.append(px); dep_all.append(dep); nrm_all.append(nrm)
                col_all.append(np.broadcast_to(rgb, (len(px), 3)))
    pix = np.concatenate(pix_all); dep = np.concatenate(dep_all)
    nrm = np.concatenate(nrm_all); col = np.concatenate(col_all)
    order = np.lexsort((-dep, pix))
    pix, dep, nrm, col = pix[order], dep[order], nrm[order], col[order]
    first = np.r_[True, pix[1:] != pix[:-1]]
    pix, dep, nrm, col = pix[first], dep[first], nrm[first], col[first]
    zbuf = np.full(size * size, -np.inf); zbuf[pix] = dep
    nb = np.zeros((size * size, 3)); nb[pix] = nrm
    cb = np.ones((size * size, 3)); cb[pix] = col
    zbuf = zbuf.reshape(size, size); nb = nb.reshape(size, size, 3); cb = cb.reshape(size, size, 3)
    hit = np.isfinite(zbuf)
    n = nb / (np.linalg.norm(nb, axis=2, keepdims=True) + 1e-12)
    n_cam = np.stack([n @ right, n @ up, n @ fwd], axis=2)
    n_cam[n_cam[..., 2] < 0] *= -1
    l1 = np.array([-0.45, 0.55, 0.70]); l1 /= np.linalg.norm(l1)
    l2 = np.array([0.6, -0.1, 0.8]); l2 /= np.linalg.norm(l2)
    diff = 0.60 * np.clip(n_cam @ l1, 0, 1) + 0.22 * np.clip(n_cam @ l2, 0, 1)
    hv = l1 + np.array([0, 0, 1.0]); hv /= np.linalg.norm(hv)
    spec = 0.20 * np.clip(n_cam @ hv, 0, 1) ** 40
    rim = 0.10 * (1 - np.clip(n_cam[..., 2], 0, 1)) ** 2
    img = cb * (0.30 + diff)[..., None] + (spec + rim)[..., None]
    z = np.where(hit, zbuf, (zbuf[hit].min() - 30) if hit.any() else 0)
    edge = np.zeros_like(z, bool)
    edge[1:, :] |= np.abs(np.diff(z, axis=0)) > 2.5   # depth jump in mm
    edge[:, 1:] |= np.abs(np.diff(z, axis=1)) > 2.5
    img[edge] *= 0.45
    img[~hit & ~edge] = 1.0
    return np.clip(img, 0, 1)


CLAY = (0.87, 0.82, 0.72)
STEEL = (0.62, 0.66, 0.72)


def preview_sheet(path, title, m, zt, notes=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fun = funnel(zt)
    near = mf.Manifold.cube([400, 400, 400]).translate([-200, -400, -100])  # camera at -y
    both = m + fun
    bb = both.bounding_box()
    frame = np.array([[x, y, z] for x in bb[0::3] for y in bb[1::3] for z in bb[2::3]])
    views = [
        ("Holder", render([(m, CLAY)], 24, -60, frame=frame)),
        ("With funnel (dummy)", render([(m, CLAY), (fun, STEEL)], 24, -60, frame=frame)),
        ("Side", render([(m, CLAY)], 0, -90, frame=frame)),
        ("Cutaway with funnel", render([(m - near, CLAY), (fun - near, STEEL)], 6, -90, frame=frame)),
    ]
    fig, axs = plt.subplots(2, 2, figsize=(10, 10.6), dpi=110)
    for ax, (t, im) in zip(axs.ravel(), views):
        ax.imshow(im)
        ax.set_title(t, fontsize=10, loc="left", color="#444")
        ax.axis("off")
    fig.suptitle(title, fontsize=15, x=0.03, ha="left", y=0.99)
    if notes:
        fig.text(0.03, 0.955, notes, fontsize=9.5, color="#555", ha="left", va="top", wrap=True)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.90, wspace=0.02, hspace=0.07)
    fig.savefig(path)
    plt.close(fig)
    print(f"preview -> {path}")


def out_path(here, name, ext):
    return os.path.join(here, f"{name}.{ext}")
