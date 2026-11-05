# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "scikit-image", "manifold3d", "trimesh", "matplotlib"]
# ///
"""Side-by-side overview of all drafts (reads the STLs + JSON sidecars)."""
import json
import os

import manifold3d as mf
import matplotlib
import numpy as np
import trimesh

import organic as O

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DRAFTS = [("draft_a_tulip", "A - Tulpe (tulip)"), ("draft_b_woven", "B - Geflecht (woven)"),
          ("draft_c_vine", "C - Ranke (vine)")]


def load(name):
    t = trimesh.load(os.path.join(HERE, name + ".stl"))
    m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                            tri_verts=np.asarray(t.faces, np.uint32)))
    return m, json.load(open(os.path.join(HERE, name + ".json")))["z_top"]


items = [(title, *load(name)) for name, title in DRAFTS]
frame = np.array([[x, y, z] for x in (-44, 44) for y in (-44, 44) for z in (-2, 78)])
fig, axs = plt.subplots(2, 3, figsize=(15, 10.2), dpi=100)
for col, (title, m, zt) in enumerate(items):
    axs[0, col].imshow(O.render([(m, O.CLAY)], 22, -60, size=700, frame=frame))
    axs[1, col].imshow(O.render([(m, O.CLAY), (O.funnel(zt), O.STEEL)], 22, -60, size=700,
                                frame=frame))
    axs[0, col].set_title(title, fontsize=14, loc="left")
    for r in (0, 1):
        axs[r, col].axis("off")
fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.95, wspace=0.02, hspace=0.04)
fig.savefig(os.path.join(HERE, "drafts_overview.png"))
print("overview -> drafts_overview.png")
