"""Pinned, isolated Kimodo runtime. Importing this module never loads GPU models."""

import hashlib
import os
from pathlib import Path

from .store import child, read_json

SOURCE_REPO = "https://github.com/nv-tlabs/kimodo.git"
SOURCE_REV = "1aece8c124d73d255ceff5086d983b844c9f4e94"
MODEL_NAME = "Kimodo-SOMA-RP-v1.1"
PYTHON_VERSION = "3.11.13"
MODEL_PINS = {
    "motion": ("nvidia/Kimodo-SOMA-RP-v1.1", "6c9233af1180b8151e3c4703477104af5dce9dd5"),
    "base": ("meta-llama/Meta-Llama-3-8B-Instruct", "8afb486c1db24fe5011ec46dfbe5b5dccdb575c2"),
    "mntp": ("McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp", "31474e395ada192e8ed1586db6be79fb3b70c9c0"),
    "supervised": ("McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
                   "baa8ebf04a1c2500e61288e7dad65e8ae42601a7"),
}
SOMA_JOINTS = {"Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head", "HeadEnd", "Jaw"} | {
    side + part for side in ("Left", "Right") for part in (
        "Eye", "Shoulder", "Arm", "ForeArm", "Hand", "Leg", "Shin", "Foot", "ToeBase", "ToeEnd")
} | {side + "Hand" + finger + suffix for side in ("Left", "Right")
     for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
     for suffix in (("1", "2", "3", "End") if finger == "Thumb" else ("1", "2", "3", "4", "End"))}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def installation(root):
    path = root / ".runtime/installed/kimodo.json"
    if not path.is_file():
        raise FileNotFoundError("Kimodo unavailable. Run python scripts/bootstrap_kimodo.py")
    value = read_json(path)
    if not value.get("ready") or value.get("source_revision") != SOURCE_REV:
        raise RuntimeError("Kimodo setup is incomplete or uses another source pin; run scripts/bootstrap_kimodo.py")
    runtime = root / ".runtime/kimodo"
    for relative in (".venv/pyvenv.cfg", "source/kimodo/model/kimodo_model.py"):
        if not (runtime / relative).is_file():
            raise FileNotFoundError(f"Kimodo runtime is missing {relative}")
    (runtime / ".venv/bin/python").lstat()
    if value.get("models") != {name: {"repository": repo, "revision": rev} for name, (repo, rev) in MODEL_PINS.items()}:
        raise ValueError("Kimodo model pins do not match the supported runtime")
    files = value["files"]
    if not files or any(not any(item["path"].startswith(f"models/{name}/") for item in files) for name in MODEL_PINS):
        raise ValueError("Kimodo model inventory is incomplete")
    for item in files:
        path = child(runtime, *item["path"].split("/"))
        if not path.is_file() or path.stat().st_size != item["size_bytes"]:
            raise FileNotFoundError(f"Kimodo model file is missing or changed: {item['path']}")
    return value


def capability(root):
    try:
        value = installation(root)
        return {"available": True, "local": True, "backend": "kimodo", "model": MODEL_NAME,
                "source_revision": value["source_revision"], "inference_verified": value.get("inference_verified", False)}
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {"available": False, "local": True, "backend": "kimodo", "reason": str(error)}


def worker_command(root, script, request, installed):
    runtime = root / ".runtime/kimodo"
    if installed.get("platform") == "wsl":
        from .local_rig import wsl_path

        distro = installed["wsl_distribution"]
        folder, program, spec = (wsl_path(path, distro) for path in (runtime, script, request))
        return ["wsl", "--distribution", distro, "--exec", folder + "/.venv/bin/python",
                "-u", program, "--runtime", folder, "--request", spec]
    if os.name == "nt":
        raise ValueError("Use the WSL Kimodo installation on Windows")
    return [str(runtime / ".venv/bin/python"), "-u", str(script), "--runtime", str(runtime),
            "--request", str(request)]
