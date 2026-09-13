"""Small conveniences for trusted agent-authored Blender scripts.

This is an authoring API, not a sandbox. Scripts may use the full local bpy API.
"""

from copy import deepcopy
from pathlib import Path

import blender_character_worker as character
import bpy


def action_curves(action):
    """Iterate both current slotted and legacy action curves."""
    if action.is_action_layered:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", ()):
                    for curve in bag.fcurves:
                        yield bag.slot_handle, curve
    else:
        for curve in action.fcurves:
            yield 0, curve


def stash_action(owner, name=None):
    """Bind an active action/slot to a muted NLA track for clip export."""
    animation = owner.animation_data
    if animation is None or animation.action is None:
        return None
    action, slot = animation.action, animation.action_slot
    label = name or action.name
    if name is not None:
        action.name = name
        if action.name != name:
            raise ValueError(f"Action name already exists: {name!r}")
    action.use_fake_user = True
    existing = next((track for track in animation.nla_tracks
                     if any(strip.action == action and strip.action_slot == slot for strip in track.strips)),
                    None)
    if existing is None:
        existing = animation.nla_tracks.new()
        strip = existing.strips.new(label, int(action.frame_range[0]), action)
        if slot is not None:
            strip.action_slot = slot
    existing.name, existing.mute, existing.is_solo = label, True, False
    animation.action_slot = None
    animation.action = None
    return action


class AuthoringContext:
    """Injected as the global ``context`` in the snapshotted authoring script.

    Coordinates are Blender Z-up meters. ``objects`` maps actual scene names to
    bpy objects, and ``armatures`` lists current armatures. ``parameters`` is the
    request's JSON dictionary. Source/output are absolute pathlib Paths.

    Call ``capture_rest`` after deliberate object rest-transform or default morph
    edits and before keyframing them. Rig edit-mode changes, mesh coordinates,
    weights and materials do not need that call. ``reset_pose`` returns animated
    objects/morphs/bones to captured defaults without deleting their clips.
    ``new_action`` avoids name collisions and stores prior clips. Direct bpy is
    also supported; scripts must retain correctly bound actions/slots themselves.
    """

    def __init__(self, source, output, parameters):
        self.source = Path(source).resolve()
        self.output = Path(output).resolve()
        self.parameters = deepcopy(parameters)

    @property
    def objects(self):
        return {obj.name: obj for obj in bpy.context.scene.objects}

    @property
    def armatures(self):
        return [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]

    def capture_rest(self):
        """Record current node/default morph values as the intended rest state."""
        character.capture_preview_defaults(use_imported_rest=False)
        # glTF's old import snapshot must not override these defaults when the
        # newly saved source.blend is reopened for a later authoring revision.
        for obj in bpy.context.scene.objects:
            if obj.is_property_set("gltf2_animation_rest"):
                obj.property_unset("gltf2_animation_rest")
            if hasattr(obj, "gltf2_animation_weight_rest"):
                obj.gltf2_animation_weight_rest.clear()

    def reset_pose(self):
        for owner in character.animation_owners():
            stash_action(owner)
        # A script may deliberately remove scene objects. Their old RNA handles
        # must not be dereferenced while resetting surviving objects.
        current = set(bpy.context.scene.objects)
        character._preview_defaults = {obj: defaults for obj, defaults in character._preview_defaults.items()
                                       if obj in current}
        character.select_preview_clip(None)
        for rig in self.armatures:
            rig.data.pose_position = "POSE"
        bpy.context.view_layer.update()

    def stash_action(self, owner, name=None):
        return stash_action(owner, name)

    def new_action(self, owner, name):
        """Start a unique named clip on an object or mesh shape-key datablock."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A nonempty action name is required")
        if bpy.data.actions.get(name) is not None:
            raise ValueError(f"Action name already exists: {name!r}; use a new name or explicitly edit that action")
        previous = character._preview_defaults.copy()
        character.capture_preview_defaults(use_imported_rest=False)
        # New pivot/control objects need a rest snapshot before their first key.
        # Existing objects retain their explicit/source rest defaults.
        character._preview_defaults.update(previous)
        self.reset_pose()
        animation = owner.animation_data_create()
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        animation.action = action
        animation.action_slot = action.slots.new(owner.id_type, owner.name)
        return action

    def bake_action(self, owner, name, frame_start, frame_end, *, only_selected=False, clear_constraints=True):
        """Bake evaluated constraints/retarget motion to a named object/pose clip.

        Set up constraints and source playback first. This keeps the evaluated
        scene alive while bpy bakes, then stashes the resulting action. By default
        constraints are removed from the target after their motion is baked.
        """
        if frame_end <= frame_start:
            raise ValueError("Baking needs an increasing frame interval")
        if bpy.data.actions.get(name) is not None:
            raise ValueError(f"Action name already exists: {name!r}")
        if owner.animation_data and owner.animation_data.action:
            previous, slot = owner.animation_data.action, owner.animation_data.action_slot
            stash_action(owner)
            # Keep its evaluated motion while baking, but bind the old clip to a
            # track before bpy replaces the owner's active action.
            owner.animation_data.action = previous
            owner.animation_data.action_slot = slot
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        owner.select_set(True)
        bpy.context.view_layer.objects.active = owner
        bpy.ops.nla.bake(frame_start=int(frame_start), frame_end=int(frame_end), step=1,
                         only_selected=only_selected, visual_keying=True, clear_constraints=clear_constraints,
                         clear_parents=False, use_current_action=False, clean_curves=False,
                         bake_types={"POSE", "OBJECT"} if owner.type == "ARMATURE" else {"OBJECT"})
        if owner.animation_data is None or owner.animation_data.action is None:
            raise ValueError("Baking produced no target action")
        return stash_action(owner, name)
