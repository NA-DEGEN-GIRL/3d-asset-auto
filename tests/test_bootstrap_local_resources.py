"""Resource handoff during isolated setup, with all external work mocked."""

import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_bootstrap(name):
    path = Path(__file__).resolve().parents[1] / f"scripts/bootstrap_{name}.py"
    spec = importlib.util.spec_from_file_location(f"bootstrap_{name}_resource_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_guard(monkeypatch, bootstrap):
    active = []

    @contextmanager
    def guard(root, runtime, command):
        active.append(runtime)
        yield {"command": command, "env": None, "report": {}}
        active.remove(runtime)

    monkeypatch.setattr(bootstrap, "resource_guard", guard)
    return active


def test_native_rig_setup_passes_selected_environment_and_guards_only_cuda_probe(tmp_path, monkeypatch):
    bootstrap = load_bootstrap("local_rig")
    active = mock_guard(monkeypatch, bootstrap)
    runtime = tmp_path / ".runtime/local-rig"
    (runtime / "source").mkdir(parents=True)
    uv = tmp_path / "uv"
    uv.touch()
    calls = []
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda *_: str(uv))
    monkeypatch.setattr(bootstrap, "CHECKPOINTS", ())
    monkeypatch.setattr(bootstrap, "patch_source", lambda source, **kwargs: [])
    monkeypatch.setattr(bootstrap, "child_env", lambda root, runtime: {
        "CUDA_VISIBLE_DEVICES": "GPU-selected", "OMP_NUM_THREADS": "2", "PATH": "/usr/bin"})

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "GPU-selected"
        assert kwargs["env"]["OMP_NUM_THREADS"] == "2"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return bootstrap.SOURCE_REV
        code = command[-1]
        if "-c" in command and "device='cuda'" in code:
            assert active == ["local_rig"]
            return json.dumps({"gpu": "selected", "attention_finite": True})
        assert not active
        return "TRUE" if "-c" in command and "_GLIBCXX_USE_CXX11_ABI" in code else ""

    monkeypatch.setattr(bootstrap, "run", run)
    bootstrap.install(tmp_path, None)
    assert len([command for command, _ in calls if "-c" in command and "device='cuda'" in command[-1]]) == 1
    assert not active


@pytest.mark.parametrize("selected", [None, {"CUDA_VISIBLE_DEVICES": "GPU-selected", "OMP_NUM_THREADS": "2"}])
def test_native_parts_setup_preserves_default_or_selected_environment_and_guards_probe(
        tmp_path, monkeypatch, selected):
    bootstrap = load_bootstrap("local_parts")
    active = mock_guard(monkeypatch, bootstrap)
    runtime = tmp_path / ".runtime/local-parts"
    (runtime / "GeoSAM2/sam2").mkdir(parents=True)
    (runtime / "GeoSAM2/sam2/build_sam.py").touch()
    (runtime / f"GeoSAM2-{bootstrap.CODE_REVISION}.tar.gz").touch()
    (runtime / bootstrap.MODEL_NAME).write_bytes(b"x")
    lock = tmp_path / "requirements.lock"
    lock.write_text("fixture==1\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "REQUIREMENTS", lock)
    monkeypatch.setattr(bootstrap, "MODEL_BYTES", 1)
    monkeypatch.setattr(bootstrap, "download", lambda *args: None)
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(sys, "argv", ["bootstrap_local_parts.py", "--root", str(tmp_path)])
    policy_calls = []
    monkeypatch.setattr(bootstrap, "apply_process_resources", lambda root: policy_calls.append(root))
    monkeypatch.setattr(bootstrap, "child_env", lambda root, runtime: selected)
    calls = []

    def check_output(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"] is selected
        if "device='cuda'" in command[-1]:
            assert active == ["local_parts"]
            return json.dumps({"gpu": "selected"})
        assert not active
        return "/usr/local/bin/uv"

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"] is selected
        assert not active

    monkeypatch.setattr(bootstrap.subprocess, "check_output", check_output)
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    bootstrap.main()
    assert policy_calls == [tmp_path.resolve()]
    assert len(calls) == 4
    assert not active


@pytest.mark.parametrize("name,runtime", [("kimodo", "kimodo"), ("local_rig", "local_rig"),
                                         ("local_parts", "local_parts")])
def test_active_policy_rejects_wsl_bridge_before_any_external_command(tmp_path, monkeypatch, name, runtime):
    bootstrap = load_bootstrap(name)
    from asset_auto.resources import ResourcePolicyError

    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(sys, "argv", [f"bootstrap_{name}.py", "--root", str(tmp_path)])
    calls = []

    def reject(root, selected_runtime):
        calls.append((root, selected_runtime))
        raise ResourcePolicyError("Active resource policy: run setup natively inside Linux/WSL")

    def forbidden(*args, **kwargs):
        pytest.fail("Bridge rejection must happen before any external command")

    monkeypatch.setattr(bootstrap, "reject_bridge", reject)
    monkeypatch.setattr(bootstrap.subprocess, "run", forbidden)
    monkeypatch.setattr(bootstrap.subprocess, "check_output", forbidden)
    with pytest.raises(ResourcePolicyError, match="natively inside Linux/WSL"):
        bootstrap.main()
    assert calls == [(tmp_path.resolve(), runtime)]


def test_rig_native_entrypoint_applies_process_controls_before_install(tmp_path, monkeypatch):
    bootstrap = load_bootstrap("local_rig")
    calls = []
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(sys, "argv", ["bootstrap_local_rig.py", "--root", str(tmp_path)])
    monkeypatch.setattr(bootstrap, "apply_process_resources", lambda root: calls.append("policy"))
    monkeypatch.setattr(bootstrap, "install", lambda *args: calls.append("install"))
    bootstrap.main()
    assert calls == ["policy", "install"]
