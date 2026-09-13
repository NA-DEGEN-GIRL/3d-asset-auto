"""Author one local biped clip on an existing skin, executed by Blender.

This is deliberately an inspectable procedural baseline, not learned motion or
motion capture. Author the requested preset separately, then merge it onto the
original GLB, preserving every other clip and the original skin/geometry bytes.
"""

import json
import math
import re
import sys
from itertools import pairwise
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_character_worker as character
from animation_merge import merge

ALIASES = {
    "root": ("Root", "ArmatureRoot"),
    "pelvis": ("Pelvis", "Hips", "Hip"),
    "chest": ("Chest", "UpperChest", "Spine02", "Spine2", "Spine1", "Spine"),
    "head": ("Head",),
    "left_upper_arm": ("L_Upperarm", "upper_arm.L", "LeftArm", "LeftUpperArm"),
    "right_upper_arm": ("R_Upperarm", "upper_arm.R", "RightArm", "RightUpperArm"),
    "left_forearm": ("L_Forearm", "forearm.L", "LeftForeArm", "LeftLowerArm"),
    "right_forearm": ("R_Forearm", "forearm.R", "RightForeArm", "RightLowerArm"),
    "left_thigh": ("L_Thigh", "thigh.L", "LeftUpLeg", "LeftUpperLeg"),
    "right_thigh": ("R_Thigh", "thigh.R", "RightUpLeg", "RightUpperLeg"),
    "left_shin": ("L_Calf", "shin.L", "LeftLeg", "LeftLowerLeg"),
    "right_shin": ("R_Calf", "shin.R", "RightLeg", "RightLowerLeg"),
    "left_foot": ("L_Foot", "foot.L", "LeftFoot"),
    "right_foot": ("R_Foot", "foot.R", "RightFoot"),
}


def token(name):
    return re.sub(r"[^a-z0-9]", "", name.lower().removeprefix("mixamorig:"))


def resolve_bones(rig, provided, animation):
    unknown = set(provided) - set(ALIASES)
    if unknown:
        raise ValueError(f"Unknown bone_map roles: {sorted(unknown)}; supported: {sorted(ALIASES)}")
    resolved = dict(provided)
    for role, name in resolved.items():
        if name not in rig.data.bones:
            raise ValueError(f"bone_map {role}: bone {name!r} does not exist")
    for role, aliases in ALIASES.items():
        if role in resolved:
            continue
        for alias in aliases:
            matches = [bone.name for bone in rig.data.bones if token(bone.name) == token(alias)]
            if len(matches) == 1:
                resolved[role] = matches[0]
                break
    required = ({f"{side}_{part}" for side in ("left", "right")
                 for part in ("thigh", "shin", "foot")} if animation != "idle" else {"chest"})
    missing = required - set(resolved)
    if missing:
        raise ValueError(f"Provide observed bone_map roles {sorted(missing)}. Inspect actual "
                         "head_world/tail_world and parent links; generic bone numbers are not semantic names.")
    # One joint cannot perform distinct limb roles or both sides of the body.
    mapped_limb = [resolved[role] for role in resolved if role.startswith(("left_", "right_"))]
    if len(mapped_limb) != len(set(mapped_limb)):
        raise ValueError("Distinct limb roles must map to distinct bones")
    for side in ("left", "right"):
        names = [resolved.get(f"{side}_{part}") for part in ("thigh", "shin", "foot")]
        if not all(names):
            continue
        for ancestor, descendant in pairwise(names):
            if rig.data.bones[ancestor] not in rig.data.bones[descendant].parent_recursive:
                raise ValueError(f"{side} leg bone_map is not an ordered thigh/shin/foot hierarchy")
    return resolved


def clear_clips():
    for owner in character.animation_owners():
        owner.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    # Import evaluates its first animation; recover the actual imported rest first.
    for obj, (matrix, weights) in character._preview_defaults.items():
        obj.matrix_basis = matrix
        for name, value in weights.items():
            obj.data.shape_keys.key_blocks[name].value = value
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            for bone in obj.pose.bones:
                bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


