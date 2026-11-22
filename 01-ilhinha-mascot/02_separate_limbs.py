"""Step 2: cut the hands and feet off the body so they float, like a classic platformer hero.

The image-to-3D generator glued Ilhinha's hands and feet to her body. In the mesh they were already separate
"islands" (loose parts) that just touched the body, so the fix is:

  1. split the mesh into loose parts,
  2. the biggest part is the body; parts with at least --min-share of its faces are limbs;
     tiny bits (flowers, pebbles, stray triangles) are joined back to the body,
  3. limbs whose centre is near the bottom of the body are FEET: they move down (--drop) and a bit out (--spread);
     the others are HANDS: they move outwards, away from the body centre (--gap),
  4. holes where a part was glued are filled, normals recalculated, each origin moved to its own centre,
  5. optional --float: drivers make the body bob up and down, with hands and feet following a few frames late
     (that delay is what makes the floating limbs read as "alive").

Names: Body, Hand_L, Hand_R, Foot_L, Foot_R (L = viewer's left when the model faces -Y, Blender's front view).
Sizes are fractions of the model height.

Usage:
  blender -b step1.blend --python 02_separate_limbs.py -- --objects Body --float --save step2.blend
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import bounds, height, meshes, parse_args, save  # noqa: E402


def options(p):
    p.add_argument("--min-share", type=float, default=0.01,
                   help="a loose part is a limb if it has at least this share of the body's faces")
    p.add_argument("--gap", type=float, default=0.10, help="how far the hands move out")
    p.add_argument("--drop", type=float, default=0.085, help="how far the feet move down")
    p.add_argument("--spread", type=float, default=0.02, help="how far the feet move out")
    p.add_argument("--feet-zone", type=float, default=0.15,
                   help="limbs whose centre is below body bottom + this share of the body height are feet")
    p.add_argument("--float", action="store_true", help="add a looping floating idle (drivers)")
    p.add_argument("--period", type=int, default=48, help="frames per float cycle")


def center(o):
    lo, hi = bounds([o])
    return (lo + hi) / 2


def split_loose(obj):
    before = set(bpy.data.objects)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return [obj] + [o for o in bpy.data.objects if o not in before]


def join(target, others):
    if not others:
        return
    bpy.ops.object.select_all(action="DESELECT")
    for o in others + [target]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()


def close_and_center(o):
    """Fill the holes left where the part was glued, fix normals, put the origin at the part's centre."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    res = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.triangulate(bm, faces=res["faces"])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    pts = [Vector(c) for c in o.bound_box]
    c = sum(pts, Vector()) / 8
    o.data.transform(Matrix.Translation(-c))
    o.matrix_world = o.matrix_world @ Matrix.Translation(c)
    for p in o.data.polygons:
        p.use_smooth = True


def add_float(parts, amp, period):
    """Body bobs; each limb copies the motion a few frames late and a bit bigger. Loops every `period` frames."""
    delays = {"Body": (0, 1.0), "Hand_L": (5, 1.4), "Hand_R": (7, 1.3), "Foot_L": (9, 1.1), "Foot_R": (11, 1.1)}
    for i, o in enumerate(parts):
        d, k = delays.get(o.name.split(".")[0], (6 + i, 1.2))
        fc = o.driver_add("delta_location", 2)
        # a "simple expression": runs without enabling Python auto-execution
        fc.driver.expression = f"{amp * k:.5f}*sin(6.283185*(frame-{d})/{period})"
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, period


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    objs = meshes(args.objects)
    if len(objs) != 1:
        raise SystemExit("give exactly one mesh with --objects (the generated character)")
    model_h = height(objs)

    parts = split_loose(objs[0])
    body = max(parts, key=lambda o: len(o.data.polygons))
    min_faces = args.min_share * len(body.data.polygons)
    limbs = [o for o in parts if o is not body and len(o.data.polygons) >= min_faces]
    bits = [o for o in parts if o is not body and o not in limbs]
    join(body, bits)
    body.name = "Body"
    print(f"{len(parts)} loose parts: body, {len(limbs)} limbs, {len(bits)} small bits joined back to the body")

    blo, bhi = bounds([body])
    bc = (blo + bhi) / 2
    for o in limbs:
        c = center(o)
        out = Vector((c.x - bc.x, c.y - bc.y, 0))
        out = out.normalized() if out.length > 1e-6 else Vector((1, 0, 0))
        side = "L" if c.x < bc.x else "R"
        if c.z < blo.z + args.feet_zone * (bhi.z - blo.z):
            o.name = f"Foot_{side}"
            move = out * args.spread * model_h + Vector((0, 0, -args.drop * model_h))
        else:
            o.name = f"Hand_{side}"
            move = out * args.gap * model_h
        o.matrix_world = Matrix.Translation(move) @ o.matrix_world
        print(f"  {o.name}: {len(o.data.polygons)} faces, moved {tuple(round(v, 3) for v in move)}")

    for o in [body] + limbs:
        close_and_center(o)

    if args.float:
        add_float([body] + limbs, 0.025 * model_h, args.period)
        print(f"floating idle: {args.period} frames per loop")
    save(args.save)


main()
