"""Core downloads exclude engines; authentication stays confined to GitHub API requests."""

import importlib.util
import sys
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture
def bootstrap():
    spec = importlib.util.spec_from_file_location(
        "bootstrap", Path(__file__).resolve().parents[1] / "scripts" / "bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    return bootstrap


def test_github_token_is_not_sent_to_download_hosts_or_redirects(monkeypatch, bootstrap):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    captured = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, **kwargs: captured.append(req))
    bootstrap.request("https://api.github.com/repos/owner/repo/releases")
    bootstrap.request("https://github.com/owner/repo/releases/download/tool.zip")
    bootstrap.request("https://huggingface.co/model")
    bootstrap.request("http://api.github.com/repos/owner/repo/releases")
    api, *others = captured
    assert api.get_header("Authorization") == "Bearer test-token"
    assert all(req.get_header("Authorization") is None for req in others)
    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
        api, None, 302, "Found", {}, "https://example.com/download"
    )
    assert redirected.get_header("Authorization") is None


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], {"blender", "trellis", "models"}),
        (["--only", "blender"], {"blender"}),
        (["--only", "godot"], {"godot"}),
        (["--only", "all"], {"blender", "trellis", "godot", "models"}),
    ],
)
def test_installer_downloads_only_selected_components(monkeypatch, tmp_path, bootstrap, arguments, expected):
    downloaded = []

    def record(component):
        downloaded.append(component)
        return {"component": component}

    monkeypatch.setattr(sys, "argv", ["bootstrap.py", *arguments])
    monkeypatch.setattr(bootstrap, "RUNTIME", tmp_path)
    monkeypatch.setattr(bootstrap, "blender", lambda system: record("blender"))
    monkeypatch.setattr(bootstrap, "models", lambda: record("models"))
    monkeypatch.setattr(bootstrap, "github_tool", lambda repo, version, name, target: record(target.name))
    bootstrap.main()
    assert set(downloaded) == expected
    assert {path.stem for path in (tmp_path / "installed").glob("*.json")} == expected
