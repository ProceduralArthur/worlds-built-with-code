"""Render quick previews of a model: still views from several angles, or a turntable for a GIF.

The camera is orthographic, frames every visible mesh automatically and turns around the model
(yaw 0 = front, looking at the model from -Y). Cycles on the CPU, so it runs on any machine.
If the scene has no lamps, a sun is added (only matters before the toon step; the toon shader ignores lamps).

Usage:
  blender -b step4.blend --python render_preview.py -- --views 0,35,180 --out renders/after.png
  blender -b step4.blend --python render_preview.py -- --turntable 48 --res 360 --out frames/turn.png
    (turntable: frames saved as turn_0001.png ... ; the animation advances one frame per image,
     so the vein pulse and the floating idle play while the camera turns)
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import bounds, hex_to_linear, parse_args  # noqa: E402


def options(p):
    p.add_argument("--out", required=True, help="output .png (view or frame number is added to the name)")
    p.add_argument("--views", default="0", help="comma-separated yaw angles in degrees (0 = front)")
    p.add_argument("--turntable", type=int, default=0, help="render N frames of a 360-degree turn instead")
    p.add_argument("--frame", type=int, default=1, help="scene frame for still views")
    p.add_argument("--res", type=int, default=720, help="square image size in pixels")
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--bg", default="0E7C7B", help="background colour, hex (channel teal by default)")
    p.add_argument("--margin", type=float, default=1.35, help="frame size / model size")


def setup(args):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = args.samples
    sc.render.threads_mode, sc.render.threads = "FIXED", args.threads
    sc.render.resolution_x = sc.render.resolution_y = args.res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*hex_to_linear(args.bg), 1)
    bg.inputs["Strength"].default_value = 1.0
    if not any(o.type == "LIGHT" for o in sc.objects):
        sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
        sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    sc.camera = cam
    return sc, cam


def aim(cam, lo, hi, yaw_deg, margin):
    c, size = (lo + hi) / 2, (hi - lo)
    cam.data.ortho_scale = max(size.x, size.y, size.z) * margin
    d = size.length * 3 + 1
    r = math.radians(yaw_deg)
    cam.location = c + Vector((math.sin(r) * d, -math.cos(r) * d, 0.15 * size.z))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = d * 3


def render(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    sc, cam = setup(args)
    objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
    base, _ = os.path.splitext(os.path.abspath(args.out))
    if args.turntable:
        sc.frame_set(1)
        lo, hi = bounds(objs)  # frame once, so the camera does not breathe with the animation
        for i in range(args.turntable):
            sc.frame_set(sc.frame_start + i)
            aim(cam, lo, hi, 360.0 * i / args.turntable, args.margin)
            render(sc, f"{base}_{i + 1:04d}.png")
    else:
        sc.frame_set(args.frame)
        lo, hi = bounds(objs)
        for yaw in [float(v) for v in args.views.split(",")]:
            aim(cam, lo, hi, yaw, args.margin)
            render(sc, f"{base}_{int(yaw):03d}.png")


main()