class Motion:
    def __init__(self, rig, mapping, forward, floor, height):
        self.rig, self.mapping, self.forward = rig, mapping, forward
        self.floor, self.height = floor, height
        self.up, self.right = Vector((0, 0, 1)), Vector((0, 0, 1)).cross(forward).normalized()
        self.rest = {bone.name: bone.matrix_local.copy() for bone in rig.data.bones}
        self.base_location, self.base_world = rig.location.copy(), rig.matrix_world.copy()
        self.parent_inverse = (rig.parent.matrix_world.inverted().to_3x3()
                               if rig.parent else Matrix.Identity(3))
        self.clamped = 0
        self.corrections = []
        self.ankles = {}
        self.leg_length = height * .4
        for side in ("left", "right"):
            if f"{side}_foot" in mapping and f"{side}_thigh" in mapping:
                foot = rig.data.bones[mapping[f"{side}_foot"]]
                hip = rig.data.bones[mapping[f"{side}_thigh"]]
                self.ankles[side] = self.base_world @ foot.head_local
                length = (self.base_world @ hip.head_local - self.ankles[side]).length
                if length < height * .03:
                    raise ValueError(f"{side} leg has implausibly short joint spacing; inspect bone_map")
                self.leg_length = min(self.leg_length, length)

    def reset(self):
        self.rig.location = self.base_location
        for bone in self.rig.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
            bone.rotation_mode = "QUATERNION"
        bpy.context.view_layer.update()

    def rotate(self, role, world_axis, angle):
        if role not in self.mapping:
            return
        name = self.mapping[role]
        world_rotation = (self.rig.matrix_world @ self.rest[name]).to_quaternion()
        local_axis = world_rotation.inverted() @ world_axis
        self.rig.pose.bones[name].rotation_quaternion = Quaternion(local_axis.normalized(), angle)

    def direction(self, name, start, end, rest_end):
        rest = self.rest[name].to_quaternion()
        # Imported joint node rotations need not point Blender's display tail
        # toward the next joint. Align the actual parent-to-child rest vector.
        reference = (rest_end - self.rest[name].translation).normalized()
        rotation = reference.rotation_difference((end - start).normalized()) @ rest
        self.rig.pose.bones[name].matrix = Matrix.Translation(start) @ rotation.to_matrix().to_4x4()
        bpy.context.view_layer.update()

    def leg(self, side, world_target):
        names = [self.mapping[f"{side}_{part}"] for part in ("thigh", "shin", "foot")]
        upper, _, foot = (self.rig.pose.bones[name] for name in names)
        inverse = self.rig.matrix_world.inverted()
        target, start = inverse @ world_target, upper.head.copy()
        length_a = (self.rest[names[1]].translation - self.rest[names[0]].translation).length
        length_b = (self.rest[names[2]].translation - self.rest[names[1]].translation).length
        if min(length_a, length_b) <= 1e-6:
            raise ValueError(f"{side} leg joints coincide; inspect bone_map")
        delta = target - start
        if delta.length < 1e-6:
            raise ValueError(f"{side} ankle target coincides with hip")
        direction = delta.normalized()
        distance = min(max(delta.length, abs(length_a - length_b) + 1e-5),
                       (length_a + length_b) * .999)
        if abs(distance - delta.length) > 1e-5:
            self.clamped += 1
            target = start + direction * distance
        along = (length_a ** 2 - length_b ** 2 + distance ** 2) / (2 * distance)
        across = math.sqrt(max(0, length_a ** 2 - along ** 2))
        forward = inverse.to_3x3() @ self.forward
        bend = forward - direction * forward.dot(direction)
        if bend.length < 1e-5:
            raise ValueError(f"{side} leg is parallel to forward axis; inspect rig_forward_axis/bone_map")
        knee = start + direction * along + bend.normalized() * across
        self.direction(names[0], start, knee, self.rest[names[1]].translation)
        self.direction(names[1], knee, target, self.rest[names[2]].translation)
        foot.matrix = Matrix.Translation(target) @ self.rest[names[2]].to_quaternion().to_matrix().to_4x4()
        bpy.context.view_layer.update()

    def sample(self, animation, phase, *, in_place=True):
        self.reset()
        if animation == "idle":
            self.rotate("chest", self.right, math.sin(phase) * .012)
            self.rotate("head", self.up, math.sin(phase) * .018)
        else:
            running = animation == "run"
            length = self.leg_length
            lower = (-.11 if running else -.07) * length
            bob = (.025 if running else .01) * length * math.cos(2 * phase)
            travel = self.forward * (phase / (2 * math.pi) * length * (1.5 if running else .8))
            self.rig.location += self.parent_inverse @ (self.up * (lower + bob)
                                                        + (Vector() if in_place else travel))
            bpy.context.view_layer.update()
            for side, offset in (("left", 0), ("right", math.pi)):
                cycle = phase + offset
                stride = (.30 if running else .18) * length * math.sin(cycle)
                lift = (.18 if running else .08) * length * max(0, math.cos(cycle))
                target = self.ankles[side] + self.forward * stride + self.up * lift
                if not in_place:
                    target += travel
                self.leg(side, target)
                self.rotate(f"{side}_upper_arm", self.right,
                            math.sin(cycle) * (.5 if running else .23))
                if running:
                    self.rotate(f"{side}_forearm", self.right, -.65)
        bpy.context.view_layer.update()
        low, _ = character.evaluated_bounds()
        correction = max(0, self.floor - low.z)
        self.rig.location += self.parent_inverse @ (self.up * correction)
        self.corrections.append(correction)
        bpy.context.view_layer.update()


