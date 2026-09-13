"""Verify merged clips against their original Blender-deformed source meshes.

Default: isolated authored maintenance fixture, no models/API/GPU inference.
Optional existing assets: --base BASE.glb --source WALK.glb --source RUN.glb.
"""

import argparse
import hashlib
import json
import struct
import sys
import uuid
from pathlib import Path


def document(path):
    raw = Path(path).read_bytes()
    length, kind = struct.unpack_from("<I4s", raw, 12)
    assert kind == b"JSON"
    return json.loads(raw[20:20 + length])


def fixture(out):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "scripts"))
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    import blender_character_worker as character
    from smoke_character import make_fixture

    make_fixture(out)
    character.load_character(out / "fixture.blend")
    character.select_preview_clip(None)
    bpy.context.scene.frame_set(0)
    character.export_character(out / "fixture.glb")


def split_fixture(path, out):
    raw = path.read_bytes()
    size = struct.unpack_from("<I", raw, 12)[0]
    doc = document(path)
    assert len(doc["animations"]) == 2
    outputs = []
    for index, animation in enumerate(list(doc["animations"])):
        doc["animations"] = [animation]
        encoded = json.dumps(doc, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        body = struct.pack("<I4s", len(encoded), b"JSON") + encoded + raw[20 + size:]
        output = out / f"fixture-clip-{index}.glb"
        output.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
        outputs.append(output)
    return outputs


def verify(request_path):
    import bpy

    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src" / "asset_auto"))
    import blender_character_worker as character

    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    merged = request["merged"]

    def points(source, clip_name, duration):
        character.load_character(source)
        rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        assert rigs, "Fixture must retain its armature"
        rest_bones = {(rig.name, bone.name) for rig in rigs for bone in rig.data.bones}
        assert character.select_preview_clip(clip_name)
        snapshots = []
        for fraction in (0, .2, .4, .6, .8, 1):
            character.frame_at(duration * fraction)
            dependency_graph = bpy.context.evaluated_depsgraph_get()
            snapshot = {}
            for index, obj in enumerate(sorted(character.meshes(), key=lambda item: item.data.name)):
                evaluated = obj.evaluated_get(dependency_graph)
                mesh = evaluated.to_mesh()
                snapshot[index] = [tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices]
                evaluated.to_mesh_clear()
            snapshots.append(snapshot)
        return snapshots, rest_bones

    clips = []
    for clip in request["clips"]:
        expected, original_bones = points(clip["source"], clip["name"], clip["duration_seconds"])
        actual, actual_bones = points(merged, clip["name"], clip["duration_seconds"])
        assert original_bones == actual_bones
        maximum = 0.0
        for left, right in zip(expected, actual, strict=True):
            assert left.keys() == right.keys()
            for name in left:
                assert len(left[name]) == len(right[name])
                for first, second in zip(left[name], right[name], strict=True):
                    maximum = max(maximum, max(abs(a - b) for a, b in zip(first, second, strict=True)))
        assert maximum < 2e-5, f"Merged {clip['name']} changes actual mesh deformation: {maximum}"
        clips.append({"name": clip["name"], "sampled_frames": 6,
                      "maximum_source_deformation_difference_m": maximum,
                      "bones": len(actual_bones)})
    character.load_character(merged)
    character.select_preview_clip(None)
    summary = character.rigging_summary()
    assert summary["weighted_vertices"] > 0
    assert not any(mesh["unweighted_vertices"] for mesh in summary["meshes"])
    if request.get("render"):
        out = Path(request_path).parent / "renders"
        out.mkdir()
        character.render_views(out)
        character.animation_previews(out, character.animation_summary(document(merged)))
    result = {"passed": True, "clips": clips, "weighted_vertices": summary["weighted_vertices"],
              "source_deformation_equivalent": True}
    Path(request_path).with_name("blender-validation.json").write_text(json.dumps(result, indent=2),
                                                                     encoding="utf-8")


def main():
    from asset_auto.animation_merge import merge
    from asset_auto.pipeline import run_logged
    from asset_auto.settings import executable

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--render", action="store_true", help="Also save local visual review images")
    args = parser.parse_args()
    if bool(args.base) != bool(args.source):
        parser.error("Use --base together with at least one --source")
    repository = Path(__file__).resolve().parents[1]
    out = repository / ".work" / f"smoke-animation-merge-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    command = [executable(repository, "blender"), "--background", "--factory-startup", "--disable-autoexec",
               "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--"]
    if args.base:
        inputs = [args.base.resolve(), *(source.resolve() for source in args.source)]
    else:
        run_logged([*command, "fixture", str(out)], out / "fixture.log", cwd=repository)
        inputs = split_fixture(out / "fixture.glb", out)
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    merged = out / "merged.glb"
    report = merge(inputs[0], [{"path": str(path)} for path in inputs[1:]], merged)
    originals = {animation["name"]: str(path) for path in inputs for animation in document(path)["animations"]}
    request = {"merged": str(merged), "render": args.render,
               "clips": [{**clip, "source": originals[clip["name"]]} for clip in report["clips"]]}
    request_path = out / "verify-request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    run_logged([*command, "verify", str(request_path)], out / "blender.log", cwd=repository)
    assert hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    original, destination = document(inputs[0]), document(merged)
    for key in ("nodes", "meshes", "skins", "materials", "textures", "images"):
        assert original.get(key) == destination.get(key), f"Merge modified base {key}"
    result = {"passed": True, "sandbox": str(out), "merge": report,
              "blender": json.loads((out / "blender-validation.json").read_text(encoding="utf-8")),
              "source_hashes_unchanged": hashes, "api_calls": 0}
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--" in sys.argv:
        operation, argument = sys.argv[sys.argv.index("--") + 1:]
        if operation == "fixture":
            fixture(Path(argument))
        elif operation == "verify":
            verify(argument)
        else:
            raise ValueError(f"Unknown smoke operation: {operation}")
    else:
        main()
