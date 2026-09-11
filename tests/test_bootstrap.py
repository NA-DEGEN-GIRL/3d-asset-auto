"""Download authentication must stay confined to GitHub API requests."""

import importlib.util
import urllib.request
from pathlib import Path


def test_github_token_is_not_sent_to_download_hosts_or_redirects(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "bootstrap", Path(__file__).resolve().parents[1] / "scripts" / "bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
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
