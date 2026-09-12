"""Rigid scene transforms that preserve embedded GLB geometry and image bytes."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path


def rotate_scene_y(source, target, degrees):
    """Wrap scene roots in shared Y-rotation parents, preserving existing nodes and BIN chunks."""
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError("A prepared GLB must use a separate output file")
    if not isinstance(degrees, (int, float)) or isinstance(degrees, bool) or not math.isfinite(degrees):
        raise ValueError("GLB yaw must be a finite number")
    raw = source.read_bytes()
    if len(raw) < 20 or struct.unpack_from("<4sII", raw) != (b"glTF", 2, len(raw)):
        raise ValueError("Invalid GLB 2.0 header or length")
    chunks = []
    offset = 12
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError("Truncated GLB chunk header")
        length, kind = struct.unpack_from("<I4s", raw, offset)
        end = offset + 8 + length
        if length % 4 or end > len(raw):
            raise ValueError("Invalid GLB chunk length")
        chunks.append((kind, raw[offset + 8:end]))
        offset = end
    if chunks[0][0] != b"JSON" or sum(kind == b"JSON" for kind, _ in chunks) != 1:
        raise ValueError("GLB must begin with one JSON chunk")
    if degrees == 0:
        temporary = target.with_name(target.name + ".part")
        temporary.write_bytes(raw)
        temporary.replace(target)
        return
    try:
        document = json.loads(chunks[0][1])
    except (ValueError, UnicodeError):
        raise ValueError("Invalid GLB JSON chunk") from None
    if not isinstance(document, dict):
        raise ValueError("Invalid GLB scene document")  # noqa: TRY004 - malformed file data, not argument type
    nodes = document.setdefault("nodes", [])
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise ValueError("Invalid GLB nodes")
    node_count = len(nodes)

    def indices(value):
        if (
            not isinstance(value, list)
            or any(not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < node_count for index in value)
        ):
            raise ValueError("Invalid GLB scene node references")
        return value

    child_nodes = {index for node in nodes for index in indices(node.get("children", []))}
    if not document.get("scenes"):
        document["scenes"] = [{"nodes": [index for index in range(node_count) if index not in child_nodes]}]
        document["scene"] = 0
    scenes = document["scenes"]
    if not isinstance(scenes, list) or any(not isinstance(scene, dict) for scene in scenes):
        raise ValueError("Invalid GLB scenes")
    radians = math.radians(degrees) / 2
    wrappers = {}
    for scene in scenes:
        roots = indices(scene.get("nodes", []))
        prepared_roots = []
        for root in roots:
            if root not in wrappers:
                wrappers[root] = len(nodes)
                nodes.append({
                    "name": "TripoRigInput", "children": [root],
                    "rotation": [0, math.sin(radians), 0, math.cos(radians)],
                })
            prepared_roots.append(wrappers[root])
        scene["nodes"] = prepared_roots
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    chunks[0] = (b"JSON", encoded)
    body = b"".join(struct.pack("<I4s", len(data), kind) + data for kind, data in chunks)
    prepared = struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(prepared)
    temporary.replace(target)
