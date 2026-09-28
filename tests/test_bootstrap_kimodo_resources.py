"""Kimodo setup isolation without running CUDA, compiling, or downloading models."""

import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def bootstrap(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/bootstrap_kimodo.py"
    spec = importlib.util.spec_from_file_location("bootstrap_kimodo_resources_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "resource_guard", lambda root, runtime, command: nullcontext(
        {"command": command, "env": None, "report": {}}))
    return module


@pytest.fixture
def pinned_build_fragment():
    # The pinned upstream setup.py passes the old Python variable even though
    # MotionCorrection's CMakeLists.txt uses find_package(Python3 ...).
    return '''cmake_args = [
            f"-DPYTHON_EXECUTABLE={sys.executable}",
        ]
build_args = []
build_args += ["--", "-j4"]
'''


def test_setup_environment_keeps_private_selection_and_replaces_parent_python(bootstrap, tmp_path, monkeypatch):
    parent = {"VIRTUAL_ENV": "/app/.venv", "PYTHONHOME": "/python313", "PYTHONPATH": "/app/modules",
              "PATH": os.pathsep.join(["/app/.venv/bin", "/mnt/c/Windows", "/usr/bin"]),
              "CUDA_VISIBLE_DEVICES": "GPU-selected", "OMP_NUM_THREADS": "2", "HF_HOME": "/login/hf"}
    before = parent.copy()
    calls = []

    def child_env(root, backend):
        calls.append((root, backend))
        return parent

    monkeypatch.setattr(bootstrap, "child_env", child_env)
    env = bootstrap.setup_environment(tmp_path)
    runtime = tmp_path / ".runtime/kimodo"
    assert calls == [(tmp_path, "kimodo")]
    assert parent == before
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-selected"
    assert env["OMP_NUM_THREADS"] == "2"
    assert env["VIRTUAL_ENV"] == str(runtime / ".venv")
    assert env["PATH"].split(os.pathsep)[0] == str(runtime / ".venv/bin")
    assert "/mnt/c/Windows" not in env["PATH"]
    assert "PYTHONHOME" not in env and "PYTHONPATH" not in env
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["HF_TOKEN_PATH"] == str(Path("/login/hf/token"))
    assert env["HF_HOME"] == str(runtime / "cache/huggingface")


@pytest.mark.parametrize("original,token", [
    ({"HF_TOKEN_PATH": "/credentials/login", "HF_HOME": "/old/hf"}, "/credentials/login"),
    ({"HF_HOME": "/old/hf"}, str(Path("/old/hf/token"))),
    ({"XDG_CACHE_HOME": "/user/cache"}, str(Path("/user/cache/huggingface/token"))),
    ({}, None),
])
def test_cache_relocation_preserves_login_path_without_reading_it(bootstrap, tmp_path, monkeypatch, original, token):
    monkeypatch.setattr(bootstrap, "child_env", lambda *_: original)
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: pytest.fail("Do not inspect token contents"))
    env = bootstrap.setup_environment(tmp_path)
    assert env["HF_TOKEN_PATH"] == (token or str(Path.home() / ".cache/huggingface/token"))
    assert env["HF_HOME"] == str(tmp_path / ".runtime/kimodo/cache/huggingface")
    assert "HF_TOKEN_PATH" not in original or original["HF_TOKEN_PATH"] == "/credentials/login"


def test_unconfigured_resources_preserve_inherited_cuda_and_thread_environment(bootstrap, tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "child_env", lambda *_: None)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-already-selected")
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    before = os.environ.copy()
    env = bootstrap.setup_environment(tmp_path)
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-already-selected"
    assert env["OMP_NUM_THREADS"] == "3"
    assert dict(os.environ) == before


@pytest.mark.parametrize("env,expected_jobs", [({}, "-j4"), ({"OMP_NUM_THREADS": "2"}, "-j2")])
def test_temporary_build_passes_findpython3_interpreter_and_thread_limit(
        bootstrap, tmp_path, pinned_build_fragment, env, expected_jobs):
    original = tmp_path / "checkout"
    original.mkdir()
    (original / "setup.py").write_text(pinned_build_fragment, encoding="utf-8")
    build = tmp_path / "temporary-build"
    shutil.copytree(original, build)
    bootstrap.prepare_build_source(build, env)
    runtime_python = str(tmp_path / ".runtime/kimodo/.venv/bin/python")
    context = runpy.run_path(str(build / "setup.py"), init_globals={
        "sys": SimpleNamespace(executable=runtime_python)})
    assert f"-DPython3_EXECUTABLE={runtime_python}" in context["cmake_args"]
    assert context["build_args"] == ["--", expected_jobs]
    assert (original / "setup.py").read_text(encoding="utf-8") == pinned_build_fragment


