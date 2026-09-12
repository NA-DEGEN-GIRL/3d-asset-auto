"""Contract tests for opt-in paid generation, with no real keys or network calls."""

import hashlib
import io
import json
import socket
import struct
import urllib.error
import urllib.request

import pytest
from pydantic import ValidationError

from asset_auto import tripo, tripo_credentials
from asset_auto.models import AssetSpec
from asset_auto.store import read_json, write_json


def glb_bytes():
    scene = b'{"asset":{"version":"2.0"}}'
    scene += b" " * (-len(scene) % 4)
    chunk = struct.pack("<I4s", len(scene), b"JSON") + scene
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk


@pytest.fixture(autouse=True)
def isolate_credentials_and_network(monkeypatch):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY_FILE", raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("Tests must never access the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(tripo.time, "sleep", lambda seconds: None)


@pytest.fixture
def reference(tmp_path):
    path = tmp_path / "front.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nlocal-test-reference")
    return path


def spec_for(image="front.png", **overrides):
    values = {
        "asset_id": "tripo-prop",
        "provider": "tripo",
        "image": image,
        "tripo": {"max_credits": 30},
    }
    return AssetSpec.model_validate(values | overrides)


class FakeProvider:
    def __init__(self, folder, *, balance=100, states=("success",), create_error=None):
        self.folder = folder
        self.available = balance
        self.states = iter(states)
        self.create_error = create_error
        self.calls = []

    def balance(self):
        self.calls.append(("balance",))
        return {"balance": self.available}

    def upload(self, path):
        self.calls.append(("upload", path.name))
        return "private-token-" + path.stem

    def create(self, mode, payload):
        self.calls.append(("create", mode, payload))
        assert read_json(self.folder / "tripo.json")["state"] == "submitting"
        if self.create_error:
            raise self.create_error
        return {"task_id": "known-task-123"}

    def task(self, task_id):
        self.calls.append(("task", task_id))
        assert read_json(self.folder / "tripo.json")["task_id"] == task_id
        return {
            "status": next(self.states),
            "progress": 75,
            "credits_consumed": 30,
            "output": {"model_url": "https://cdn.example.com/model.glb?private=signed"},
        }

    def download(self, url, target):
        self.calls.append(("download",))
        target.write_bytes(glb_bytes())


def client_with_openers(api=None, downloads=None):
    client = object.__new__(tripo.TripoClient)
    client._key = "test-secret-never-real"
    client._api = api
    client._downloads = downloads
    return client


class FakeOpener:
    def __init__(self, contents=b"", error=None):
        self.contents = contents
        self.error = error
        self.requests = []

    def open(self, request, **kwargs):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(self.contents)


def test_tripo_is_explicit_and_trellis_remains_default():
    assert AssetSpec(asset_id="local-prop", image="front.png").provider == "trellis"
    with pytest.raises(ValidationError, match="explicit provider: tripo"):
        AssetSpec(asset_id="local-prop", image="front.png", tripo={"max_credits": 30})
    with pytest.raises(ValidationError, match="explicit provider: tripo"):
        AssetSpec(asset_id="local-prop", views={"front": "front.png", "back": "back.png"})
    with pytest.raises(ValidationError, match="max_credits"):
        spec_for(tripo=None)


@pytest.mark.parametrize(
    "changes",
    [
        {"image": None},
        {"views": {"front": "f.png", "back": "b.png"}},
        {"image": None, "views": {"front": "f.png"}},
        {"image": None, "views": {"back": "b.png", "left": "l.png"}},
        {"image": None, "views": {"front": "f.png", "left": " "}},
        {"image": None, "views": {"front": "f.png", "top": "t.png"}},
        {"source": "mesh.glb"},
    ],
)
def test_input_modes_require_single_image_or_named_front_and_other_view(changes):
    with pytest.raises(ValidationError):
        spec_for(**changes)


@pytest.mark.parametrize("budget", [0, -1, 100001, 1.5, None])
def test_paid_budget_is_explicit_and_bounded(budget):
    with pytest.raises(ValidationError):
        spec_for(tripo={"max_credits": budget})
    with pytest.raises(ValidationError):
        spec_for(tripo={"max_credits": 30, "model": "latest"})


