# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "scikit-image", "manifold3d", "trimesh", "matplotlib"]
# ///
"""Draft C - "Ranke" (vine): three tapered stems stand as a tripod on a flat
root ring, swirl inward and each forks into two twigs; the six twig tips carry
the flange and touch the basket wall with precise faces.

    uv run draft_c_vine.py
"""
import os

import numpy as np

import organic as O

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "draft_c_vine"
ZT = O.z_top(0.0)
ZB = ZT - O.FUNNEL["basket_h"]
BLEND = 1.6   # smooth-union radius at forks and roots (mm)

# (r, angle offset deg, z), angle relative to the stem's base angle
LEG = [(38, 0, -1.5), (33.6, 5.5, 7.5), (28.5, 13, 15), (24, 22, 23), (21.5, 31, 29), (21.5, 37, 33)]
TWIG_A = [(24, 32, 39), (27.8, 26, ZB - 1), (28.8, 22, ZB + 3), (28.9, 20, ZB + 9),
          (28.6, 19.5, ZT - 7), (28.2, 20, ZT - 3), (28.0, 20, ZT + 3)]
TWIG_B = [(24, 43, 38.5), (27.8, 51.5, ZB - 1), (28.6, 60, ZB + 5), (28.9, 68, ZB + 10.5),
          (28.6, 74, ZT - 6), (28.2, 78, ZT - 3), (28.0, 80, ZT + 3)]
ROOTS = [(38.5, 0), (34, 30), (29.5, 60), (34, 90)]   # repeated every 120 deg


def pts(spec, base):
    return [O.polar(r, base + a, z) for r, a, z in spec]


def build():
    f = O.Field((-44, -44, -3), (44, 44, ZT + 4), 0.3)
    worst = 90.0
    for i in range(3):
        base = 120 * i
        leg = O.sample_path(pts(LEG, base))
        O.add_tube(f, leg, np.linspace(3.4, 2.5, len(leg)), k=BLEND)
        worst = min(worst, O.path_min_angle(leg))
        for twig in (TWIG_A, TWIG_B):
            p = O.sample_path(pts(LEG[-3:], base) + pts(twig, base))
            O.add_tube(f, p, np.linspace(2.4, 1.65, len(p)), k=BLEND)
            worst = min(worst, O.path_min_angle(p))
    print(f"flattest stem direction: {worst:.1f} deg from horizontal (need >= 45)")
    ring = [O.polar(r, a + 120 * i, 1.0) for i in range(3) for r, a in ROOTS]
    O.add_tube(f, O.closed_path(ring, step=0.5), 2.6, k=BLEND)
    O.finish_basket_seat(f, ZT)
    return O.to_manifold(f)


if __name__ == "__main__":
    shape = build()
    O.report(NAME, shape, ZT)
    O.export_stl(shape, O.out_path(HERE, NAME, "stl"), ZT)
    O.preview_sheet(O.out_path(HERE, NAME, "png"), "Draft C - Ranke (vine)", shape, ZT,
                    "Three tapered stems stand on a flat root ring, swirl inward and fork;\n"
                    "the 6 twig tips carry the flange and touch the basket wall with precise faces.")
