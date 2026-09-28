"""Private host resource policy, resolved without importing any model/CUDA runtime.

Configuration is read-only. Only ``apply_process_resources`` changes this process,
and only its Linux affinity/nice/OOM controls. GPU and thread settings belong to
individual child environments so one runtime cannot contaminate the next.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

RUNTIMES = ("trellis", "kimodo", "local_rig", "local_parts", "blender")
CUDA_ONLY = frozenset(RUNTIMES) - {"blender"}
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
GPU_UUID = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
TOP_KEYS = {"version", "gpu", "protected_gpus", "cpus", "threads", "nice", "oom_score_adj",
            "max_parallel_blender", "runtimes"}
RUNTIME_KEYS = {"gpu", "threads", "allow_protected"}
TOP_KEYS |= {"wait_timeout_seconds", "poll_interval_seconds"}
DEFAULT_POLL_INTERVAL_SECONDS = 2


class ResourcePolicyError(ValueError):
    """An explicit resource policy is invalid or cannot be honored safely."""


def _integer(value, label, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        interval = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise ResourcePolicyError(f"{label} must be an integer {interval}")


def _uuids(value, label, *, empty=False):
    if not isinstance(value, list) or (not value and not empty):
        raise ResourcePolicyError(f"{label} must be a {'possibly empty ' if empty else 'nonempty '}list of GPU UUIDs")
    if any(not isinstance(item, str) or not GPU_UUID.fullmatch(item) for item in value):
        raise ResourcePolicyError(f"{label} accepts full GPU UUIDs only; numeric indices are not supported")
    if len({item.lower() for item in value}) != len(value):
        raise ResourcePolicyError(f"{label} contains duplicate GPU UUIDs")


def _gpu(value, label):
    if isinstance(value, str) and value in ("auto", "cpu"):
        return
    _uuids(value, label)


def parse_cpus(value):
    """Expand a nonempty comma-separated CPU/range list without altering affinity."""
    if not isinstance(value, str) or not value.strip():
        raise ResourcePolicyError("cpus must be a nonempty CPU range string, for example 0-3,6")
    result = set()
    for token in value.split(","):
        token = token.strip()
        if not re.fullmatch(r"[0-9]+(?:-[0-9]+)?", token):
            raise ResourcePolicyError("cpus must contain CPU numbers or ascending inclusive ranges")
        bounds = token.split("-")
        first, last = int(bounds[0]), int(bounds[-1])
        if first > last or last > 1048575:
            raise ResourcePolicyError("cpus contains a descending or unreasonably large range")
        result.update(range(first, last + 1))
    return sorted(result)


def _validate(value, label="resources", *, runtime=None):
    if not isinstance(value, dict):
        raise ResourcePolicyError(f"{label} must be an object")
    allowed = TOP_KEYS if runtime is None else RUNTIME_KEYS | (
        {"text_encoder_device"} if runtime == "kimodo" else set())
    unknown = set(value) - allowed
    if unknown:
        raise ResourcePolicyError(f"Unknown {label} fields: {', '.join(sorted(unknown))}")
    if "version" in value and (type(value["version"]) is not int or value["version"] != 1):
        raise ResourcePolicyError(f"{label}.version must be 1")
    if "gpu" in value:
        _gpu(value["gpu"], f"{label}.gpu")
    if "protected_gpus" in value:
        _uuids(value["protected_gpus"], f"{label}.protected_gpus", empty=True)
    if "cpus" in value:
        parse_cpus(value["cpus"])
    for key in ("threads", "max_parallel_blender"):
        if key in value:
            _integer(value[key], f"{label}.{key}", 1)
    if "nice" in value:
        _integer(value["nice"], f"{label}.nice", -20, 19)
    if "oom_score_adj" in value:
        _integer(value["oom_score_adj"], f"{label}.oom_score_adj", -1000, 1000)
    for key in ("wait_timeout_seconds", "poll_interval_seconds"):
        if key in value:
            duration = value[key]
            if duration is None and key == "wait_timeout_seconds":
                continue
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                raise ResourcePolicyError(f"{label}.{key} must be a positive finite number"
                                          + (" or null" if key == "wait_timeout_seconds" else ""))
    if "allow_protected" in value and type(value["allow_protected"]) is not bool:
        raise ResourcePolicyError(f"{label}.allow_protected must be a boolean")
    if "text_encoder_device" in value and value["text_encoder_device"] not in ("cpu", "cuda"):
        raise ResourcePolicyError(f"{label}.text_encoder_device must be cpu or cuda")
    if "runtimes" in value:
        if not isinstance(value["runtimes"], dict):
            raise ResourcePolicyError(f"{label}.runtimes must be an object")
        for name, override in value["runtimes"].items():
            if name not in RUNTIMES:
                raise ResourcePolicyError(f"Unknown resource runtime: {name}")
            _validate(override, f"{label}.runtimes.{name}", runtime=name)


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ResourcePolicyError(f"Duplicate JSON field: {key}")
        value[key] = item
    return value


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_json_object)
    except (OSError, ValueError) as error:
        raise ResourcePolicyError(f"Cannot read resource configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise ResourcePolicyError(f"Resource configuration must be an object: {path}")
    return value


def _load(root):
    policy = {"version": 1, "gpu": "auto"}
    sources = {"version": "default", "gpu": "default"}

    def merge(layer, source):
        _validate(layer)
        for key, value in layer.items():
            if key == "runtimes":
                for runtime, override in value.items():
                    policy.setdefault("runtimes", {}).setdefault(runtime, {}).update(copy.deepcopy(override))
                    sources.update({f"runtimes.{runtime}.{field}": source for field in override})
            else:
                policy[key] = copy.deepcopy(value)
                sources[key] = source

    local = Path(root) / "asset-system.local.json"
    if local.exists():
        conf = _read(local)
        if "resources" in conf:
            merge(conf["resources"], str(local))
    explicit = os.environ.get("ASSET_AUTO_RESOURCES_FILE")
    if explicit is not None and not explicit.strip():
        raise ResourcePolicyError("ASSET_AUTO_RESOURCES_FILE must name a file")
    directory = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    host = Path(explicit).expanduser() if explicit is not None else directory / "codex-skill-runtimes/resources.json"
    if explicit is not None or host.exists():
        merge(_read(host), str(host))
    for key, variable in (("gpu", "ASSET_AUTO_GPU"), ("cpus", "ASSET_AUTO_CPUS"),
                          ("threads", "ASSET_AUTO_THREADS")):
        if variable not in os.environ:
            continue
        value = os.environ[variable].strip()
        if key == "gpu" and value not in ("auto", "cpu"):
            value = [part.strip() for part in value.split(",")]
        if key == "threads":
            if not re.fullmatch(r"[0-9]+", value):
                raise ResourcePolicyError("ASSET_AUTO_THREADS must be a positive integer")
            value = int(value)
        merge({key: value}, f"env:{variable}")
    return policy, sources


def load(root):
    """Return the strictly validated merged policy; this never changes process state."""
    return _load(root)[0]


def resolve(root, runtime=None):
    """Resolve one runtime, retaining field provenance. Environment overrides win."""
    if runtime is not None and runtime not in RUNTIMES:
        raise ResourcePolicyError(f"Unknown resource runtime: {runtime}")
    policy, sources = _load(root)
    effective = {key: copy.deepcopy(value) for key, value in policy.items() if key != "runtimes"}
    effective_sources = {key: value for key, value in sources.items() if not key.startswith("runtimes.")}
    if runtime is not None:
        for key, value in policy.get("runtimes", {}).get(runtime, {}).items():
            if effective_sources.get(key, "").startswith("env:ASSET_AUTO_"):
                continue
            effective[key] = copy.deepcopy(value)
            effective_sources[key] = sources[f"runtimes.{runtime}.{key}"]
    if "cpus" in effective:
        requested = parse_cpus(effective["cpus"])
        if sys.platform.startswith("linux") and hasattr(os, "sched_getaffinity"):
            allowed = os.sched_getaffinity(0)
            if not set(requested).issubset(allowed):
                raise ResourcePolicyError("Configured cpus are outside this process's current allowed affinity")
    return {"effective": effective, "sources": effective_sources, "runtime": runtime}


def inventory():
    """Read physical GPU UUIDs and capacity through nvidia-smi, with no CUDA probe."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=uuid,name,memory.total", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        devices = []
        for row in csv.reader(io.StringIO(result.stdout), skipinitialspace=True):
            if not row or not any(part.strip() for part in row):
                continue
            if len(row) != 3:
                raise ValueError("nvidia-smi returned an unexpected inventory row")
            identifier, name, memory = (part.strip() for part in row)
            _uuids([identifier], "nvidia-smi UUID")
            capacity = int(memory)
            if capacity <= 0:
                raise ValueError("nvidia-smi returned an invalid GPU memory capacity")
            devices.append({"uuid": identifier, "name": name, "memory_total_mib": capacity})
        if len({gpu["uuid"].lower() for gpu in devices}) != len(devices):
            raise ValueError("nvidia-smi returned duplicate GPU UUIDs")
        return {"available": True, "gpus": devices}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"available": False, "gpus": [], "reason": str(error)}