def test_credential_file_and_environment_precedence(tmp_path, monkeypatch):
    default = tmp_path / ".secrets/tripo_api_key"
    default.parent.mkdir()
    default.write_text("\ufefffile-test-key\n", encoding="utf-8")
    assert tripo_credentials.api_key(tmp_path) == "file-test-key"
    custom = tmp_path / "custom.key"
    custom.write_text("custom-test-key", encoding="utf-8")
    monkeypatch.setenv("TRIPO_API_KEY_FILE", "custom.key")
    assert tripo_credentials.api_key(tmp_path) == "custom-test-key"
    monkeypatch.setenv("TRIPO_API_KEY", " environment-test-key ")
    custom.unlink()
    assert tripo_credentials.api_key(tmp_path) == "environment-test-key"
    assert tripo_credentials.key_configured(tmp_path)


def test_invalid_or_missing_credentials_do_not_expose_contents(tmp_path, monkeypatch):
    assert not tripo_credentials.key_configured(tmp_path)
    secret = "private-test-key newline"
    monkeypatch.setenv("TRIPO_API_KEY", secret)
    with pytest.raises(ValueError) as error:
        tripo_credentials.api_key(tmp_path)
    assert "private-test-key" not in str(error.value)
    assert not tripo_credentials.key_configured(tmp_path)


