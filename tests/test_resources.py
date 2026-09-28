import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_auto import resources

# Synthetic device identities: never copy a real host inventory into tests.
GPU_A = "GPU-11111111-1111-1111-1111-111111111111"
GPU_B = "GPU-22222222-2222-2222-2222-222222222222"
GPU_MISSING = "GPU-33333333-3333-3333-3333-333333333333"


@pytest.fixture
def host(tmp_path, monkeypatch):
    for variable in list(os.environ):
        if variable.startswith("ASSET_AUTO_") or variable in (
                "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "TEXT_ENCODER_DEVICE", *resources.THREAD_ENV):
            monkeypatch.delenv(variable)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "host-config"))
    monkeypatch.setattr(resources, "inventory", lambda: {
        "available": True,
        "gpus": [{"uuid": GPU_A, "name": "Synthetic 24 GiB", "memory_total_mib": 24 * 1024},
                 {"uuid": GPU_B, "name": "Synthetic 8 GiB", "memory_total_mib": 8 * 1024}],
    })
    return tmp_path


def configure(root, policy):
    (root / "asset-system.local.json").write_text(json.dumps({"resources": policy}), encoding="utf-8")


def host_config(root, policy):
    path = root / "host-config/codex-skill-runtimes/resources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def test_no_config_preserves_environment_and_does_not_probe(host, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,0")
    monkeypatch.setenv("CUDA_DEVICE_ORDER", "FASTEST_FIRST")
    monkeypatch.setenv("OMP_NUM_THREADS", "7")
    monkeypatch.setattr(resources, "inventory", lambda: pytest.fail("default mode must not probe GPU inventory"))
    original = dict(os.environ)
    assert resources.load(host) == {"version": 1, "gpu": "auto"}
    for runtime in resources.RUNTIMES:
        assert resources.child_env(host, runtime) is None
    assert resources.blender_threads(host) is None
    assert resources.kimodo_text_encoder_device(host) is None
    resources.apply_process_resources(host)
    assert dict(os.environ) == original


def test_merge_precedence_and_runtime_isolation(host, monkeypatch):
    configure(host, {"gpu": [GPU_A], "threads": 2, "nice": 5,
                     "runtimes": {"blender": {"threads": 3}, "kimodo": {"gpu": [GPU_B]}}})
    host_path = host_config(host, {"version": 1, "threads": 4, "runtimes": {"blender": {"threads": 5}}})
    assert resources.resolve(host, "trellis")["effective"]["threads"] == 4
    assert resources.blender_threads(host) == 5
    assert resources.resolve(host, "kimodo")["effective"]["gpu"] == [GPU_B]
    assert resources.resolve(host, "blender")["sources"]["threads"] == str(host_path)
    monkeypatch.setenv("ASSET_AUTO_THREADS", "6")
    monkeypatch.setenv("ASSET_AUTO_GPU", GPU_A)
    assert resources.blender_threads(host) == 6
    assert resources.resolve(host, "kimodo")["effective"]["gpu"] == [GPU_A]
    assert resources.resolve(host, "kimodo")["sources"]["gpu"] == "env:ASSET_AUTO_GPU"


def test_override_file_replaces_xdg_path(host, monkeypatch):
    host_config(host, {"threads": 2})
    private = host / "override.json"
    private.write_text(json.dumps({"version": 1, "threads": 3}), encoding="utf-8")
    monkeypatch.setenv("ASSET_AUTO_RESOURCES_FILE", str(private))
    assert resources.load(host)["threads"] == 3
    private.unlink()
    with pytest.raises(resources.ResourcePolicyError, match="Cannot read resource configuration"):
        resources.load(host)


@pytest.mark.parametrize("value", [
    None, [], {"version": 2}, {"version": True}, {"unknown": 1}, {"gpu": "0"}, {"gpu": ["0"]},
    {"gpu": []}, {"gpu": [GPU_A, GPU_A]}, {"protected_gpus": GPU_A}, {"protected_gpus": ["GPU-short"]},
    {"cpus": "3-1"}, {"cpus": "0,,1"}, {"cpus": [0, 1]}, {"threads": True}, {"threads": 0},
    {"threads": "2"}, {"nice": -21}, {"nice": 20}, {"oom_score_adj": -1001}, {"oom_score_adj": 1001},
    {"max_parallel_blender": 0}, {"runtimes": []}, {"runtimes": {"typo": {}}},
    {"runtimes": {"trellis": {"cpus": "0"}}}, {"runtimes": {"blender": {"text_encoder_device": "cpu"}}},
    {"runtimes": {"kimodo": {"text_encoder_device": "auto"}}},
    {"runtimes": {"trellis": {"allow_protected": "true"}}},
    {"wait_timeout_seconds": 0}, {"wait_timeout_seconds": True}, {"wait_timeout_seconds": float("inf")},
    {"poll_interval_seconds": None}, {"poll_interval_seconds": -1}, {"poll_interval_seconds": float("nan")},
])
def test_invalid_policy_fails_closed(host, value):
    configure(host, value)
    with pytest.raises(resources.ResourcePolicyError):
        resources.load(host)


