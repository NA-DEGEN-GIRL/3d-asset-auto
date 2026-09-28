import builtins
import json
import os
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from filelock import FileLock, Timeout

from asset_auto import resources
from asset_auto import runtime_execution as execution

GPU_A = "GPU-11111111-1111-1111-1111-111111111111"
GPU_B = "GPU-22222222-2222-2222-2222-222222222222"


@pytest.fixture
def host(tmp_path, monkeypatch):
    # Keep ordinary subprocess.run mocks portable. Dedicated tests below cover
    # the native Linux managed Popen/process-group branch explicitly.
    monkeypatch.setattr(execution.sys, "platform", "win32")
    for variable in list(os.environ):
        if variable.startswith("ASSET_AUTO_") or variable in (
                "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "TEXT_ENCODER_DEVICE", *resources.THREAD_ENV):
            monkeypatch.delenv(variable)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "host-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "host-cache"))
    monkeypatch.setattr(resources, "inventory", lambda: {
        "available": True,
        "gpus": [{"uuid": identifier, "name": "Synthetic device", "memory_total_mib": 24 * 1024}
                 for identifier in (GPU_A, GPU_B)],
    })
    monkeypatch.setattr(execution, "gpu_busy", lambda identifiers: [])
    return tmp_path


def configure(root, policy):
    root.mkdir(parents=True, exist_ok=True)
    (root / "asset-system.local.json").write_text(json.dumps({"resources": policy}), encoding="utf-8")


def clock(monkeypatch, on_sleep=None):
    state = {"now": 0, "sleeps": []}
    monkeypatch.setattr(execution.time, "monotonic", lambda: state["now"])

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds
        if on_sleep is not None:
            on_sleep()

    monkeypatch.setattr(execution.time, "sleep", sleep)
    return state


def assert_gpu_lease_free(identifier):
    with FileLock(execution.lock_directory() / f"{identifier.lower()}.lock", timeout=0):
        pass


def test_default_run_preserves_argv_and_environment_without_filelock(host, monkeypatch):
    calls = []
    original_import = builtins.__import__

    def no_filelock(name, *args, **kwargs):
        if name == "filelock":
            raise ImportError("synthetic stdlib-only interpreter")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_filelock)
    monkeypatch.setattr(execution, "gpu_busy", lambda identifiers: pytest.fail("auto must not query busy GPUs"))
    monkeypatch.setattr(resources, "inventory", lambda: pytest.fail("auto must not query GPU inventory"))

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(execution.subprocess, "run", run)
    command = ["synthetic-worker", "--device", "legacy"]
    execution.run(host, "trellis", command)
    assert calls[0][0] == command
    assert "env" not in calls[0][1]
    assert not (host / "host-cache").exists()


