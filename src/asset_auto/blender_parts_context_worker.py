"""Prepare GeoSAM2 views and split labelled source triangles; run inside Blender.

The inference mesh uses Blender world coordinates. Its face order is an explicit
contract, independent of glTF importer/exporter vertex reordering. Segmentation
never remeshes, fills cut surfaces, infers names, or modifies the source file.
"""

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

VIEW_AZIMUTHS = [180, 210, 240, 270, 300, 330, 0, 30, 60, 90, 120, 150]
VIEW_ELEVATIONS = [0, 25, 0, -25] * 3
SCHEMA = "asset-auto-geosam2-context-v1"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")


def load_static(source):
    if source.suffix.lower() != ".glb":
        raise ValueError("Local segmentation context requires an exact source GLB")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects = sorted((obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
                     key=lambda obj: obj.name)
    if not objects:
        raise ValueError("Source has no mesh objects")
    if any(obj.type == "ARMATURE" or obj.animation_data for obj in bpy.context.scene.objects):
        raise ValueError("Segmentation requires a static mesh without a rig or animation")
    if any(obj.data.shape_keys or obj.modifiers for obj in objects):
        raise ValueError("Segmentation requires static geometry without modifiers or morph targets")
    return objects


def canonical_mesh(objects):
    vertices, faces, object_indices, polygon_indices, loops, local_vertices = [], [], [], [], [], []
    metadata = []
    for object_index, obj in enumerate(objects):
        mesh = obj.data
        mesh.calc_loop_triangles()
        offset = len(vertices)
        face_start = len(faces)
        vertices.extend(list(obj.matrix_world @ vertex.co) for vertex in mesh.vertices)
        for triangle in mesh.loop_triangles:
            faces.append([offset + index for index in triangle.vertices])
            local_vertices.append(list(triangle.vertices))
            loops.append(list(triangle.loops))
            object_indices.append(object_index)
            polygon_indices.append(triangle.polygon_index)
        metadata.append({"name": obj.name, "vertices": len(mesh.vertices),
                         "face_start": face_start, "face_count": len(faces) - face_start,
                         "matrix_world": [list(row) for row in obj.matrix_world]})
    if not faces:
        raise ValueError("Source has no triangles")
    arrays = {
        "vertices": np.asarray(vertices, dtype=np.float64),
        "faces": np.asarray(faces, dtype=np.int64),
        "object_index": np.asarray(object_indices, dtype=np.int64),
        "polygon_index": np.asarray(polygon_indices, dtype=np.int64),
        "loop_indices": np.asarray(loops, dtype=np.int64),
        "local_vertex_indices": np.asarray(local_vertices, dtype=np.int64),
    }
    if not np.isfinite(arrays["vertices"]).all():
        raise ValueError("Source vertices must be finite")
    return arrays, metadata


def file_node(tree, output, prefix, file_format, *, raw=False):
    node = tree.nodes.new("CompositorNodeOutputFile")
    node.base_path = str(output)
    node.file_slots[0].path = prefix
    node.format.file_format = file_format
    node.format.color_mode = "RGBA"
    node.format.color_depth = "32" if file_format == "OPEN_EXR" else "8"
    if raw:
        node.format.color_management = "OVERRIDE"
        node.format.view_settings.view_transform = "Raw"
    return node


def configure_render(output, resolution, samples):
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = samples
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world = bpy.data.worlds.new("segmentation_context_world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.5, 1)
    for index, (location, energy) in enumerate([((2, -3, 4), 450), ((-3, -1, 2), 250), ((1, 3, 3), 600)]):
        data = bpy.data.lights.new(f"context_light_{index}", "AREA")
        data.energy, data.size = energy, 4
        light = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (-light.location).to_track_quat("-Z", "Y").to_euler()
    # GeoSAM2 conditions on geometry normals, independent of texture normal maps.
    # The original materials were saved before this temporary render-only edit.
    for material in bpy.data.materials:
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    for link in list(node.inputs["Normal"].links):
                        material.node_tree.links.remove(link)
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render = tree.nodes.new("CompositorNodeRLayers")
    composite = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(render.outputs["Image"], composite.inputs["Image"])
    bpy.context.view_layer.use_pass_z = True
    bpy.context.view_layer.use_pass_normal = True
    depth = file_node(tree, output, "depth_", "OPEN_EXR", raw=True)
    tree.links.new(render.outputs["Depth"], depth.inputs["Image"])
    separate = tree.nodes.new("CompositorNodeSeparateXYZ")
    combine = tree.nodes.new("CompositorNodeCombineXYZ")
    tree.links.new(render.outputs["Normal"], separate.inputs[0])
    for index in range(3):
        remap = tree.nodes.new("CompositorNodeMapRange")
        remap.inputs[1].default_value, remap.inputs[2].default_value = -1, 1
        remap.inputs[3].default_value, remap.inputs[4].default_value = 0, 1
        tree.links.new(separate.outputs[index], remap.inputs[0])
        tree.links.new(remap.outputs[0], combine.inputs[index])
    alpha = tree.nodes.new("CompositorNodeSetAlpha")
    alpha.mode = "REPLACE_ALPHA"
    tree.links.new(combine.outputs[0], alpha.inputs["Image"])
    tree.links.new(render.outputs["Alpha"], alpha.inputs["Alpha"])
    normal = file_node(tree, output, "normal_", "PNG", raw=True)
    tree.links.new(alpha.outputs[0], normal.inputs["Image"])
    return scene


def prepare(request):
    source = Path(request["source"]).resolve()
    output = Path(request["output"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "context.json").exists():
        raise ValueError("A completed context already exists; choose a new output directory")
    resolution = int(request.get("resolution", 1024))
    if not 64 <= resolution <= 2048 or request.get("views", 12) != 12:
        raise ValueError("GeoSAM2 context requires 12 views and resolution between 64 and 2048")
    source_hash = sha256(source)
    objects = load_static(source)
    arrays, objects_meta = canonical_mesh(objects)
    topology = output / "canonical.npz"
    np.savez_compressed(topology, **arrays)
    snapshot = output / "prepared.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(snapshot))
    low, high = arrays["vertices"].min(axis=0), arrays["vertices"].max(axis=0)
    extent = high - low
    if extent.max() < 1e-9:
        raise ValueError("Cannot render a zero-size mesh")
    scale = float(1 / extent.max())
    translation = -(low + high) * scale / 2
    normalization = Matrix.Translation(Vector(translation)) @ Matrix.Scale(scale, 4)
    worlds = {obj: obj.matrix_world.copy() for obj in objects}
    for obj in objects:
        obj.parent = None
        obj.matrix_world = normalization @ worlds[obj]
    scene = configure_render(output, resolution, int(request.get("samples", 32)))
    data = bpy.data.cameras.new("segmentation_context_camera")
    data.type, data.lens, data.sensor_width, data.sensor_fit = "PERSP", 50, 36, "HORIZONTAL"
    data.clip_start, data.clip_end = 0.001, 100
    camera = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    distance = 50 / 36 * float(np.linalg.norm(extent * scale))
    transforms, images = [], []
    for index, (azimuth, elevation) in enumerate(zip(VIEW_AZIMUTHS, VIEW_ELEVATIONS, strict=True)):
        azimuth, elevation = math.radians(azimuth), math.radians(elevation)
        camera.location = (distance * math.cos(elevation) * math.cos(azimuth),
                           distance * math.cos(elevation) * math.sin(azimuth),
                           distance * math.sin(elevation))
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.frame_set(index)
        bpy.context.view_layer.update()
        transforms.append([list(row) for row in camera.matrix_world])
        scene.render.filepath = str(output / f"color_{index:04d}.png")
        bpy.ops.render.render(write_still=True)
        images.append({"view": index, "color": f"color_{index:04d}.png",
                       "depth": f"depth_{index:04d}.exr", "normal": f"normal_{index:04d}.png"})
    metadata = {"camera_angle_x": 2 * math.atan(36 / 100), "camera_lens": 50,
                "sensor_width": 36, "env_texture": "null", "bbox_size": list(extent * scale),
                "scaling_factor": scale, "translation": list(translation),
                "normalization_formula": "normalized_vertices = vertices * scaling_factor + translation",
                "transforms": transforms, "resolution": resolution}
    write_json(output / "meta.json", metadata)
    if sha256(source) != source_hash:
        raise ValueError("Source changed while context was being prepared")
    files = [topology.name, snapshot.name, "meta.json"]
    files.extend(entry[key] for entry in images for key in ("color", "normal", "depth"))
    files = {name: {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size}
             for name in files}
    manifest = {"schema": SCHEMA, "source": str(source), "source_sha256": source_hash,
                "canonical": topology.name, "canonical_sha256": sha256(topology),
                "prepared": snapshot.name, "prepared_sha256": sha256(snapshot),
                "meta": "meta.json", "meta_sha256": sha256(output / "meta.json"),
                "coordinate_system": "Blender world Z-up meters",
                "vertices": len(arrays["vertices"]), "faces": len(arrays["faces"]),
                "objects": objects_meta, "views": images, "files": files,
                "blender_version": bpy.app.version_string}
    write_json(output / "context.json", manifest)
    return manifest


def copy_subset(obj, triangles, polygon_indices, loop_indices, name):
    source = obj.data
    used = sorted({int(vertex) for triangle in triangles for vertex in triangle})
    remap = {vertex: index for index, vertex in enumerate(used)}
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([source.vertices[index].co for index in used], [],
                     [[remap[int(index)] for index in triangle] for triangle in triangles])
    for material in source.materials:
        mesh.materials.append(material)
    for polygon, original in zip(mesh.polygons, polygon_indices, strict=True):
        polygon.material_index = source.polygons[int(original)].material_index
        polygon.use_smooth = source.polygons[int(original)].use_smooth
    flat_loops = [int(index) for indices in loop_indices for index in indices]
    for layer in source.uv_layers:
        target = mesh.uv_layers.new(name=layer.name)
        for index, original in enumerate(flat_loops):
            target.data[index].uv = layer.data[original].uv
    for attribute in source.color_attributes:
        if attribute.domain not in {"POINT", "CORNER"}:
            continue
        target = mesh.color_attributes.new(attribute.name, attribute.data_type, attribute.domain)
        mapping = used if attribute.domain == "POINT" else flat_loops
        for index, original in enumerate(mapping):
            target.data[index].color = attribute.data[original].color
    mesh.update()
    mesh.normals_split_custom_set([source.corner_normals[index].vector for index in flat_loops])
    part = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(part)
    part.matrix_world = obj.matrix_world.copy()
    part["asset_part"] = name
    part["segmentation_source_object"] = obj.name
    return part


def segment(request):
    context = Path(request["context"]).resolve()
    output = Path(request["output"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((context / "context.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Unsupported segmentation context schema")
    if (output / "generated.glb").resolve() == Path(manifest["source"]).resolve():
        raise ValueError("Segmentation output must not overwrite its source GLB")
    for filename, expected in manifest["files"].items():
        path = context / filename
        if path.parent != context or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            raise ValueError(f"Segmentation context file changed: {filename}")
    for path, expected in [(Path(manifest["source"]), manifest["source_sha256"]),
                           (context / manifest["canonical"], manifest["canonical_sha256"]),
                           (context / manifest["prepared"], manifest["prepared_sha256"])]:
        if sha256(path) != expected:
            raise ValueError(f"Segmentation context provenance mismatch: {path.name}")
    labels_path = Path(request["face_labels"]).resolve()
    labels = np.load(labels_path, allow_pickle=False)
    if labels.shape != (manifest["faces"],) or labels.dtype.kind not in "iu":
        raise ValueError("Face labels must be one integer per canonical triangle")
    if labels.dtype.kind == "u" and labels.max() > np.iinfo(np.int64).max:
        raise ValueError("Face label exceeds the supported integer range")
    labels = labels.astype(np.int64)
    if labels.min() < -1:
        raise ValueError("Face labels below -1 are unsupported")
    labels[labels <= 0] = 0
    names = {int(key): value for key, value in request.get("names", {}).items()}
    if any(index <= 0 or not isinstance(name, str) or
           not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", name) for index, name in names.items()):
        raise ValueError("Names must map positive observed labels to safe part identifiers")
    observed = sorted(int(value) for value in np.unique(labels))
    if set(names) - set(observed):
        raise ValueError("Names include labels that were not observed on any source triangle")
    names = {label: names.get(label, f"part_{label}") if label else "unclassified" for label in observed}
    if len(set(names.values())) != len(names):
        raise ValueError("Part names must be unique")
    arrays = np.load(context / manifest["canonical"], allow_pickle=False)
    bpy.ops.wm.open_mainfile(filepath=str(context / manifest["prepared"]), load_ui=False)
    objects = [bpy.data.objects[entry["name"]] for entry in manifest["objects"]]
    current, _ = canonical_mesh(objects)
    if any(not np.array_equal(current[key], arrays[key]) for key in current):
        raise ValueError("Prepared source topology no longer matches the inference mesh")
    originals = set(bpy.context.scene.objects)
    parts, used_names = [], set()
    for label in observed:
        matching_objects = [index for index in range(len(objects))
                            if np.any((labels == label) & (arrays["object_index"] == index))]
        for object_index in matching_objects:
            select = (labels == label) & (arrays["object_index"] == object_index)
            name = names[label]
            if len(matching_objects) > 1:
                name = f"{name[:52]}_source{object_index}"
            if name in used_names:
                raise ValueError("Part names collide after preserving source object boundaries")
            used_names.add(name)
            part = copy_subset(objects[object_index], arrays["local_vertex_indices"][select],
                               arrays["polygon_index"][select], arrays["loop_indices"][select], name)
            parts.append({"name": name, "label": label, "faces": int(np.count_nonzero(select)),
                          "source_object": objects[object_index].name, "object": part})
    for obj in originals:
        bpy.data.objects.remove(obj, do_unlink=True)
    # Original names can match requested semantic names; assign again after removal.
    for index, part in enumerate(parts):
        part["object"].name = f"__segmentation_name_pending_{index}"
    for part in parts:
        part["object"].name = part["name"]
        if part["object"].name != part["name"]:
            raise ValueError("Blender could not assign the exact requested part name")
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part["object"].select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "generated.blend"))
    bpy.ops.export_scene.gltf(filepath=str(output / "generated.glb"), export_format="GLB",
                             use_selection=True, export_animations=False, export_extras=True)
    report = {"schema": SCHEMA, "source_sha256": manifest["source_sha256"],
              "canonical_sha256": manifest["canonical_sha256"], "face_labels_sha256": sha256(labels_path),
              "source_faces": manifest["faces"], "output_faces": sum(part["faces"] for part in parts),
              "parts": [{key: value for key, value in part.items() if key != "object"} for part in parts],
              "unclassified_faces": int(np.count_nonzero(labels == 0)),
              "geometry_changed": False, "cut_surfaces_filled": False, "semantic_review": "pending"}
    write_json(output / "segment-report.json", report)
    return report


def main():
    request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    if request["action"] == "prepare":
        result = prepare(request)
    elif request["action"] == "segment":
        result = segment(request)
    else:
        raise ValueError("Expected prepare or segment action")
    print(json.dumps({"action": request["action"], "faces": result.get("faces", result.get("output_faces"))}))


if __name__ == "__main__":
    main()
