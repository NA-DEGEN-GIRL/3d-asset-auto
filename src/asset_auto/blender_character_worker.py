"""Rig-aware import/export and preview worker, executed by portable Blender."""

import hashlib
import json
import math
import shutil
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_worker as static_worker
from blender_worker import bounds, inspect, render_views

MAX_PREVIEW_CLIPS = 8
_preview_defaults = {}


def meshes():
    # Rig control widgets are editor helpers, never character geometry.
    widgets = {bone.custom_shape for obj in bpy.context.scene.objects if obj.type == "ARMATURE"
               for bone in obj.pose.bones if bone.custom_shape is not None}
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj not in widgets]


# The reused numeric/render helpers consult their module's mesh selector.
static_worker.meshes = meshes


def load_character(source):
    if not hasattr(bpy.types.Object, "gltf2_animation_rest"):
        # Also recognize rest-state properties in .blend files saved after a glTF import.
        from io_scene_gltf2.blender.com.gltf2_blender_ui import anim_ui_register

        anim_ui_register()
    if Path(source).suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source), disable_bone_shape=True)
    if not meshes():
        raise ValueError("Input contains no character mesh objects")
    capture_preview_defaults(from_gltf=Path(source).suffix.lower() != ".blend")


def capture_preview_defaults(*, from_gltf=False, use_imported_rest=True):
    """Keep local rest transforms/morph defaults before any clip changes them."""
    global _preview_defaults
    _preview_defaults = {}
    for obj in bpy.context.scene.objects:
        matrix = obj.matrix_basis.copy()
        imported_rest = use_imported_rest and obj.is_property_set("gltf2_animation_rest")
        if imported_rest:
            # The importer stores the node's local transform before applying its first clip.
            matrix = Matrix(obj.gltf2_animation_rest)
        weights = {}
        if obj.type == "MESH" and obj.data.shape_keys:
            blocks = list(obj.data.shape_keys.key_blocks)[1:]
            imported = [item.val for item in obj.gltf2_animation_weight_rest]
            weights = {block.name: (imported[index] if index < len(imported) else 0)
                       if from_gltf or imported_rest else block.value
                       for index, block in enumerate(blocks)}
        _preview_defaults[obj] = (matrix, weights)


def glb_document(path):
    with Path(path).open("rb") as stream:
        magic, version, length = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2 or length != Path(path).stat().st_size:
            raise ValueError("Expected a complete GLB 2.0 file")
        chunk_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        if chunk_type != b"JSON":
            raise ValueError("GLB must start with a JSON chunk")
        return json.loads(stream.read(chunk_length))


def animation_summary(document):
    clips = []
    accessors = document.get("accessors", [])
    for index, animation in enumerate(document.get("animations", [])):
        starts, ends = [], []
        for sampler in animation.get("samplers", []):
            accessor = accessors[sampler["input"]]
            if accessor.get("min") and accessor.get("max"):
                starts.append(accessor["min"][0])
                ends.append(accessor["max"][0])
        start, end = min(starts, default=0), max(ends, default=0)
        clips.append({
            "index": index,
            "name": animation.get("name", f"Animation_{index}"),
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": end - start,
            "channels": len(animation.get("channels", [])),
        })
    return {"count": len(clips), "clips": clips}


