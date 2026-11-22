"""Step 1: make a heavy AI-generated mesh light enough to animate.

Image-to-3D tools often return millions of triangles. Ilhinha came out with 1,953,851; this script brought
her down to about 50,000 while keeping the silhouette.

What it does:
  1. merges duplicate vertices (generated meshes are often a "triangle soup" with split seams),
  2. adds a Decimate modifier (Collapse) with ratio = target / current triangles, and applies it.

Usage:
  blender -b --python 01_decimate.py -- --input model.glb --target-tris 50000 --save step1.blend
"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import height, meshes, parse_args, save, triangles  # noqa: E402


def options(p):
    p.add_argument("--target-tris", type=int, default=50000, help="triangles to keep (whole model)")
    p.add_argument("--merge", type=float, default=0.0002,
                   help="merge vertices closer than this fraction of the model height (0 = skip)")


def merge_by_distance(obj, dist):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.to_mesh(obj.data)
    bm.free()
    return before - len(obj.data.vertices)


def apply_decimate(obj, ratio):
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    # Apply the modifier without operators: build a new mesh from the evaluated object.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    old = obj.data
    obj.modifiers.remove(mod)
    obj.data = new
    new.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    objs = meshes(args.objects)
    h = height(objs)
    if args.merge > 0:
        merged = sum(merge_by_distance(o, args.merge * h) for o in objs)
        print(f"merged {merged} duplicate vertices")
    before = triangles(objs)
    ratio = min(1.0, args.target_tris / before)
    if ratio < 1.0:
        for o in objs:
            apply_decimate(o, ratio)
    print(f"triangles: {before:,} -> {triangles(objs):,} (ratio {ratio:.4f})")
    save(args.save)


main()