def _encoder(effective):
    value = effective.get("text_encoder_device", os.environ.get("TEXT_ENCODER_DEVICE", "cuda"))
    if value not in ("cpu", "cuda"):
        raise ResourcePolicyError("Kimodo TEXT_ENCODER_DEVICE must be cpu or cuda")
    return value


def _runtime_check(resolved, gpu_inventory=None):
    runtime = resolved["runtime"]
    effective = resolved["effective"]
    gpu = effective["gpu"]
    protected = {item.lower() for item in effective.get("protected_gpus", [])}
    allow_protected = effective.get("allow_protected", False)
    report = {**resolved, "allowed": True, "selected_gpus": [], "warnings": [],
              "cuda_verified": False, "memory_estimates_are_guarantees": False}
    if runtime == "kimodo":
        encoder = _encoder(effective)
        report["text_encoder_device"] = encoder
        report["minimum_memory_mib"] = (17 if encoder == "cuda" else 2) * 1024
    if runtime == "local_rig":
        report["estimated_memory_mib"] = 14 * 1024
    if gpu == "cpu":
        if runtime in CUDA_ONLY:
            raise ResourcePolicyError(f"{runtime} requires CUDA and does not support resources gpu=cpu")
        report["selection"] = "cpu"
        return report
    selected = gpu if isinstance(gpu, list) else None
    if gpu == "auto" and protected and not allow_protected and runtime in CUDA_ONLY:
        inherited = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        candidates = [part.strip() for part in inherited.split(",")]
        if not candidates or any(not GPU_UUID.fullmatch(part) for part in candidates):
            raise ResourcePolicyError(
                f"{runtime}: gpu=auto is ambiguous while protected_gpus is configured; select full GPU UUIDs")
        selected = candidates
    if selected is None:
        report["selection"] = "auto (inherited environment unchanged)"
        if runtime in CUDA_ONLY:
            report["warnings"].append("Automatic GPU selection and available memory are unverified")
        return report
    if protected.intersection(item.lower() for item in selected) and not allow_protected:
        raise ResourcePolicyError(
            f"{runtime} selects a protected GPU; explicit runtimes.{runtime}.allow_protected=true is required")
    gpu_inventory = inventory() if gpu_inventory is None else gpu_inventory
    if not gpu_inventory["available"]:
        raise ResourcePolicyError(f"Cannot validate selected GPU UUIDs: {gpu_inventory.get('reason', 'unavailable')}")
    devices = {item["uuid"].lower(): item for item in gpu_inventory["gpus"]}
    missing = [item for item in selected if item.lower() not in devices]
    if missing:
        raise ResourcePolicyError(f"Selected GPU UUIDs are absent from nvidia-smi inventory: {', '.join(missing)}")
    report["selected_gpus"] = [devices[item.lower()] for item in selected]
    report["selection"] = "explicit UUIDs" if isinstance(gpu, list) else "inherited explicit UUIDs"
    # These workers use logical cuda:0 after filtering. Do not sum multiple GPUs or
    # infer the physical host's GPU 0 from a reordered/filtered CUDA environment.
    memory = report["selected_gpus"][0]["memory_total_mib"]
    if runtime == "kimodo" and memory < report["minimum_memory_mib"]:
        raise ResourcePolicyError(
            f"Kimodo text_encoder_device={encoder} requires at least "
            f"{report['minimum_memory_mib']} MiB total GPU memory on its first visible GPU; selected GPU has "
            f"{memory} MiB. Select a sufficient GPU or explicitly configure a supported encoder device.")
    if runtime == "local_rig" and memory < report["estimated_memory_mib"]:
        report["warnings"].append("Selected GPU is below the approximately 14 GiB local rig memory estimate")
    report["warnings"].append("Total GPU memory does not measure free memory or guarantee inference success")
    return report


