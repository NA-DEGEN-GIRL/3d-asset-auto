"""Real Blender assessment of rigid/morph motion and usage propagation. No inference/API."""

import hashlib
import json
import math
import sys
import uuid
from pathlib import Path


def fixture(out):
    import bpy

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "asset_auto"))
    import blender_character_worker as character
    from blender_authoring_tools import AuthoringContext
    from io_scene_gltf2.blender.com.gltf2_blender_ui import anim_ui_register

    anim_ui_register()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, .5))
    obj = bpy.context.object
    obj.name = "panel"
    obj.rotation_mode = "XYZ"
    bpy.context.scene.render.fps = 30
    obj.shape_key_add(name="Basis")
    shape = obj.shape_key_add(name="compress")
    for vertex in shape.data:
        vertex.co.z *= .5
    character.capture_preview_defaults()
    context = AuthoringContext(out / "fixture.blend", out, {})
    for name in ("oscillate", "translate", "hold", "stalled"):
        context.new_action(obj, name)
        for frame in range(31):
            t = frame / 30
            obj.location.x = 2*t if name == "translate" else 0
            obj.rotation_euler.z = (math.sin(t * 2*math.pi) if name == "oscillate" else
                                    min(t*4, 1) if name == "hold" else
                                    min(t*5, 1, (1-t)*5) if name == "stalled" else 0)
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        context.stash_action(obj)
    context.new_action(obj.data.shape_keys, "compress")
    for frame in range(31):
        shape.value = .5 - .5 * math.cos(frame / 30 * 2*math.pi)
        shape.keyframe_insert(data_path="value", frame=frame)
    context.stash_action(obj.data.shape_keys)
    context.reset_pose()
    character.export_character(out / "fixture.glb")


def main():
    from asset_auto.assessment import assess
    from asset_auto.authoring import merge_animations
    from asset_auto.models import AssessmentRequest, AssetSpec, MergeAnimationsRequest
    from asset_auto.pipeline import generate, run_logged
    from asset_auto.settings import executable
    from asset_auto.store import read_json, write_json

    root = Path(__file__).resolve().parents[1]
    out = root / ".work" / ("smoke-assessment-" + uuid.uuid4().hex[:8])
    out.mkdir()
    blender = executable(root, "blender")
    write_json(out / "asset-system.local.json", {"blender": blender})
    run_logged([blender, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
                "--python", str(Path(__file__).resolve()), "--", str(out)], out / "fixture.log")
    source = generate(out, AssetSpec(asset_id="device", provider="import", asset_kind="animated",
                                     source=str(out / "fixture.glb"), triangle_budget=100))
    folder = out / ".assets/device" / source["revision"]
    hashes = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ("asset.glb", "source.blend", "manifest.json")}
    request = AssessmentRequest(asset_id="device", revision=source["revision"], max_render_frames=12, usage={
        "purpose": "Reusable moving device; no humanoid or eye-specific assumptions",
        "features": [{"name": "panel", "representation": "rigid transform plus morph deformation",
                      "intended_behavior": "oscillate, translate, hold and compress", "acceptance": ["Surface remains coherent at extrema"]}],
        "clips": {
            "oscillate": {"playback": "loop", "rules": {"max_still_seconds": .15, "max_angular_velocity_jump_dps": 10}},
            "translate": {"playback": "loop", "motion": "root_motion", "root_target": "object:panel"},
            "hold": {"playback": "hold", "events": [{"name": "extension", "time_seconds": .25}]},
            "stalled": {"playback": "loop", "rules": {"max_still_seconds": .2}},
            "compress": {"playback": "loop", "rules": {"max_still_seconds": .15}},
        }})
    report = assess(out, request)
    assert report["clips"]["stalled"]["numeric_status"] == "failed"
    for name in ("oscillate", "translate", "compress"):
        assert report["clips"][name]["numeric_status"] == "passed", report["clips"][name]
    assert not any(check["name"].startswith("loop_") for check in report["clips"]["hold"]["checks"])
    assert report["clips"]["translate"]["root_motion"]["mean_displacement_speed_mps"] > 1.99
    assert report["rendered_frames"] == 12
    assert report["requested_views"] == ["front", "right", "back"]
    assert report["clips"]["hold"]["view_counts"] == {"front": 1, "right": 1, "back": 1}
    assert report["clips"]["compress"]["unrendered_view_images"] > 0
    assert sum(clip["unrendered_frames"] for clip in report["clips"].values()) > 0
    assert any("event:extension" in frame["reasons"] and "file" in frame for frame in report["clips"]["hold"]["frames"])
    assert any("morph:" in target for target in report["targets"])
    evidence = Path(report["evidence_directory"])
    assert len(list(evidence.glob("*.png"))) == 12, "Rendering must respect the total image budget"
    assert all((evidence / filename).is_file() for clip in report["clips"].values()
               for frame in clip["frames"] for filename in frame.get("views", {}).values())
    assert all((evidence / frame["file"]).is_file() for clip in report["clips"].values() for frame in clip["frames"] if "file" in frame)
    assert all(hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    merged = merge_animations(out, MergeAnimationsRequest(asset_id="device", revision=source["revision"],
        sources=[{"asset_id": "device", "revision": source["revision"], "clips": ["hold"], "rename": {"hold": "open_once"}}]))
    inherited = read_json(out / ".assets/device" / merged["revision"] / "usage.json")
    assert inherited["usage"]["clips"]["open_once"]["playback"] == "hold"
    assert inherited["usage"]["clips"]["open_once"]["events"][0]["name"] == "extension"
    assert inherited["status"] == "inherited_requires_reassessment"
    assert not (out / ".assets/device" / merged["revision"] / "assessment.json").exists()
    result = {"passed": True, "sandbox": str(out), "evidence": str(evidence), "source_revision": source["revision"],
              "merged_revision": merged["revision"], "checks": ["periodic rigid and morph loops", "root displacement",
              "intentional hold allowed", "unintended plateau detected", "events and budget coverage",
              "final GLB/source immutability", "rename-aware contract merge without inheriting approval"],
              "visual_review": "pending; inspect emitted images separately"}
    write_json(out / "result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--" in sys.argv:
        fixture(Path(sys.argv[sys.argv.index("--") + 1]))
    else:
        main()
