"""Real Blender context/split regression; authored fixtures, no models or paid API."""

import json
import math
import runpy
import sys
import uuid
from pathlib import Path


def triangle_snapshot():
    import bpy

    triangles = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for tri in mesh.loop_triangles:
            corners = []
            for vertex, loop in zip(tri.vertices, tri.loops, strict=True):
                point = obj.matrix_world @ mesh.vertices[vertex].co
                normal = (normal_matrix @ mesh.corner_normals[loop].vector).normalized()
                uv = mesh.uv_layers.active.data[loop].uv
                corners.append(tuple(round(value, 5) for value in (*point, *normal, *uv)))
            mat = mesh.materials[mesh.polygons[tri.polygon_index].material_index]
            color = mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value
            triangles.append((tuple(sorted(corners)), tuple(round(value, 5) for value in color)))
    return sorted(triangles)


def blender_smoke(sandbox):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    worker = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                               "src/asset_auto/blender_parts_context_worker.py"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Deliberately non-unit scale, transformed parenting, two materials and UVs.
    parent = bpy.data.objects.new("fixture_parent", None)
    bpy.context.scene.collection.objects.link(parent)
    parent.location = (3, -2, 1)
    parent.rotation_euler.z = 0.3
    for index in range(2):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(index * 0.8, 0, 0.7))
        obj = bpy.context.object
        obj.name = f"fixture_{index}"
        obj.parent = parent
        obj.scale = (0.4, 0.5, 0.6)
        obj.rotation_euler.y = index * 0.17
        for slot in range(2):
            material = bpy.data.materials.new(f"material_{index}_{slot}")
            material.use_nodes = True
            material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
                0.6 if slot else 0.05, 0.1 + 0.5 * index, 0.2, 1)
            obj.data.materials.append(material)
        for face in obj.data.polygons:
            face.material_index = face.index % 2
    source = sandbox / "fixture.glb"
    bpy.ops.export_scene.gltf(filepath=str(source), export_format="GLB", export_animations=False)
    source_hash = worker["sha256"](source)
    context = sandbox / "context"
    manifest = worker["prepare"]({"source": str(source), "output": str(context),
                                  "resolution": 128, "samples": 8})
    assert manifest["faces"] == 24 and len(manifest["views"]) == 12
    metadata = json.loads((context / "meta.json").read_text(encoding="utf-8"))
    arrays = np.load(context / "canonical.npz", allow_pickle=False)
    normalized = arrays["vertices"] * metadata["scaling_factor"] + metadata["translation"]
    assert np.allclose(normalized.min(axis=0) + normalized.max(axis=0), 0)
    assert abs(np.ptp(normalized, axis=0).max() - 1) < 1e-7
    for index, entry in enumerate(manifest["views"]):
        for field in ("color", "normal", "depth"):
            image = bpy.data.images.load(str(context / entry[field]), check_existing=False)
            image.colorspace_settings.name = "Non-Color"
            pixels = np.asarray(image.pixels[:], dtype=float).reshape(128, 128, 4)
            assert tuple(image.size) == (128, 128)
            if field == "normal":
                foreground = pixels[..., 3] > 0.99
                assert foreground.sum() > 300
                lengths = np.linalg.norm(pixels[foreground, :3] * 2 - 1, axis=1)
                assert 0.97 < np.median(lengths) < 1.03
            elif field == "depth":
                valid = pixels[..., 0] < 100
                assert valid.sum() > 300 and pixels[valid, 0].min() > 0
            bpy.data.images.remove(image)
        camera = Matrix(metadata["transforms"][index])
        direction = camera.to_3x3() @ Vector((0, 0, -1))
        assert direction.dot(-camera.translation.normalized()) > 0.99999
    # EEVEE's depth must be forward camera-Z, rather than ray length. This
    # distinction otherwise silently moves GeoSAM2 back-projected surface points.
    camera = Matrix(metadata["transforms"][0])
    origin, rotation = camera.translation, camera.to_3x3()
    depth_image = bpy.data.images.load(str(context / "depth_0000.exr"), check_existing=False)
    pixels = np.asarray(depth_image.pixels[:]).reshape(128, 128, 4)
    hits = 0
    for x, y in [(65, 40), (70, 60), (100, 70), (80, 80)]:
        tangent = math.tan(metadata["camera_angle_x"] / 2)
        ray = Vector((((x + 0.5) / 128 - 0.5) * 2 * tangent,
                      ((y + 0.5) / 128 - 0.5) * 2 * tangent, -1))
        hit, location, *_ = bpy.context.scene.ray_cast(
            bpy.context.evaluated_depsgraph_get(), origin, rotation @ ray.normalized())
        if hit:
            camera_depth = -(rotation.inverted() @ (location - origin)).z
            assert abs(pixels[y, x, 0] - camera_depth) < 0.002
            hits += 1
    assert hits >= 3
    bpy.data.images.remove(depth_image)
    bpy.ops.wm.open_mainfile(filepath=str(context / "prepared.blend"), load_ui=False)
    original_triangles = triangle_snapshot()
    # First label crosses both source objects; unlabeled triangles remain present.
    labels = np.where(np.arange(manifest["faces"]) % 3 == 0, 1, 2).astype(np.int64)
    labels[0] = -1
    labels_path = sandbox / "labels.npy"
    np.save(labels_path, labels)
    result = worker["segment"]({"context": str(context), "output": str(sandbox / "split"),
                                "face_labels": str(labels_path), "names": {"1": "observed_one",
                                                                          "2": "observed_two"}})
    assert result["source_faces"] == result["output_faces"] == 24
    assert result["unclassified_faces"] == 1
    assert triangle_snapshot() == original_triangles, "Source geometry/UV/material/normal changed"
    # Check the delivered GLB, allowing unavoidable float32 roundtrip rounding.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(sandbox / "split/generated.glb"))
    delivered = triangle_snapshot()
    assert len(delivered) == len(original_triangles)
    for actual, expected in zip(delivered, original_triangles, strict=True):
        assert np.allclose(actual[0], expected[0], atol=3e-5)
        assert np.allclose(actual[1], expected[1], atol=1e-5)
    base_request = {"context": str(context), "output": str(sandbox / "rejected"),
                    "face_labels": str(labels_path)}
    for bad_labels, names, message in [
        (labels[:2], {}, "one integer per"),
        (labels.astype(float), {}, "one integer per"),
        (labels, {"3": "unobserved"}, "not observed"),
        (labels, {"1": "same", "2": "same"}, "unique"),
        (labels, {"1": "../unsafe"}, "safe part"),
    ]:
        np.save(labels_path, bad_labels)
        try:
            worker["segment"](base_request | {"names": names})
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("Invalid segmentation input was accepted")
    np.save(labels_path, labels)
    image_path = context / manifest["views"][0]["color"]
    image_bytes = image_path.read_bytes()
    image_path.write_bytes(image_bytes + b"tampered")
    try:
        worker["segment"](base_request)
    except ValueError as error:
        assert "context file changed" in str(error)
    else:
        raise AssertionError("Changed prompt image was accepted")
    finally:
        image_path.write_bytes(image_bytes)
    # Importing a skinned GLB must not flatten a rig into a static context.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    mesh = bpy.context.object
    bpy.ops.object.armature_add()
    rig = bpy.context.object
    modifier = mesh.modifiers.new("rig", "ARMATURE")
    modifier.object = rig
    mesh.vertex_groups.new(name=rig.data.bones[0].name).add(list(range(8)), 1, "REPLACE")
    rigged = sandbox / "rigged.glb"
    bpy.ops.export_scene.gltf(filepath=str(rigged), export_format="GLB")
    try:
        worker["prepare"]({"source": str(rigged), "output": str(sandbox / "rejected-rig")})
    except ValueError as error:
        assert "static mesh" in str(error)
    else:
        raise AssertionError("A rigged input entered the static segmentation context")
    assert worker["sha256"](source) == source_hash
    (sandbox / "result.json").write_text(json.dumps({
        "passed": True, "sandbox": str(sandbox), "blender_version": bpy.app.version_string,
        "checks": ["12 official camera poses", "normal alpha and unit vectors", "camera-Z depth projection",
                   "non-unit source normalization", "all source triangles retained",
                   "world geometry, UV, normals and material preservation",
                   "delivered GLB preservation", "unknown faces retained",
                   "invalid labels/names rejected", "changed prompt images rejected",
                   "rigged inputs rejected", "source unchanged"],
    }, indent=2), encoding="utf-8")