def test_build_adapter_rejects_unrecognized_upstream_without_overwriting_it(bootstrap, tmp_path):
    setup = tmp_path / "setup.py"
    setup.write_text("# Different build contract\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="build script changed"):
        bootstrap.prepare_build_source(tmp_path, {})
    assert setup.read_text(encoding="utf-8") == "# Different build contract\n"


@pytest.mark.parametrize("result", [
    subprocess.CalledProcessError(1, ["python", "-c", "probe"]),
    '{"cuda_test_passed": false}',
    '[]',
    'not JSON',
    '',
])
def test_probe_failures_explain_isolated_runtime_and_never_retry(bootstrap, tmp_path, monkeypatch, result):
    calls = []
    selected = {"CUDA_VISIBLE_DEVICES": "GPU-private", "OMP_NUM_THREADS": "2"}

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(bootstrap, "run", run)
    python = tmp_path / ".runtime/kimodo/.venv/bin/python"
    with pytest.raises(RuntimeError, match="isolated Python/CUDA probe failed") as raised:
        bootstrap.probe_runtime(tmp_path, python, selected)
    assert "motion_correction" in str(raised.value)
    assert "private resource selection" in str(raised.value)
    assert "No alternate GPU was tried" in str(raised.value)
    assert len(calls) == 1
    assert calls[0][0][0] == python
    assert calls[0][1]["env"] == selected


def test_probe_refreshes_resource_selection_without_restoring_parent_python(bootstrap, tmp_path, monkeypatch):
    runtime_env = {"VIRTUAL_ENV": "isolated-venv", "PATH": "isolated-bin", "HF_HOME": "isolated-cache",
                   "CUDA_VISIBLE_DEVICES": "GPU-before-wait", "OMP_NUM_THREADS": "4"}
    guarded_env = {"VIRTUAL_ENV": "parent-venv", "PATH": "parent-bin", "HF_HOME": "parent-cache",
                   "CUDA_VISIBLE_DEVICES": "GPU-selected", "OMP_NUM_THREADS": "2"}
    monkeypatch.setattr(bootstrap, "resource_guard", lambda root, runtime, command: nullcontext(
        {"command": command, "env": guarded_env, "report": {}}))

    def run(command, **kwargs):
        assert kwargs["env"] == runtime_env | {"CUDA_VISIBLE_DEVICES": "GPU-selected", "OMP_NUM_THREADS": "2"}
        return '{"cuda_test_passed": true}'

    monkeypatch.setattr(bootstrap, "run", run)
    assert bootstrap.probe_runtime(tmp_path, tmp_path / "python", runtime_env)["cuda_test_passed"] is True


def test_probe_keeps_policy_failure_actionable_without_launching_cuda(bootstrap, tmp_path, monkeypatch):
    error = bootstrap.ResourcePolicyError("Selected GPU is protected")

    def guard(*args):
        raise error

    monkeypatch.setattr(bootstrap, "resource_guard", guard)
    monkeypatch.setattr(bootstrap, "run", lambda *args, **kwargs: pytest.fail("CUDA must not launch"))
    with pytest.raises(bootstrap.ResourcePolicyError) as raised:
        bootstrap.probe_runtime(tmp_path, tmp_path / "python", {})
    assert raised.value is error


def test_mocked_install_uses_selected_resources_for_every_child_and_runtime_python_for_build(
        bootstrap, tmp_path, monkeypatch, pinned_build_fragment):
    runtime = tmp_path / ".runtime/kimodo"
    source = runtime / "source"
    source.mkdir(parents=True)
    (source / "setup.py").write_text(pinned_build_fragment, encoding="utf-8")
    uv = tmp_path / "uv"
    uv.touch()
    calls = []
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda command: str(uv))
    monkeypatch.setattr(bootstrap, "child_env", lambda root, backend: {
        "CUDA_VISIBLE_DEVICES": "GPU-private", "OMP_NUM_THREADS": "2", "VIRTUAL_ENV": "/app/.venv"})

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return bootstrap.SOURCE_REV
        if args[0] == "git":
            return ""
        if "setup.py" in args:
            built = kwargs["cwd"]
            assert "-DPython3_EXECUTABLE=" in (built / "setup.py").read_text(encoding="utf-8")
            (built / "dist").mkdir()
            (built / "dist/kimodo.whl").write_bytes(b"mock wheel")
        if "-c" in args:
            return json.dumps({"torch": "fixture", "gpu": "private device", "cuda_test_passed": True})
        return "" if kwargs.get("capture") else None

    monkeypatch.setattr(bootstrap, "run", run)
    bootstrap.install(tmp_path, None, True)
    assert all(kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "GPU-private" for _, kwargs in calls)
    assert all(kwargs["env"]["VIRTUAL_ENV"] == str(runtime / ".venv") for _, kwargs in calls)
    build = next(args for args, _ in calls if "setup.py" in args)
    assert build[0] == runtime / ".venv/bin/python"
    assert not any("--download-models" in args for args, _ in calls)
    assert (source / "setup.py").read_text(encoding="utf-8") == pinned_build_fragment


def test_native_entrypoint_applies_process_resources_before_install(bootstrap, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["bootstrap_kimodo.py", "--root", str(tmp_path), "--skip-models"])
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(bootstrap, "apply_process_resources", lambda root: calls.append(("resources", root)))
    monkeypatch.setattr(bootstrap, "install", lambda root, *args: calls.append(("install", root)))
    bootstrap.main()
    assert calls == [("resources", tmp_path.resolve()), ("install", tmp_path.resolve())]