def dense_check(path, animation, duration, frames, mapping):
    character.load_character(str(path))
    character.select_preview_clip(None)
    character.frame_at(0)
    rest_low, rest_high = character.evaluated_bounds()
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    feet = {side: rig.pose.bones[name] for side in ("left", "right")
            if (name := mapping.get(f"{side}_foot"))}
    foot_samples = {side: [] for side in feet}
    if not character.select_preview_clip(animation):
        raise ValueError("Generated clip could not be activated after GLB reimport")
    samples = []
    for index in range(frames * 2 + 1):
        seconds = duration * index / (frames * 2)
        character.frame_at(seconds)
        low, high = character.evaluated_bounds()
        if not all(math.isfinite(value) for point in (low, high) for value in point):
            raise ValueError("Generated animation has non-finite deformed bounds")
        samples.append({"time_seconds": seconds, "minimum_z_m": low.z,
                        "floor_penetration_m": max(0, rest_low.z - low.z),
                        "height_m": high.z - low.z})
        for side, foot in feet.items():
            foot_samples[side].append(list(rig.matrix_world @ foot.head))
    tolerance = max(.0001, (rest_high.z - rest_low.z) * .002)
    maximum = max(sample["floor_penetration_m"] for sample in samples)
    foot_motion = {}
    for side, positions in foot_samples.items():
        extents = [max(p[axis] for p in positions) - min(p[axis] for p in positions) for axis in range(3)]
        foot_motion[side] = {"joint_head_extent_xyz_m": extents,
                             "joint_head_path_m": sum((Vector(b) - Vector(a)).length
                                                      for a, b in pairwise(positions)),
                             "measurement": "ankle joint motion, not a foot-contact/foot-sliding proof"}
    return {"scope": "all_authored_frames_and_half_frames_after_GLB_reimport",
            "samples": len(samples), "floor_reference_m": rest_low.z,
            "tolerance_m": tolerance, "maximum_penetration_m": maximum,
            "below_floor_samples": sum(sample["floor_penetration_m"] > tolerance for sample in samples),
            "minimum_animated_height_m": min(sample["height_m"] for sample in samples),
            "foot_joint_motion": foot_motion,
            "sample_values": samples}


