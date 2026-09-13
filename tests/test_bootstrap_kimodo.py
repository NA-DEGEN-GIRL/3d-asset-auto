"""HF permission failures must stay actionable without requiring model downloads."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class GatedError(Exception):
    pass


def http_error(status, message):
    error = Exception(message)
    error.response = SimpleNamespace(status_code=status)
    return error


def wrapped(error):
    outer = Exception("File missing from local cache; please check your connection")
    outer.__cause__ = error
    return outer


@pytest.fixture
def bootstrap():
    path = Path(__file__).resolve().parents[1] / "scripts/bootstrap_kimodo.py"
    spec = importlib.util.spec_from_file_location("bootstrap_kimodo_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("error,expected", [
    (GatedError("Account must be approved"), "model_access"),
    (wrapped(GatedError("Account must be approved")), "model_access"),
    (wrapped(http_error(403, "Please enable access to public gated repositories in your "
                             "fine-grained token settings to view this repository")), "token_scope"),
    (wrapped(http_error(401, "Invalid credentials")), "token_auth"),
    (wrapped(http_error(403, "Unrelated access policy")), None),
    (wrapped(http_error(503, "Service unavailable")), None),
    (ConnectionError("Network unavailable"), None),
])
def test_permission_cause_is_distinguished_from_network_failure(bootstrap, error, expected):
    assert bootstrap.access_issue(error, GatedError) == expected


def test_permission_cause_handles_context_cycles(bootstrap):
    error = wrapped(http_error(403, "Enable access in fine-grained token settings"))
    error.__cause__.__context__ = error
    assert bootstrap.access_issue(error, GatedError) == "token_scope"
    error.__cause__.response.status_code = 503
    assert bootstrap.access_issue(error, GatedError) is None


def test_scope_failure_keeps_public_downloads_and_reports_no_credential(bootstrap, tmp_path, monkeypatch, capsys):
    runtime = tmp_path / ".runtime/kimodo"
    runtime.mkdir(parents=True)
    secret = "fake-private-test-value"
    token_file = tmp_path / ".secrets/hf_token"
    token_file.parent.mkdir()
    token_file.write_text(secret, encoding="utf-8")
    monkeypatch.setattr(bootstrap, "MODEL_PINS", {"base": ("vendor/gated", "base-pin"),
                                                "motion": ("vendor/public", "motion-pin")})
    calls = []

    def snapshot_download(repo, **kwargs):
        calls.append(repo)
        assert kwargs["token"] == secret
        if repo == "vendor/gated":
            raise wrapped(http_error(403, f"{secret}: enable access in fine-grained token settings"))
        folder = kwargs["local_dir"]
        folder.mkdir(parents=True)
        (folder / "weights.safetensors").write_bytes(b"public model fixture")
        (folder / ".cache").mkdir()
        (folder / ".cache/private-metadata").write_text("not a model file")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        get_token=lambda: pytest.fail("Saved token must be reused"), snapshot_download=snapshot_download))
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", SimpleNamespace(GatedRepoError=GatedError))
    with pytest.raises(RuntimeError, match="account approval alone is insufficient") as raised:
        bootstrap.download(tmp_path, runtime)
    assert calls == ["vendor/gated", "vendor/public"]
    records = json.loads((runtime / "model-files-partial.json").read_text())
    assert len(records) == 1 and records[0]["path"] == "models/motion/weights.safetensors"
    assert records[0]["sha256"] == bootstrap.sha256(runtime / records[0]["path"])
    assert secret not in str(raised.value) + capsys.readouterr().out
    assert raised.value.__context__ is None


def test_unrelated_download_error_is_preserved(bootstrap, tmp_path, monkeypatch):
    error = wrapped(http_error(503, "Retry later"))

    def snapshot_download(*args, **kwargs):
        raise error

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        get_token=lambda: None, snapshot_download=snapshot_download))
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", SimpleNamespace(GatedRepoError=GatedError))
    with pytest.raises(Exception) as raised:
        bootstrap.download(tmp_path, tmp_path / "runtime")
    assert raised.value is error
