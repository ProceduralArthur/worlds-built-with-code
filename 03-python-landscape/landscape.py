"""Procedural landscape in ~200 lines of Blender Python (video 3, Procedural Arthur).

Mountains, a valley lake, slope-aware materials, forests, rocks, sky and sun. One seed = one world.
Tested on Blender 4.4, CPU only:

    blender -b --factory-startup -t 2 --python landscape.py -- --seed 42 --out prova.png --res 640 360 --samples 16
"""
import math
import random
import sys

import bpy
from mathutils import Vector, noise

# ---------- 1. settings from the command line ----------
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default, cast=str, n=1):
    if name not in argv:
        return default
    i = argv.index(name)
    vals = [cast(v) for v in argv[i + 1:i + 1 + n]]
    return vals[0] if n == 1 else vals


SEED = arg("--seed", 42, int)
OUT = arg("--out", "//landscape.png")
RES = arg("--res", [1920, 1080], int, 2)
SAMPLES = arg("--samples", 64, int)

SIZE, DIV = 120.0, 300        # terrain: 120 m wide, 300x300 quads
PEAK = 28.0                   # tallest mountain, metres
WATER = 2.2                   # lake level
random.seed(SEED)
OFFSET = Vector((random.uniform(-500, 500), random.uniform(-500, 500), 0))  # the seed moves us through the noise


# ---------- 2. an empty scene ----------
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = SAMPLES
    s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = RES
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    return s


# ---------- 3. the height function: the heart of the video ----------
def ridged(p, octaves=6):
    """Ridged multifractal: sharp crests instead of soft blobs."""
    total, amp, freq = 0.0, 1.0, 1.0
    for _ in range(octaves):
        n = 1.0 - abs(noise.noise(p * freq, noise_basis="PERLIN_ORIGINAL"))
        total += n * n * amp
        amp *= 0.5
        freq *= 2.0
    return total


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def height(x, y):
    p = Vector((x, y, 0.0)) * 0.018 + OFFSET
    warp = Vector((noise.noise(p * 0.7), noise.noise(p * 0.7 + Vector((31, 7, 0))), 0)) * 0.6
    mountains = max(ridged(p + warp) - 0.9, 0.0) ** 1.6   # raw ridged is ~0.5..1.9: keep only the crests
    back = 0.15 + 0.85 * smooth((y + 30) / 70)             # low in front, high at the back
    hills = noise.fractal(p * 2.5, 0.6, 2.0, 4) * 0.06     # small bumps everywhere
    valley = math.exp(-((x * 0.6) ** 2 + (y + 10) ** 2) / 900)  # carve a basin for the lake
    h = mountains * back * (1 - 0.9 * valley) + hills + 0.04
    edge = min(1.0, (SIZE / 2 - max(abs(x), abs(y))) / 12)  # soften the borders
    return max(h * PEAK * max(edge, 0.0), 0.0)


def terrain():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=DIV, y_subdivisions=DIV, size=SIZE)
    t = bpy.context.object
    t.name = "Terrain"
    for v in t.data.vertices:
        v.co.z = height(v.co.x, v.co.y)
    t.data.polygons.foreach_set("use_smooth", [True] * len(t.data.polygons))
    return t


