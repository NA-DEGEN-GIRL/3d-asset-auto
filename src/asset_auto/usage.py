"""Portable usage contracts, bound to exact GLB bytes; never quality approvals."""

from copy import deepcopy

from .models import AssetUsage
from .store import Store, read_json, write_json


def load_usage(directory, digest):
    path = directory / "usage.json"
    if not path.exists():
        return None
    record = read_json(path)
    if record.get("source_sha256") != digest:
        raise ValueError("Usage metadata belongs to different GLB bytes; reassess with an explicit usage contract")
    return AssetUsage.model_validate(record["usage"]).model_dump()


def inherit(root, out, manifest, parent, processing):
    if not parent:
        return
    original = Store(root).revision(manifest["asset_id"], parent)
    previous = read_json(original / "manifest.json")
    usage = load_usage(original, previous["files"]["asset.glb"]["sha256"])
    if processing and processing.get("operation") == "merge-animations":
        for index, source in enumerate(processing["sources"]):
            donor = None
            item = processing["inputs"][index + 1]
            if origin := item.get("origin"):
                directory = Store(root).revision(origin["asset_id"], origin["revision"])
                donor = load_usage(directory, item["sha256"])
            for clip in source["clips"]:
                if usage:
                    usage["clips"].pop(clip["name"], None)
                if donor and clip["source"] in donor["clips"]:
                    if usage is None:
                        usage = AssetUsage().model_dump()
                    usage["clips"][clip["name"]] = deepcopy(donor["clips"][clip["source"]])
    if usage is None:
        return
    names = {clip["name"] for clip in manifest["inspection"].get("animations", {}).get("clips", [])}
    usage["clips"] = {name: clip for name, clip in usage["clips"].items() if name in names}
    write_json(out / "usage.json", {"version": 1, "source_sha256": manifest["files"]["asset.glb"]["sha256"],
                                    "usage": usage, "status": "inherited_requires_reassessment",
                                    "inherited_from": {"asset_id": manifest["asset_id"], "revision": parent},
                                    "note": "Intent only; changed geometry/timing/targets require confirmation. No evidence inherited."})
