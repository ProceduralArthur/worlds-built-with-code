"""Small helpers shared by the scripts in this folder.

Every script follows the same pattern:

    blender -b [model.blend] --python <script>.py -- [--input MODEL] [--objects A,B] [options] [--save OUT.blend]

* ``--input``   loads a model first (.blend, .glb/.gltf, .fbx or .obj). Without it the script works on the
                file Blender was started with (the optional ``model.blend`` above).
* ``--objects`` comma-separated mesh names to work on. Default: every mesh in the scene.
* ``--save``    writes the result to a new .blend (textures are packed inside). Your input is never overwritten.

Sizes are given as a FRACTION OF THE MODEL HEIGHT, so the same numbers work on a 1 m character
and on a 20 m one. (Ilhinha is about 1 m tall, so 0.015 means 1.5 cm for her.)
"""
import argparse
import os
import sys

import bpy
from mathutils import Vector


def parse_args(description, add_options=None):
    """Read the options that come after `--` on the Blender command line."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="blender -b --python <script> --", description=description)
    p.add_argument("--input", help="model to load (.blend, .glb, .gltf, .fbx, .obj)")
    p.add_argument("--objects", help="comma-separated mesh names to process (default: all meshes)")
    p.add_argument("--save", help="save the result to this .blend file")
    if add_options:
        add_options(p)
    args = p.parse_args(argv)
    load(args.input)
    return args


def load(path):
    if not path:
        return
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f"unsupported file type: {ext}")


def meshes(names=None):
    """The mesh objects to work on."""
    if not names:
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    else:
        objs = []
        for n in names.split(","):
            o = bpy.data.objects.get(n.strip())
            if o is None or o.type != "MESH":
                raise SystemExit(f"no mesh object called {n.strip()!r}")
            objs.append(o)
    if not objs:
        raise SystemExit("no mesh objects found")
    return objs


def bounds(objs):
    """World-space bounding box (min, max) of several objects, modifiers included."""
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def height(objs):
    lo, hi = bounds(objs)
    return max(hi.z - lo.z, 1e-6)


def triangles(objs):
    return sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)


def hex_to_linear(h):
    """'#3FF5E8' -> linear RGB tuple (Blender colour sockets are linear)."""
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def save(path):
    if not path:
        return
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.file.pack_all()  # keep the textures inside the .blend
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("saved", path)
