"""Run a trusted local Blender script against an existing asset, then review/export.

The request points to a snapshotted Python script. runpy injects ``context`` (an
AuthoringContext from blender_authoring_tools); scripts may import bpy directly.
This code deliberately provides no execution sandbox or network service.
"""

import hashlib
import json
import math
import runpy
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_character_worker as character
from blender_authoring_tools import AuthoringContext, action_curves, stash_action


def rna_settings(value):
    """Serialize animation settings rather than just their RNA class names.

    Modifiers have type-specific properties and envelope control collections.
    Enumerating RNA keeps those settings in the preservation contract. ID
    pointers identify bindings; their underlying meshes/rigs remain editable.
    """
    result = {}
    for prop in value.bl_rna.properties:
        name = prop.identifier
        if name == "rna_type":
            continue
        item = getattr(value, name)
        if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
            result[name] = (sorted(item) if isinstance(item, set) else list(item)
                            if getattr(prop, "is_array", False) else item)
        elif prop.type == "COLLECTION":
            result[name] = [rna_settings(element) for element in item]
        elif prop.type == "POINTER":
            if item is None:
                result[name] = None
            elif isinstance(item, bpy.types.ID):
                result[name] = {"id_type": item.id_type, "name": item.name_full,
                                "library": item.library.filepath if item.library else None}
            else:
                raise ValueError(f"Cannot preserve unsupported animation setting {value.bl_rna.identifier}.{name}")
        else:
            raise ValueError(f"Cannot preserve unsupported animation property type {prop.type}")
    return result


def action_fingerprint(action):
    curves = []
    for slot, curve in action_curves(action):
        curves.append({
            "slot": slot, "path": curve.data_path, "index": curve.array_index,
            "extrapolation": curve.extrapolation, "mute": curve.mute,
            "group": {"name": curve.group.name, "mute": curve.group.mute} if curve.group else None,
            "auto_smoothing": curve.auto_smoothing,
            "points": [rna_settings(point) for point in curve.keyframe_points],
            "samples": [list(point.co) for point in curve.sampled_points],
            "modifiers": [rna_settings(modifier) for modifier in curve.modifiers],
            "driver": rna_settings(curve.driver) if curve.driver else None,
        })
    return hashlib.sha256(json.dumps({"curves": curves, "range": list(action.frame_range),
                                      "use_frame_range": action.use_frame_range,
                                      "use_cyclic": action.use_cyclic,
                                      "slots": [(slot.handle, slot.identifier, slot.target_id_type)
                                                for slot in action.slots]},
                                     sort_keys=True).encode("utf-8")).hexdigest()


def run(request):
    out = Path(request["output"])
    out.mkdir(parents=True, exist_ok=True)
    source, script = Path(request["source"]), Path(request["script"])
    if not source.is_absolute() or not script.is_absolute():
        raise ValueError("Authoring source and script must be absolute paths")
    if source.suffix.lower() not in {".glb", ".blend"} or script.suffix.lower() != ".py":
        raise ValueError("Authoring requires an existing GLB/Blend source and a Python script")
    if not isinstance(request.get("parameters", {}), dict):
        raise TypeError("Authoring parameters must be a JSON object")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    binding = request.get("binding_sha256") or hashlib.sha256(
        json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest()
    checkpoint_path, authored = out / "authoring-executed.json", out / "authored.blend"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else None
    if checkpoint is not None and (
            checkpoint.get("binding_sha256") != binding or checkpoint.get("source_sha256") != source_hash
            or checkpoint.get("script_sha256") != script_hash or not authored.is_file()
            or checkpoint.get("authored_sha256") != hashlib.sha256(authored.read_bytes()).hexdigest()):
        raise ValueError("Authoring execution checkpoint does not match the request, inputs or authored scene")
    character.load_character(authored if checkpoint else source)
    # Only runtime-tagged helpers may be removed. Artist cameras/lights remain
    # in source.blend; the GLB exporter already excludes cameras and lights.
    for obj in list(bpy.context.scene.objects):
        if obj.get("asset_preview_light") or obj.get("asset_preview_helper") or obj.get("asset_preview_camera"):
            bpy.data.objects.remove(obj, do_unlink=True)
    context = AuthoringContext(source, out, request.get("parameters", {}))
    context.reset_pose()
    preserve = request.get("preserve_animations", True)
    if checkpoint:
        before_clips = checkpoint["input_animations"]
        timebase = checkpoint.get("input_timebase")
    else:
        scene = bpy.context.scene
        timebase = {"fps": scene.render.fps, "fps_base": scene.render.fps_base,
                    "effective_fps": scene.render.fps / scene.render.fps_base}
        before = {action.name: action_fingerprint(action) for action in bpy.data.actions} if preserve else {}
        baseline = out / "authoring-before.glb"
        character.export_character(baseline)
        before_clips = character.animation_summary(character.glb_document(baseline))
        runpy.run_path(str(script), init_globals={"context": context}, run_name="__main__")
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not character.meshes():
            raise ValueError("Authoring script left no mesh objects to export")
        for owner in character.animation_owners():
            stash_action(owner)
        context.reset_pose()
        if preserve:
            current_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
            if before_clips["count"] and not math.isclose(timebase["effective_fps"], current_fps,
                                                          rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("Authoring changed the scene animation timebase and would retime existing clips; "
                                 "retain fps/fps_base or explicitly set preserve_animations=false")
            after = {action.name: action_fingerprint(action) for action in bpy.data.actions}
            lost = [name for name, digest in before.items() if after.get(name) != digest]
            if lost:
                raise ValueError(f"Authoring removed or changed existing actions: {lost}; "
                                 "use preserve_animations=false only for deliberate replacement")
        # Subsequent export/render failure must not require executing a script
        # twice. The outer pipeline supplies an immutable input/request binding.
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(authored))
        checkpoint = {"binding_sha256": binding, "source_sha256": source_hash, "script_sha256": script_hash,
                      "authored_sha256": hashlib.sha256(authored.read_bytes()).hexdigest(),
                      "input_animations": before_clips, "input_timebase": timebase, "state": "executed"}
        temporary = checkpoint_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        temporary.replace(checkpoint_path)

    def validate(document):
        if preserve:
            names = {clip["name"] for clip in character.animation_summary(document)["clips"]}
            missing = [clip["name"] for clip in before_clips["clips"] if clip["name"] not in names]
            if missing:
                raise ValueError(f"Authoring export lost existing animation clips: {missing}")
        if not request.get("preview_clips"):
            original = {clip["name"] for clip in before_clips["clips"]}
            final_request["preview_clips"] = [clip.get("name") for clip in document.get("animations", [])
                                               if clip.get("name") not in original][:character.MAX_PREVIEW_CLIPS]

    final_request = {**request, "require_rig": request.get("require_rig", False), "target_height": None,
                     "input_yaw_degrees": 0, "preserve_input_glb": False, "rename_animation": False}
    report = character.finish(final_request, validate_export=validate)
    provenance = {
        "provider": "local", "operation": "author", "backend": "blender-script-v1",
        "source_sha256": source_hash, "script_sha256": script_hash,
        "parameters": request.get("parameters", {}), "preserve_animations": preserve,
        "input_animations": before_clips, "output_animations": report["animations"],
        "input_timebase": timebase,
        "geometry_processing": "authored edits only; no automatic normalization or decimation",
        "script_execution": "trusted local Python with full Blender/process privileges",
        "visual_review": "pending",
    }
    (out / "authoring.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return report


def main():
    request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    run(request)


if __name__ == "__main__":
    main()
