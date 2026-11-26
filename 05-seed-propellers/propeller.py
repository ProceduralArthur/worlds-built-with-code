"""Build a propeller that spins true: a fixed ring + a rotor (hub and blades) modelled around ONE exact axis.

This is the technique from the Seed episode. The image-to-3D model gave us each propeller as one fused lump (ring,
blades and hub in one surface, the ring tilted up to 16 degrees away from the blades), so spinning it made everything
wobble. Cutting the blades out of the lump failed four times, so we deleted the four propellers and modelled new ones
in code. Because every part is built around the local Z axis of its object, the rotor spins true by construction.

The parts are the same as in our build script (simplified: one colour per part instead of our painted rust and stripes):
  - Ring:  a rounded-rectangle profile swept around Z (it stays still; the arm holds it);
  - Rotor: a hub cylinder + N paddle blades (round tips, with pitch), in ONE object whose origin is on the axis.
The rotor gets a looping spin (360 degrees x turns over the loop), and the script prints a "spin check": how far the
rotor's centre of mass is from the spin axis and how far its main axis tilts away from it (both ~0 here), plus the same
numbers for a deliberately tilted copy, to show what a fused, tilted part looks like in numbers.

Run (Blender 4.x, CPU only):
    blender -b --python propeller.py -- --blades 3 --out propeller.blend --preview images/propeller.png
Options: --radius 0.20 (outer ring radius, m), --pitch 12 (blade pitch, degrees), --frames 120 --turns 3 (loop),
         --tilt-demo 11.2 (degrees for the tilted copy in the check), --gif-frames DIR (render the loop as PNG frames).
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blades", type=int, default=3)
    ap.add_argument("--radius", type=float, default=0.20)
    ap.add_argument("--pitch", type=float, default=12.0)
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--tilt-demo", type=float, default=11.2)
    ap.add_argument("--out", default="propeller.blend")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--gif-frames", default=None)
    return ap.parse_args(argv)


# ------------------------------------------------------------------ mesh builders (all in the object's local space)
class Mesh:
    """Collects vertices and faces, then becomes one object (duplicates merged, normals pointing OUT)."""

    def __init__(self):
        self.v, self.f = [], []

    def add(self, vs, fs):
        b = len(self.v)
        self.v += [tuple(x) for x in vs]
        self.f += [[b + i for i in f] for f in fs]

    def object(self, name, material):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        # Without this, some blade faces pointed inwards and the black outline (inverted hull) vanished on them:
        # the "bug of the day" in the video. Recalculating the normals fixed it.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(material)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def ring(m, r_in, r_out, half_h, z0=0.0, nseg=96, bevel=0.006):
    """Ring with a rounded rectangular profile (r_in..r_out, z0-half_h..z0+half_h), swept around Z."""
    prof = []
    corners = [(r_out - bevel, z0 + half_h - bevel, 0), (r_in + bevel, z0 + half_h - bevel, 90),
               (r_in + bevel, z0 - half_h + bevel, 180), (r_out - bevel, z0 - half_h + bevel, 270)]
    for cr, cz, a0 in corners:
        for k in range(3):
            a = math.radians(a0 + 45 * k)
            prof.append((cr + bevel * math.cos(a), cz + bevel * math.sin(a)))
    n = len(prof)
    vs, fs = [], []
    for i in range(nseg):
        th = 2 * math.pi * i / nseg
        vs += [(r * math.cos(th), r * math.sin(th), z) for r, z in prof]
    for i in range(nseg):
        j = (i + 1) % nseg
        for k in range(n):
            fs.append([i * n + k, j * n + k, j * n + (k + 1) % n, i * n + (k + 1) % n])
    m.add(vs, fs)


def cylinder(m, r, z0, z1, nseg=16):
    vs = [(r * math.cos(2 * math.pi * i / nseg), r * math.sin(2 * math.pi * i / nseg), z) for z in (z0, z1)
          for i in range(nseg)]
    fs = [[i, (i + 1) % nseg, nseg + (i + 1) % nseg, nseg + i] for i in range(nseg)]
    fs += [list(range(nseg))[::-1], [nseg + i for i in range(nseg)]]
    m.add(vs, fs)


def blade(m, r0, r1, w_root, w_max, thick, pitch_deg, angle, z=0.0, n=14):
    """Paddle blade (round tip) from radius r0 to r1, pitched by pitch_deg, at `angle` radians around Z."""
    top, bot = [], []
    for i in range(n + 1):
        s = i / n
        x = r0 + (r1 - r0) * s
        if s < 0.72:
            hw = w_root / 2 + (w_max / 2 - w_root / 2) * math.sin(min(s / 0.72, 1) * math.pi / 2)
        else:
            hw = (w_max / 2) * math.sqrt(max(0.0, 1 - ((s - 0.72) / 0.28) ** 2))
        top.append((x, hw))
        bot.append((x, -hw))
    outline = top + bot[::-1][1:-1]
    R = Matrix.Rotation(angle, 3, "Z") @ Matrix.Rotation(math.radians(pitch_deg), 3, "X")
    nb = len(outline)
    vs = [R @ Vector((x, y, thick / 2)) + Vector((0, 0, z)) for x, y in outline]
    vs += [R @ Vector((x, y, -thick / 2)) + Vector((0, 0, z)) for x, y in outline]
    fs = [list(range(nb)), [nb + i for i in range(nb)][::-1]]
    fs += [[i, nb + i, nb + (i + 1) % nb, (i + 1) % nb] for i in range(nb)]
    m.add(vs, fs)


def material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat


# ------------------------------------------------------------------ the spin check
def spin_check(ob) -> dict:
    """How 'true' an object spins around its local Z axis: distance of its centre of mass (area-weighted) from the
    axis, and the tilt between the axis and the object's own symmetry axis (the principal axis of the area
    distribution that is most different from the other two)."""
    me = ob.data
    c = np.array([p.center[:] for p in me.polygons])
    a = np.array([p.area for p in me.polygons])
    com = (c * a[:, None]).sum(0) / a.sum()
    q = c - com
    cov = (q * a[:, None]).T @ q / a.sum()
    w, vecs = np.linalg.eigh(cov)
    # symmetry axis of a flat rotor = the eigenvector whose eigenvalue stands apart from the other two
    gaps = [abs(w[0] - w[1]) + abs(w[0] - w[2]), abs(w[1] - w[0]) + abs(w[1] - w[2]), abs(w[2] - w[0]) + abs(w[2] - w[1])]
    axis = vecs[:, int(np.argmax(gaps))]
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[2])))))
    return dict(off_axis_mm=round(float(np.hypot(com[0], com[1])) * 1000, 2), tilt_deg=round(tilt, 2))


# ------------------------------------------------------------------ main
def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    r_out = a.radius
    r_in = r_out - 0.027 * r_out / 0.2
    half_h = 0.019 * r_out / 0.2
    r_blade = r_in - 0.008 * r_out / 0.2
    mats = dict(ring=material("Ring", (0.80, 0.30, 0.08)), rotor=material("Rotor", (0.85, 0.70, 0.50)),
                hub=material("Hub", (0.70, 0.45, 0.15)))

    m = Mesh()
    ring(m, r_in, r_out, half_h)
    ring_ob = m.object("Ring", mats["ring"])

    m = Mesh()
    cylinder(m, 0.022 * r_out / 0.2, -half_h, 0.016 * r_out / 0.2)
    for k in range(a.blades):
        blade(m, 0.012 * r_out / 0.2, r_blade, 0.026 * r_out / 0.2, 0.60 * r_blade, 0.009 * r_out / 0.2, a.pitch,
              2 * math.pi * k / a.blades)
    rotor = m.object("Rotor", mats["rotor"])

    # one exact axis: the rotor's origin is on it, and only its local Z rotation is animated (linear, seamless loop)
    sc.frame_start, sc.frame_end = 1, a.frames
    rotor.rotation_euler = (0, 0, 0)
    rotor.keyframe_insert("rotation_euler", index=2, frame=1)
    rotor.rotation_euler = (0, 0, 2 * math.pi * a.turns)   # frame frames+1 = frame 1 again: the loop has no seam
    rotor.keyframe_insert("rotation_euler", index=2, frame=a.frames + 1)
    fc = rotor.animation_data.action.fcurves.find("rotation_euler", index=2)
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

    # the check, on the built rotor and on a copy tilted like the AI model's worst ring (11.2 degrees off)
    ok = spin_check(rotor)
    lump = rotor.copy()
    lump.data = rotor.data.copy()
    lump.data.transform(Matrix.Rotation(math.radians(a.tilt_demo), 4, "X"))
    lump.data.transform(Matrix.Translation((0.004, 0.0, 0.0)))
    bad = spin_check(lump)
    bpy.data.meshes.remove(lump.data)
    print(f"SPIN CHECK rotor: {ok}  (built around Z: spins true)")
    print(f"SPIN CHECK tilted copy ({a.tilt_demo} deg, 4 mm off): {bad}  (this one would wobble)")

    # camera and light for the preview
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    cam.location = (0.0, -0.62 * r_out / 0.2, 0.38 * r_out / 0.2)
    cam.rotation_euler = (math.radians(58), 0, 0)
    sc.camera = cam
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), math.radians(-20), math.radians(30))
    sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.05, 0.25, 0.25, 1)
    sc.world = world
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 32
    sc.render.resolution_x = sc.render.resolution_y = 512

    out = os.path.abspath(a.out)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("saved", out)
    if a.preview:
        sc.frame_set(1)
        sc.render.filepath = os.path.abspath(a.preview)
        bpy.ops.render.render(write_still=True)
        print("preview", sc.render.filepath)
    if a.gif_frames:
        os.makedirs(a.gif_frames, exist_ok=True)
        sc.render.filepath = os.path.join(os.path.abspath(a.gif_frames), "spin_")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
