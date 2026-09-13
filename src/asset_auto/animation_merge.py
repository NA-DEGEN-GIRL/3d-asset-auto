"""Merge compatible glTF clips without rewriting the base mesh or duplicating models.

This is clip transfer on an identical named hierarchy/rest rig, not retargeting.
Only core glTF animation channels are supported; source animation/accessor
extensions are rejected rather than silently dropping their semantics.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
import uuid
from itertools import pairwise
from pathlib import Path

_COMPONENTS = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
               5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
_IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
_TOLERANCE = 1e-5


def _integer(value, label, *, minimum=0):
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"Invalid {label}")
    return value


def _item(items, index, label):
    index = _integer(index, label)
    if index >= len(items):
        raise ValueError(f"Invalid {label} reference")
    return items[index]


def _objects(document, key):
    result = document.get(key, [])
    if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
        raise ValueError(f"Invalid glTF {key}")
    return result


def _no_extensions(value):
    if isinstance(value, dict):
        if value.get("extensions"):
            raise ValueError("Animation transfer does not support extensions on animation data")
        for key, child in value.items():
            if key != "extras":
                _no_extensions(child)
    elif isinstance(value, list):
        for child in value:
            _no_extensions(child)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON property: {key}")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError(f"Non-finite GLB JSON value: {value}")


def _numbers(value, length, label):
    if not isinstance(value, (list, tuple)) or len(value) != length or any(
        isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number)
        for number in value
    ):
        raise ValueError(f"Invalid {label}")
    return value


def _close(left, right):
    return len(left) == len(right) and all(abs(a - b) <= _TOLERANCE for a, b in zip(left, right))


def _multiply(left, right):
    return [sum(left[k * 4 + row] * right[column * 4 + k] for k in range(4))
            for column in range(4) for row in range(4)]


def _inverse(matrix):
    rows = [[matrix[column * 4 + row] for column in range(4)]
            + [int(row == column) for column in range(4)] for row in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("Singular skin bind matrix")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [number / divisor for number in rows[column]]
        for row in range(4):
            if row != column:
                factor = rows[row][column]
                rows[row] = [number - factor * value for number, value in zip(rows[row], rows[column])]
    return [rows[row][column + 4] for column in range(4) for row in range(4)]


def _position_set_matches(left, right):
    # Import/export may duplicate seam vertices. Compare geometric positions
    # bidirectionally, allowing only the same tight tolerance as bind matrices.
    def contained(points, other):
        cells = {}
        for point in other:
            key = tuple(math.floor(value / _TOLERANCE) for value in point)
            cells.setdefault(key, []).append(point)
        for point in points:
            key = tuple(math.floor(value / _TOLERANCE) for value in point)
            if not any(_close(point, candidate)
                       for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)
                       for candidate in cells.get((key[0] + x, key[1] + y, key[2] + z), [])):
                return False
        return True
    return bool(left and right) and contained(left, right) and contained(right, left)


def _matrix(node):
    if "matrix" in node:
        if any(key in node for key in ("translation", "rotation", "scale")):
            raise ValueError("Node cannot contain both matrix and TRS rest transforms")
        return _numbers(node["matrix"], 16, "node matrix")
    translation = _numbers(node.get("translation", [0, 0, 0]), 3, "node translation")
    x, y, z, w = _numbers(node.get("rotation", [0, 0, 0, 1]), 4, "node rotation")
    if abs(x*x + y*y + z*z + w*w - 1) > 1e-4:
        raise ValueError("Node rest rotation must be a unit quaternion")
    scale = _numbers(node.get("scale", [1, 1, 1]), 3, "node scale")
    return [(1 - 2*y*y - 2*z*z)*scale[0], (2*x*y + 2*z*w)*scale[0], (2*x*z - 2*y*w)*scale[0], 0,
            (2*x*y - 2*z*w)*scale[1], (1 - 2*x*x - 2*z*z)*scale[1], (2*y*z + 2*x*w)*scale[1], 0,
            (2*x*z + 2*y*w)*scale[2], (2*y*z - 2*x*w)*scale[2], (1 - 2*x*x - 2*y*y)*scale[2], 0,
            *translation, 1]


class _Glb:
    def __init__(self, path):
        self.path = Path(path).resolve()
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if len(raw) < 20 or struct.unpack_from("<4sII", raw) != (b"glTF", 2, len(raw)):
            raise ValueError("Invalid GLB 2.0 header or payload length")
        chunks, offset = [], 12
        while offset < len(raw):
            if offset + 8 > len(raw):
                raise ValueError("Truncated GLB chunk header")
            size, kind = struct.unpack_from("<I4s", raw, offset)
            end = offset + 8 + size
            if size % 4 or end > len(raw):
                raise ValueError("Invalid GLB chunk payload")
            chunks.append((kind, raw[offset + 8:end]))
            offset = end
        if [kind for kind, _ in chunks] not in ([b"JSON"], [b"JSON", b"BIN\0"]):
            raise ValueError("Expected one JSON chunk and optional embedded BIN chunk")
        try:
            self.document = json.loads(chunks[0][1], object_pairs_hook=_json_object,
                                       parse_constant=_nonfinite)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid GLB JSON") from error
        if (not isinstance(self.document, dict) or not isinstance(self.document.get("asset"), dict)
                or self.document["asset"].get("version") != "2.0"):
            raise ValueError("Expected a glTF 2.0 document")
        self.binary = chunks[1][1] if len(chunks) == 2 else b""
        buffers = _objects(self.document, "buffers")
        if len(buffers) > 1 or any("uri" in buffer for buffer in buffers):
            raise ValueError("Animation merge requires a self-contained GLB buffer")
        if any("uri" in image and not str(image["uri"]).startswith("data:")
               for image in _objects(self.document, "images")):
            raise ValueError("Animation merge requires embedded images, not external image URIs")
        length = _integer(buffers[0].get("byteLength"), "buffer byteLength") if buffers else 0
        if length > len(self.binary) or len(self.binary) - length > 3:
            raise ValueError("GLB embedded buffer length does not match BIN payload")
        self.binary = self.binary[:length]
        self.accessors = _objects(self.document, "accessors")
        self.views = _objects(self.document, "bufferViews")
        self.nodes = _objects(self.document, "nodes")
        self.skins = _objects(self.document, "skins")
        self.animations = _objects(self.document, "animations")
        for index in range(len(self.views)):
            self.view(index)
        self.parents = {}
        for index, node in enumerate(self.nodes):
            _matrix(node)
            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError("Invalid node hierarchy")  # noqa: TRY004 -- malformed file data
            for child in children:
                _item(self.nodes, child, "child node")
                if child in self.parents:
                    raise ValueError("Ambiguous node hierarchy: a node has multiple parents")
                self.parents[child] = index
        self.paths = {}
        self.identities = {}
        for index in range(len(self.nodes)):
            identity = self.identity(index)
            if identity is not None:
                self.identities.setdefault(identity, []).append(index)
        names = [animation.get("name") for animation in self.animations]
        if any(not isinstance(name, str) or not name.strip() or "\0" in name for name in names):
            raise ValueError("Every animation clip must have a nonempty name")
        if len(names) != len(set(names)):
            raise ValueError("Duplicate animation clip names")
        self.by_name = dict(zip(names, self.animations))

    def identity(self, index, visiting=None):
        if index in self.paths:
            return self.paths[index]
        visiting = set() if visiting is None else visiting
        if index in visiting:
            raise ValueError("Cyclic node hierarchy")
        visiting.add(index)
        node = _item(self.nodes, index, "node")
        name = node.get("name")
        parent = self.parents.get(index)
        prefix = () if parent is None else self.identity(parent, visiting)
        result = (*prefix, name) if prefix is not None and isinstance(name, str) and name else None
        self.paths[index] = result
        visiting.remove(index)
        return result

    def view(self, index):
        view = _item(self.views, index, "bufferView")
        if view.get("buffer") != 0 or isinstance(view.get("buffer"), bool):
            raise ValueError("Invalid bufferView buffer")
        offset = _integer(view.get("byteOffset", 0), "bufferView offset")
        length = _integer(view.get("byteLength"), "bufferView length", minimum=1)
        if offset + length > len(self.binary):
            raise ValueError("bufferView exceeds embedded buffer")
        return view, self.binary[offset:offset + length]

    def values(self, index):
        accessor = _item(self.accessors, index, "accessor")
        _no_extensions(accessor)
        component = accessor.get("componentType")
        kind = accessor.get("type")
        if component not in _COMPONENTS or kind not in _WIDTHS:
            raise ValueError("Unsupported accessor type")
        count = _integer(accessor.get("count"), "accessor count", minimum=1)
        code, size = _COMPONENTS[component]
        width = _WIDTHS[kind]
        # Matrix column padding matters for 8/16-bit MAT2/MAT3. Animation data
        # and inverse bind matrices only use float components.
        if kind.startswith("MAT") and component != 5126:
            raise ValueError("Non-float matrix accessor is unsupported")
        element_size = size * width

        def decode(view_index, offset, length, fmt, item_size, *, sparse=False):
            view, payload = self.view(view_index)
            _no_extensions(view)
            offset = _integer(offset, "accessor byteOffset")
            stride = _integer(view.get("byteStride", item_size), "accessor stride", minimum=item_size)
            if sparse and "byteStride" in view:
                raise ValueError("Sparse bufferViews must not be interleaved")
            alignment = struct.calcsize(fmt[-1])
            if offset % alignment or (view.get("byteOffset", 0) + offset) % alignment or stride % alignment:
                raise ValueError("Misaligned accessor data")
            if "byteStride" in view and (stride < 4 or stride > 252 or stride % 4):
                raise ValueError("Invalid interleaved bufferView stride")
            if offset + (length - 1) * stride + item_size > len(payload):
                raise ValueError("Accessor exceeds bufferView payload")
            return [struct.unpack_from(fmt, payload, offset + row * stride) for row in range(length)]

        if "bufferView" in accessor:
            values = decode(accessor["bufferView"], accessor.get("byteOffset", 0), count,
                            "<" + code * width, element_size)
        else:
            if accessor.get("byteOffset", 0):
                raise ValueError("Accessor without bufferView must not have byteOffset")
            values = [(0,) * width for _ in range(count)]
        if "sparse" in accessor:
            sparse = accessor["sparse"]
            sparse_count = _integer(sparse.get("count"), "sparse count", minimum=1)
            if sparse_count > count:
                raise ValueError("Sparse count exceeds accessor count")
            indices, replacements = sparse.get("indices", {}), sparse.get("values", {})
            index_type = indices.get("componentType")
            if index_type not in (5121, 5123, 5125):
                raise ValueError("Invalid sparse indices type")
            index_code, index_size = _COMPONENTS[index_type]
            rows = decode(indices.get("bufferView"), indices.get("byteOffset", 0), sparse_count,
                          "<" + index_code, index_size, sparse=True)
            replacement_values = decode(replacements.get("bufferView"), replacements.get("byteOffset", 0),
                                        sparse_count, "<" + code * width, element_size, sparse=True)
            previous = -1
            for (row,), value in zip(rows, replacement_values):
                if row <= previous or row >= count:
                    raise ValueError("Sparse indices must be strictly increasing and within accessor count")
                values[row] = value
                previous = row
        if any(not math.isfinite(number) for value in values for number in value):
            raise ValueError("Non-finite animation/accessor payload")
        return values

    def morphs(self, node_index):
        node = _item(self.nodes, node_index, "morph target node")
        mesh = _item(_objects(self.document, "meshes"), node.get("mesh"), "morph mesh")
        names = mesh.get("extras", {}).get("targetNames")
        if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("Morph animation requires explicit semantic targetNames")
        if len(names) != len(set(names)):
            raise ValueError("Ambiguous morph target names")
        primitives = _objects(mesh, "primitives")
        if not primitives or any(len(primitive.get("targets", [])) != len(names) for primitive in primitives):
            raise ValueError("Morph target layout does not match semantic targetNames")
        defaults = node.get("weights", mesh.get("weights", [0] * len(names)))
        return names, _numbers(defaults, len(names), "default morph weights")

    def positions(self, node_index):
        node = _item(self.nodes, node_index, "mesh node")
        mesh = _item(_objects(self.document, "meshes"), node.get("mesh"), "mesh")
        positions = []
        for primitive in _objects(mesh, "primitives"):
            _no_extensions(primitive)
            index = primitive.get("attributes", {}).get("POSITION")
            accessor = _item(self.accessors, index, "mesh positions")
            if accessor.get("type") != "VEC3" or accessor.get("componentType") != 5126:
                raise ValueError("Bind-space verification requires float mesh positions")
            positions.extend(self.values(index))
        return positions

    def validate_animation(self, animation):
        _no_extensions(animation)
        channels, samplers = _objects(animation, "channels"), _objects(animation, "samplers")
        if not channels or not samplers:
            raise ValueError("Animation requires channels and samplers")
        seen, ends = set(), []
        for channel in channels:
            target = channel.get("target", {})
            node_index, path = target.get("node"), target.get("path")
            node = _item(self.nodes, node_index, "animation target node")
            if path not in ("translation", "rotation", "scale", "weights"):
                raise ValueError("Unsupported animation target path")
            if path != "weights" and "matrix" in node:
                raise ValueError("Animated TRS target must not contain a matrix")
            if (node_index, path) in seen:
                raise ValueError("Duplicate animation target channel")
            seen.add((node_index, path))
            sampler = _item(samplers, channel.get("sampler"), "animation sampler")
            interpolation = sampler.get("interpolation", "LINEAR")
            if interpolation not in ("LINEAR", "STEP", "CUBICSPLINE"):
                raise ValueError("Invalid animation interpolation")
            input_accessor = _item(self.accessors, sampler.get("input"), "animation input")
            output_accessor = _item(self.accessors, sampler.get("output"), "animation output")
            if input_accessor.get("type") != "SCALAR" or input_accessor.get("componentType") != 5126:
                raise ValueError("Animation times must use float SCALAR values")
            if input_accessor.get("normalized") or output_accessor.get("normalized"):
                raise ValueError("Animation float accessors must not be normalized")
            times = [value[0] for value in self.values(sampler["input"])]
            if times[0] < 0 or any(left >= right for left, right in pairwise(times)):
                raise ValueError("Animation times must be nonnegative and strictly increasing")
            for key, actual in (("min", times[0]), ("max", times[-1])):
                declared = _numbers(input_accessor.get(key), 1, f"animation time {key}")
                if not _close(declared, [actual]):
                    raise ValueError("Animation time bounds do not match the actual keyframes")
            if interpolation == "CUBICSPLINE" and len(times) < 2:
                raise ValueError("Cubic animation requires at least two keys")
            expected_type = "SCALAR" if path == "weights" else ("VEC4" if path == "rotation" else "VEC3")
            if output_accessor.get("type") != expected_type or output_accessor.get("componentType") != 5126:
                raise ValueError("Animation output type does not match target channel")
            values = self.values(sampler["output"])
            multiplier = 3 if interpolation == "CUBICSPLINE" else 1
            weights = len(self.morphs(node_index)[0]) if path == "weights" else 1
            if len(values) != len(times) * multiplier * weights:
                raise ValueError("Animation output count does not match input keys")
            if path == "rotation":
                rotations = values[1::3] if multiplier == 3 else values
                if any(abs(sum(number * number for number in value) - 1) > 1e-3 for value in rotations):
                    raise ValueError("Animation rotation keys must be unit quaternions")
            ends.append(times[-1])
        if {channel["sampler"] for channel in channels} != set(range(len(samplers))):
            raise ValueError("Animation contains unused samplers")
        return {"name": animation["name"], "duration_seconds": max(ends), "channels": len(channels)}


def _mapping(base, source, animations):
    mapped = {}

    def match(index):
        if index in mapped:
            return mapped[index]
        identity = source.identity(index)
        candidates = base.identities.get(identity, [])
        if identity is None or len(source.identities.get(identity, [])) != 1 or len(candidates) != 1:
            raise ValueError("Animated rig nodes require unambiguous matching hierarchy and names")
        target = candidates[0]
        if not _close(_matrix(source.nodes[index]), _matrix(base.nodes[target])):
            raise ValueError(f"Incompatible rest transform for {'/'.join(identity)}; retargeting is required")
        mapped[index] = target
        if index in source.parents:
            match(source.parents[index])
        return target

    def skin_signature(model, skin, *, donor):
        _no_extensions(skin)
        joints = skin.get("joints", [])
        if not isinstance(joints, list) or not joints or len(set(joints)) != len(joints):
            raise ValueError("Invalid skin joint mapping")
        for joint in joints:
            _item(model.nodes, joint, "skin joint")
        mapped_joints = [match(joint) if donor else joint for joint in joints]
        if "inverseBindMatrices" in skin:
            accessor = _item(model.accessors, skin["inverseBindMatrices"], "inverse bind matrices")
            if accessor.get("type") != "MAT4" or accessor.get("componentType") != 5126:
                raise ValueError("Invalid inverse bind matrix accessor")
            matrices = model.values(skin["inverseBindMatrices"])
            if len(matrices) != len(joints):
                raise ValueError("Inverse bind matrix count does not match joints")
        else:
            matrices = [_IDENTITY] * len(joints)
        skeleton = skin.get("skeleton")
        if skeleton is not None:
            skeleton = match(skeleton) if donor else _integer(skeleton, "skin skeleton")
        return dict(zip(mapped_joints, matrices)), skeleton

    def bind_space_matches(source_index, base_index, signature, base_signature):
        anchor = next(iter(signature))
        correction = _multiply(_inverse(base_signature[anchor]), signature[anchor])
        if not _close([correction[index] for index in (3, 7, 11, 15)], [0, 0, 0, 1]):
            return False
        if not all(_close(matrix, _multiply(base_signature[joint], correction))
                   for joint, matrix in signature.items()):
            return False
        mesh_nodes = [index for index, node in enumerate(source.nodes) if node.get("skin") == source_index]
        if not mesh_nodes:
            return False
        for index in mesh_nodes:
            target = match(index)
            if base.nodes[target].get("skin") != base_index:
                return False
            points = source.positions(index)
            transformed = [tuple(sum(correction[column * 4 + row] * point[column] for column in range(3))
                                 + correction[12 + row] for row in range(3)) for point in points]
            if not _position_set_matches(base.positions(target), transformed):
                return False
        return True

    skin_map = {}
    for index, skin in enumerate(source.skins):
        signature, skeleton = skin_signature(source, skin, donor=True)
        candidates = []
        for base_index, base_skin in enumerate(base.skins):
            base_signature, base_skeleton = skin_signature(base, base_skin, donor=False)
            if signature.keys() != base_signature.keys() or skeleton != base_skeleton:
                continue
            # Blender can bake a shared parent transform into vertices and
            # right-multiply every inverse bind by its inverse on export. This
            # is equivalent only if the common bind correction also exactly
            # reconciles the mesh positions. Never relax individual binds.
            exact = all(_close(matrix, base_signature[joint]) for joint, matrix in signature.items())
            if exact or bind_space_matches(index, base_index, signature, base_signature):
                candidates.append(base_index)
        if len(candidates) != 1:
            raise ValueError("Incompatible or ambiguous skin bind mapping; explicit retargeting is required")
        skin_map[index] = candidates[0]
    for index, node in enumerate(source.nodes):
        if "skin" in node:
            target = match(index)
            _item(source.skins, node["skin"], "node skin")
            if base.nodes[target].get("skin") != skin_map[node["skin"]]:
                raise ValueError("Skinned mesh node uses a different rig")
    for animation in animations:
        for channel in animation["channels"]:
            target = channel["target"]
            index = target["node"]
            target_index = match(index)
            if target["path"] != "weights":
                # Matching composed matrices alone is insufficient: a rotation
                # channel replaces only R, so equivalent R/S decompositions can
                # yield different motion when combined with the retained S.
                source_node, base_node = source.nodes[index], base.nodes[target_index]
                if "matrix" in base_node:
                    raise ValueError("Animated target requires matching TRS component defaults")
                for key, default in (("translation", [0, 0, 0]), ("scale", [1, 1, 1])):
                    if not _close(source_node.get(key, default), base_node.get(key, default)):
                        raise ValueError("Animated target has incompatible rest TRS component defaults")
                rotation = source_node.get("rotation", [0, 0, 0, 1])
                base_rotation = base_node.get("rotation", [0, 0, 0, 1])
                if not (_close(rotation, base_rotation)
                        or _close(rotation, [-number for number in base_rotation])):
                    raise ValueError("Animated target has incompatible rest rotation components")
            if target["path"] == "weights":
                names, defaults = source.morphs(index)
                base_names, base_defaults = base.morphs(target_index)
                if names != base_names or not _close(defaults, base_defaults):
                    raise ValueError("Incompatible semantic morph target layout or rest weights")
    return mapped


def merge(base_path, sources, output_path, *, on_conflict="error"):
    """Append selected clips to one base GLB, preserving its original model data.

    ``sources`` contains ``{path, clips: list[str] | None, rename: dict[str, str]}``.
    ``clips=None`` selects all named clips. Duplicate final names fail unless
    ``on_conflict='replace'`` explicitly replaces that clip in the base/output.
    Inputs are immutable. A failed validation never replaces the output file.
    """
    if on_conflict not in ("error", "replace"):
        raise ValueError("on_conflict must be error or replace")
    if not isinstance(sources, list) or not sources:
        raise ValueError("At least one animation source is required")
    base = _Glb(base_path)
    output_path = Path(output_path).resolve()
    if output_path == base.path:
        raise ValueError("Merged GLB must not overwrite its source")
    document = copy.deepcopy(base.document)
    animations = document.setdefault("animations", [])
    binary = bytearray(base.binary)
    for animation in base.animations:
        base.validate_animation(animation)
    source_reports = []
    for options in sources:
        if not isinstance(options, dict) or "path" not in options:
            raise ValueError("Each animation source requires a path")
        source = _Glb(options["path"])
        if output_path == source.path:
            raise ValueError("Merged GLB must not overwrite its source")
        selected = options.get("clips")
        if selected is None:
            selected = list(source.by_name)
        if not isinstance(selected, list) or not selected or any(not isinstance(name, str) for name in selected):
            raise ValueError("Clip selection must contain named source clips")
        if len(selected) != len(set(selected)) or any(name not in source.by_name for name in selected):
            raise ValueError("Unknown or duplicate selected animation clips")
        rename = options.get("rename", {})
        if not isinstance(rename, dict) or any(name not in selected for name in rename) or any(
            not isinstance(name, str) or not name.strip() or "\0" in name for name in rename.values()
        ):
            raise ValueError("Invalid clip rename mapping")
        final_names = [rename.get(name, name) for name in selected]
        if len(final_names) != len(set(final_names)):
            raise ValueError("Renamed clips have duplicate names")
        selected_animations = [source.by_name[name] for name in selected]
        for animation in selected_animations:
            source.validate_animation(animation)
        node_map = _mapping(base, source, selected_animations)
        accessor_map, view_map = {}, {}

        def copy_view(index, view_map=view_map, source=source):
            if index not in view_map:
                view, payload = source.view(index)
                _no_extensions(view)
                view = copy.deepcopy(view)
                binary.extend(b"\0" * (-len(binary) % 4))
                view["buffer"], view["byteOffset"] = 0, len(binary)
                binary.extend(payload)
                views = document.setdefault("bufferViews", [])
                view_map[index] = len(views)
                views.append(view)
            return view_map[index]

        def copy_accessor(index, accessor_map=accessor_map, source=source, copy_view=copy_view):
            if index not in accessor_map:
                accessor = copy.deepcopy(source.accessors[index])
                if "bufferView" in accessor:
                    accessor["bufferView"] = copy_view(accessor["bufferView"])
                if "sparse" in accessor:
                    for key in ("indices", "values"):
                        piece = accessor["sparse"][key]
                        piece["bufferView"] = copy_view(piece["bufferView"])
                accessors = document.setdefault("accessors", [])
                accessor_map[index] = len(accessors)
                accessors.append(accessor)
            return accessor_map[index]

        for original, name in zip(selected_animations, final_names):
            animation = copy.deepcopy(original)
            animation["name"] = name
            existing = next((i for i, item in enumerate(animations) if item["name"] == name), None)
            if existing is not None and on_conflict != "replace":
                raise ValueError(f"Animation clip already exists: {name}; rename or explicitly replace it")
            for sampler in animation["samplers"]:
                sampler["input"] = copy_accessor(sampler["input"])
                sampler["output"] = copy_accessor(sampler["output"])
            for channel in animation["channels"]:
                channel["target"]["node"] = node_map[channel["target"]["node"]]
            if existing is None:
                animations.append(animation)
            else:
                animations[existing] = animation
        source_reports.append({"path": str(source.path), "sha256": source.sha256,
                               "clips": [{"source": old, "name": new} for old, new in zip(selected, final_names)]})
    buffers = document.setdefault("buffers", [{"byteLength": 0}])
    if not buffers:
        buffers.append({"byteLength": 0})
    buffers[0]["byteLength"] = len(binary)
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary.extend(b"\0" * (-len(binary) % 4))
    body = struct.pack("<I4s", len(encoded), b"JSON") + encoded
    body += struct.pack("<I4s", len(binary), b"BIN\0") + binary
    raw = struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.part")
    try:
        temporary.write_bytes(raw)
        merged = _Glb(temporary)
        clips = [merged.validate_animation(animation) for animation in merged.animations]
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"backend": "gltf-compatible-clip-merge-v1", "base": {"path": str(base.path), "sha256": base.sha256},
            "sources": source_reports, "output_sha256": hashlib.sha256(raw).hexdigest(),
            "on_conflict": on_conflict, "clips": clips,
            "preservation": {"base_binary_prefix_unchanged": True, "model_copies_added": 0,
                             "meshes": len(document.get("meshes", [])), "skins": len(document.get("skins", [])),
                             "materials": len(document.get("materials", [])), "rest_transforms_unchanged": True}}
