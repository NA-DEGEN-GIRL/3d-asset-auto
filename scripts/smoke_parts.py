"""Real Blender part-preview/rename test using isolated, authored maintenance fixtures."""

import hashlib
import json
import runpy
import struct
import sys
import uuid
from pathlib import Path


def scene_snapshot():
    import bpy

    result = {}
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        result[obj.name] = {
            "vertices": [list(vertex.co) for vertex in obj.data.vertices],
            "world_vertices": [list(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices],
            "matrix": [list(row) for row in obj.matrix_world],
            "polygons": [list(polygon.vertices) for polygon in obj.data.polygons],
            "uv": [[list(point.uv) for point in layer.data] for layer in obj.data.uv_layers],
            "materials": [{"name": mat.name, "color": list(mat.diffuse_color),
                           "base_color": list(mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value)}
                          for mat in obj.data.materials],
            "asset_part": obj.get("asset_part"),
        }
    return result


def fixtures(sandbox):
    import bpy

    worker = runpy.run_path(str(Path(__file__).resolve().parents[1] / "src/asset_auto/blender_worker.py"))
    for count in (2, 3):
        worker["create"]({
            "materials": {
                "red": {"color": [.7, .05, .03, 1], "metallic": 0, "roughness": .5},
                "blue": {"color": [.02, .1, .7, 1], "metallic": .3, "roughness": .4},
            },
            "parts": [{"name": f"piece{chr(65 + index)}", "primitive": "box", "segments": 8,
                       "dimensions": [.3, .2, .8 - index * .15], "location": [index * .5, 0, .6],
                       "rotation_degrees": [0, 0, index * 15], "material": "blue" if index else "red",
                       "bevel": 0} for index in range(count)],
        })
        # Non-unit scale catches accidental transform baking during rename-only operations.
        bpy.data.objects["pieceA"].scale = (1.3, .8, 1.1)
        bpy.context.view_layer.update()
        source = sandbox / f"fixture-{count}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(source))
        (sandbox / f"fixture-{count}.json").write_text(json.dumps(scene_snapshot()), encoding="utf-8")


def verify(sandbox):
    import bpy

    for count in (2, 3):
        before = json.loads((sandbox / f"fixture-{count}.json").read_text(encoding="utf-8"))
        bpy.ops.wm.open_mainfile(filepath=str(sandbox / f"renamed-{count}" / "source.blend"), load_ui=False)
        after = scene_snapshot()
        mapping = {"pieceA": "handle"}
        if count == 3:
            mapping.update(pieceB="pieceC", pieceC="pieceB")
        assert set(after) == {mapping.get(name, name) for name in before}
        for name, original in before.items():
            renamed = mapping.get(name, name)
            expected = original | {"asset_part": renamed}
            assert after[renamed] == expected, f"Geometry, transform, UV or material changed for {name}"
    (sandbox / "verified.json").write_text(json.dumps({"passed": True}), encoding="utf-8")


def glb_mesh_names(path):
    with path.open("rb") as stream:
        magic, version, length = struct.unpack("<4sII", stream.read(12))
        assert magic == b"glTF" and version == 2 and length == path.stat().st_size
        size, kind = struct.unpack("<I4s", stream.read(8))
        assert kind == b"JSON"
        document = json.loads(stream.read(size))
    return {node["name"] for node in document["nodes"] if "mesh" in node}


def main():
    from asset_auto.pipeline import blender, run_logged
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    repository = Path(__file__).resolve().parents[1]
    sandbox = repository / ".work" / f"smoke-parts-{uuid.uuid4().hex[:8]}"
    sandbox.mkdir(parents=True)
    command = [executable(repository, "blender"), "--background", "--factory-startup",
               "--disable-autoexec", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--"]
    run_logged(command + ["fixtures", str(sandbox)], sandbox / "fixtures.log", cwd=repository)
    hashes = {count: hashlib.sha256((sandbox / f"fixture-{count}.blend").read_bytes()).hexdigest()
              for count in (2, 3)}
    for count in (2, 3):
        out = sandbox / f"renamed-{count}"
        out.mkdir()
        changes = [{"part": "pieceA", "rename": "handle"}]
        if count == 3:
            changes.extend([{"part": "pieceB", "rename": "pieceC"}, {"part": "pieceC", "rename": "pieceB"}])
        blender(repository, {"operation": "edit", "source": str(sandbox / f"fixture-{count}.blend"),
                             "output": str(out), "triangle_budget": 12000, "changes": changes,
                             "part_previews": True}, out)
        report = read_json(out / "inspection.json")
        expected = {"handle", "pieceB"} if count == 2 else {"handle", "pieceB", "pieceC"}
        assert report["passed"] and {part["name"] for part in report["parts"]} == expected
        assert glb_mesh_names(out / "asset.glb") == expected
        previews = read_json(out / "part-previews.json")
        assert previews["total"] == count and not previews["truncated"]
        assert {part["name"] for part in previews["parts"]} == expected
        for index, part in enumerate(previews["parts"]):
            assert part["image"] == f"part-{index:03d}.png"
            data = (out / part["image"]).read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (384, 384)
    run_logged(command + ["verify", str(sandbox)], sandbox / "verify.log", cwd=repository)
    assert read_json(sandbox / "verified.json")["passed"]
    invalid = [
        ([{"part": "pieceA", "rename": "pieceB"}], "Part rename collision"),
        ([{"part": "pieceA", "rename": "handle"}, {"part": "pieceB", "rename": "handle"}],
         "Part rename collision"),
        ([{"part": "pieceA", "rename": "handle"}, {"part": "pieceA", "rename": "grip"}], "Repeated rename"),
    ]
    for index, (changes, message) in enumerate(invalid):
        out = sandbox / f"rejected-{index}"
        out.mkdir()
        try:
            blender(repository, {"operation": "edit", "source": str(sandbox / "fixture-3.blend"),
                                 "output": str(out), "triangle_budget": 12000, "changes": changes}, out)
        except RuntimeError as error:
            assert message in str(error)
        else:
            raise AssertionError("Ambiguous part names were accepted")
        assert not (out / "source.blend").exists() and not (out / "asset.glb").exists()
    for count, digest in hashes.items():
        assert hashlib.sha256((sandbox / f"fixture-{count}.blend").read_bytes()).hexdigest() == digest
    result = {"passed": True, "checks": ["two- and three-part isolated previews", "exact GLB object names",
              "rename-only geometry, UV, transform and material preservation", "simultaneous name swaps",
              "existing-name and duplicate-target collisions rejected", "repeated rename rejected",
              "parent source hashes unchanged"], "sandbox": str(sandbox)}
    write_json(sandbox / "result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--" in sys.argv:
        operation, directory = sys.argv[sys.argv.index("--") + 1:]
        {"fixtures": fixtures, "verify": verify}[operation](Path(directory))
    else:
        main()
