"""Launch-time resource enforcement and cooperative, cross-checkout waiting.

These are per-user scheduling controls, not a sandbox. An unrelated process can
start using a GPU after the read-only busy check; no process is killed or moved.
"""

from __future__ import annotations

import csv
import io
import os
import signal
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path

from . import resources
from .store import now, write_json

progress_observer = ContextVar("resource_progress_observer", default=None)


@contextmanager
def legacy_gpu_lock(root, runtime, path):
    """Unconfigured workers retain the root lock; pinned workers share UUID leases."""
    if isinstance(resources.resolve(root, runtime)["effective"]["gpu"], list):
        yield
    else:
        from filelock import FileLock

        with FileLock(path, timeout=legacy_gpu_lock_timeout(root, runtime)):
            yield

def policy_active(root, runtime=None):
    return _effective_policy_active(resources.resolve(root, runtime)["effective"])


def _effective_policy_active(effective):
    return effective["gpu"] != "auto" or any(
        value not in (None, [], {}) for key, value in effective.items()
        if key not in ("gpu", "version"))


def reject_bridge(root, runtime):
    if policy_active(root, runtime):
        raise resources.ResourcePolicyError(
            "Private resources cannot be enforced across this WSL bridge. Run the native "
            "runtime on the execution host with its own private resources.json; do not disable the policy.")


def legacy_gpu_lock_timeout(root, runtime):
    """Retain the old root lock, but let explicit policies wait consistently."""
    if not policy_active(root, runtime):
        return 3600
    return resources.resolve(root, runtime)["effective"].get("wait_timeout_seconds") or -1


