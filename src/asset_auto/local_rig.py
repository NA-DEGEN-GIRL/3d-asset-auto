"""Local learned skeleton and weight prediction using an isolated SkinTokens runtime."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .store import now, read_json, write_json


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def installation(root):
    path = root / ".runtime/installed/local-rig.json"
    if not path.is_file():
        raise FileNotFoundError("Local rigging unavailable. Run python scripts/bootstrap_local_rig.py")
    value = read_json(path)
    if not value.get("ready") or value.get("backend") != "skintokens":
        raise RuntimeError("Local rigging installation has not passed its GPU readiness check")
    runtime = root / ".runtime/local-rig"
    required = [runtime / ".venv/pyvenv.cfg", runtime / "source/demo.py",
                runtime / "source/src/model/tokenrig.py", root / "scripts/local_rig/run.py",
                root / "scripts/local_rig/helper.py"]
    for required_path in required:
        if not required_path.is_file():
            raise FileNotFoundError(f"Local rigging installation is incomplete: {required_path}")
    # Windows cannot follow a Linux symlink in WSL's venv. Check the link itself and its managed binary.
    (runtime / ".venv/bin/python").lstat()
    if not any(path.is_file() and path.stat().st_size for path in (runtime / "python").glob("*/bin/python3.11")):
        raise FileNotFoundError("The isolated local rig Python interpreter is missing")
    for checkpoint in value["checkpoints"]:
        checkpoint_path = runtime / "source" / checkpoint["path"]
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Local rigging checkpoint is missing: {checkpoint['path']}")
        if checkpoint.get("size_bytes") is not None and checkpoint_path.stat().st_size != checkpoint["size_bytes"]:
            raise RuntimeError(f"Local rigging checkpoint size changed: {checkpoint['path']}")
    return value


def capability(root):
    try:
        installed = installation(root)
        return {"available": True, "backend": "skintokens", "local": True,
                "minimum_vram_gb": 14, "source_revision": installed["source_revision"]}
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {"available": False, "backend": "skintokens", "reason": str(error)}


def wsl_path(path, distro):
    return subprocess.run(
        ["wsl", "--distribution", distro, "--exec", "wslpath", "-a", str(path.resolve())],
        check=True, capture_output=True, text=True, encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ).stdout.strip()


def command(root, out, source_glb, installed, run_id=None):
    runtime = root / ".runtime/local-rig"
    script = root / "scripts/local_rig/run.py"
    if installed.get("platform") == "wsl":
        distro = installed["wsl_distribution"]
        paths = [wsl_path(path, distro) for path in (runtime, script, source_glb, out / "generated.glb")]
        runtime_path, script_path, source_path, target_path = paths
        result = ["wsl", "--distribution", distro, "--exec", runtime_path + "/.venv/bin/python",
                "-u", script_path, "--source-root", runtime_path + "/source", "--input", source_path,
                "--output", target_path, "--seed", "42", "--num-beams", "10"]
    else:
        result = [str(runtime / ".venv/bin/python"), "-u", str(script), "--source-root", str(runtime / "source"),
            "--input", str(source_glb), "--output", str(out / "generated.glb"),
            "--seed", "42", "--num-beams", "10"]
    if run_id:
        result.extend(["--run-id", run_id])
    return result


def validate_output(target):
    with target.open("rb") as stream:
        header = stream.read(12)
    if len(header) != 12 or struct.unpack("<4sII", header) != (b"glTF", 2, target.stat().st_size):
        raise ValueError("Local rigging returned an invalid GLB")


def child_is_running(root, out, source_glb, installed):
    args = command(root, out, source_glb, installed)
    args = args[:args.index("--source-root")]
    directory = wsl_path(out, installed["wsl_distribution"]) if installed.get("platform") == "wsl" else str(out)
    result = subprocess.run(
        [*args, "--probe-lock", directory], check=True, capture_output=True, text=True,
        timeout=60, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.stdout.strip() not in ("busy", "free"):
        raise RuntimeError("Cannot reconcile the local rig worker lock")
    return result.stdout.strip() == "busy"


def recover(root, out, source_glb, installed, expected):
    path = out / "local-rig.json"
    if not path.is_file():
        if (out / "generated.glb").exists():
            raise RuntimeError("Unrecorded local rig output preserved; use a new revision")
        return None
    previous = read_json(path)
    for key in ("source_sha256", "source_revision", "model_revision", "request_sha256", "seed", "num_beams"):
        if previous.get(key) != expected[key]:
            raise RuntimeError("Existing local rig output belongs to another source, model or request")
    if previous.get("checkpoints") != expected["checkpoints"]:
        raise RuntimeError("Existing local rig output uses different checkpoint hashes")
    if (previous.get("runtime_fingerprint") is not None
            and previous["runtime_fingerprint"] != expected["runtime_fingerprint"]):
        raise RuntimeError("Existing local rig output uses a different patched runtime")
    target = out / "generated.glb"
    receipt_path = out / "local-rig-child.json"
    receipt = read_json(receipt_path) if receipt_path.exists() else {}
    same_receipt = receipt.get("run_id") == previous.get("run_id")
    if receipt.get("state") == "exported" and same_receipt and not target.exists():
        run_id = previous["run_id"]
        if uuid.UUID(run_id).hex != run_id:
            raise RuntimeError("Invalid local rig receipt run identifier")
        for key in ("source_sha256", "source_revision", "model_revision", "request_sha256"):
            if receipt.get(key) != expected[key]:
                raise RuntimeError("Local rig worker receipt does not match its request")
        if (previous.get("runtime_fingerprint") is not None
                and receipt.get("runtime_fingerprint") != previous["runtime_fingerprint"]):
            raise RuntimeError("Local rig worker receipt does not match its runtime")
        if child_is_running(root, out, source_glb, installed):
            raise RuntimeError("Local rig worker is finalizing its GLB; resume after completion")
        partial = out / f"generated-{run_id}.partial.glb"
        validate_output(partial)
        if sha256(partial) != receipt["output_sha256"]:
            raise RuntimeError("Local rig worker partial output hash changed")
        partial.rename(target)
        receipt["state"] = "completed"
        write_json(receipt_path, receipt)
    if previous["state"] == "completed":
        validate_output(target)
        if sha256(target) != previous["output_sha256"]:
            raise RuntimeError("Completed local rig output changed; preserving it")
        return previous
    if (receipt.get("state") in ("exported", "completed") and target.exists()
            and receipt.get("run_id") == previous.get("run_id")):
        for key in ("source_sha256", "source_revision", "model_revision", "request_sha256"):
            if receipt.get(key) != expected[key]:
                raise RuntimeError("Local rig worker receipt does not match its request")
        if (previous.get("runtime_fingerprint") is not None
                and receipt.get("runtime_fingerprint") != previous["runtime_fingerprint"]):
            raise RuntimeError("Local rig worker receipt does not match its runtime")
        validate_output(target)
        if sha256(target) != receipt["output_sha256"]:
            raise RuntimeError("Local rig worker output hash changed")
        previous.update(state="completed", output_sha256=receipt["output_sha256"],
                        completed_at=receipt["completed_at"])
        write_json(path, previous)
        return previous
    worker_failed = receipt.get("state") == "failed" and receipt.get("run_id") == previous.get("run_id")
    if previous["state"] == "running" and not worker_failed:
        age = (datetime.now(UTC) - datetime.fromisoformat(previous["started_at"])).total_seconds()
        # The timeout includes interpreter/import startup. A missing receipt can be a launch in progress.
        if age < 1900 or child_is_running(root, out, source_glb, installed):
            raise RuntimeError("Local rig worker is active or reconciling; resume after its receipt completes")
    elif child_is_running(root, out, source_glb, installed):
        raise RuntimeError("Local rig worker is still running; resume after completion")
    suffix = previous.get("run_id", uuid.uuid4().hex)
    if uuid.UUID(suffix).hex != suffix:
        raise RuntimeError("Invalid local rig run identifier")
    write_json(out / f"local-rig-{suffix}.json", previous)
    if target.exists():
        target.rename(out / f"generated-{suffix}.partial.glb")
    return None


def generate(root, request, out, source_glb):
    """Write generated.glb and sanitized provenance; the caller owns the shared GPU lock."""
    root, out, source_glb = Path(root).resolve(), Path(out).resolve(), Path(source_glb).resolve()
    installed = installation(root)
    runtime = root / ".runtime/local-rig"
    for checkpoint in installed["checkpoints"]:
        path = runtime / "source" / checkpoint["path"]
        if not path.is_file() or sha256(path) != checkpoint["sha256"]:
            raise RuntimeError("SkinTokens checkpoint changed or missing; rerun its bootstrap")
    for patch in installed["patches"]:
        if sha256(runtime / "source" / patch["path"]) != patch["sha256"]:
            raise RuntimeError("SkinTokens runtime patch changed; reconcile before running inference")
    out.mkdir(parents=True, exist_ok=True)
    target = out / "generated.glb"
    source_hash = sha256(source_glb)
    request_data = request.model_dump(mode="json") if hasattr(request, "model_dump") else (request or {})
    request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
    runtime_identity = {
        "source_revision": installed["source_revision"], "model_revision": installed["model_revision"],
        "checkpoints": installed["checkpoints"], "patches": installed["patches"],
        "dependency_freeze_sha256": installed.get("dependency_freeze_sha256"),
        "runner_sha256": sha256(root / "scripts/local_rig/run.py"),
    }
    helper = root / "scripts/local_rig/helper.py"
    if helper.exists():
        runtime_identity["helper_sha256"] = sha256(helper)
    fingerprint = hashlib.sha256(json.dumps(runtime_identity, sort_keys=True).encode()).hexdigest()
    metadata = {
        "provider": "local", "backend": "skintokens", "operation": "rig",
        "source_sha256": source_hash, "source_revision": installed["source_revision"],
        "model_revision": installed["model_revision"], "checkpoints": installed["checkpoints"],
        "seed": 42, "num_beams": 10, "use_transfer": True, "credits_consumed": 0,
        "request_sha256": request_hash, "run_id": uuid.uuid4().hex,
        "runtime": runtime_identity, "runtime_fingerprint": fingerprint,
        "state": "running", "started_at": now(),
    }
    recovered = recover(root, out, source_glb, installed, metadata)
    if recovered is not None:
        return recovered
    write_json(out / "local-rig.json", metadata)
    log = out / "local-rig.log"
    try:
        with log.open("wb") as stream:
            result = subprocess.run(
                command(root, out, source_glb, installed, metadata["run_id"]),
                stdout=stream, stderr=subprocess.STDOUT,
                timeout=1850, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
    except (OSError, subprocess.TimeoutExpired):
        metadata.update(state="failed", completed_at=now())
        write_json(out / "local-rig.json", metadata)
        raise
    if result.returncode:
        metadata.update(state="failed", completed_at=now())
        write_json(out / "local-rig.json", metadata)
        detail = log.read_text(encoding="utf-8", errors="replace")[-3500:]
        raise RuntimeError(f"Local rigging failed; inspect {log}\n{detail}")
    validate_output(target)
    if sha256(source_glb) != source_hash:
        raise RuntimeError("Source GLB changed during local rigging")
    metadata.update(state="completed", output_sha256=sha256(target), completed_at=now())
    write_json(out / "local-rig.json", metadata)
    return metadata