@pytest.mark.parametrize("raw", ["{broken", '{"resources": {"gpu": "auto", "gpu": "cpu"}}', "[]"])
def test_invalid_json_fails_closed(host, raw):
    (host / "asset-system.local.json").write_text(raw, encoding="utf-8")
    with pytest.raises(resources.ResourcePolicyError):
        resources.load(host)


def test_wait_configuration_allows_unbounded_or_explicit_timeout(host):
    configure(host, {"wait_timeout_seconds": None, "poll_interval_seconds": 0.5})
    assert resources.load(host)["wait_timeout_seconds"] is None
    assert resources.load(host)["poll_interval_seconds"] == 0.5
    configure(host, {"wait_timeout_seconds": 120})
    assert resources.load(host)["wait_timeout_seconds"] == 120


@pytest.mark.parametrize(("variable", "value"), [
    ("ASSET_AUTO_THREADS", "0"), ("ASSET_AUTO_THREADS", "1.0"), ("ASSET_AUTO_THREADS", ""),
    ("ASSET_AUTO_GPU", "0"), ("ASSET_AUTO_GPU", ""), ("ASSET_AUTO_CPUS", "-1"),
    ("ASSET_AUTO_RESOURCES_FILE", ""),
])
def test_invalid_environment_fails_closed(host, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(resources.ResourcePolicyError):
        resources.load(host)


def test_uuid_selection_only_changes_child(host, monkeypatch):
    configure(host, {"gpu": [GPU_B, GPU_A], "threads": 3})
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MKL_NUM_THREADS", "8")
    original = dict(os.environ)
    child = resources.child_env(host, "trellis")
    assert child["CUDA_VISIBLE_DEVICES"] == f"{GPU_B},{GPU_A}"
    assert child["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    for variable in resources.THREAD_ENV:
        assert child[variable] == "3"
    assert dict(os.environ) == original


def test_auto_environment_override_preserves_inherited_cuda(host, monkeypatch):
    configure(host, {"gpu": [GPU_A], "runtimes": {"trellis": {"gpu": [GPU_B]}}})
    monkeypatch.setenv("ASSET_AUTO_GPU", "auto")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    assert resources.child_env(host, "trellis") is None


@pytest.mark.parametrize("runtime", sorted(resources.CUDA_ONLY))
def test_cpu_refused_for_cuda_only_workers(host, runtime):
    configure(host, {"gpu": "cpu"})
    with pytest.raises(resources.ResourcePolicyError, match="requires CUDA"):
        resources.child_env(host, runtime)


def test_cpu_blender_allowed_with_software_rendering(host):
    configure(host, {"gpu": "cpu"})
    child = resources.child_env(host, "blender")
    assert child["CUDA_VISIBLE_DEVICES"] == ""
    assert child["ASSET_AUTO_BLENDER_CPU"] == "1"
    assert child["LIBGL_ALWAYS_SOFTWARE"] == "1"


def test_missing_uuid_rejected(host):
    configure(host, {"gpu": [GPU_MISSING]})
    with pytest.raises(resources.ResourcePolicyError, match="absent"):
        resources.child_env(host, "trellis")


def test_inventory_unavailable_rejects_explicit_uuid(host, monkeypatch):
    configure(host, {"gpu": [GPU_A]})
    monkeypatch.setattr(resources, "inventory", lambda: {"available": False, "reason": "not installed"})
    with pytest.raises(resources.ResourcePolicyError, match="Cannot validate"):
        resources.runtime_check(host, "local_parts")


def test_protected_uuid_requires_runtime_opt_in(host):
    configure(host, {"gpu": [GPU_A], "protected_gpus": [GPU_A],
                     "runtimes": {"local_rig": {"allow_protected": True}}})
    with pytest.raises(resources.ResourcePolicyError, match="protected GPU"):
        resources.runtime_check(host, "trellis")
    assert resources.runtime_check(host, "local_rig")["allowed"]


def test_protected_gpu_auto_ambiguous_fails_but_cpu_blender_is_safe(host, monkeypatch):
    configure(host, {"protected_gpus": [GPU_A]})
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(resources.ResourcePolicyError, match="ambiguous"):
        resources.runtime_check(host, "trellis")
    assert resources.child_env(host, "blender")["ASSET_AUTO_BLENDER_CPU"] == "1"
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", GPU_B)
    assert resources.runtime_check(host, "trellis")["selection"] == "inherited explicit UUIDs"
    assert resources.child_env(host, "trellis") is None
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", GPU_A)
    with pytest.raises(resources.ResourcePolicyError, match="protected GPU"):
        resources.runtime_check(host, "trellis")


def test_runtime_child_overrides_are_isolated(host):
    configure(host, {"gpu": [GPU_A], "threads": 3,
                     "runtimes": {"kimodo": {"gpu": [GPU_B], "text_encoder_device": "cpu", "threads": 2},
                                  "blender": {"gpu": "cpu"}}})
    original = dict(os.environ)
    kimodo = resources.child_env(host, "kimodo")
    assert kimodo["CUDA_VISIBLE_DEVICES"] == GPU_B
    assert kimodo["TEXT_ENCODER_DEVICE"] == "cpu"
    assert kimodo["OMP_NUM_THREADS"] == "2"
    assert resources.child_env(host, "blender")["CUDA_VISIBLE_DEVICES"] == ""
    trellis = resources.child_env(host, "trellis")
    assert trellis["CUDA_VISIBLE_DEVICES"] == GPU_A
    assert "TEXT_ENCODER_DEVICE" not in trellis
    assert dict(os.environ) == original


def test_launch_snapshot_keeps_child_selection_consistent_if_config_changes(host):
    configure(host, {"gpu": [GPU_A], "threads": 2})
    checked = resources.runtime_check(host, "trellis")
    configure(host, {"gpu": [GPU_B], "threads": 8})
    child = resources.child_env(host, "trellis", checked=checked)
    assert child["CUDA_VISIBLE_DEVICES"] == GPU_A
    assert child["OMP_NUM_THREADS"] == "2"
    with pytest.raises(resources.ResourcePolicyError, match="another runtime"):
        resources.child_env(host, "blender", checked=checked)


def test_kimodo_memory_uses_first_visible_device_not_combined_memory(host):
    configure(host, {"gpu": [GPU_B, GPU_A]})
    with pytest.raises(resources.ResourcePolicyError, match="17408 MiB"):
        resources.runtime_check(host, "kimodo")
    configure(host, {"gpu": [GPU_A, GPU_B]})
    assert resources.runtime_check(host, "kimodo")["allowed"]


def test_kimodo_mixed_mode_and_inherited_encoder(host, monkeypatch):
    configure(host, {"gpu": [GPU_B]})
    monkeypatch.setenv("TEXT_ENCODER_DEVICE", "cpu")
    report = resources.runtime_check(host, "kimodo")
    assert report["minimum_memory_mib"] == 2048
    assert resources.kimodo_text_encoder_device(host) is None
    assert resources.child_env(host, "kimodo")["TEXT_ENCODER_DEVICE"] == "cpu"
    monkeypatch.setenv("TEXT_ENCODER_DEVICE", "invalid")
    with pytest.raises(resources.ResourcePolicyError, match="TEXT_ENCODER_DEVICE"):
        resources.runtime_check(host, "kimodo")


def test_kimodo_explicit_encoder_takes_precedence_over_inherited_environment(host, monkeypatch):
    configure(host, {"gpu": [GPU_B], "runtimes": {"kimodo": {"text_encoder_device": "cpu"}}})
    monkeypatch.setenv("TEXT_ENCODER_DEVICE", "cuda")
    assert resources.child_env(host, "kimodo")["TEXT_ENCODER_DEVICE"] == "cpu"


def test_rig_estimate_advisory_and_trellis_has_no_universal_memory_gate(host):
    configure(host, {"gpu": [GPU_B]})
    report = resources.runtime_check(host, "local_rig")
    assert report["allowed"]
    assert any("14 GiB" in warning for warning in report["warnings"])
    assert resources.runtime_check(host, "trellis")["allowed"]


def test_cpu_affinity_must_be_current_allowed_subset(host, monkeypatch):
    monkeypatch.setattr(resources.sys, "platform", "linux")
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda pid: {2, 3, 4, 7}, raising=False)
    configure(host, {"cpus": "2-4,7"})
    assert resources.resolve(host)["effective"]["cpus"] == "2-4,7"
    configure(host, {"cpus": "0-4"})
    with pytest.raises(resources.ResourcePolicyError, match="current allowed affinity"):
        resources.resolve(host)


def test_apply_linux_controls_absolute_repeated_and_never_gain_priority(host, monkeypatch):
    configure(host, {"cpus": "2-3", "nice": 10, "oom_score_adj": 400})
    state = {"cpus": {2, 3, 4}, "nice": 2, "oom_score_adj": 0}
    writes = {"nice": [], "oom": []}
    monkeypatch.setattr(resources.sys, "platform", "linux")
    monkeypatch.setattr(resources.os, "PRIO_PROCESS", 0, raising=False)
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda pid: state["cpus"], raising=False)
    monkeypatch.setattr(resources.os, "sched_setaffinity",
                        lambda pid, cpus: state.update(cpus=cpus), raising=False)
    monkeypatch.setattr(resources.os, "getpriority", lambda which, pid: state["nice"], raising=False)

    def setpriority(which, pid, value):
        state["nice"] = value
        writes["nice"].append(value)

    monkeypatch.setattr(resources.os, "setpriority", setpriority, raising=False)
    read_text, write_text = Path.read_text, Path.write_text

    def fake_read(path, *args, **kwargs):
        if path.as_posix() == "/proc/self/oom_score_adj":
            return str(state["oom_score_adj"])
        return read_text(path, *args, **kwargs)

    def fake_write(path, value, *args, **kwargs):
        if path.as_posix() == "/proc/self/oom_score_adj":
            state["oom_score_adj"] = int(value)
            writes["oom"].append(int(value))
            return len(value)
        return write_text(path, value, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read)
    monkeypatch.setattr(Path, "write_text", fake_write)
    report = resources.apply_process_resources(host)
    resources.apply_process_resources(host)
    assert report["actual_process"]["cpus"] == [2, 3]
    assert writes == {"nice": [10], "oom": [400]}
    configure(host, {"nice": -10, "oom_score_adj": -400})
    report = resources.apply_process_resources(host)
    assert report["actual_process"]["nice"] == 10
    assert report["actual_process"]["oom_score_adj"] == 400
    assert report["enforcement"]["nice"].startswith("unchanged")
    assert writes == {"nice": [10], "oom": [400]}


