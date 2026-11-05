# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "scikit-image", "manifold3d", "trimesh", "matplotlib"]
# ///
"""Draft B - "Geflecht" (woven): 8 + 8 tapered tendrils twist in opposite
directions up an hourglass. They meet in pairs on a wavy foot ring and again
at the top, where the 8 crossings become the seat pads.

    uv run draft_b_woven.py
"""
import math
import os

import numpy as np

import organic as O

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "draft_b_woven"
ZT = O.z_top(0.0)
ZB = ZT - O.FUNNEL["basket_h"]
N = 8              # tendrils per direction
MAX_SLOPE = 0.92   # horizontal / vertical travel of a tendril -> >= 47 deg
Z_FOOT = 1.0       # pairs meet here, inside the foot ring
BLEND = 1.0        # smooth-union radius where tendrils meet (mm)

# centre-line radius of the tendrils over height (r, z)
PROFILE = [(37.2, -2.5), (36, Z_FOOT), (30.5, 10), (25, 20), (23, 28), (24.5, 36),
           (28.6, ZB), (29.2, ZB + 7), (28.8, ZB + 13), (28.2, ZT - 4), (28.0, ZT + 3)]


def twist_law():
    rz = O.sample_path([(r, 0, z) for r, z in PROFILE], step=0.2)
    zs = np.linspace(PROFILE[0][1], PROFILE[-1][1], 800)
    R = np.interp(zs, rz[:, 2], rz[:, 0])
    dR = np.gradient(R, zs)
    # as much twist as the overhang limit allows ...
    c = np.sqrt(np.clip(MAX_SLOPE ** 2 - dR ** 2, 0, None)) / R
    tw = np.concatenate([[0], np.cumsum((c[1:] + c[:-1]) / 2 * np.diff(zs))])
    tw -= np.interp(Z_FOOT, zs, tw)
    # ... scaled so that the two families meet in pairs at the foot and the seat
    top = np.interp(ZT, zs, tw)
    m = math.floor(2 * top * N / (2 * math.pi))
    tw *= (m * math.pi / N) / top
    print(f"twist foot->seat {math.degrees(m * math.pi / N):.1f} deg, {m} crossings per tendril")
    return zs, R, tw, m


def build():
    zs, R, tw, m = twist_law()
    f = O.Field((-44, -44, -3), (44, 44, ZT + 4), 0.3)
    radius = np.interp(zs, [zs[0], ZT], [1.9, 1.45])
    for k in range(N):
        for sign in (1, -1):
            phase = 2 * math.pi * k / N + (0 if sign == 1 else 2 * m * math.pi / N)
            ang = phase + sign * tw
            O.add_tube(f, np.c_[R * np.cos(ang), R * np.sin(ang), zs], radius, k=BLEND)
    a = np.linspace(0, 2 * math.pi, 97)[:-1]
    rr = 36 + 1.6 * np.cos(N * a)          # the ring bulges where tendrils land
    ring = np.c_[rr * np.cos(a), rr * np.sin(a), np.full_like(a, Z_FOOT)]
    O.add_tube(f, O.closed_path(ring, step=0.5), 2.4, k=BLEND)
    O.finish_basket_seat(f, ZT)
    return O.to_manifold(f)


if __name__ == "__main__":
    shape = build()
    O.report(NAME, shape, ZT)
    O.export_stl(shape, O.out_path(HERE, NAME, "stl"), ZT)
    O.preview_sheet(O.out_path(HERE, NAME, "png"), "Draft B - Geflecht (woven)", shape, ZT,
                    "16 tapered tendrils twist up an hourglass and meet in 8 pairs on the foot ring and at the top;\n"
                    "the 8 top crossings carry the flange and touch the basket wall with precise faces.")