def rigging_summary():
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    per_mesh = []
    for obj in meshes():
        rigs = {
            modifier.object
            for modifier in obj.modifiers
            if modifier.type == "ARMATURE" and modifier.object is not None
        }
        bone_names = {bone.name for rig in rigs for bone in rig.data.bones}
        bone_groups = {group.index for group in obj.vertex_groups if group.name in bone_names}
        weighted, invalid, non_unit, near_zero = 0, 0, 0, 0
        for vertex in obj.data.vertices:
            weights = [group.weight for group in vertex.groups if group.group in bone_groups]
            if any(not math.isfinite(weight) or weight < 0 for weight in weights):
                invalid += 1
            total = sum(weight for weight in weights if math.isfinite(weight))
            weighted += total > 1e-8
            non_unit += total > 1e-8 and abs(total - 1) > 1e-3
            near_zero += total > 1e-8 and not any(weight > .0001 for weight in weights)
        per_mesh.append({
            "name": obj.name,
            "armatures": sorted(rig.name for rig in rigs),
            "vertices": len(obj.data.vertices),
            "weighted_vertices": weighted,
            "unweighted_vertices": len(obj.data.vertices) - weighted,
            "invalid_weight_vertices": invalid,
            "non_unit_weight_vertices": non_unit,
            "near_zero_weight_vertices": near_zero,
        })
    return {
        "armatures": [{
            "name": obj.name,
            "bone_count": len(obj.data.bones),
            "coordinate_system": "Blender Z-up world, meters",
            "bones": [{
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "deform": bone.use_deform,
                "head_world": list(obj.matrix_world @ bone.head_local),
                "tail_world": list(obj.matrix_world @ bone.tail_local),
            } for bone in obj.data.bones],
        } for obj in armatures],
        "bones": sum(len(obj.data.bones) for obj in armatures),
        "weighted_vertices": sum(item["weighted_vertices"] for item in per_mesh),
        "unweighted_vertices": sum(item["unweighted_vertices"] for item in per_mesh),
        "meshes": per_mesh,
    }


def validate_armature_modifiers():
    for obj in meshes():
        if sum(modifier.type == "ARMATURE" for modifier in obj.modifiers) > 1:
            raise ValueError(f"Multiple armature modifiers on {obj.name!r} are unsupported; "
                             "GLB export would silently discard a rig")