def lock_directory():
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    directory = base / "codex-skill-runtimes" / "locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def gpu_busy(identifiers):
    """Return compute users of the selected UUIDs; never initialize CUDA."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        selected = {value.lower() for value in identifiers}
        busy = []
        for row in csv.reader(io.StringIO(result.stdout)):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != 2 or not resources.GPU_UUID.fullmatch(row[0].strip()):
                raise ValueError("nvidia-smi returned an unsupported compute-process row")
            if row[0].strip().lower() in selected:
                busy.append({"uuid": row[0].strip(), "pid": int(row[1].strip())})
        return busy
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise resources.ResourcePolicyError(f"Cannot inspect selected GPU occupancy: {error}") from error


def _blender_command(command, threads):
    if threads is None:
        return command
    # Blender interprets options in order. Put the limit before the script and
    # reject a contradictory user flag instead of allowing it to override policy.
    head = command[1:command.index("--")] if "--" in command else command[1:]
    already_present = False
    for index, arg in enumerate(head):
        if arg in ("-t", "--threads"):
            if index + 1 == len(head) or head[index + 1] != str(threads):
                raise resources.ResourcePolicyError("Blender --threads conflicts with private resource policy")
            already_present = True
        elif arg.startswith("--threads="):
            if arg != f"--threads={threads}":
                raise resources.ResourcePolicyError("Blender --threads conflicts with private resource policy")
            already_present = True
        elif arg.startswith("-t") and arg[2:].lstrip("-").isdigit():
            if arg != f"-t{threads}":
                raise resources.ResourcePolicyError("Blender -t conflicts with private resource policy")
            already_present = True
    return command if already_present else [command[0], "--threads", str(threads), *command[1:]]


@contextmanager
def resource_guard(root, runtime, command, record_path=None):
    """Hold resource leases until the child exits; yield command/env/report.

    No policy keeps the original argv/environment. Explicit GPUs wait for both
    cooperating jobs (even in another checkout) and existing compute processes.
    Blender uses CPU rendering under a GPU policy, so only its CPU slot is held.
    """
    command = [str(value) for value in command]
    if not command:
        raise ValueError("A resource command is required")
    if Path(command[0]).name.lower() in ("wsl", "wsl.exe"):
        reject_bridge(root, runtime)
    checked = resources.runtime_check(root, runtime)
    effective = checked["effective"]
    env = resources.child_env(root, runtime, checked=checked)
    process = resources.apply_process_resources(root, resolved=checked)
    if runtime == "blender":
        command = _blender_command(command, effective.get("threads"))
    identifiers = sorted(gpu["uuid"].lower() for gpu in checked["selected_gpus"]) if runtime in resources.CUDA_ONLY else []
    slots = effective.get("max_parallel_blender") if runtime == "blender" else None
    directory = lock_directory() if identifiers or slots else None
    lease_type, lock_timeout = None, ()
    if directory is not None:
        try:
            from filelock import FileLock as lease_type
            from filelock import Timeout as lock_timeout
        except ImportError as error:
            raise resources.ResourcePolicyError(
                "Explicit resource leases require the filelock dependency; complete the core runtime setup"
            ) from error
    started = time.monotonic()
    timeout = effective.get("wait_timeout_seconds")
    interval = effective.get("poll_interval_seconds", 2)
    report = {"runtime": runtime, "resolved": checked, "process": process,
              "process_state_scope": "Launching parent; OS controls are inherited when the child starts",
              "child_process_state_verified": False,
              "child_environment": {key: (env or os.environ)[key] for key in (
                  "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "TEXT_ENCODER_DEVICE",
                  "ASSET_AUTO_BLENDER_CPU", "LIBGL_ALWAYS_SOFTWARE", *resources.THREAD_ENV)
                  if key in (env or os.environ)},
              "lease_directory": str(directory) if directory else None,
              "gpu_lease_uuids": identifiers, "started_at": now(),
              "limitations": ["Cooperative per-user leases; external launches can race the occupancy check",
                              "GPU occupancy checks cover compute processes, not every graphics workload",
                              "Trusted Blender scripts must honor CPU rendering; this is not a sandbox",
                              ("Native Linux explicit policies clean up the child process group; escaped sessions "
                               "and Windows descendants are not contained")]}

    def update(state, **fields):
        report.update(state=state, **fields)
        if record_path is not None:
            write_json(Path(record_path), report)
        observer = progress_observer.get()
        if observer is not None:
            observer({key: report.get(key) for key in
                      ("runtime", "state", "waiting_reason", "waited_seconds", "error")})

    try:
        while True:
            waiting = None
            with ExitStack() as leases:
                try:
                    for identifier in identifiers:
                        leases.enter_context(lease_type(directory / f"{identifier}.lock", timeout=0))
                    if slots:
                        for slot in range(slots):
                            try:
                                leases.enter_context(lease_type(directory / f"blender-{slot}.lock", timeout=0))
                                report["blender_slot"] = slot
                                break
                            except lock_timeout:
                                continue
                        else:
                            waiting = "All configured Blender slots are in use"
                except lock_timeout:
                    waiting = "A selected GPU is leased by another asset job"
                if waiting is None and identifiers:
                    busy = gpu_busy(identifiers)
                    if busy:
                        waiting = "A selected GPU has existing compute processes"
                        report["busy_processes"] = busy
                elapsed = time.monotonic() - started
                if waiting is None:
                    report.pop("busy_processes", None)
                    update("running", waited_seconds=elapsed, waiting_reason=None)
                    yield {"command": command, "env": env, "report": report}
                    update("completed", finished_at=now())
                    return
                # Release any partial GPU acquisitions before waiting, avoiding
                # deadlocks when jobs request overlapping device sets.
            if report.get("waiting_reason") != waiting:
                print(f"Waiting for {runtime}: {waiting}. No alternate GPU will be selected.", file=sys.stderr)
            update("waiting_resources", waiting_reason=waiting, waited_seconds=elapsed)
            if timeout is not None and elapsed >= timeout:
                raise resources.ResourcePolicyError(
                    f"Timed out waiting for {runtime} resources after {elapsed:.1f}s; no work was submitted")
            time.sleep(min(interval, max(0, timeout - elapsed)) if timeout is not None else interval)
    except BaseException as error:
        update("cancelled" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed",
               error=str(error), finished_at=now())
        raise


def _stop_process_group(process):
    """End our native Linux foreground process group before returning its lease.

    The direct child is always reaped. A descendant that deliberately creates a
    different session is outside this cooperative launcher contract.
    """
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def run(root, runtime, command, *, log=None, timeout=None):
    """Guard a trusted command, preserving its output or writing a local log."""
    record = Path(log).with_suffix(".resources.json") if log is not None else None
    with resource_guard(root, runtime, command, record) as launch, ExitStack() as stack:
        options = {"cwd": root,
                   "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0}
        if launch["env"] is not None:
            options["env"] = launch["env"]
        if log is not None:
            options.update(stdout=stack.enter_context(Path(log).open("wb")), stderr=subprocess.STDOUT)
        effective = launch["report"]["resolved"]["effective"]
        if sys.platform.startswith("linux") and _effective_policy_active(effective):
            process = subprocess.Popen(launch["command"], start_new_session=True, **options)
            try:
                returncode = process.wait(timeout=timeout)
            finally:
                _stop_process_group(process)
            result = subprocess.CompletedProcess(launch["command"], returncode)
        else:
            if timeout is not None:
                options["timeout"] = timeout
            result = subprocess.run(launch["command"], check=False, **options)
        if result.returncode:
            # Record failure inside the guard so a nonzero child cannot produce
            # a misleading completed resource sidecar.
            detail = Path(log).read_text(encoding="utf-8", errors="replace")[-5000:] if log else ""
            raise RuntimeError(f"{runtime} process failed ({result.returncode})" +
                               (f"; log: {log}\n{detail}" if log else ""))
        return result
