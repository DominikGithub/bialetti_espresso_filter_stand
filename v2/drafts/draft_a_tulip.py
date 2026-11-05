# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "scikit-image", "manifold3d", "trimesh", "matplotlib"]
# ///
"""Draft A - "Tulpe" (tulip): lily-pad foot, slender fluted stalk that hides
the stem, five thin petals with a gentle twist. Each petal tip has a notch:
the flange rests on its ledge and the flange rim is located by its wall.

    uv run draft_a_tulip.py
"""
import math
import os

import numpy as np

import organic as O

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "draft_a_tulip"
FLOOR = 2.4
ZT = O.z_top(FLOOR)              # flange underside
ZB = ZT - O.FUNNEL["basket_h"]   # basket bottom
ZTIP = ZT + 5.0                  # petal tips rise past the flange
N_PET = 5
SWIRL = 0.6                      # twist, degrees per mm of height
GAP_R = 2.5                      # radius of the rounded gap bottoms
ZG = ZB + 4.0                    # gap bottoms
PETAL_HW = 5.0                   # petal half width at the flange (mm)

BORE_R = 6.6                     # stalk bore around the stem
# inner surface (r, z); the flare stays at <= 40 deg so it prints without support
INNER = [(BORE_R, ZB - 27), (7.3, ZB - 24), (9.0, ZB - 21), (13.2, ZB - 16), (17.6, ZB - 10.8),
         (21.8, ZB - 5.6), (25.2, ZB - 1.0), (26.3, ZB + 2.2), (27.0, ZB + 6), (27.6, ZB + 11),
         (27.9, ZB + 15), (28.6, ZT), (30.8, ZTIP + 1)]


def wall(z):
    return float(np.interp(z, [ZB - 24, ZB - 12, ZB + 6, ZT - 2, ZTIP], [2.6, 2.6, 2.4, 3.2, 2.8]))


def inner_r(z):
    p = O.sample_path([(r, 0, zz) for r, zz in INNER], step=0.2)
    return float(np.interp(z, p[:, 2], p[:, 0]))


def section():
    """Closed (r, z) outline of the plain (un-fluted, un-cut) body."""
    outer_ctrl = [(44, 0, 1.6), (36, 0, 2.3), (28, 0, 3.4), (20, 0, 5.5), (14, 0, 9),
                  (11, 0, 13), (9.4, 0, 17.5), (9.0, 0, ZB - 27)]
    outer_ctrl += [(inner_r(z) + wall(z), 0, z) for z in
                   (ZB - 22, ZB - 16, ZB - 10.8, ZB - 5.6, ZB - 1.0, ZB + 2.2, ZB + 6, ZB + 11,
                    ZB + 15, ZT, ZTIP + 1)]
    outer = O.sample_path(outer_ctrl, step=0.3)[:, [0, 2]]
    inner = O.sample_path([(r, 0, z) for r, z in INNER], step=0.3)[:, [0, 2]][::-1]
    return np.vstack([[(0, 0), (44, 0)], outer, inner, [(BORE_R, FLOOR), (0, FLOOR)]])


def swirl(z):
    return SWIRL * (z - ZB)


def gap_sdf(s, z):
    """Gap between petals in the unrolled (arc length s, z) plane."""
    zc = ZG + GAP_R
    half = math.pi / N_PET * 29.5                      # half pitch at petal radius
    t = np.clip((z - zc) / (ZT - zc), 0, 1)
    w = GAP_R + (half - PETAL_HW - GAP_R) * t ** 0.9
    q = np.clip((z - ZT) / (ZTIP - ZT), 0, 1)
    w = np.where(z > ZT, half - PETAL_HW * np.sqrt(np.clip(1 - q * q, 0, 1)), w)
    return np.where(z < zc, np.hypot(s, z - zc) - GAP_R, s - w)


def build():
    rz = O.RZField(section(), h=0.08)
    f = O.Field((-46, -46, -1), (46, 46, ZTIP + 2), 0.3)
    nz = f.n[2]
    for z0 in range(0, nz, 16):
        sl = (slice(0, f.n[0]), slice(0, f.n[1]), slice(z0, min(z0 + 16, nz)))
        X, Y, Z = f.coords(sl)
        r = np.hypot(X, Y)
        th = np.degrees(np.arctan2(Y, X))
        # fluting on the stalk, lily-pad lobes on the foot
        a = np.interp(Z, [6, 14, ZB - 24, ZB - 8], [0, 0.06, 0.06, 0])
        flute = 1 + a * np.cos(np.radians(N_PET * (th - swirl(Z))))
        wf = np.clip(1 - (Z - 3) / 5, 0, 1)
        pad = 1 + wf * 0.055 * (1 - np.cos(np.radians(N_PET * (th - 36 - swirl(0.0)))))
        d = rz(r * pad / flute, Z)
        # petal gaps (soft edged)
        u = np.mod(th - swirl(Z) - 180 / N_PET, 360 / N_PET) - 180 / N_PET
        g = gap_sdf(np.abs(np.radians(u)) * r, Z)
        f.d[sl] = -O.smin(-d, g, 0.8)
    O.finish_flange_seat(f, ZT, ZTIP)
    return O.to_manifold(f)


if __name__ == "__main__":
    shape = build()
    O.report(NAME, shape, ZT)
    O.export_stl(shape, O.out_path(HERE, NAME, "stl"), ZT)
    O.preview_sheet(O.out_path(HERE, NAME, "png"), "Draft A - Tulpe (tulip)", shape, ZT,
                    "Lily-pad foot, fluted twisting stalk hides the stem, 5 thin petals.\n"
                    "Each petal tip has a notch: the flange rests on its ledge, the flange rim is located by its wall.")
