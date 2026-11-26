"""Swept-volume check: in every frame of the animation, does any part enter the space a spinning rotor sweeps?

The check from the Seed episode ("a check I would never do by eye"): for each rotor (an object whose name starts with
--rotor-prefix, spinning around its own local Z axis), the swept volume is a cylinder in the rotor's local space: radius
= the farthest rotor vertex from the axis, height = the rotor's z range (plus a small margin). Then, frame by frame, every
vertex of every other mesh is moved into the rotor's local space and counted if it falls inside. Seed's 6 clips gave 0
hits. The test is on vertices (fast; keep your meshes dense enough, or lower --step). `--demo` adds an arm that
swings into the rotor's disc, so you can see a hit being caught.

Run (Blender 4.x, CPU only, no rendering):
    blender -b propeller.blend --python swept_volume_check.py -- --demo
    blender -b your_file.blend --python swept_volume_check.py -- --rotor-prefix Helice_ --step 2
Options: --step N (check every N frames), --margin 0.003 (m), --skip NAME (repeatable: objects to ignore, e.g. the
rotor's own ring if it can touch), --json out.json (write the hits).
"""
from __future__ import annotations

import argparse
import json
import sys

import bmesh
import bpy
import numpy as np


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotor-prefix", default="Rotor")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--margin", type=float, default=0.003)
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--json", default=None)
    ap.add_argument("--demo", action="store_true")
    return ap.parse_args(argv)


def add_demo_arm(sc):
    """A thin box that swings down through the rotor's disc in the middle of the loop (frames ~50-70)."""
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    arm = bpy.context.active_object
    arm.name = "DemoArm"
    arm.dimensions = (0.03, 0.03, 0.30)
    bpy.ops.object.transform_apply(scale=True)
    bm = bmesh.new()   # the check counts VERTICES (as ours did): give the box enough of them
    bm.from_mesh(arm.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=10, use_grid_fill=True)
    bm.to_mesh(arm.data)
    bm.free()
    arm.location = (0.10, 0.0, 0.30)
    mid = (sc.frame_start + sc.frame_end) // 2
    for fr, z in ((sc.frame_start, 0.30), (mid - 10, 0.30), (mid, 0.08), (mid + 10, 0.30), (sc.frame_end, 0.30)):
        arm.location.z = z
        arm.keyframe_insert("location", index=2, frame=fr)
    return arm


def main():
    a = args()
    sc = bpy.context.scene
    if a.demo:
        add_demo_arm(sc)
    rotors = [o for o in sc.objects if o.type == "MESH" and o.name.startswith(a.rotor_prefix)]
    if not rotors:
        sys.exit(f"no mesh named {a.rotor_prefix}*")
    others = [o for o in sc.objects if o.type == "MESH" and o not in rotors and o.name not in a.skip]
    vol = {}
    for r in rotors:
        v = np.array([x.co[:] for x in r.data.vertices])
        vol[r.name] = (np.hypot(v[:, 0], v[:, 1]).max() + a.margin, v[:, 2].min() - a.margin, v[:, 2].max() + a.margin)
    local = {o.name: np.c_[np.array([x.co[:] for x in o.data.vertices]), np.ones(len(o.data.vertices))] for o in others}
    hits = {}
    for fr in range(sc.frame_start, sc.frame_end + 1, a.step):
        sc.frame_set(fr)
        for r in rotors:
            Mi = np.array(r.matrix_world.inverted())
            rad, z0, z1 = vol[r.name]
            for o in others:
                P = (local[o.name] @ np.array(o.matrix_world).T) @ Mi.T
                k = int(((np.hypot(P[:, 0], P[:, 1]) < rad) & (P[:, 2] > z0) & (P[:, 2] < z1)).sum())
                if k:
                    hits.setdefault(f"{r.name} <- {o.name}", []).append((fr, k))
    n = sum(len(v) for v in hits.values())
    print(f"SWEPT VOLUME CHECK: {len(rotors)} rotor(s), {len(others)} other mesh(es), frames "
          f"{sc.frame_start}-{sc.frame_end} step {a.step}: {'NO HITS' if not hits else f'{n} frame hits'}")
    for k, v in hits.items():
        print(f"  {k}: frames {v[0][0]}-{v[-1][0]} ({len(v)} checked frames, up to {max(x[1] for x in v)} vertices)")
    if a.json:
        json.dump(hits, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