# ---------- 4. materials: colour by height, rock by slope ----------
def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def ramp(nt, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    el = r.color_ramp.elements
    el[0].position, el[0].color = stops[0]
    el[1].position, el[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        el.new(pos).color = col
    return r


def terrain_material(obj):
    m = bpy.data.materials.new("Terrain")
    m.use_nodes = True
    nt, L = m.node_tree, m.node_tree.links
    bsdf = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    xyz = nt.nodes.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], xyz.inputs[0])
    hmap = node(nt, "ShaderNodeMapRange", **{"From Min": WATER - 0.5, "From Max": PEAK * 0.9})
    L.new(xyz.outputs["Z"], hmap.inputs["Value"])
    by_height = ramp(nt, [(0.00, (0.30, 0.26, 0.18, 1)),   # wet sand
                          (0.05, (0.13, 0.22, 0.05, 1)),   # meadow
                          (0.25, (0.06, 0.13, 0.03, 1)),   # dark forest floor
                          (0.45, (0.17, 0.155, 0.14, 1)),  # bare rock
                          (0.62, (0.92, 0.93, 0.96, 1))])  # snow
    L.new(hmap.outputs["Result"], by_height.inputs["Fac"])
    nz = nt.nodes.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Normal"], nz.inputs[0])
    slope = ramp(nt, [(0.70, (1, 1, 1, 1)), (0.82, (0, 0, 0, 1))])  # 1 = steep
    L.new(nz.outputs["Z"], slope.inputs["Fac"])
    grain = node(nt, "ShaderNodeTexNoise", Scale=0.8, Detail=8.0)
    rock = ramp(nt, [(0.35, (0.09, 0.085, 0.08, 1)), (0.65, (0.22, 0.20, 0.18, 1))])
    L.new(grain.outputs["Fac"], rock.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(slope.outputs["Color"], mix.inputs["Factor"])
    L.new(by_height.outputs["Color"], mix.inputs["A"])
    L.new(rock.outputs["Color"], mix.inputs["B"])
    L.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bump = node(nt, "ShaderNodeBump", Strength=0.35)
    L.new(grain.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    obj.data.materials.append(m)


def flat_material(name, color, rough=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    return m


# ---------- 5. water and sky ----------
def water():
    bpy.ops.mesh.primitive_plane_add(size=SIZE, location=(0, 0, WATER))
    w = bpy.context.object
    w.name = "Lake"
    m = flat_material("Water", (0.02, 0.09, 0.12, 1), 0.04)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Transmission Weight"].default_value = 0.6
    b.inputs["IOR"].default_value = 1.33
    w.data.materials.append(m)


def sky(scene):
    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    sky_tex = world.node_tree.nodes.new("ShaderNodeTexSky")  # physical sky (Nishita)
    sky_tex.sun_elevation = math.radians(random.uniform(9, 20))  # golden-hour-ish, varies with seed
    sky_tex.sun_rotation = math.radians(random.uniform(150, 230))
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.08  # the physical sky is very bright
    world.node_tree.links.new(sky_tex.outputs["Color"], bg.inputs["Color"])
    bpy.ops.object.light_add(type="SUN")
    sun = bpy.context.object
    sun.data.energy = 2.5
    sun.data.color = (1.0, 0.85, 0.7)
    sun.rotation_euler = (math.pi / 2 - sky_tex.sun_elevation, 0, sky_tex.sun_rotation + math.pi / 2)


# ---------- 6. scatter: one mesh, many cheap copies ----------
def tree_mesh():
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.12, depth=1.2, location=(0, 0, 0.6))
    trunk = bpy.context.object
    trunk.data.materials.append(flat_material("Bark", (0.20, 0.12, 0.06, 1)))
    leaves = flat_material("Needles", (0.02, 0.07, 0.025, 1))
    parts = [trunk]
    for i, (r, z) in enumerate([(1.0, 1.6), (0.8, 2.5), (0.55, 3.3)]):
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=r, depth=1.6, location=(0, 0, z))
        bpy.context.object.data.materials.append(leaves)
        parts.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = trunk
    bpy.ops.object.join()
    trunk.hide_render = trunk.hide_viewport = True  # the template itself stays hidden
    return trunk.data


def rock_mesh():
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
    r = bpy.context.object
    for v in r.data.vertices:
        v.co *= 0.75 + 0.5 * noise.noise(v.co * 1.7 + OFFSET)
    r.data.materials.append(flat_material("Stone", (0.25, 0.23, 0.21, 1), 0.9))
    r.hide_render = r.hide_viewport = True
    return r.data


def slope_at(x, y, d=0.5):
    dx = height(x + d, y) - height(x - d, y)
    dy = height(x, y + d) - height(x, y - d)
    return math.hypot(dx, dy) / (2 * d)


def scatter(mesh, count, ok, scale, name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    placed, tries = 0, 0
    while placed < count and tries < count * 40:
        tries += 1
        x, y = random.uniform(-SIZE / 2.2, SIZE / 2.2), random.uniform(-SIZE / 2.2, SIZE / 2.2)
        z = height(x, y)
        if not ok(x, y, z):
            continue
        o = bpy.data.objects.new(f"{name}_{placed}", mesh)  # linked duplicate: shares the mesh
        o.location = (x, y, z - 0.1)
        o.rotation_euler = (random.uniform(-0.08, 0.08), random.uniform(-0.08, 0.08), random.uniform(0, 6.28))
        o.scale = [random.uniform(*scale)] * 3
        coll.objects.link(o)
        placed += 1
    return placed


def forest_density(x, y):
    return noise.noise(Vector((x, y, 0)) * 0.05 + OFFSET * 2) > -0.1  # patches, not a carpet


# ---------- 7. camera and render ----------
def camera(scene):
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    cam.data.lens = 28
    y0 = -SIZE * 0.42
    cam.location = (6, y0, height(6, y0) + 7)
    target = Vector((0, 20, PEAK * 0.3))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam


def main():
    scene = reset()
    terrain_material(terrain())
    water()
    sky(scene)
    trees = scatter(tree_mesh(), 1500,
                    lambda x, y, z: WATER + 0.6 < z < PEAK * 0.5 and slope_at(x, y) < 0.6 and forest_density(x, y),
                    (0.7, 1.4), "Trees")
    rocks = scatter(rock_mesh(), 250, lambda x, y, z: z > WATER and slope_at(x, y) > 0.4, (0.3, 1.2), "Rocks")
    camera(scene)
    print(f"seed={SEED} trees={trees} rocks={rocks}", flush=True)
    scene.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
    print("saved", OUT, flush=True)


main()
