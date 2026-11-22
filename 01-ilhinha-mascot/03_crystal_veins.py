"""Step 3: turn painted crystal veins into glowing, pulsing ones.

On the generated model the veins were only a cyan colour in the texture. This script finds that colour in the
base-colour texture with a hue/saturation/brightness window and plugs the result into the material's emission,
scaled by a "VeinPulse" value that is keyframed as a smooth loop (a heartbeat for the crystal).

No baking, no painting: it works on any material that has an Image Texture feeding the Principled BSDF Base Color.
Pick the colour of YOUR veins with --hue (0..1: 0 red, 0.17 yellow, 0.33 green, 0.5 cyan, 0.67 blue, 0.83 magenta).

Usage:
  blender -b step2.blend --python 03_crystal_veins.py -- --hue 0.40 0.58 --color 3FF5E8 --save step3.blend
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import hex_to_linear, meshes, parse_args, save  # noqa: E402


def options(p):
    p.add_argument("--hue", type=float, nargs=2, default=[0.40, 0.58], help="hue window of the veins (0..1)")
    p.add_argument("--min-sat", type=float, default=0.40, help="minimum saturation of the veins")
    p.add_argument("--min-val", type=float, default=0.55, help="minimum brightness of the veins")
    p.add_argument("--color", default="3FF5E8", help="glow colour, hex")
    p.add_argument("--strength", type=float, default=3.0, help="emission strength at the top of the pulse")
    p.add_argument("--low", type=float, default=0.08, help="pulse value at the bottom of the cycle (0..1)")
    p.add_argument("--period", type=int, default=48, help="frames per pulse (24 fps: 48 = 2 s)")


def find_image(socket, seen=None):
    """Walk the links upstream from a socket until an Image Texture node is found."""
    seen = seen or set()
    for link in socket.links:
        n = link.from_node
        if n.name in seen:
            continue
        seen.add(n.name)
        if n.type == "TEX_IMAGE" and n.image:
            return n
        for s in n.inputs:
            found = find_image(s, seen)
            if found:
                return found
    return None


def step(nt, value, a, b):
    """0 below a, 1 above b (or the reverse if a > b), linear in between."""
    m = nt.nodes.new("ShaderNodeMapRange")
    m.clamp = True
    nt.links.new(value, m.inputs["Value"])
    m.inputs["From Min"].default_value = a
    m.inputs["From Max"].default_value = b
    return m.outputs["Result"]


def multiply(nt, *values):
    out = values[0]
    for v in values[1:]:
        m = nt.nodes.new("ShaderNodeMath")
        m.operation = "MULTIPLY"
        nt.links.new(out, m.inputs[0])
        if isinstance(v, (int, float)):
            m.inputs[1].default_value = v
        else:
            nt.links.new(v, m.inputs[1])
        out = m.outputs[0]
    return out


def add_veins(mat, args, color):
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        print(f"  {mat.name}: no Principled BSDF, skipped")
        return False
    tex = find_image(bsdf.inputs["Base Color"])
    if tex is None:
        print(f"  {mat.name}: no image texture on Base Color, skipped")
        return False

    # Blender works in linear colour; the hue/sat/value thresholds are easier to pick in sRGB, like an image editor.
    to_srgb = nt.nodes.new("ShaderNodeGamma")
    to_srgb.inputs["Gamma"].default_value = 1 / 2.2
    nt.links.new(tex.outputs["Color"], to_srgb.inputs["Color"])
    hsv = nt.nodes.new("ShaderNodeSeparateColor")
    hsv.mode = "HSV"
    nt.links.new(to_srgb.outputs[0], hsv.inputs[0])
    h, s, v = hsv.outputs
    soft = 0.03
    in_hue = multiply(nt, step(nt, h, args.hue[0] - soft, args.hue[0] + soft),
                      step(nt, h, args.hue[1] + soft, args.hue[1] - soft))
    mask = multiply(nt, in_hue, step(nt, s, args.min_sat, args.min_sat + 0.18),
                    step(nt, v, args.min_val, args.min_val + 0.17))

    pulse = nt.nodes.new("ShaderNodeValue")
    pulse.name = pulse.label = "VeinPulse"
    strength = multiply(nt, mask, pulse.outputs[0], args.strength)

    bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    nt.links.new(strength, bsdf.inputs["Emission Strength"])

    # pulse: low -> 1 -> low, smooth (sine) and repeated forever with a Cycles modifier
    sock = pulse.outputs[0]
    half = args.period / 2
    for frame, value in [(1, args.low), (1 + half, 1.0), (1 + args.period, args.low)]:
        sock.default_value = value
        sock.keyframe_insert("default_value", frame=frame)
    path = f'nodes["{pulse.name}"].outputs[0].default_value'
    fc = next(f for f in nt.animation_data.action.fcurves if f.data_path == path)
    for k in fc.keyframe_points:
        k.interpolation = "SINE"
        k.easing = "EASE_IN_OUT"
    fc.modifiers.new("CYCLES")
    print(f"  {mat.name}: veins from image {tex.image.name!r}")
    return True


def main():
    args = parse_args(__doc__.splitlines()[0], options)
    color = hex_to_linear(args.color)
    mats = {s.material for o in meshes(args.objects) for s in o.material_slots if s.material}
    done = sum(add_veins(m, args, color) for m in mats if m.use_nodes)
    if not done:
        raise SystemExit("no material with an image texture on Base Color: nothing to do")
    print(f"glowing veins added to {done} material(s); pulse every {args.period} frames")
    save(args.save)


main()
