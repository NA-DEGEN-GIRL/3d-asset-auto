"""Read-only, exact decoded-data comparison of GLB clips and their model context.

This detects unintended export/resampling changes; it is not a motion-quality
judge or a sampled equivalence test for differently encoded animations.
"""

from __future__ import annotations

import copy
import hashlib
import json
import struct

from .animation_merge import _COMPONENTS, _Glb, _no_extensions
from .models import AnimationComparisonRequest


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _accessor(model, index, cache):
    if index not in cache:
        rows = model.values(index)
        accessor = model.accessors[index]
        code = _COMPONENTS[accessor["componentType"]][0]
        pack = struct.Struct("<" + code * len(rows[0])).pack
        digest = hashlib.sha256()
        for row in rows:
            digest.update(pack(*row))
        cache[index] = {"component_type": accessor["componentType"], "type": accessor["type"],
                        "count": accessor["count"], "normalized": accessor.get("normalized", False),
                        "values_sha256": digest.hexdigest()}
    return cache[index]


def _model_context(model, cache):
    """Conservative core glTF model identity, independent of accessor buffer packing."""
    document = copy.deepcopy(model.document)
    for key in ("asset", "animations", "accessors", "bufferViews", "buffers"):
        document.pop(key, None)
    _no_extensions(document)
    if document.get("extensionsUsed") or document.get("extensionsRequired"):
        raise ValueError("Model context uses extensions; core glTF comparison cannot verify them")
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            primitive["attributes"] = {key: _accessor(model, index, cache)
                                       for key, index in primitive["attributes"].items()}
            if "indices" in primitive:
                primitive["indices"] = _accessor(model, primitive["indices"], cache)
            if "targets" in primitive:
                primitive["targets"] = [{key: _accessor(model, index, cache) for key, index in target.items()}
                                        for target in primitive["targets"]]
    for skin in document.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = _accessor(model, skin["inverseBindMatrices"], cache)
    for image in document.get("images", []):
        if "bufferView" in image:
            view, payload = model.view(image.pop("bufferView"))
            _no_extensions(view)
            image["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    return {key: _digest(value) for key, value in document.items()}


def _clip(model, animation, cache):
    model.validate_animation(animation)
    channels, starts, ends = {}, [], []
    for channel in animation["channels"]:
        target = channel["target"]
        identity = model.identity(target["node"])
        if identity is None or len(model.identities[identity]) != 1:
            raise ValueError("Clip comparison needs unambiguous named target hierarchies")
        sampler = animation["samplers"][channel["sampler"]]
        times = model.values(sampler["input"])
        starts.append(times[0][0])
        ends.append(times[-1][0])
        item = {"interpolation": sampler.get("interpolation", "LINEAR"),
                "times": _accessor(model, sampler["input"], cache),
                "values": _accessor(model, sampler["output"], cache)}
        if target["path"] == "weights":
            item["morph_targets"] = model.morphs(target["node"])[0]
        channels[(*identity, target["path"])] = item
    summary = {"start_seconds": min(starts), "end_seconds": max(ends),
               "span_seconds": max(ends) - min(starts), "channels": len(channels),
               "key_count": sum(item["times"]["count"] for item in channels.values()),
               "data_sha256": _digest(sorted(channels.items()))}
    return summary, channels


def compare(before_path, after_path, *, changed_clips=()):
    """Compare every clip; declared edits do not exempt the shared rig/model.

    No files, revisions or reviews are written. Even identical clip channels do
    not establish preserved appearance when the model context changed.
    """
    before, after = _Glb(before_path), _Glb(after_path)
    names = set(before.by_name) | set(after.by_name)
    if (not isinstance(changed_clips, (list, tuple))
            or any(not isinstance(name, str) or not name.strip() for name in changed_clips)
            or len(changed_clips) != len(set(changed_clips))):
        raise ValueError("changed_clips must contain unique nonblank clip names")
    unknown = set(changed_clips) - names
    if unknown:
        raise ValueError(f"Declared changed clips do not exist in either input: {sorted(unknown)}")
    caches = [{}, {}]
    clips = {}
    for name in sorted(names):
        snapshots = [_clip(model, model.by_name[name], cache) if name in model.by_name else None
                     for model, cache in zip((before, after), caches)]
        left, right = snapshots
        differences = []
        if left is None:
            status = "added"
        elif right is None:
            status = "removed"
        else:
            for target in sorted(set(left[1]) | set(right[1])):
                old, new = left[1].get(target), right[1].get(target)
                fields = (["added_channel"] if old is None else ["removed_channel"] if new is None
                          else [key for key in old.keys() | new.keys() if old.get(key) != new.get(key)])
                if fields:
                    differences.append({"target": list(target[:-1]), "path": target[-1],
                                        "changed": sorted(fields)})
            status = "changed" if differences else "identical"
        clips[name] = {"declared_edit": name in changed_clips, "status": status,
                       "before": left[0] if left else None, "after": right[0] if right else None,
                       "channel_differences": differences}
    try:
        contexts = [_model_context(model, cache) for model, cache in zip((before, after), caches)]
        sections = sorted(key for key in contexts[0].keys() | contexts[1].keys()
                          if contexts[0].get(key) != contexts[1].get(key))
        context = {"status": "changed" if sections else "identical", "changed_sections": sections,
                   "before_sha256": _digest(contexts[0]), "after_sha256": _digest(contexts[1])}
    except (ValueError, KeyError, TypeError, IndexError) as error:
        context = {"status": "unverified", "reason": str(error)}
    protected = sorted(set(before.by_name) - set(changed_clips))
    unexpected = [name for name, item in clips.items()
                  if not item["declared_edit"] and item["status"] != "identical"]
    if unexpected or context["status"] == "changed":
        status = "changed"
    elif not protected:
        status = "no_protected_clips"
    elif context["status"] == "unverified":
        status = "unverified"
    else:
        status = "preserved"
    return {
        "backend": "gltf-clip-comparison-v1",
        "before": {"path": str(before.path), "sha256": before.sha256},
        "after": {"path": str(after.path), "sha256": after.sha256},
        "declared_changed_clips": list(changed_clips), "protected_clips": protected,
        "unexpected_changed_clips": unexpected, "preservation_status": status,
        "model_context": context, "clips": clips, "visual_review": "untested",
        "limitations": [
            "Exact decoded channel data, interpolation and core model context; no motion-quality approval.",
            "Changed data may be equivalent resampling; compare poses at matching seconds in Blender to resolve.",
            "No evaluated vertex, contact, rendering or engine comparison. Usage sidecars are not compared.",
            "Model metadata or node/index reordering can conservatively report a context change.",
        ],
    }


def compare_request(root, request: AnimationComparisonRequest):
    from .pipeline import input_path

    return compare(input_path(root, request.before, {".glb"}), input_path(root, request.after, {".glb"}),
                   changed_clips=request.changed_clips)