def rotate_input_hierarchy(degrees):
    """GLB Y yaw maps to Blender Z yaw; keep bones, weights and channels local."""
    degrees = float(degrees)
    if not math.isfinite(degrees):
        raise ValueError("input_yaw_degrees must be finite")
    if not degrees:
        return {"input_yaw_degrees": 0, "rotation_parent": None}
    roots = [obj for obj in bpy.context.scene.objects
             if obj.parent is None and obj.type not in ("CAMERA", "LIGHT")]
    parent = bpy.data.objects.new("asset_input_yaw", None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in roots:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    parent.rotation_euler.z = math.radians(degrees)
    bpy.context.view_layer.update()
    return {"input_yaw_degrees": degrees, "rotation_parent": parent.name,
            "rotation_axis": "Blender Z / glTF Y"}


def normalize_hierarchy(height):
    """Apply a shared parent transform without baking bones, weights or animation."""
    if height is None:
        return {"mode": "preserve", "target_height": None}
    if not math.isfinite(height) or height <= 0:
        raise ValueError("target_height must be finite and positive")
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    positions = [(obj, obj.data.pose_position) for obj in armatures]
    try:
        for obj, _ in positions:
            obj.data.pose_position = "REST"
        bpy.context.view_layer.update()
        low, high = bounds(meshes())
    finally:
        for obj, position in positions:
            obj.data.pose_position = position
        bpy.context.view_layer.update()
    if high.z - low.z < 1e-8:
        raise ValueError("Cannot normalize a zero-height character")
    factor = height / (high.z - low.z)
    center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    roots = [obj for obj in bpy.context.scene.objects
             if obj.parent is None and obj.type not in ("CAMERA", "LIGHT")]
    parent = bpy.data.objects.new("asset_normalization", None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in roots:
        # An identity parent preserves every local transform and animated channel.
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    parent.scale = (factor,) * 3
    parent.location = -center * factor
    bpy.context.view_layer.update()
    return {"mode": "shared_parent", "target_height": height,
            "scale": factor, "translation": list(parent.location), "parent": parent.name}


def animation_owners():
    owners = list(bpy.context.scene.objects)
    owners.extend(obj.data.shape_keys for obj in meshes() if obj.data.shape_keys)
    return [owner for owner in owners if owner.animation_data]


def name_single_clip(name):
    if not name:
        return
    # Blender's single-armature exporter also includes saved, unbound actions.
    actions = set(bpy.data.actions)
    for owner in animation_owners():
        if owner.animation_data.action:
            actions.add(owner.animation_data.action)
        for track in owner.animation_data.nla_tracks:
            actions.update(strip.action for strip in track.strips if strip.action)
    if len(actions) == 1:
        action = next(iter(actions))
        action.name = name
        for owner in animation_owners():
            for track in owner.animation_data.nla_tracks:
                if any(strip.action == action for strip in track.strips):
                    track.name = name


def select_preview_clip(name):
    """Activate each matching imported action slot; preview scene is disposable."""
    matched = False
    owners = animation_owners()
    for owner in owners:
        animation = owner.animation_data
        if animation.action is not None:
            animation.action_slot = None
        animation.action = None
        for track in animation.nla_tracks:
            track.mute = True
            track.is_solo = False
    for obj, (matrix, weights) in _preview_defaults.items():
        obj.matrix_basis = matrix
        if weights:
            for key, value in weights.items():
                obj.data.shape_keys.key_blocks[key].value = value
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            for bone in obj.pose.bones:
                bone.matrix_basis = Matrix.Identity(4)
    for owner in owners:
        for track in owner.animation_data.nla_tracks:
            if track.name == name and track.strips:
                owner.animation_data.action = track.strips[0].action
                owner.animation_data.action_slot = track.strips[0].action_slot
                matched = True
    return matched


def evaluated_bounds():
    dependency_graph = bpy.context.evaluated_depsgraph_get()
    return bounds([obj.evaluated_get(dependency_graph) for obj in meshes()])


def frame_at(seconds):
    scene = bpy.context.scene
    frame = seconds * scene.render.fps / scene.render.fps_base
    integer = math.floor(frame)
    scene.frame_set(integer, subframe=frame - integer)
    bpy.context.view_layer.update()
    return frame


def animation_previews(out, summary, preferred=None, *, grounded=False, selected_names=None):
    select_preview_clip(None)
    frame_at(0)
    rest_low, rest_high = evaluated_bounds()
    floor = 0.0 if grounded else rest_low.z
    tolerance = max(.0001, (rest_high.z - rest_low.z) * .01)
    quality = {"scope": "preview_samples_only",
               "floor_reference": "ground_plane" if grounded else "rest_pose_bounds",
               "floor_reference_m": floor, "rest_min_z_m": rest_low.z,
               "tolerance_m": tolerance, "warnings": []}
    clips = list(summary["clips"])
    if selected_names:
        missing = set(selected_names) - {clip["name"] for clip in clips}
        if missing:
            raise ValueError(f"Requested preview clips do not exist: {sorted(missing)}")
        if len(selected_names) > MAX_PREVIEW_CLIPS:
            raise ValueError(f"At most {MAX_PREVIEW_CLIPS} preview clips can be selected")
        chosen = [clip for name in selected_names for clip in clips if clip["name"] == name]
        clips = chosen + [clip for clip in clips if clip not in chosen]
    elif preferred and any(clip["name"] == preferred for clip in clips):
        matching = [clip for clip in clips if clip["name"] == preferred]
        clips = matching + [clip for clip in clips if clip not in matching]
    selected = clips[:MAX_PREVIEW_CLIPS]
    sampled, all_points = [], []
    for clip in selected:
        if not select_preview_clip(clip["name"]):
            raise ValueError(f"Exported animation cannot be activated: {clip['name']}")
        start, end = clip["start_seconds"], clip["end_seconds"]
        samples = []
        # Exclude the duplicate endpoint of looping clips; sample distinct cycle phases.
        for index, seconds in enumerate(start + (end - start) * phase for phase in (0, 1 / 3, 2 / 3)):
            frame = frame_at(seconds)
            low, high = evaluated_bounds()
            all_points.extend((low, high))
            samples.append({"time_seconds": seconds, "frame": frame, "view": "perspective",
                            "file": f"animation-{clip['index']:02d}-{index:02d}.png",
                            "floor_penetration_m": max(0, floor - low.z),
                            "bounds": {"min": list(low), "max": list(high)}})
        below_floor = sum(sample["floor_penetration_m"] > tolerance for sample in samples)
        maximum_penetration = max(sample["floor_penetration_m"] for sample in samples)
        if below_floor:
            quality["warnings"].append(
                f"Animation {clip['name']!r}: {below_floor}/{len(samples)} preview samples extend "
                f"below the {quality['floor_reference']} by up to {maximum_penetration:.4f} m; "
                "inspect ground contact. Only preview samples were checked; motion is unchanged.")
        sampled.append({"name": clip["name"], "samples": samples,
                        "floor_check": {"below_floor_samples": below_floor,
                                        "maximum_penetration_m": maximum_penetration}})
    if all_points:
        low = Vector(tuple(min(point[i] for point in all_points) for i in range(3)))
        high = Vector(tuple(max(point[i] for point in all_points) for i in range(3)))
        center, extent = (low + high) / 2, max(high - low)
        camera = bpy.context.scene.camera
        camera.location = center + Vector((3, -4, 2.5)) * extent
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.ortho_scale = extent * 1.8
        # Root-motion clips can leave the original resting pose's lighting volume.
        preview_lights = {obj.get("asset_preview_light"): obj
                          for obj in bpy.context.scene.objects
                          if obj.type == "LIGHT" and obj.get("asset_preview_light")}
        for name, direction, energy, size in (("key", (2, -3, 4), 450, 3),
                                              ("fill", (-3, -1, 2), 250, 4),
                                              ("rim", (1, 3, 3), 600, 2)):
            light = preview_lights[name]
            light.location = center + Vector(direction) * extent
            light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
            light.data.energy, light.data.size = energy * extent * extent, size * extent
        for clip in sampled:
            select_preview_clip(clip["name"])
            for sample in clip["samples"]:
                frame_at(sample["time_seconds"])
                bpy.context.scene.render.filepath = str(out / sample["file"])
                bpy.ops.render.render(write_still=True)
    result = {"clips": sampled, "sampled_clips": len(sampled), "total_clips": len(clips),
              "max_preview_clips": MAX_PREVIEW_CLIPS,
              "camera": "shared orthographic perspective across all sampled clips",
              "view_coverage": "single_view_overview", "additional_views_required_for_motion_review": True,
              "quality_checks": quality,
              "visual_review": "pending"}
    (out / "animation-previews.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def export_character(path):
    validate_armature_modifiers()
    bpy.ops.object.select_all(action="DESELECT")
    objects = set(meshes()) | {obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"}
    for obj in list(objects):
        while obj.parent is not None:
            obj = obj.parent
            objects.add(obj)
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_image_format="AUTO", export_yup=True, export_apply=False,
        export_skins=True, export_all_influences=True, export_def_bones=False,
        export_animations=True, export_animation_mode="ACTIONS",
        export_force_sampling=True, export_frame_range=False,
        export_hierarchy_flatten_bones=False, export_hierarchy_flatten_objs=False,
        export_armature_object_remove=False, export_cameras=False, export_lights=False,
    )


def finish(request, *, validate_export=None):
    """Inspect/save/export an already loaded scene, then preview its actual GLB.

    Callers that author a scene must capture its intended rest defaults first.
    The optional validator runs after export, before inspection or previews.
    """
    out = Path(request["output"])
    out.mkdir(parents=True, exist_ok=True)
    preserve_glb = request.get("preserve_input_glb", False)
    if preserve_glb and (Path(request["source"]).suffix.lower() != ".glb"
                         or request.get("target_height") is not None
                         or request.get("input_yaw_degrees", 0)
                         or (request.get("animation_name") and request.get("rename_animation", True))):
        raise ValueError("preserve_input_glb requires a GLB source without normalization, yaw or clip renaming")
    validate_armature_modifiers()
    if request.get("rename_animation", True):
        name_single_clip(request.get("animation_name"))
    # glTF import activates its first clip. Export from the stored node/morph
    # rest defaults so that clip's first root pose cannot replace GLB defaults.
    # The actions and their NLA slots stay available for the ACTIONS exporter.
    select_preview_clip(None)
    rotation = rotate_input_hierarchy(request.get("input_yaw_degrees", 0))
    normalization = normalize_hierarchy(request.get("target_height"))
    normalization.update(rotation)
    if rotation["rotation_parent"]:
        normalization["mode"] = "shared_parent"
    report = inspect(request["triangle_budget"])
    report["normalization"] = normalization
    report["rigging"] = rigging_summary()
    if request.get("require_rig", True) and not report["rigging"]["bones"]:
        raise ValueError("Character input has no armature bones")
    for item in report["rigging"]["meshes"]:
        if item["near_zero_weight_vertices"]:
            raise ValueError(f"{item['name']}: {item['near_zero_weight_vertices']} vertices have "
                             "only near-zero skin weights (all influences <= 0.0001); "
                             "GLB export would discard their bone influences")
        if item["invalid_weight_vertices"]:
            report["errors"].append(f"{item['name']}: invalid skin weights")
        if item["armatures"] and item["unweighted_vertices"]:
            report["warnings"].append(
                f"{item['name']}: {item['unweighted_vertices']} vertices have no bone weights")
        if item["non_unit_weight_vertices"]:
            report["warnings"].append(f"{item['name']}: exporter will normalize non-unit weights")
    if request.get("require_rig", True) and not report["rigging"]["weighted_vertices"]:
        raise ValueError("Character input has no weighted mesh vertices")
    bpy.ops.file.pack_all()
    # Save before temporary previews, preserving all original actions and their slots.
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "source.blend"))
    if preserve_glb:
        shutil.copyfile(request["source"], out / "asset.glb")
    else:
        export_character(out / "asset.glb")
    document = glb_document(out / "asset.glb")
    report["rigging"]["exported_skins"] = len(document.get("skins", []))
    report["animations"] = animation_summary(document)
    if request.get("require_rig", True) and not report["rigging"]["exported_skins"]:
        raise ValueError("Export lost the character skin")
    if request.get("require_animation", False) and not report["animations"]["count"]:
        raise ValueError("Character input/export has no animation clips")
    if validate_export is not None:
        validate_export(document)
    report["passed"] = not report["errors"]
    (out / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Inspect the actual delivery GLB. Preview activation cannot alter saved source/actions.
    load_character(str(out / "asset.glb"))
    select_preview_clip(None)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    render_views(out)
    previews = animation_previews(out, report["animations"], request.get("animation_name"),
                                  grounded=request.get("target_height") is not None,
                                  selected_names=request.get("preview_clips"))
    report["animation_quality"] = previews["quality_checks"]
    report["warnings"].extend(previews["quality_checks"]["warnings"])
    if dense := request.get("dense_motion_check"):
        # Keep this in the existing Blender process. The delivery exporter can
        # resample clips, so generated.glb checks are not final asset.glb checks.
        from blender_motion_worker import dense_check

        clip = next(item for item in report["animations"]["clips"]
                    if item["name"] == request["animation_name"])
        frames = int(dense["authored_frames"]) - 1
        if frames < 1:
            raise ValueError("Dense motion validation requires at least two authored frames")
        quality = dense_check(out / "asset.glb", clip["name"], clip["duration_seconds"],
                              frames, dense["bone_map"])
        quality["artifact"] = {"file": "asset.glb", "stage": "final_delivery",
                               "sha256": hashlib.sha256((out / "asset.glb").read_bytes()).hexdigest()}
        report["animation_quality"]["dense_ground_checks"] = quality
        if quality["below_floor_samples"]:
            report["warnings"].append("Final delivery animation penetrates the floor beyond dense-check "
                                      "tolerance; inspect the motion before approving it.")
        (out / "local-motion-delivery.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    (out / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    load_character(request["source"])
    finish(request)


if __name__ == "__main__":
    main()
