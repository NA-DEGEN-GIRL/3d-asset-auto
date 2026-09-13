"""Apply SOMA world rotations to an observed humanoid mapping in Blender.

Executed by the existing trusted authoring worker with an AuthoringContext.
No remeshing, skin replacement, or deletion of existing clips is performed.
"""

import hashlib
import json
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

ALIGNMENT_CHILDREN = {
    "Hips": ("Spine1", "Spine2", "Chest"), "Spine1": ("Spine2", "Chest"),
    "Spine2": ("Chest",), "Chest": ("Neck1", "Neck2", "Head"), "Neck1": ("Neck2", "Head"),
    "Neck2": ("Head",), "Head": ("HeadEnd",),
    **{side + part: (side + child,) for side in ("Left", "Right") for part, child in (
        ("Shoulder", "Arm"), ("Arm", "ForeArm"), ("ForeArm", "Hand"),
        ("Hand", "HandMiddle1"), ("Leg", "Shin"), ("Shin", "Foot"), ("Foot", "ToeBase"))},
}


def retarget(context):
    if len(context.armatures) != 1:
        raise ValueError("Kimodo retargeting requires exactly one humanoid armature")
    rig = context.armatures[0]
    options = context.parameters
    mapping = options["bone_map"]
    data = json.loads((context.output / "motion-data.json").read_text(encoding="utf-8"))
    source_names = data["joint_names"]
    source_index = {name: index for index, name in enumerate(source_names)}
    if len(source_names) != len(source_index) or set(mapping) - set(source_names):
        raise ValueError("Mapping contains unknown or ambiguous SOMA joint names")
    if set(mapping.values()) - set(rig.data.bones.keys()):
        raise ValueError("Mapping contains target bones absent from the authoring scene")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Map each target bone only once")
    context.reset_pose()
    if rig.constraints or any(bone.constraints for bone in rig.pose.bones):
        raise ValueError("Bake or resolve target rig constraints before direct rotation retargeting")
    scale = rig.matrix_world.to_scale()
    if min(scale) <= 0 or rig.matrix_world.determinant() <= 0 or max(scale) - min(scale) > 1e-5:
        raise ValueError("Target armature must have positive uniform world scale")
    for name in mapping.values():
        if not rig.data.bones[name].use_inherit_rotation or rig.data.bones[name].inherit_scale != "FULL":
            raise ValueError("Retargeting currently requires standard inherited bone transforms")
    for side in ("Left", "Right"):
        for parent, child in (("Leg", "Shin"), ("Shin", "Foot"), ("Arm", "ForeArm"), ("ForeArm", "Hand")):
            if rig.data.bones[mapping[side + parent]] not in rig.data.bones[mapping[side + child]].parent_recursive:
                raise ValueError("Mapped limb order does not follow the observed target hierarchy")
    neutral = [Vector(point) for point in data["neutral_joints"]]
    # SOMA is Y-up/+Z-forward; the rest of this authoring pipeline is Z-up.
    yaw = {"-y": 0, "+x": math.pi / 2, "+y": math.pi, "-x": -math.pi / 2}[options["forward_axis"]]
    axes = Matrix.Rotation(yaw, 3, "Z") @ Matrix.Rotation(math.pi / 2, 3, "X")
    rig_rotation = rig.matrix_world.to_quaternion().to_matrix()
    source_to_rig = rig_rotation.inverted() @ axes
    ordered = sorted(rig.data.bones, key=lambda bone: len(bone.parent_recursive))
    rest = {bone.name: bone.matrix_local.to_quaternion().to_matrix() for bone in ordered}
    calibrated, calibration_angles, adjustments = {}, {}, {}
    for source, target in sorted(mapping.items(), key=lambda item: len(rig.data.bones[item[1]].parent_recursive)):
        child = next((name for name in ALIGNMENT_CHILDREN.get(source, ()) if name in mapping), None)
        adjustment = Quaternion()
        if child is not None:
            target_direction = rig.data.bones[mapping[child]].head_local - rig.data.bones[target].head_local
            desired_direction = source_to_rig @ (neutral[source_index[child]] - neutral[source_index[source]])
            if min(target_direction.length, desired_direction.length) < 1e-6:
                raise ValueError("Mapped reference joints coincide; inspect the rig mapping")
            adjustment = target_direction.rotation_difference(desired_direction)
        else:
            # Unmapped terminal anatomy supplies no second reference vector.
            # Carry the parent's reference adjustment instead of leaving an
            # A-pose wrist behind when the forearm is aligned to a T-pose.
            ancestor = next((bone.name for bone in rig.data.bones[target].parent_recursive
                             if bone.name in adjustments), None)
            if ancestor is not None:
                adjustment = adjustments[ancestor].copy()
        adjustments[target] = adjustment
        calibrated[target] = adjustment.to_matrix() @ rest[target]
        calibration_angles[target] = math.degrees(adjustment.angle)
    source_lengths, target_lengths = [], []
    for side in ("Left", "Right"):
        source_lengths.append(sum((neutral[source_index[side + b]] - neutral[source_index[side + a]]).length
                                  for a, b in (("Leg", "Shin"), ("Shin", "Foot"))))
        target_lengths.append(sum((rig.data.bones[mapping[side + b]].head_local -
                                   rig.data.bones[mapping[side + a]].head_local).length
                                  for a, b in (("Leg", "Shin"), ("Shin", "Foot"))))
    motion_scale = sum(target_lengths) / sum(source_lengths)
    if not math.isfinite(motion_scale) or motion_scale <= 0:
        raise ValueError("Cannot derive a positive motion scale from mapped leg lengths")
    rotations, positions = data["global_rotations"], data["root_positions"]
    if len(rotations) != len(positions) or len(rotations) < 2 or not 1 <= data["fps"] <= 120:
        raise ValueError("Invalid Kimodo motion timing")
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    source_duration = (len(rotations) - 1) / data["fps"]
    # Blender's sampled GLB exporter uses whole scene frames. Round the span
    # and preserve both endpoint poses instead of silently truncating a fractional end.
    target_span = max(1, round(source_duration * fps))
    if any(not math.isfinite(value) for point in positions for value in point):
        raise ValueError("Non-finite root translation")
    import blender_character_worker as character

    floor, _ = character.evaluated_bounds()
    root_bone = rig.data.bones[mapping["Hips"]]
    # SOMA neutral joints are pelvis-centered, but generated roots are heights
    # above the ground. Subtract the target's existing pelvis height only once.
    target_rest_height = (rig.matrix_world @ root_bone.head_local).z - floor.z
    source_rest_height = target_rest_height / (motion_scale * scale.x)
    initial_root = Vector(positions[0])
    action = context.new_action(rig, options["clip_name"])
    by_target = {target: source_index[source] for source, target in mapping.items()}
    previous_quaternions = {}
    for index, (source_rotations, root_position) in enumerate(zip(rotations, positions, strict=True)):
        if len(source_rotations) != len(source_names):
            raise ValueError("Kimodo rotation count does not match its skeleton")
        frame = 1 + index * target_span / (len(rotations) - 1)
        global_pose = {}
        for bone in ordered:
            parent_pose = global_pose[bone.parent.name] if bone.parent else Matrix.Identity(3)
            parent_rest = rest[bone.parent.name] if bone.parent else Matrix.Identity(3)
            local_rest = parent_rest.inverted() @ rest[bone.name]
            if bone.name in by_target:
                source_rotation = Matrix(source_rotations[by_target[bone.name]])
                if any(not math.isfinite(value) for row in source_rotation for value in row):
                    raise ValueError("Non-finite source joint rotation")
                desired = source_to_rig @ source_rotation @ source_to_rig.inverted() @ calibrated[bone.name]
                basis = local_rest.inverted() @ parent_pose.inverted() @ desired
                quaternion = basis.to_quaternion().normalized()
                if bone.name in previous_quaternions and quaternion.dot(previous_quaternions[bone.name]) < 0:
                    quaternion.negate()
                previous_quaternions[bone.name] = quaternion.copy()
                pose_bone = rig.pose.bones[bone.name]
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.rotation_quaternion = quaternion
                pose_bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone.name)
                global_pose[bone.name] = desired
            else:
                global_pose[bone.name] = parent_pose @ local_rest
        delta = Vector(root_position)
        delta.y -= source_rest_height
        delta.x, delta.z = (0, 0) if options["in_place"] else (
            root_position[0] - initial_root.x, root_position[2] - initial_root.z)
        delta = source_to_rig @ delta * motion_scale
        parent_pose = global_pose[root_bone.parent.name] if root_bone.parent else Matrix.Identity(3)
        parent_rest = rest[root_bone.parent.name] if root_bone.parent else Matrix.Identity(3)
        local_rest = parent_rest.inverted() @ rest[root_bone.name]
        rig.pose.bones[root_bone.name].location = local_rest.inverted() @ parent_pose.inverted() @ delta
        rig.pose.bones[root_bone.name].keyframe_insert("location", frame=frame, group=root_bone.name)
    from blender_authoring_tools import action_curves

    for _slot, curve in action_curves(action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    context.stash_action(rig)
    signature = [{"name": bone.name, "parent": bone.parent.name if bone.parent else None,
                  "rest": [list(row) for row in bone.matrix_local]} for bone in ordered]
    report = {"bone_map": mapping, "forward_axis": options["forward_axis"], "motion_scale": motion_scale,
              "target_rest_height_m": target_rest_height, "reference_floor_z_m": floor.z,
              "rig_signature": hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest(),
              "reference_alignment_degrees": calibration_angles,
              "unmapped_target_bones": sorted(set(rest) - set(mapping.values())),
              "frames": len(rotations), "source_fps": data["fps"], "target_scene_fps": fps,
              "source_duration_seconds": source_duration, "target_duration_seconds": target_span / fps,
              "duration_rounding_seconds": target_span / fps - source_duration,
              "in_place": options["in_place"], "retarget_solver": "mapped world rotations with reference alignment",
              "contact_review": "pending", "visual_review": "pending"}
    (context.output / "retarget-map.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if "context" in globals():
    retarget(globals()["context"])