@pytest.mark.parametrize(
    "character,source", [("\x1b", "environment"), ("\x7f", "environment"), ("é", "environment"), ("\x00", "file")]
)
def test_control_and_nonascii_credential_characters_are_rejected_without_exposure(
    tmp_path, monkeypatch, character, source
):
    secret = "private-test-key" + character + "suffix"
    if source == "environment":
        monkeypatch.setenv("TRIPO_API_KEY", secret)
    else:
        path = tmp_path / ".secrets/tripo_api_key"
        path.parent.mkdir()
        path.write_text(secret, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        tripo_credentials.api_key(tmp_path)
    assert secret not in str(error.value)
    assert "private-test-key" not in str(error.value)
    assert not tripo_credentials.key_configured(tmp_path)


def test_plan_is_read_only_and_does_not_require_credentials(tmp_path, reference, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Planning must not initialize an authenticated client")

    monkeypatch.setattr(tripo, "TripoClient", denied)
    before = set(tmp_path.rglob("*"))
    proposed = tripo.plan(tmp_path, spec_for(tripo={"max_credits": 29}))
    assert proposed["estimated_credits"] == 30
    assert proposed["within_budget"] is False
    assert proposed["model"] == "v3.1-20260211"
    assert proposed["mode"] == "image-to-model"
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("budget,balance,expected", [(29, 100, []), (30, 29, [("balance",)])])
def test_spending_guards_prevent_uploads_and_paid_submission(tmp_path, reference, budget, balance, expected):
    out = tmp_path / "revision"
    client = FakeProvider(out, balance=balance)
    with pytest.raises(tripo.TripoError):
        tripo.generate(tmp_path, spec_for(tripo={"max_credits": budget}), out, client=client)
    assert client.calls == expected
    assert not out.exists()


def test_named_multiview_payload_and_local_provenance(tmp_path, reference):
    for name in ("left", "back", "right"):
        (tmp_path / f"{name}.png").write_bytes(reference.read_bytes())
    spec = spec_for(image=None, views={name: f"{name}.png" for name in ("right", "back", "front", "left")})
    out = tmp_path / "revision"
    client = FakeProvider(out)
    result = tripo.generate(tmp_path, spec, out, client=client)
    created = [call for call in client.calls if call[0] == "create"]
    assert len(created) == 1
    _, mode, payload = created[0]
    assert mode == "multiview-to-model"
    assert payload["inputs"] == [
        {view: "private-token-reference-" + view} for view in ("front", "left", "back", "right")
    ]
    assert "input" not in payload
    assert payload["model"] == "v3.1-20260211"
    assert payload["texture_quality"] == payload["geometry_quality"] == "standard"
    assert payload["texture"] and payload["pbr"]
    assert payload["model_seed"] == payload["texture_seed"] == spec.seed
    assert result["state"] == "success"
    assert result["download_sha256"] == hashlib.sha256((out / "generated.glb").read_bytes()).hexdigest()
    assert result["credits_consumed"] == 30
    assert result["reported_over_budget"] is False
    assert all((out / item["file"]).is_file() for item in result["references"])
    checkpoint = (out / "tripo.json").read_text()
    assert "private-token" not in checkpoint
    assert "private=signed" not in checkpoint


def test_timed_out_polling_resumes_recorded_task_without_second_charge(tmp_path, reference):
    out = tmp_path / "revision"
    client = FakeProvider(out, states=("running", "success"))
    spec = spec_for()
    with pytest.raises(tripo.TripoError, match="resume-tripo"):
        tripo.generate(tmp_path, spec, out, client=client, poll_timeout=0)
    waiting = read_json(out / "tripo.json")
    assert waiting["task_id"] == "known-task-123"
    assert waiting["state"] == "waiting"
    with pytest.raises(tripo.TripoError, match="resume"):
        tripo.generate(tmp_path, spec, out, client=client)
    result = tripo.generate(tmp_path, spec, out, resume=True, client=client)
    assert result["state"] == "success"
    assert sum(call[0] == "create" for call in client.calls) == 1
    assert sum(call[0] == "upload" for call in client.calls) == 1
    payload = next(call[2] for call in client.calls if call[0] == "create")
    assert payload["input"] == "private-token-reference-image"
    assert "inputs" not in payload


def test_ambiguous_submission_is_persisted_and_never_retried(tmp_path, reference):
    out = tmp_path / "revision"
    client = FakeProvider(out, create_error=TimeoutError("sensitive diagnostic"))
    spec = spec_for()
    with pytest.raises(tripo.TripoError, match="outcome is unknown") as error:
        tripo.generate(tmp_path, spec, out, client=client)
    assert "sensitive diagnostic" not in str(error.value)
    record = read_json(out / "tripo.json")
    assert record["state"] == "submission_unknown"
    assert "task_id" not in record
    with pytest.raises(tripo.TripoError, match="resume"):
        tripo.generate(tmp_path, spec, out, client=client)
    with pytest.raises(tripo.TripoError, match="dashboard"):
        tripo.generate(tmp_path, spec, out, resume=True, client=client)
    assert sum(call[0] == "create" for call in client.calls) == 1


@pytest.mark.parametrize("state", ["failed", "cancelled", "banned", "expired", "unrecognized"])
def test_terminal_and_unknown_status_preserve_task_without_retry(tmp_path, reference, state):
    out = tmp_path / "revision"
    client = FakeProvider(out, states=(state,))
    with pytest.raises(tripo.TripoError, match="status"):
        tripo.generate(tmp_path, spec_for(), out, client=client)
    assert read_json(out / "tripo.json")["task_id"] == "known-task-123"
    assert sum(call[0] == "create" for call in client.calls) == 1
    assert not any(call[0] == "download" for call in client.calls)


def test_verified_raw_model_reuses_offline_after_blender_failure(tmp_path, monkeypatch):
    out = tmp_path / "revision"
    out.mkdir()
    target = out / "generated.glb"
    target.write_bytes(glb_bytes())
    record = {
        "task_id": "known-task-123",
        "state": "success",
        "download_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    write_json(out / "tripo.json", record)

    def denied(*args, **kwargs):
        raise AssertionError("Offline Blender recovery must not initialize a remote client")

    monkeypatch.setattr(tripo, "TripoClient", denied)
    assert tripo.generate(tmp_path, spec_for(), out, resume=True) == record


def test_invalid_cached_raw_with_matching_hash_downloads_known_task_again(tmp_path):
    out = tmp_path / "revision"
    out.mkdir()
    target = out / "generated.glb"
    target.write_bytes(b"<html>temporarily unavailable</html>")
    record = {
        "task_id": "known-task-123",
        "state": "success",
        "max_credits": 30,
        "download_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    write_json(out / "tripo.json", record)
    client = FakeProvider(out)
    recovered = tripo.generate(tmp_path, spec_for(), out, resume=True, client=client)
    assert client.calls == [("task", "known-task-123"), ("download",)]
    assert target.read_bytes() == glb_bytes()
    assert recovered["download_sha256"] != record["download_sha256"]
    assert recovered["download_sha256"] == hashlib.sha256(glb_bytes()).hexdigest()


@pytest.mark.parametrize("invalid", [b"short", b"<html>private-error-detail</html>", glb_bytes()[:-1]])
def test_invalid_download_is_not_cached_and_resume_does_not_resubmit(tmp_path, reference, monkeypatch, invalid):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))])
    out = tmp_path / "revision"
    client = FakeProvider(out, states=("success", "success"))
    opener = FakeOpener(invalid)
    transport = client_with_openers(downloads=opener)
    monkeypatch.setattr(client, "download", transport.download)
    with pytest.raises(tripo.TripoError) as error:
        tripo.generate(tmp_path, spec_for(), out, client=client)
    assert "private-error-detail" not in str(error.value)
    assert "private=signed" not in str(error.value)
    assert not (out / "generated.glb").exists()
    failed = read_json(out / "tripo.json")
    assert failed["task_id"] == "known-task-123"
    assert "download_sha256" not in failed
    opener.contents = glb_bytes()
    recovered = tripo.generate(tmp_path, spec_for(), out, resume=True, client=client)
    assert recovered["download_sha256"] == hashlib.sha256(glb_bytes()).hexdigest()
    assert (out / "generated.glb").read_bytes() == glb_bytes()
    assert sum(call[0] == "create" for call in client.calls) == 1
    assert len(opener.requests) == 2