def runtime_check(root, runtime):
    """Preflight explicit device policy; raise rather than silently changing device."""
    return _runtime_check(resolve(root, runtime))


def child_env(root, runtime, *, checked=None):
    """Return an isolated child environment, or None for unchanged inheritance."""
    checked = runtime_check(root, runtime) if checked is None else checked
    if checked["runtime"] != runtime:
        raise ResourcePolicyError("Checked resource policy belongs to another runtime")
    effective = checked["effective"]
    updates = {}
    if effective["gpu"] != "auto":
        updates["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        updates["CUDA_VISIBLE_DEVICES"] = (
            "" if effective["gpu"] == "cpu" else ",".join(effective["gpu"]))
    if "threads" in effective:
        updates.update({key: str(effective["threads"]) for key in THREAD_ENV})
    if runtime == "kimodo" and "text_encoder_device" in effective:
        updates["TEXT_ENCODER_DEVICE"] = effective["text_encoder_device"]
    if runtime == "blender" and (effective["gpu"] != "auto" or effective.get("protected_gpus")):
        updates.update(ASSET_AUTO_BLENDER_CPU="1", LIBGL_ALWAYS_SOFTWARE="1")
    return {**os.environ, **updates} if updates else None


def blender_threads(root):
    return resolve(root, "blender")["effective"].get("threads")


