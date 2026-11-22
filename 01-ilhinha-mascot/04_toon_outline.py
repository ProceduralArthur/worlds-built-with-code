"""Step 4: toon shader + black outline, so the 3D model looks like the 2D drawing.

Toon shader: instead of smooth light, the angle between the surface and a fixed light direction (N . L) goes into a
Color Ramp set to CONSTANT, which gives hard bands (shadow, mid-tone, light). The texture colour is multiplied by
the bands and anything the material already emits (for example the veins from step 3) is added on top.
The result goes into an Emission shader, so it looks the same in Cycles and EEVEE and needs no lamps.

Outline ("inverted hull"): a Solidify modifier makes a slightly bigger copy of the surface with flipped normals and
gives it a black material. From the camera you only see that shell where it sticks out around the silhouette.
The outline material is black on the shell's front faces and transparent on its back faces (Cycles), and uses
backface culling (EEVEE and game engines).

Works on any material that uses a Principled BSDF (the default in Blender and in glTF/FBX imports).

Usage:
  blender -b step3.blend --python 04_toon_outline.py -- --outline 0.015 --save step4.blend
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import hex_to_linear, height, meshes, parse_args, save  # noqa: E402

# Toon bands: (position on N.L, brightness multiplier). Same values as Ilhinha's first toon material.
BANDS = [(0.0, (0.58, 0.56, 0.56)),   # shadow (slightly warm grey, never black)
         (0.12, (0.82, 0.81, 0.80)),  # mid-tone
         (0.50, (1.0, 1.0, 1.0))]     # light


def options(p):
    p.add_argument("--light", type=float, nargs=3, default=[-0.45, -0.65, 0.62],
                   help="direction TO the light, world space (default: above, front, viewer's left)")
    p.add_argument("--outline", type=float, default=0.015, help="outline thickness (0 = no outline)")
    p.add_argument("--outline-color", default="010101", help="outline colour, hex")


def source(nt, socket):
    """What feeds a socket: the linked output, or the socket's own value."""
    return socket.links[0].from_socket if socket.is_linked else socket.default_value


def connect(nt, value, target):
    if isinstance(value, bpy.types.NodeSocket):
        nt.links.new(value, target)
    elif hasattr(value, "__len__"):
        target.default_value = tuple(value)[:len(target.default_value)]  # e.g. RGBA colour -> XYZ vector
    else:
        target.default_value = value


def make_toon(mat, light):
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if bsdf is None or out is None:
        print(f"  {mat.name}: no Principled BSDF, skipped")
        return False
    base = source(nt, bsdf.inputs["Base Color"])
    emit_color = source(nt, bsdf.inputs["Emission Color"])
    emit_strength = source(nt, bsdf.inputs["Emission Strength"])
    normal = source(nt, bsdf.inputs["Normal"]) if bsdf.inputs["Normal"].is_linked else None

    # N . L  ->  constant colour ramp = hard bands
    if normal is None:
        normal = nt.nodes.new("ShaderNodeNewGeometry").outputs["Normal"]
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(normal, dot.inputs[0])
    dot.inputs[1].default_value = Vector(light).normalized()
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.label = "Toon bands"
    ramp.color_ramp.interpolation = "CONSTANT"
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = BANDS[0][0], (*BANDS[0][1], 1)
    el[1].position, el[1].color = BANDS[-1][0], (*BANDS[-1][1], 1)
    for pos, col in BANDS[1:-1]:
        el.new(pos).color = (*col, 1)
    nt.links.new(dot.outputs["Value"], ramp.inputs["Fac"])

    # texture colour x bands
    lit = nt.nodes.new("ShaderNodeMix")
    lit.data_type, lit.blend_type = "RGBA", "MULTIPLY"
    lit.inputs[0].default_value = 1.0
    connect(nt, base, lit.inputs[6])
    nt.links.new(ramp.outputs["Color"], lit.inputs[7])

    # + whatever the material emitted before (glowing veins)
    glow = nt.nodes.new("ShaderNodeVectorMath")
    glow.operation = "SCALE"
    connect(nt, emit_color, glow.inputs[0])
    connect(nt, emit_strength, glow.inputs["Scale"])
    total = nt.nodes.new("ShaderNodeVectorMath")
    total.operation = "ADD"
    nt.links.new(lit.outputs[2], total.inputs[0])
    nt.links.new(glow.outputs["Vector"], total.inputs[1])

    shader = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(total.outputs["Vector"], shader.inputs["Color"])
    nt.links.new(shader.outputs[0], out.inputs["Surface"])  # the Principled BSDF stays in the tree, unplugged
    print(f"  {mat.name}: toon")
    return True


def outline_material(color):
    mat = bpy.data.materials.new("Outline")
    mat.use_nodes = True
    mat.use_backface_culling = True  # EEVEE / game engines: hide the shell's back faces
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    ink = nt.nodes.new("ShaderNodeEmission")
    ink.inputs["Color"].default_value = (*color, 1)
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")  # Cycles: back faces of the shell are see-through
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
    nt.links.new(ink.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def add_outline(obj, mat, thickness):
    slot = len(obj.data.materials)
    obj.data.materials.append(mat)
    mod = obj.modifiers.new("Outline", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 1.0              # grow outwards
    mod.use_flip_normals = True   # the "inverted" in inverted hull
    mod.use_rim = False
    mod.use_even_offset = False   # even offset can make spikes on decimated meshes
    mod.material_offset = slot    # the shell uses the outline material


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    objs = meshes(args.objects)
    mats = {s.material for o in objs for s in o.material_slots if s.material and s.material.use_nodes}
    done = sum(make_toon(m, args.light) for m in mats)
    print(f"toon shader on {done} material(s)")
    if args.outline > 0:
        ink = outline_material(hex_to_linear(args.outline_color))
        t = args.outline * height(objs)
        for o in objs:
            add_outline(o, ink, t)
        print(f"outline {t:.4f} on {len(objs)} object(s)")
    # 'Standard' keeps the flat toon colours as they are (AgX/Filmic would wash them out)
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"
    save(args.save)


main()