def test_explicit_leases_require_dependency_with_clear_error(host, monkeypatch):
    configure(host, {"gpu": [GPU_A]})
    original_import = builtins.__import__

    def no_filelock(name, *args, **kwargs):
        if name == "filelock":
            raise ImportError("synthetic missing dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_filelock)
    with (pytest.raises(resources.ResourcePolicyError, match="filelock dependency"),
          execution.resource_guard(host, "trellis", ["worker"])):
        pytest.fail("missing lease dependency must prevent launch")


def test_blender_threads_env_and_cpu_rendering_without_gpu_lease(host, monkeypatch):
    configure(host, {"gpu": [GPU_A], "threads": 3, "max_parallel_blender": 1})
    monkeypatch.setattr(execution, "gpu_busy", lambda identifiers: pytest.fail("CPU Blender needs no GPU lease"))
    with execution.resource_guard(host, "blender", ["blender", "-b", "--python", "worker.py", "--", "x"]) as job:
        assert job["command"][:4] == ["blender", "--threads", "3", "-b"]
        assert job["env"]["OMP_NUM_THREADS"] == "3"
        assert job["env"]["LIBGL_ALWAYS_SOFTWARE"] == "1"
        assert job["env"]["ASSET_AUTO_BLENDER_CPU"] == "1"
        assert job["report"]["gpu_lease_uuids"] == []
        assert job["report"]["blender_slot"] == 0
        assert job["report"]["child_process_state_verified"] is False


@pytest.mark.parametrize("flags", [
    ["--threads", "2", "--threads", "4"], ["-t", "2", "-t0"], ["--threads=4"], ["-t4"],
    ["-t0"], ["-t-1"], ["--threads"],
])
def test_conflicting_blender_thread_flags_fail(host, flags):
    configure(host, {"threads": 2})
    with (pytest.raises(resources.ResourcePolicyError, match="conflicts"),
          execution.resource_guard(host, "blender", ["blender", *flags])):
        pytest.fail("conflicting Blender flags must prevent launch")


@pytest.mark.parametrize("flags", [["-t2"], ["--threads=2"], ["-t", "2", "--threads", "2"]])
def test_matching_blender_thread_flags_preserved(host, flags):
    configure(host, {"threads": 2})
    command = ["blender", *flags, "--", "--threads", "unrelated-script-option"]
    with execution.resource_guard(host, "blender", command) as job:
        assert job["command"] == command


def test_busy_selected_gpu_waits_then_runs_same_uuid(host, monkeypatch, capsys):
    configure(host, {"gpu": [GPU_A], "poll_interval_seconds": 0.25})
    state = clock(monkeypatch)
    queries = []

    def busy(identifiers):
        queries.append(identifiers)
        return [{"uuid": GPU_A, "pid": 123}] if len(queries) == 1 else []

    monkeypatch.setattr(execution, "gpu_busy", busy)
    record = host / "queued.resources.json"
    with execution.resource_guard(host, "trellis", ["worker"], record) as job:
        assert job["env"]["CUDA_VISIBLE_DEVICES"] == GPU_A
        assert job["report"]["state"] == "running"
        assert job["report"]["waited_seconds"] == 0.25
        assert "busy_processes" not in job["report"]
    assert queries == [[GPU_A.lower()], [GPU_A.lower()]]
    assert state["sleeps"] == [0.25]
    assert "No alternate GPU" in capsys.readouterr().err
    assert json.loads(record.read_text())["state"] == "completed"
    assert_gpu_lease_free(GPU_A)


def test_cross_checkout_gpu_lease_waits_for_other_checkout(host, monkeypatch):
    first_root, second_root = host / "first", host / "second"
    for root in (first_root, second_root):
        configure(root, {"gpu": [GPU_A], "poll_interval_seconds": 0.1})
    first = execution.resource_guard(first_root, "trellis", ["first-worker"])
    first_launch = first.__enter__()
    state = clock(monkeypatch, lambda: first.__exit__(None, None, None))
    with execution.resource_guard(second_root, "local_parts", ["second-worker"]) as second:
        assert second["report"]["lease_directory"] == first_launch["report"]["lease_directory"]
        assert first_launch["report"]["state"] == "completed"
    assert state["sleeps"] == [0.1]
    assert_gpu_lease_free(GPU_A)


def test_partial_gpu_leases_are_released_before_wait(host, monkeypatch):
    configure(host, {"gpu": [GPU_A, GPU_B], "poll_interval_seconds": 0.1})
    blocker = FileLock(execution.lock_directory() / f"{GPU_B.lower()}.lock", timeout=0)
    blocker.acquire()

    def unblock():
        assert_gpu_lease_free(GPU_A)
        blocker.release()

    state = clock(monkeypatch, unblock)
    try:
        with execution.resource_guard(host, "trellis", ["worker"]) as job:
            assert job["env"]["CUDA_VISIBLE_DEVICES"] == f"{GPU_A},{GPU_B}"
    finally:
        blocker.release()
    assert state["sleeps"] == [0.1]


def test_blender_slot_waits_for_release(host, monkeypatch):
    configure(host, {"max_parallel_blender": 1, "poll_interval_seconds": 0.1})
    blocker = FileLock(execution.lock_directory() / "blender-0.lock", timeout=0)
    blocker.acquire()
    state = clock(monkeypatch, blocker.release)
    try:
        with execution.resource_guard(host, "blender", ["blender"]) as job:
            assert job["report"]["blender_slot"] == 0
    finally:
        blocker.release()
    assert state["sleeps"] == [0.1]


def test_wait_timeout_does_not_launch_and_releases_gpu_lease(host, monkeypatch):
    configure(host, {"gpu": [GPU_A], "poll_interval_seconds": 0.25, "wait_timeout_seconds": 0.5})
    state = clock(monkeypatch)
    monkeypatch.setattr(execution, "gpu_busy", lambda identifiers: [{"uuid": GPU_A, "pid": 123}])
    record = host / "timeout.resources.json"
    with (pytest.raises(resources.ResourcePolicyError, match="Timed out"),
          execution.resource_guard(host, "trellis", ["worker"], record)):
        pytest.fail("busy timeout must not launch")
    assert state["sleeps"] == [0.25, 0.25]
    assert json.loads(record.read_text())["state"] == "failed"
    assert_gpu_lease_free(GPU_A)


@pytest.mark.parametrize("error", [KeyboardInterrupt(), RuntimeError("synthetic failure")])
def test_cancel_or_failure_releases_gpu_lease(host, error):
    configure(host, {"gpu": [GPU_A]})
    record = host / "failed.resources.json"
    with pytest.raises(type(error)), execution.resource_guard(host, "trellis", ["worker"], record):
        raise error
    expected = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
    assert json.loads(record.read_text())["state"] == expected
    assert_gpu_lease_free(GPU_A)


def test_nonzero_subprocess_records_failure_and_releases(host, monkeypatch):
    configure(host, {"gpu": [GPU_A]})

    def fail(command, **kwargs):
        kwargs["stdout"].write(b"synthetic worker failure\n")
        kwargs["stdout"].flush()
        return SimpleNamespace(returncode=9)

    monkeypatch.setattr(execution.subprocess, "run", fail)
    log = host / "worker.log"
    with pytest.raises(RuntimeError, match=r"process failed \(9\)"):
        execution.run(host, "trellis", ["worker"], log=log)
    assert json.loads(log.with_suffix(".resources.json").read_text())["state"] == "failed"
    assert_gpu_lease_free(GPU_A)


def test_subprocess_timeout_releases_lease(host, monkeypatch):
    configure(host, {"gpu": [GPU_A]})

    def expire(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(execution.subprocess, "run", expire)
    with pytest.raises(subprocess.TimeoutExpired):
        execution.run(host, "trellis", ["worker"], timeout=5)
    assert_gpu_lease_free(GPU_A)


@pytest.mark.parametrize("policy", [
    {"gpu": [GPU_A], "protected_gpus": [GPU_A]},
    {"gpu": ["GPU-33333333-3333-3333-3333-333333333333"]},
])
def test_invalid_gpu_policy_fails_before_waiting(host, monkeypatch, policy):
    configure(host, policy)
    monkeypatch.setattr(execution.time, "sleep", lambda seconds: pytest.fail("invalid policy must not queue"))
    with pytest.raises(resources.ResourcePolicyError), execution.resource_guard(host, "trellis", ["worker"]):
        pytest.fail("invalid policy must not launch")


def test_wsl_bridge_only_accepts_unchanged_legacy_policy(host):
    with execution.resource_guard(host, "trellis", ["wsl", "--exec", "worker"]) as job:
        assert job["env"] is None
    configure(host, {"threads": 2})
    with (pytest.raises(resources.ResourcePolicyError, match="WSL bridge"),
          execution.resource_guard(host, "trellis", ["wsl.exe", "--exec", "worker"])):
        pytest.fail("private policy must not disappear across WSL bridge")


def test_launch_resolves_one_policy_snapshot(host, monkeypatch):
    configure(host, {"gpu": [GPU_A], "threads": 2})
    original_check = resources.runtime_check

    def check_then_edit(root, runtime):
        checked = original_check(root, runtime)
        configure(root, {"gpu": [GPU_B], "threads": 8})
        return checked

    monkeypatch.setattr(resources, "runtime_check", check_then_edit)
    with execution.resource_guard(host, "trellis", ["worker"]) as job:
        assert job["env"]["CUDA_VISIBLE_DEVICES"] == GPU_A
        assert job["env"]["OMP_NUM_THREADS"] == "2"
        assert job["report"]["gpu_lease_uuids"] == [GPU_A.lower()]


def test_gpu_busy_uses_read_only_compute_query(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=f"{GPU_A}, 123\n{GPU_B}, 456\n")

    monkeypatch.setattr(execution.subprocess, "run", run)
    assert execution.gpu_busy([GPU_A]) == [{"uuid": GPU_A, "pid": 123}]
    assert calls == [["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"]]


def test_gpu_busy_probe_failure_fails_closed(monkeypatch):
    def unavailable(command, **kwargs):
        raise FileNotFoundError("synthetic missing nvidia-smi")

    monkeypatch.setattr(execution.subprocess, "run", unavailable)
    with pytest.raises(resources.ResourcePolicyError, match="occupancy"):
        execution.gpu_busy([GPU_A])


@pytest.mark.parametrize("outcome", ["success", "nonzero", "timeout", "cancel"])
def test_linux_managed_child_group_cleanup_precedes_lease_release(host, monkeypatch, outcome):
    configure(host, {"gpu": [GPU_A]})
    monkeypatch.setattr(execution.sys, "platform", "linux")
    monkeypatch.setattr(execution.signal, "SIGKILL", 9, raising=False)
    events = []
    exitcode = 7 if outcome == "nonzero" else 0
    lease = execution.lock_directory() / f"{GPU_A.lower()}.lock"

    def assert_lease_held():
        with pytest.raises(Timeout), FileLock(lease, timeout=0):
            pytest.fail("process cleanup must finish before releasing the GPU lease")

    class Process:
        pid = 987654
        waits = 0

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            assert_lease_held()
            self.waits += 1
            if self.waits == 1:
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired(["worker"], timeout)
                if outcome == "cancel":
                    raise KeyboardInterrupt()
            return exitcode

    def spawn(command, **options):
        events.append(("spawn", options))
        assert command == ["worker"]
        assert options["start_new_session"] is True
        assert "timeout" not in options
        assert options["env"]["CUDA_VISIBLE_DEVICES"] == GPU_A
        return Process()

    def signal_group(pid, signum):
        assert pid == Process.pid
        assert_lease_held()
        events.append(("signal", signum))

    monkeypatch.setattr(execution.subprocess, "Popen", spawn)
    monkeypatch.setattr(execution.os, "killpg", signal_group, raising=False)
    expected = {"nonzero": RuntimeError, "timeout": subprocess.TimeoutExpired, "cancel": KeyboardInterrupt}
    failure = pytest.raises(expected[outcome]) if outcome in expected else nullcontext()
    record = host / "managed.log"
    with failure:
        result = execution.run(host, "trellis", ["worker"], log=record, timeout=10)
        assert result.returncode == 0
    assert [event for event in events if event[0] == "signal"] == [
        ("signal", execution.signal.SIGTERM), ("signal", execution.signal.SIGKILL)]
    assert [event for event in events if event[0] == "wait"] == [("wait", 10), ("wait", 2), ("wait", 2)]
    expected_state = "completed" if outcome == "success" else "cancelled" if outcome == "cancel" else "failed"
    assert json.loads(record.with_suffix(".resources.json").read_text())["state"] == expected_state
    assert_gpu_lease_free(GPU_A)


def test_linux_unconfigured_auto_retains_existing_subprocess_launch(host, monkeypatch):
    monkeypatch.setattr(execution.sys, "platform", "linux")
    monkeypatch.setattr(execution.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("legacy path changed"))
    calls = []

    def run(command, **options):
        calls.append(options)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(execution.subprocess, "run", run)
    execution.run(host, "trellis", ["worker"])
    assert "start_new_session" not in calls[0]
    assert "env" not in calls[0]


def test_process_group_cleanup_escalates_after_bounded_grace(monkeypatch):
    monkeypatch.setattr(execution.signal, "SIGKILL", 9, raising=False)
    events = []

    class Process:
        pid = 987654

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if len(events) == 2:
                raise subprocess.TimeoutExpired(["worker"], timeout)
            return -9

    monkeypatch.setattr(execution.os, "killpg", lambda pid, signum: events.append(("signal", signum)), raising=False)
    execution._stop_process_group(Process())
    assert events == [("signal", execution.signal.SIGTERM), ("wait", 2),
                      ("signal", execution.signal.SIGKILL), ("wait", 2)]
