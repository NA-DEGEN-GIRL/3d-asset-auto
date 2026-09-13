"""Local GeoSAM2 part masks, grounded by points on inspected context renders.

The caller owns the shared GPU lock. Third-party inference runs in its own
environment; the application's Python environment never imports torch.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from .settings import executable
from .store import read_json, write_json

CODE_REPO = "VAST-AI-Research/GeoSAM2"
CODE_REVISION = "b5de23c60ab487d407b623d394a1614f9714761c"
MODEL_REPO = "VAST-AI/GeoSAM2"
MODEL_REVISION = "ba92f5f50418f2fe9af1078448b63176df13b1ee"
MODEL_NAME = "geosam2.pt"
MODEL_SHA256 = "2e391c0d9455fe92b69d61cdc94754d9b8081b9b541d09e1b6a3a55ebf6c6de0"
MODEL_BYTES = 615627435


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def installed(root):
    path = Path(root) / ".runtime" / "installed" / "local-parts.json"
    if not path.is_file():
        raise FileNotFoundError("Local segmentation is not installed; run python scripts/bootstrap_local_parts.py")
    result = read_json(path)
    if result.get("code_revision") != CODE_REVISION or result.get("model_sha256") != MODEL_SHA256:
        raise ValueError("Local segmentation installation pins differ; rerun bootstrap_local_parts.py")
    model = Path(root) / ".runtime" / "local-parts" / MODEL_NAME
    if not model.is_file() or model.stat().st_size != MODEL_BYTES:
        raise FileNotFoundError("Local segmentation checkpoint is missing or incomplete")
    runtime = model.parent
    if not (runtime / ".venv" / "pyvenv.cfg").is_file() or not (runtime / "GeoSAM2" / "sam2" / "build_sam.py").is_file():
        raise FileNotFoundError("Local segmentation Python environment or source is missing")
    return result


def available(root):
    try:
        return {"available": True, **installed(root)}
    except (OSError, ValueError) as error:
        return {"available": False, "reason": str(error), "backend": "geosam2"}


def _run(command, log, cwd, timeout=3600):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with Path(log).open("wb") as stream:
        result = subprocess.run(
            [str(x) for x in command], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
            check=False, timeout=timeout, creationflags=flags,
        )
    if result.returncode:
        tail = Path(log).read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Local segmentation process failed; log: {log}\n{tail}")


def _blender(root, request, out, log_name):
    request_path = Path(out) / f"{log_name}-request.json"
    write_json(request_path, request)
    _run(
        [executable(root, "blender"), "--background", "--factory-startup", "--disable-autoexec",
         "--python-exit-code", "1", "--python", Path(__file__).with_name("blender_parts_context_worker.py"),
         "--", request_path], Path(out) / f"{log_name}.log", root,
    )


def _context(path, source_glb, *, root=None):
    path = Path(path).expanduser()
    if not path.is_absolute() and root is not None:
        path = Path(root) / path
    path = path.resolve()
    if path.is_dir():
        path = path / "context.json"
    data = read_json(path)
    if data.get("source_sha256") != sha256(source_glb):
        raise ValueError("Segmentation context does not match the exact source GLB")
    if data.get("schema") != "asset-auto-geosam2-context-v1":
        raise ValueError("Unsupported local segmentation context schema")
    expected_files = {"canonical.npz", "prepared.blend", "meta.json"}
    expected_files.update(f"{prefix}_{view:04d}.{extension}" for view in range(12)
                          for prefix, extension in (("color", "png"), ("normal", "png"), ("depth", "exr")))
    if set(data.get("files", {})) != expected_files:
        raise ValueError("Segmentation context must certify geometry and all twelve rendered views")
    for name in sorted(expected_files):
        file = path.parent / name
        expected = data["files"][name]
        if not file.is_file() or file.stat().st_size != expected.get("bytes") or sha256(file) != expected.get("sha256"):
            raise ValueError(f"Segmentation context file changed or is incomplete: {name}")
    meta = read_json(path.parent / "meta.json")
    if meta.get("resolution") != 1024 or len(meta.get("transforms", [])) != 12:
        raise ValueError("GeoSAM2 requires a twelve-view context at 1024 pixels")
    return path, data


def prepare(root, source_glb, outputdir):
    root, source_glb, outputdir = Path(root).resolve(), Path(source_glb).resolve(), Path(outputdir).resolve()
    outputdir.mkdir(parents=True, exist_ok=True)
    if (outputdir / "context.json").exists():
        path, data = _context(outputdir, source_glb)
        return {**data, "context": str(path)}
    _blender(root, {"action": "prepare", "source": str(source_glb), "output": str(outputdir)}, outputdir, "prepare")
    path, data = _context(outputdir, source_glb)
    return {**data, "context": str(path)}


def _linux_path(path, distro):
    if os.name != "nt":
        return str(Path(path).resolve())
    return subprocess.check_output(
        ["wsl.exe", "-d", distro, "--exec", "wslpath", "-a", "-u", Path(path).resolve().as_posix()],
        text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).strip()


def segment(root, request, out, source_glb):
    root, out, source_glb = Path(root).resolve(), Path(out).resolve(), Path(source_glb).resolve()
    spec = request.model_dump() if hasattr(request, "model_dump") else dict(request)
    context_path, context = _context(spec["segmentation_context"], source_glb, root=root)
    install = installed(root)
    out.mkdir(parents=True, exist_ok=True)
    binding = {"source_sha256": sha256(source_glb), "context_sha256": sha256(context_path), "request": spec}
    binding_hash = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    checkpoint = out / "local-parts.json"
    if checkpoint.exists():
        previous = read_json(checkpoint)
        if previous.get("binding_sha256") != binding_hash:
            raise ValueError("Local segmentation resume request/context differs from the checkpoint")
        generated_name = previous.get("generated_file", "generated.glb")
        if generated_name not in ("generated.glb", "generated.blend"):
            raise ValueError("Unexpected segmentation output in checkpoint")
        if previous.get("state") == "complete" and (out / generated_name).is_file():
            if sha256(out / generated_name) == previous.get("generated_sha256"):
                return previous
            raise ValueError("Completed segmentation output hash differs from checkpoint")
    metadata = {
        "provider": "local", "backend": "geosam2", "license": "Apache-2.0",
        "code_revision": CODE_REVISION, "model_revision": MODEL_REVISION, "model_sha256": MODEL_SHA256,
        "binding_sha256": binding_hash, "source_sha256": binding["source_sha256"],
        "context_sha256": binding["context_sha256"], "state": "inference",
        "semantic_review": "pending", "semantic_names_source": "agent points on observed context render",
        "source_geometry_preserved": True, "textures_preserved": True,
    }
    write_json(checkpoint, metadata)
    distro = install.get("wsl_distribution", "Ubuntu-24.04")
    runtime = root / ".runtime" / "local-parts"
    if sha256(runtime / MODEL_NAME) != MODEL_SHA256:
        raise ValueError("Local segmentation checkpoint checksum changed; rerun bootstrap_local_parts.py")
    command_request = {
        "context": _linux_path(context_path.parent, distro), "output": _linux_path(out, distro),
        "code": _linux_path(runtime / "GeoSAM2", distro), "checkpoint": _linux_path(runtime / MODEL_NAME, distro),
        "view": spec.get("segmentation_view", 0), "parts": spec["segmentation_parts"],
        "source_sha256": binding["source_sha256"], "binding_sha256": binding_hash,
    }
    request_path = out / "geosam2-request.json"
    write_json(request_path, command_request)
    worker = Path(__file__).with_name("local_parts_inference_worker.py")
    python_path = _linux_path(runtime / ".venv" / "bin" / "python", distro)
    command = [python_path, _linux_path(worker, distro), _linux_path(request_path, distro)]
    if os.name == "nt":
        command = ["wsl.exe", "-d", distro, "--exec", *command]
    _run(command, out / "geosam2.log", root)
    report = read_json(out / "inference-report.json")
    if report.get("binding_sha256") != binding_hash:
        raise ValueError("Segmentation inference output has an unexpected request binding")
    names = {str(part["id"]): part["name"] for part in report["parts"] if part["faces"] > 0}
    if not names:
        raise ValueError("GeoSAM2 found no supported faces for the observed parts; inspect masks and revise prompts")
    _blender(root, {"action": "segment", "context": str(context_path.parent),
                   "face_labels": str(out / "face-labels.npy"), "names": names, "output": str(out)}, out, "split")
    metadata.update({"state": "complete", "generated_file": "generated.blend",
                     "generated_sha256": sha256(out / "generated.blend"),
                     "glb_sha256": sha256(out / "generated.glb"),
                     "inference": report, "segmentation": read_json(out / "segment-report.json"),
                     "context_topology_sha256": context.get("canonical_sha256"),
                     "warnings": report.get("warnings", []) + [
                         (f"Local segmentation retained {report['evidence']['unknown_faces']} unclassified faces "
                          f"({report['evidence']['unknown_fraction']:.1%}); inspect part boundaries and names."),
                     ]})
    write_json(checkpoint, metadata)
    return metadata
