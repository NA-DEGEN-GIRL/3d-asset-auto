"""Reproducible local adaptations of Effekseer's CC0 samples; no paid generation.

Creates editable XML projects and a gallery manifest. Run the pinned conversion
helper separately. This is an example recipe, not a generic effect-authoring API.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from ice_nodes import add_ice_nodes


def put(parent: ET.Element, path: str, value: object) -> ET.Element:
    node = parent
    for name in path.split("/"):
        found = node.find(name)
        node = found if found is not None else ET.SubElement(node, name)
    node.text = str(value)
    return node


def random_value(parent: ET.Element, path: str, center: float, spread: float = 0) -> None:
    for key, value in [("Center", center), ("Max", center + spread), ("Min", center - spread)]:
        put(parent, f"{path}/{key}", value)


def offset_node(node: ET.Element, x: float, z: float, delay: float) -> None:
    """Translate the active location representation, preserving velocity."""
    kind = node.findtext("LocationValues/Type", "0")
    paths = {"0": ["Fixed/Location"], "1": ["PVA/Location"], "2": ["Easing/Start", "Easing/End"]}
    for path in paths.get(kind, []):
        for axis, delta in [("X", x), ("Z", z)]:
            prefix = f"LocationValues/{path}/{axis}"
            if kind == "0":
                put(node, prefix, float(node.findtext(prefix, "0")) + delta)
            else:
                for key in ["Center", "Max", "Min"]:
                    put(node, f"{prefix}/{key}", float(node.findtext(f"{prefix}/{key}", "0")) + delta)
    path = "CommonValues/GenerationTimeOffset"
    item = node.find(path)
    if item is not None and len(item):
        for key in ["Center", "Max", "Min"]:
            put(node, f"{path}/{key}", float(node.findtext(f"{path}/{key}", "0")) + delay)
    else:
        put(node, path, float(node.findtext(path, "0")) + delay)


def copy_resources(project: ET.Element, source: Path, target: Path) -> None:
    """Keep sample-relative resource names and copy only actual references."""
    for node in project.iter():
        if len(node) or not node.text:
            continue
        value = node.text.strip().replace("\\", "/")
        if Path(value).suffix.lower() not in {".png", ".jpg", ".dds", ".wav", ".ogg", ".fbx", ".obj", ".mqo", ".efkmodel", ".efkmat"} or Path(value).is_absolute():
            continue
        candidate = (source / value).resolve()
        if not candidate.is_relative_to(source.resolve()):
            continue
        if candidate.is_file():
            destination = target / value
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            node.text = value
            # The runtime loads the converter's cached model, not the source FBX.
            model = candidate.with_suffix(".efkmodel")
            if model.is_file() and model != candidate:
                shutil.copy2(model, destination.with_suffix(".efkmodel"))
        elif value == "Model/crystal.efkmodel" and (target / "Model/crystal.obj").is_file():
            # Explicit next step in this recipe, before effect conversion.
            continue
        else:
            raise FileNotFoundError(f"Missing sample resource: {value} in {source.name}")


RECIPES = [
    {
        "id": "fire", "source": "01_Pierre02/FireBall.efkproj",
        "name": "홍염의 낙하", "subtitle": "EMBERFALL · FIRE",
        "description": "응축되는 불꽃 → 전진하는 화염탄 → 폭발과 잔불. Pierre의 CC0 FireBall을 게임 공간 크기와 발사 경로에 맞춰 조정한 효과입니다.",
        "duration": 8, "scale": 0.42, "position": [0, 0.08, -3],
        "cameraTarget": [0, 1.8, 1.8], "cameraDistance": 19,
        "events": [{"time": 1.4, "label": "응축"}, {"time": 2.28, "label": "발사"}, {"time": 2.85, "label": "폭발"}, {"time": 4.1, "label": "잔불"}], "color": "#ffa56a",
    },
    {
        "id": "ice", "source": "01_NextSoft01/MagicCold.efkproj",
        "name": "빙결의 비", "subtitle": "FROSTFALL · ICE",
        "description": "6개의 3D 결정체가 시간차로 낙하하고 충격 시점에 42개 파편이 퍼집니다. 원본 결정체 메시와 NextSoft의 CC0 냉기 입자를 결합했습니다. 파괴 시점은 저작된 것이며 실시간 충돌 계산은 아닙니다.",
        "duration": 4.2, "scale": 0.65, "position": [0, 0.12, 0],
        "cameraTarget": [0, 2.7, 0], "cameraDistance": 17,
        "events": [{"time": 0.55, "label": "낙하"}, {"time": 1.15, "label": "첫 파편"}, {"time": 1.6, "label": "연속 파괴"}, {"time": 2.2, "label": "냉기"}], "color": "#81d8ff",
    },
    {
        "id": "lightning", "source": "01_NextSoft01/MagicThunder.efkproj",
        "name": "삼중 낙뢰", "subtitle": "THUNDER TRIAD · LIGHTNING",
        "description": "세 위치에 시차를 두고 떨어지는 번개와 방전 입자. NextSoft의 CC0 번개를 공간적으로 재배치했습니다. 번개 몸체는 입자용 텍스처이며 실시간 충돌 계산은 아닙니다.",
        "duration": 3.2, "scale": 0.35, "position": [0, 0.08, 0],
        "cameraTarget": [0, 2.5, 0], "cameraDistance": 19,
        "events": [{"time": 0.36, "label": "첫 낙뢰"}, {"time": 0.72, "label": "연쇄"}, {"time": 1.08, "label": "잔광"}], "color": "#c9adff",
    },
    {
        "id": "arcane", "source": "01_AndrewFM01/magic_circle.efkproj",
        "name": "비전의 문양", "subtitle": "ARCANE SEAL · SUMMON",
        "description": "지면에 정렬된 동심 고리와 회전 문양. AndrewFM의 CC0 마법진을 유한 수명·등장·퇴장 페이드가 있는 소환 효과로 바꿨습니다.",
        "duration": 5.5, "scale": 3.7, "position": [0, 0.1, 0], "rotation": [-math.pi / 2, 0, 0],
        "cameraTarget": [0, 0.5, 0], "cameraDistance": 14,
        "events": [{"time": 0.5, "label": "등장"}, {"time": 2.4, "label": "회전"}, {"time": 4.75, "label": "소멸"}], "color": "#9db4ff",
    },
]


def author(samples: Path, output: Path) -> None:
    if output.exists():
        raise SystemExit("Choose a new output directory to preserve previous revisions.")
    if not all((samples / recipe["source"]).is_file() for recipe in RECIPES):
        raise SystemExit("Expected Sample/ from the pinned Windows editor bundle.")
    output.mkdir(parents=True)
    manifest = {"version": 1, "title": "Effekseer · 마법 연구실", "effects": []}
    for recipe in RECIPES:
        source = samples / recipe["source"]
        project = ET.parse(source).getroot()
        destination = output / "effects" / recipe["id"]
        destination.mkdir(parents=True)
        children = project.find("Root/Children")
        assert children is not None
        if recipe["id"] == "fire":
            # A shorter forward sweep keeps the projectile and impact in one
            # gameplay-sized view while preserving the sampled expression.
            for value in project.findall("Root/Children/Node/LocationValues/LocationFCurve/FCurve/Keys/Z/*/*"):
                if value.tag in {"Value", "LeftY", "RightY"}:
                    value.text = str(float(value.text) * 0.8)
        elif recipe["id"] == "ice":
            for i, node in enumerate(children.findall("Node")):
                offset_node(node, -1.2 if i % 2 else 0.6, -0.7 if i % 2 else 0.7, i * 5)
                if i < 4:
                    put(node, "CommonValues/MaxGeneration/Value", 42)
            add_ice_nodes(project, destination)
        elif recipe["id"] == "lightning":
            originals = list(children)
            children.clear()
            for i, (x, z) in enumerate([(-4, -1.5), (3.5, -2), (0, 3)]):
                for original in originals:
                    node = copy.deepcopy(original)
                    put(node, "Name", f"Strike {i + 1} / {original.findtext('Name')}")
                    offset_node(node, x, z, 10 + i * 16)
                    children.append(node)
        elif recipe["id"] == "arcane":
            for node in project.findall(".//Node"):
                put(node, "CommonValues/RemoveWhenLifeIsExtinct", "True")
                put(node, "CommonValues/RemoveWhenParentIsRemoved", "True")
                random_value(node, "CommonValues/Life", 300)
                for phase, frames in [("In", 24), ("Out", 40)]:
                    put(node, f"RendererCommonValues/Fade{phase}Type", 1)
                    put(node, f"RendererCommonValues/Fade{phase}/Frame", frames)
                if node.findtext("DrawingValues/Type") == "4":
                    put(node, "DrawingValues/Ring/Billboard", 2)  # Fixed; 3 is RotatedBillboard.
        # Depth testing enables world geometry to occlude transparent particles.
        for node in project.findall(".//Node"):
            common = node.find("RendererCommonValues")
            if common is None:
                continue
            put(common, "ZTest", "True")
            put(common, "ZWrite", "True" if node.findtext("DrawingValues/Type") == "5" else "False")
        put(project, "EndFrame", round(recipe["duration"] * 60))
        copy_resources(project, source.parent, destination)
        ET.indent(project)
        ET.ElementTree(project).write(destination / "source.efkproj", encoding="utf-8", xml_declaration=True)
        notice = (
            f"Adapted from Effekseer 1.80.7 Sample/{recipe['source']}\n"
            "Original effects/textures: CC0, Effekseer and named sample contributors.\n"
            "https://github.com/effekseer/Effekseer/releases/tag/1807\n"
            "Runtime: MIT; preserve the supplied runtime license separately.\n"
        )
        (destination / "ATTRIBUTION.txt").write_text(notice, encoding="utf-8")
        entry = {key: value for key, value in recipe.items() if key != "source"}
        entry.update(url=f"effects/{recipe['id']}/effect.efkefc", seed=42)
        manifest["effects"].append(entry)
    (output / "effects.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    author(args.samples.resolve(), args.out.resolve())