def main():
    request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    out = Path(request["output"])
    out.mkdir(parents=True, exist_ok=True)
    animation = request["animation"]
    if animation not in ("idle", "walk", "run"):
        raise ValueError("Local motion supports idle, walk and run")
    character.load_character(request["source"])
    character.validate_armature_modifiers()
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Local motion requires exactly one armature")
    rig = rigs[0]
    summary = character.rigging_summary()
    if not summary["weighted_vertices"] or summary["unweighted_vertices"]:
        raise ValueError("Local motion requires every mesh vertex to have skin weights")
    for item in summary["meshes"]:
        if item["invalid_weight_vertices"] or item["near_zero_weight_vertices"]:
            raise ValueError("Local motion input has invalid or vanishing skin weights")
    clear_clips()
    scale = rig.matrix_world.to_scale()
    if min(scale) <= 0 or max(scale) - min(scale) > 1e-4 * max(scale):
        raise ValueError("Local motion requires a positive uniform armature world scale")
    mapping = resolve_bones(rig, request.get("bone_map", {}), animation)
    forward = {"+z": (0, -1, 0), "-z": (0, 1, 0),
               "+x": (1, 0, 0), "-x": (-1, 0, 0)}[request.get("rig_forward_axis", "+z")]
    low, high = character.evaluated_bounds()
    height = high.z - low.z
    if height <= 1e-6:
        raise ValueError("Local motion requires nonzero character height")
    motion = Motion(rig, mapping, Vector(forward), low.z, height)
    fps = 30
    frames = {"idle": 60, "walk": 30, "run": 20}[animation]
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = fps, 1
    scene.frame_start, scene.frame_end = 0, frames
    for frame in range(frames + 1):
        scene.frame_set(frame)
        motion.sample(animation, frame / frames * 2 * math.pi,
                      in_place=request.get("animate_in_place", True))
        for bone in rig.pose.bones:
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            bone.keyframe_insert(data_path="location", frame=frame)
        rig.keyframe_insert(data_path="location", frame=frame)
    action = rig.animation_data.action
    action.name, action.use_fake_user = animation, True
    # Avoid Bezier overshoot between tightly sampled grounded poses.
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for curve in channelbag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "LINEAR"
    rig.animation_data.action = None
    motion.reset()
    # Saving/exporting in actual rest is essential: otherwise the last pose leaks
    # into GLB node defaults and shifts the rest height on the next import.
    bpy.ops.file.pack_all()
    preset = out / "preset"
    preset.mkdir(exist_ok=True)
    character.export_character(preset / "requested.glb")
    exported = character.animation_summary(character.glb_document(preset / "requested.glb"))
    if exported["count"] != 1 or exported["clips"][0]["duration_seconds"] <= 0:
        raise ValueError("Local animation export must contain exactly one nonempty clip")
    merged = merge(request["source"], [{"path": str(preset / "requested.glb"), "clips": [animation]}],
                   out / "generated.glb", on_conflict="replace")
    # Keep the editable source consistent with the merged delivery, rather than
    # leaving a .blend that contains only the temporary requested preset.
    character.load_character(str(out / "generated.glb"))
    character.select_preview_clip(None)
    bpy.context.view_layer.update()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "generated.blend"))
    merged_clips = character.animation_summary(character.glb_document(out / "generated.glb"))
    quality = dense_check(out / "generated.glb", animation, frames / fps, frames, mapping)
    warnings = ["Procedural baseline motion, not motion capture; inspect deformation and foot sliding.",
                "Grounding translates the whole rig; foot contact and joint limits are not a physics simulation.",
                "Dense motion checks cover the requested preset; retained clips keep their previous review scope."]
    if motion.clamped:
        warnings.append(f"IK reach was clamped {motion.clamped} times; inspect leg proportions and bone_map.")
    if quality["below_floor_samples"]:
        warnings.append("Reimported interpolated motion penetrates the floor beyond tolerance; review required.")
    report = {
        "provider": "local", "operation": "animate", "model": "procedural-biped-ik-v1",
        "method": "analytic_two_bone_IK_and_procedural_rotation",
        "generated_file": "generated.glb", "animation": animation,
        "clip_policy": "preserve_existing_replace_requested",
        "clips": merged_clips["clips"], "clip_merge": merged,
        "rig_forward_axis": request.get("rig_forward_axis", "+z"),
        "animate_in_place": request.get("animate_in_place", True), "bone_map": mapping,
        "duration_seconds": frames / fps, "authored_fps": fps, "authored_frames": frames + 1,
        "ik_reach_clamps": motion.clamped,
        "maximum_ground_correction_m": max(motion.corrections),
        "ground_checks": quality, "warnings": warnings, "visual_review": "pending",
        "blender_version": bpy.app.version_string,
    }
    (out / "local-motion.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
