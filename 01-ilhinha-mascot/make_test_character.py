"""Build a small stand-in for an AI-generated character, to try the scripts without your own model.

It imitates what the image-to-3D tool gave us: ONE mesh object ("Character") where the body and the hands and feet
are separate islands that only touch, plus a texture with cyan "crystal veins" painted on a brown rock.
Everything is generated here (no downloads); the result depends only on --seed.

Usage:
  blender -b --factory-startup --python make_test_character.py -- --save test_character.blend
"""
import math
import os
import random
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import parse_args, save  # noqa: E402


def options(p):
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--texture", type=int, default=512, help="texture size in pixels")


def painted_texture(size, rng):
    """Brown rock with darker blotches and a few bright cyan zig-zag veins."""
    y, x = np.mgrid[0:size, 0:size] / size
    blotch = 0.5 + 0.5 * np.sin(x * 23 + np.sin(y * 17) * 2) * np.sin(y * 19 + np.cos(x * 13) * 2)
    img = np.zeros((size, size, 4), np.float32)
    img[..., 0] = 0.30 + 0.12 * blotch
    img[..., 1] = 0.19 + 0.08 * blotch
    img[..., 2] = 0.11 + 0.05 * blotch
    img[..., 3] = 1.0
    cyan = np.array([0.25, 0.96, 0.91], np.float32)
    for _ in range(14):  # veins: random walks, 2-3 px wide
        px, py = rng.uniform(0, size), rng.uniform(0, size)
        ang = rng.uniform(0, 2 * math.pi)
        for _ in range(rng.randint(40, 90)):
            ang += rng.uniform(-0.6, 0.6)
            px, py = (px + 2 * math.cos(ang)) % size, (py + 2 * math.sin(ang)) % size
            ix, iy = int(px), int(py)
            img[max(iy - 1, 0):iy + 2, max(ix - 1, 0):ix + 2, :3] = cyan
    im = bpy.data.images.new("TestCharacter_BaseColor", size, size, alpha=False)
    im.pixels[:] = img.ravel()  # values are stored as sRGB, like a painted texture
    im.pack()
    return im


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    rng = random.Random(args.seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # body: a rounded rock, about 1 m tall with the feet
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.62))
    body = bpy.context.object
    body.scale = (0.80, 0.70, 0.62)
    sub = body.modifiers.new("Round", "SUBSURF")
    sub.levels = 3
    bpy.ops.object.convert(target="MESH")
    for v in body.data.vertices:  # lumpy, so it reads as rock
        v.co *= 1.0 + 0.06 * math.sin(v.co.x * 11 + args.seed) * math.cos(v.co.y * 9) * math.sin(v.co.z * 7)
    parts = [body]
    # hands touch the sides, feet touch the bottom: separate islands, glued visually
    for x, z, r in [(-0.47, 0.50, 0.13), (0.47, 0.50, 0.13), (-0.20, 0.17, 0.15), (0.20, 0.17, 0.15)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r, location=(x, 0, z))
        parts.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.join()
    body.name = body.data.name = "Character"

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    for p in body.data.polygons:
        p.use_smooth = True

    mat = bpy.data.materials.new("TestCharacter")
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = painted_texture(args.texture, rng)
    bsdf = nt.nodes["Principled BSDF"]
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    body.data.materials.append(mat)
    print(f"test character: {len(body.data.polygons)} faces, 5 islands")
    save(args.save)


main()
