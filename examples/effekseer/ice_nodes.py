"""Original faceted mesh particles for the Effekseer ice example.

This is an authored sequence, not a rigid-body/collision simulation. Coordinates
are Effekseer Y-up units and times are 60 Hz frames. Convert the written OBJ with
the pinned EffekseerResourceConverter before exporting the effect project.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

IMPACT_FRAMES = (62, 72, 84, 96, 112, 126)


def _put(parent: ET.Element, path: str, value: object) -> None:
    for tag in path.split("/"):
        child = parent.find(tag)
        parent = child if child is not None else ET.SubElement(parent, tag)
    parent.text = str(value)


def _value(parent: ET.Element, path: str, value: float) -> None:
    for field in ("Center", "Max", "Min"):
        _put(parent, f"{path}/{field}", round(value, 6))


def _vector(parent: ET.Element, path: str, values: tuple[float, ...]) -> None:
    for axis, value in zip("XYZ", values, strict=True):
        _value(parent, f"{path}/{axis}", value)


def _crystal_obj(destination: Path) -> None:
    """Write a closed 24-triangle crystal with explicit flat face normals."""
    vertices = []
    for y, radius, turn in [(-0.3, 0.53, 0.0), (0.43, 0.39, 0.12)]:
        for index in range(6):
            angle = index * math.tau / 6 + turn
            vertices.append((math.cos(angle) * radius, y, math.sin(angle) * radius))
    vertices.extend([(0.055, -1.0, -0.02), (-0.045, 1.16, 0.035)])
    faces = []
    for index in range(6):
        following = (index + 1) % 6
        faces.extend([
            (12, index, following),
            (13, index + 6, following + 6),
            (index, following, following + 6),
            (index, following + 6, index + 6),
        ])
    lines = ["# Original faceted crystal for the local Effekseer VFX recipe", "o Crystal", "s off"]
    lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices)
    oriented = []
    for face in faces:
        a, b, c = (vertices[index] for index in face)
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        center = [(a[i] + b[i] + c[i]) / 3 for i in range(3)]
        if sum(normal[i] * center[i] for i in range(3)) < 0:
            face = (face[0], face[2], face[1])
            normal = [-value for value in normal]
        length = math.sqrt(sum(value * value for value in normal))
        lines.append("vn " + " ".join(f"{value / length:.6f}" for value in normal))
        oriented.append(face)
    # A harmless UV triplet keeps model converters expecting UVs well-defined.
    lines.extend(["vt 0 0", "vt 1 0", "vt 0.5 1"])
    for normal, face in enumerate(oriented, 1):
        lines.append("f " + " ".join(f"{index + 1}/{uv}/{normal}" for uv, index in enumerate(face, 1)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _model_node(name: str, start: int, life: int, scale: tuple[float, float, float], fragment: bool = False) -> ET.Element:
    node = ET.Element("Node")
    _put(node, "Name", name)
    _put(node, "IsRendered", "True")
    _put(node, "CommonValues/MaxGeneration/Value", 1)
    _put(node, "CommonValues/MaxGeneration/Infinite", "False")
    _value(node, "CommonValues/Life", life)
    _value(node, "CommonValues/GenerationTimeOffset", start)
    _put(node, "CommonValues/RemoveWhenLifeIsExtinct", "True")
    _put(node, "ScalingValues/Type", 0)
    for axis, value in zip("XYZ", scale, strict=True):
        _put(node, f"ScalingValues/Fixed/Scale/{axis}", value)
    _put(node, "DrawingValues/Type", 5)
    _put(node, "DrawingValues/Model/Model", "Model/crystal.efkmodel")
    _put(node, "DrawingValues/Model/Lighting", "True")
    for channel, value in zip("RGBA", (115, 205, 250, 255), strict=True):
        _put(node, f"DrawingValues/Model/Color_Fixed/{channel}", value)
    _put(node, "RendererCommonValues/AlphaBlend", 1 if fragment else 0)
    _put(node, "RendererCommonValues/ZTest", "True")
    _put(node, "RendererCommonValues/ZWrite", "True")
    if fragment:
        _put(node, "RendererCommonValues/FadeOutType", 1)
        _put(node, "RendererCommonValues/FadeOut/Frame", 12)
    ET.SubElement(node, "Children")
    return node


def add_ice_nodes(project: ET.Element, destination: Path) -> None:
    """Append six falling crystals and seven burst fragments per crystal.

    ``destination`` is the effect's directory containing ``source.efkproj``.
    Preserve these model nodes' ZWrite values when changing sprite blend/depth
    settings elsewhere. The six impact events occur at 1.033, 1.2, 1.4, 1.6,
    1.867 and 2.1 seconds. All fragments fade out within another 0.5 seconds,
    while their authored trajectories remain above the ground.
    """
    children = project.find("Root/Children")
    if children is None:
        raise ValueError("Expected an EffekseerProject with Root/Children")
    if any(node.findtext("Name", "").startswith("Authored ice /") for node in children):
        raise ValueError("Original ice nodes have already been appended")
    model_path = destination / "Model" / "crystal.obj"
    if model_path.exists() or model_path.with_suffix(".efkmodel").exists():
        raise FileExistsError("Choose a new effect revision instead of overwriting the crystal source")
    _crystal_obj(model_path)
    positions = [(-2.6, -1.6), (1.3, -1.1), (2.8, 1.1), (-1.4, 1.9), (0.1, 0.1), (-3.0, 1.0)]
    for index, ((x, z), impact) in enumerate(zip(positions, IMPACT_FRAMES, strict=True)):
        life = 38 + index % 3 * 3
        height = 7.2 + index % 3 * 0.8
        radius = 0.72 + index % 3 * 0.10
        crystal = _model_node(f"Authored ice / Hail {index + 1}", impact - life, life, (radius, radius, radius))
        _put(crystal, "LocationValues/Type", 2)
        _vector(crystal, "LocationValues/Easing/Start", (x - 0.55, height, z - 0.25))
        _vector(crystal, "LocationValues/Easing/End", (x, radius, z))
        _put(crystal, "LocationValues/Easing/StartSpeed", -10)
        _put(crystal, "LocationValues/Easing/EndSpeed", 20)
        _put(crystal, "RotationValues/Type", 0)
        _put(crystal, "RotationValues/Fixed/Rotation/Y", index * 41)
        children.append(crystal)
        for piece in range(7):
            angle = piece * math.tau / 7 + index * 0.37
            speed = 0.08 + piece % 3 * 0.025
            size = 0.20 + piece % 3 * 0.065
            fragment = _model_node(f"Authored ice / Impact {index + 1} fragment {piece + 1}", impact, 30, (size, size * 0.8, size * 0.72), True)
            _put(fragment, "LocationValues/Type", 1)
            _vector(fragment, "LocationValues/PVA/Location", (x, 0.7, z))
            _vector(fragment, "LocationValues/PVA/Velocity", (math.cos(angle) * speed, 0.075 + piece % 3 * 0.017, math.sin(angle) * speed))
            _vector(fragment, "LocationValues/PVA/Acceleration", (0, -0.004, 0))
            _put(fragment, "RotationValues/Type", 1)
            _vector(fragment, "RotationValues/PVA/Rotation", (piece * 47, index * 59, piece * 31))
            _vector(fragment, "RotationValues/PVA/Velocity", (4.0 + piece, -3.0 - index, 2.0 + piece))
            children.append(fragment)
