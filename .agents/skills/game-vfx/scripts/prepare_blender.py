# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake reusable VFX field data and editable lightning paths using Blender.

Run with Blender --background --python THIS_FILE -- --output NEW_DIR --seed 17.
Output is authored noise/geometry, not a fluid simulation or learned inference.
"""

import argparse
import hashlib
import json
import math
import random
import sys
from array import array
from pathlib import Path

import bpy
from mathutils import Vector, noise


def periodic_noise(x, y, z, frequency):
    """Blend opposite noise domains for a continuous periodic field."""
    value = 0.0
    for dz in (0, 1):
        wz = z if dz else 1.0 - z
        for dy in (0, 1):
            wy = y if dy else 1.0 - y
            for dx in (0, 1):
                wx = x if dx else 1.0 - x
                p = Vector(((x - dx) * frequency, (y - dy) * frequency,
                            (z - dz) * frequency))
                value += wx * wy * wz * noise.noise(p, noise_basis='PERLIN_NEW')
    return max(0.0, min(1.0, 0.5 + value * 0.9))


def bake_noise(out):
    size, columns = 64, 8
    width = size * columns
    pixels = array('f', [0.0]) * (width * width * 4)
    for z in range(size):
        for y in range(size):
            for x in range(size):
                i = (((z // columns) * size + y) * width + (z % columns) * size + x) * 4
                p = (x / size, y / size, z / size)
                pixels[i] = periodic_noise(*p, 3.0)
                pixels[i + 1] = periodic_noise(*p, 8.0)
                pixels[i + 2] = periodic_noise(*p, 15.0)
                pixels[i + 3] = 1.0
    image = bpy.data.images.new('VFX_Periodic_Field_64', width=width, height=width, alpha=True)
    image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(pixels)
    image.filepath_raw = str(out / 'noise.png')
    image.file_format = 'PNG'
    image.save()
    image.pack()
    return image


def lightning_paths(seed):
    rng = random.Random(seed)
    main = []
    for i in range(37):
        t = i / 36
        taper = math.sin(math.pi * t)
        main.append([round((0.5 * math.sin(t * 17) + rng.uniform(-0.28, 0.28)) * taper, 5),
                     round(8.0 - 7.84 * t, 5),
                     round((0.32 * math.sin(t * 23 + 1) + rng.uniform(-0.24, 0.24)) * taper, 5)])
    paths, roles = [main], ['trunk']
    for i in range(11):
        origin = main[4 + i * 2]
        angle = i * 2.39996
        length = rng.uniform(1.2, 2.9)
        branch = [origin]
        for j in range(1, 13):
            t = j / 12
            branch.append([round(origin[0] + math.cos(angle) * length * t + rng.uniform(-0.18, 0.18), 5),
                           round(max(0.12, origin[1] - length * 1.3 * t + rng.uniform(-0.12, 0.12)), 5),
                           round(origin[2] + math.sin(angle) * length * t + rng.uniform(-0.18, 0.18), 5)])
        paths.append(branch)
        roles.append('branch')
    for i in range(9):
        angle = i * math.tau / 9
        branch = [[0.0, 0.10, 0.0]]
        for j in range(1, 13):
            t = j / 12
            angle += rng.uniform(-0.16, 0.16)
            branch.append([round(math.cos(angle) * 3.4 * t, 5),
                           round(0.08 + rng.random() * 0.1, 5),
                           round(math.sin(angle) * 3.4 * t, 5)])
        paths.append(branch)
        roles.append('ground')
    return paths, roles


def curve_object(index, points, role, material):
    curve = bpy.data.curves.new(f'Lightning_{role}_{index:02}', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = 0.028 if role == 'trunk' else 0.010
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for point, (x, y, z) in zip(spline.points, points, strict=True):
        point.co = (x, -z, y, 1.0)  # Y-up contract -> Blender Z-up.
    obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Use a new or empty output directory; existing outputs are preserved.')
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    noise.seed_set(args.seed)
    image = bake_noise(out)
    paths, roles = lightning_paths(args.seed)
    mat = bpy.data.materials.new('Lightning_Core')
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (0.32, 0.5, 1.0, 1.0)
    bsdf.inputs['Emission Color'].default_value = (0.25, 0.5, 1.0, 1.0)
    bsdf.inputs['Emission Strength'].default_value = 4.0
    for i, (points, role) in enumerate(zip(paths, roles, strict=True)):
        curve_object(i, points, role, mat)
    recipes = {
        'schema_version': 1, 'seed': args.seed, 'coordinates': 'Y-up, meters',
        'noise': {'file': 'noise.png', 'size': 64, 'columns': 8, 'rows': 8,
                  'channels': ['coarse', 'medium', 'fine', 'opaque'],
                  'color_space': 'linear-data', 'slice_order': 'z increasing, rows from image bottom',
                  'sampling': 'periodic XYZ; wrap texels inside each tile, interpolate adjacent Z slices'},
        'lightning': {'paths': paths, 'roles': roles},
        'fire': {'representation': 'authored spatial density field; not fluid simulation',
                 'height': 5.0, 'base_radius': 1.5},
        'ice': {'clip': 'ice_fall_break', 'source_duration': 6.0, 'impact': 2.0,
                'start_offset': 1 / 24, 'input': 'caller-supplied generated ice GLB'},
    }
    (out / 'recipes.json').write_text(json.dumps(recipes, indent=2), encoding='utf-8')
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene['vfx_recipe'] = 'Blender noise-field and lightning authoring source; web playback is separate.'
    scene['noise_image'] = image.name
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'source.blend'))
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.convert(target='MESH')
    bpy.ops.export_scene.gltf(filepath=str(out / 'recipe-geometry.glb'), export_format='GLB',
                             export_animations=False)
    outputs = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
               for name in ['noise.png', 'recipes.json', 'source.blend', 'recipe-geometry.glb']}
    provenance = {'backend': 'Blender authored noise and curves', 'blender': bpy.app.version_string,
                  'seed': args.seed, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'outputs': outputs, 'learned_inference': False, 'fluid_simulation': False,
                  'noise_samples': 64 ** 3, 'lightning_paths': len(paths)}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'noise_samples': 64 ** 3, 'paths': len(paths)}))


if __name__ == '__main__':
    main()