def test_windows_reports_os_controls_unenforced(host, monkeypatch):
    configure(host, {"cpus": "0-2", "nice": 10, "oom_score_adj": 400, "threads": 2})
    monkeypatch.setattr(resources.sys, "platform", "win32")
    report = resources.apply_process_resources(host)
    assert all("unenforced" in value for value in report["enforcement"].values())
    assert resources.child_env(host, "blender")["OMP_NUM_THREADS"] == "2"
    assert resources.describe(host)["unenforced_os_fields"] == ["cpus", "nice", "oom_score_adj"]


def test_describe_is_read_only_reports_policy_sources_status_and_actual_state(host, monkeypatch):
    configure(host, {"gpu": [GPU_B]})
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "inherited-value")
    original = dict(os.environ)
    report = resources.describe(host)
    assert report["policy"]["gpu"] == [GPU_B]
    assert report["sources"]["gpu"].endswith("asset-system.local.json")
    assert report["gpu_inventory"]["available"]
    assert report["runtimes"]["kimodo"]["allowed"] is False
    assert report["runtimes"]["trellis"]["selected_gpus"][0]["uuid"] == GPU_B
    assert report["actual_process"]["environment"]["CUDA_VISIBLE_DEVICES"] == "inherited-value"
    assert dict(os.environ) == original
    json.dumps(report)


def test_inventory_uses_read_only_uuid_query(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=f'{GPU_A}, "Synthetic, GPU", 24576\n')

    monkeypatch.setattr(resources.subprocess, "run", run)
    report = resources.inventory()
    assert report["available"]
    assert report["gpus"] == [{"uuid": GPU_A, "name": "Synthetic, GPU", "memory_total_mib": 24576}]
    assert calls[0][0] == ["nvidia-smi", "--query-gpu=uuid,name,memory.total", "--format=csv,noheader,nounits"]
    assert calls[0][1]["timeout"] == 15