@pytest.mark.parametrize("method,count", [("POST", 1), ("GET", 3)])
def test_transport_retries_only_read_requests_and_sanitizes_errors(method, count):
    opener = FakeOpener(error=urllib.error.URLError("test-secret-never-real https://signed.example/?secret"))
    client = client_with_openers(api=opener)
    with pytest.raises(tripo.TripoError) as error:
        client.request(method, "/generation/image-to-model", {"input": "token"})
    assert len(opener.requests) == count
    assert "test-secret-never-real" not in str(error.value)
    assert "signed.example" not in str(error.value)
    assert opener.requests[0].get_header("Authorization") == "Bearer test-secret-never-real"


def test_api_errors_suppress_vendor_body_and_credentials():
    error = urllib.error.HTTPError(
        "https://openapi.tripo3d.ai/v3/files", 401, "test-secret-never-real", {}, None
    )
    client = client_with_openers(api=FakeOpener(error=error))
    with pytest.raises(tripo.TripoError, match="HTTP 401") as caught:
        client.request("POST", "/files", b"image")
    assert "test-secret-never-real" not in str(caught.value)


@pytest.mark.parametrize("balance", [True, -1, "30", None, float("nan"), float("inf")])
def test_balance_rejects_invalid_available_credit_values(balance):
    response = json.dumps({"code": 0, "data": {"balance": balance}}).encode()
    client = client_with_openers(api=FakeOpener(response))
    with pytest.raises(tripo.TripoError, match="balance"):
        client.balance()


def test_downloads_use_separate_request_without_bearer(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))])
    opener = FakeOpener(glb_bytes())
    client = client_with_openers(downloads=opener)
    target = tmp_path / "result.glb"
    client.download("https://cdn.example.com/file.glb?signed=token", target)
    assert target.read_bytes() == glb_bytes()
    assert opener.requests[0].get_header("Authorization") is None
    assert not target.with_suffix(".glb.part").exists()
    redirected = tripo.DownloadRedirect().redirect_request(
        opener.requests[0], None, 302, "Found", {}, "https://other.example.com/file.glb"
    )
    assert redirected.get_header("Authorization") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.com/a.glb",
        "file:///private/model.glb",
        "https://user:pass@cdn.example.com/a.glb",
        "https://cdn.example.com:8443/a.glb",
    ],
)
def test_download_rejects_insecure_urls_before_dns(url):
    with pytest.raises(tripo.TripoError):
        tripo.validate_download_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://[private-secret/model.glb",
        "https://cdn.example.com:private-secret/model.glb?signature=private-secret",
        "https://cdn.example.com:999999/model.glb?signature=private-secret",
    ],
)
def test_malformed_download_url_and_redirect_errors_hide_signed_details(url):
    with pytest.raises(tripo.TripoError) as error:
        tripo.validate_download_url(url)
    assert url not in str(error.value)
    assert "private-secret" not in str(error.value)
    with pytest.raises(tripo.TripoError) as redirected:
        tripo.DownloadRedirect().redirect_request(
            urllib.request.Request("https://public.example.com/model.glb"), None, 302, "Found", {}, url
        )
    assert url not in str(redirected.value)
    assert "private-secret" not in str(redirected.value)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fc00::1"])
def test_download_and_redirect_reject_private_addresses(address, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(tripo.TripoError, match="Non-public"):
        tripo.validate_download_url("https://cdn.example.com/model.glb")
    with pytest.raises(tripo.TripoError, match="Non-public"):
        tripo.DownloadRedirect().redirect_request(
            urllib.request.Request("https://public.example.com/model.glb"),
            None, 302, "Found", {}, "https://private.example.com/model.glb",
        )


def test_authenticated_api_redirect_is_refused_without_exposing_key():
    request = urllib.request.Request("https://openapi.tripo3d.ai/v3/account/balance")
    request.add_unredirected_header("Authorization", "Bearer test-secret-never-real")
    with pytest.raises(tripo.TripoError, match="redirect refused") as caught:
        tripo.NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://evil.example.com/")
    assert "test-secret-never-real" not in str(caught.value)
