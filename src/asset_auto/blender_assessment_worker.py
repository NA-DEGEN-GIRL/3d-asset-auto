"""Evaluate final GLB transforms and render selected critical moments locally."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_character_worker as character
from motion_quality import analyze, important_frames, render_schedule, sample_times

VIEW_DIRECTIONS = {"front": (0, -4, .4), "back": (0, 4, .4), "left": (-4, 0, .4),
                   "right": (4, 0, .4), "perspective": (3, -4, 2.5)}


def pose():
    result = {}

    def transform(key, matrix):
        position, rotation, scale = matrix.decompose()
        result[key] = {"p": list(position), "q": list(rotation), "s": list(scale)}

    for obj in bpy.context.scene.objects:
        if obj.type in {"CAMERA", "LIGHT"}:
            continue
        transform("object:" + obj.name, obj.matrix_basis)
        if obj.type == "ARMATURE":
            for bone in obj.pose.bones:
                transform("bone:" + obj.name + "/" + bone.name, bone.matrix_basis)
        if obj.type == "MESH" and obj.data.shape_keys:
            for key in list(obj.data.shape_keys.key_blocks)[1:]:
                result["morph:" + obj.name + "/" + key.name] = {"value": key.value}
    for item in result.values():
        for value in item.values():
            if not all(math.isfinite(number) for number in (value if isinstance(value, list) else [value])):
                raise ValueError("Non-finite animated transforms")
    return result


def run(request):
    source, out = Path(request["source"]), Path(request["output"])
    character.load_character(source)
    character.select_preview_clip(None)
    character.frame_at(0)
    targets = list(pose())
    reports, tracks = {}, {}
    for name, clip in request["clips"].items():
        usage = request["usage"]["clips"][name]
        if not character.select_preview_clip(name):
            raise ValueError(f"Cannot activate final GLB clip: {name}")
        times = sample_times(clip["start_seconds"], clip["end_seconds"], request["sample_rate"],
                             request["max_samples_per_clip"], usage["events"])
        samples = []
        for seconds in times:
            character.frame_at(seconds)
            low, high = character.evaluated_bounds()
            if not all(math.isfinite(value) for point in (low, high) for value in point):
                raise ValueError("Non-finite evaluated mesh bounds")
            samples.append({"time_seconds": seconds, "pose": pose(), "bounds": {"min": list(low), "max": list(high)}})
        report = analyze(samples, usage)
        report["frames"] = important_frames(samples, usage["events"], report, usage["rules"])
        report["playback_policy"] = usage["playback"]
        report["manual_acceptance"] = [{"criterion": text, "status": "untested"} for text in usage["acceptance"]]
        reports[name], tracks[name] = report, samples
    # Round-robin allocation prevents one clip from consuming all preview slots.
    views = request.get("views", ["front", "right", "back"])
    chosen = render_schedule(reports, views, request["max_render_frames"]) if request["render"] else []
    if chosen:
        character.select_preview_clip(None)
        character.frame_at(0)
        # Reuse the established lighting setup, then fit a shared camera to the
        # evaluated bounds of every frame actually being rendered.
        character.render_views(out, render=False)
        all_bounds = []
        for name, frame, _view in chosen:
            sample = min(tracks[name], key=lambda sample: abs(sample["time_seconds"] - frame["time_seconds"]))
            all_bounds.extend(Vector(sample["bounds"][key]) for key in ("min", "max"))
        low = Vector([min(point[i] for point in all_bounds) for i in range(3)])
        high = Vector([max(point[i] for point in all_bounds) for i in range(3)])
        center, extent = (low + high) / 2, max(max(high - low), .001)
        camera = bpy.context.scene.camera
        camera.data.ortho_scale = extent * 1.8
        camera.data.clip_start, camera.data.clip_end = max(extent * .001, 1e-6), max(extent * 30, 1)
        for obj in bpy.context.scene.objects:
            if obj.get("asset_preview_light"):
                direction = {"key": (2, -3, 4), "fill": (-3, -1, 2), "rim": (1, 3, 3)}[obj["asset_preview_light"]]
                obj.location = center + Vector(direction) * extent
                obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
                obj.data.energy = {"key": 450, "fill": 250, "rim": 600}[obj["asset_preview_light"]] * extent * extent
                obj.data.size = extent * 3
        for index, (name, frame, view) in enumerate(chosen):
            character.select_preview_clip(name)
            character.frame_at(frame["time_seconds"])
            camera.location = center + Vector(VIEW_DIRECTIONS[view]) * extent
            camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
            filename = f"moment-{index:03d}-{view}.png"
            frame.setdefault("views", {})[view] = filename
            frame.setdefault("file", filename)
            bpy.context.scene.render.filepath = str(out / filename)
            bpy.ops.render.render(write_still=True)
    for name, report in reports.items():
        for frame in report["frames"]:
            frame["unrendered_views"] = [view for view in views if view not in frame.get("views", {})]
        report["rendered_frames"] = sum(len(frame.get("views", {})) for frame in report["frames"])
        report["rendered_moments"] = sum("file" in frame for frame in report["frames"])
        report["unrendered_frames"] = sum("file" not in frame for frame in report["frames"])
        report["unrendered_view_images"] = sum(len(frame["unrendered_views"]) for frame in report["frames"])
        report["view_counts"] = {view: sum(view in frame.get("views", {}) for frame in report["frames"])
                                 for view in views}
        report["visual_review"] = "pending" if report["rendered_frames"] else "untested"
        # Keep scalar/bounds evidence without duplicating all skeletal poses.
        report["sample_bounds"] = [{"time_seconds": sample["time_seconds"], "bounds": sample["bounds"]} for sample in tracks[name]]
    result = {"clips": reports, "targets": targets, "rendered_frames": len(chosen),
              "requested_views": views,
              "coordinate_system": "Blender Z-up meters; node/bone local transform checks"}
    (out / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8")))