def main():
    from asset_auto.pipeline import blender, run_logged
    from asset_auto.settings import executable

    root = Path(__file__).resolve().parents[1]
    sandbox = root / ".work" / f"smoke-local-parts-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    command = [executable(root, "blender"), "--background", "--factory-startup", "--disable-autoexec",
               "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--"]
    run_logged(command + [str(sandbox)], sandbox / "smoke.log", cwd=root)
    delivered = sandbox / "pipeline-delivery"
    delivered.mkdir()
    # A low budget is intentional: the delivery stage must report the excess,
    # while preserving all source triangles and the translated placement.
    blender(root, {"operation": "import", "source": str(sandbox / "split/generated.blend"),
                   "output": str(delivered), "part_previews": True, "preserve_geometry": True,
                   "triangle_budget": 12}, delivered)
    report = json.loads((delivered / "inspection.json").read_text(encoding="utf-8"))
    assert report["triangles"] == 24 and not report["passed"]
    assert report["triangle_budget"] == 12
    assert "preserved" in report["geometry_processing"]
    previews = json.loads((delivered / "part-previews.json").read_text(encoding="utf-8"))
    assert previews["total"] == 5 and not previews["truncated"]
    assert all((delivered / part["image"]).is_file() for part in previews["parts"])
    run_logged(command + [str(sandbox), "verify-delivery"], sandbox / "delivery-verify.log", cwd=root)
    print((sandbox / "result.json").read_text(encoding="utf-8"))


def verify_delivery(sandbox):
    import bpy
    import numpy as np

    bpy.ops.wm.open_mainfile(filepath=str(sandbox / "context/prepared.blend"), load_ui=False)
    original = triangle_snapshot()
    bpy.ops.wm.open_mainfile(filepath=str(sandbox / "pipeline-delivery/source.blend"), load_ui=False)
    assert triangle_snapshot() == original, "Delivery changed world positions, UVs, materials or normals"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(sandbox / "pipeline-delivery/asset.glb"))
    delivered = triangle_snapshot()
    assert len(delivered) == len(original) == 24
    for actual, expected in zip(delivered, original, strict=True):
        assert np.allclose(actual[0], expected[0], atol=3e-5)
        assert np.allclose(actual[1], expected[1], atol=1e-5)
    report_path = sandbox / "result.json"
    result = json.loads(report_path.read_text(encoding="utf-8"))
    result["checks"].extend(["final pipeline preserves translated placement, UVs, materials and normals",
                             "final pipeline retains all triangles despite an exceeded budget",
                             "final delivered GLB preservation", "final per-part previews"])
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if "--" in sys.argv:
        arguments = sys.argv[sys.argv.index("--") + 1:]
        operation = verify_delivery if arguments[1:] == ["verify-delivery"] else blender_smoke
        operation(Path(arguments[0]))
    else:
        main()