def kimodo_text_encoder_device(root):
    """Return an explicit encoder override only; None preserves runtime defaults."""
    return resolve(root, "kimodo")["effective"].get("text_encoder_device")


def actual_process_state():
    state = {"pid": os.getpid(), "platform": sys.platform,
             "environment": {key: os.environ[key] for key in (
                 "CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "TEXT_ENCODER_DEVICE", *THREAD_ENV)
                 if key in os.environ}}
    if sys.platform.startswith("linux"):
        if hasattr(os, "sched_getaffinity"):
            state["cpus"] = sorted(os.sched_getaffinity(0))
        if hasattr(os, "getpriority"):
            state["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
        try:
            state["oom_score_adj"] = int(Path("/proc/self/oom_score_adj").read_text().strip())
        except (OSError, ValueError) as error:
            state["oom_score_adj_unavailable"] = str(error)
    return state


def apply_process_resources(root, *, resolved=None):
    """Apply only global Linux OS controls, as absolute non-privilege-raising limits.

    Repeated calls cannot accumulate nice/OOM changes. Requested numerical values
    below current values are left unchanged: this never raises scheduling priority
    or grants more OOM protection. Windows receives GPU/thread child env only.
    """
    resolved = resolve(root) if resolved is None else resolved
    effective = resolved["effective"]
    before = actual_process_state()
    enforcement = {}
    for key in ("cpus", "nice", "oom_score_adj"):
        if key not in effective:
            continue
        if not sys.platform.startswith("linux"):
            enforcement[key] = "unenforced on this platform; Linux-only process control"
            continue
        try:
            if key == "cpus":
                if not hasattr(os, "sched_setaffinity"):
                    raise ResourcePolicyError("Linux CPU affinity is unavailable")
                os.sched_setaffinity(0, set(parse_cpus(effective[key])))
            elif key == "nice":
                current = os.getpriority(os.PRIO_PROCESS, 0)
                if effective[key] < current:
                    enforcement[key] = "unchanged: policy never raises scheduling priority"
                    continue
                if effective[key] > current:
                    os.setpriority(os.PRIO_PROCESS, 0, effective[key])
            else:
                target = Path("/proc/self/oom_score_adj")
                current = int(target.read_text().strip())
                if effective[key] < current:
                    enforcement[key] = "unchanged: policy never grants additional OOM protection"
                    continue
                if effective[key] > current:
                    target.write_text(str(effective[key]))
            enforcement[key] = "applied"
        except (OSError, ValueError, AttributeError) as error:
            raise ResourcePolicyError(f"Could not apply resource control {key}: {error}") from error
    return {**resolved, "enforcement": enforcement, "before": before, "actual_process": actual_process_state()}


def describe(root):
    """Read-only host report: effective policy, provenance, inventory and status."""
    policy, sources = _load(root)
    gpu_inventory = inventory()
    statuses = {}
    for runtime in RUNTIMES:
        try:
            statuses[runtime] = _runtime_check(resolve(root, runtime), gpu_inventory)
        except ResourcePolicyError as error:
            statuses[runtime] = {"allowed": False, "reason": str(error)}
    actual = actual_process_state()
    unenforced = [] if sys.platform.startswith("linux") else [
        key for key in ("cpus", "nice", "oom_score_adj") if key in policy]
    return {"policy": policy, "sources": sources, "gpu_inventory": gpu_inventory, "runtimes": statuses,
            "actual_process": actual, "unenforced_os_fields": unenforced,
            "notes": ["GPU memory estimates do not guarantee free capacity or inference success",
                      "Process nice and oom_score_adj never decrease their current numerical values"]}
