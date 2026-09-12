"""Opt-in Tripo v3 adapter. Never automatically retry charge-creating requests."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .models import AssetSpec
from .store import now, read_json, write_json
from .tripo_credentials import api_key

API_BASE = "https://openapi.tripo3d.ai/v3"
ESTIMATED_CREDITS = 30
PRICE_SOURCE = "https://developers.tripo3d.ai/en/pricing"
PRICE_CHECKED = "2026-09-12"
MAX_IMAGE_BYTES = 20_000_000
MAX_MODEL_BYTES = 1_000_000_000
VIEW_ORDER = ("front", "left", "back", "right")
TERMINAL_FAILURES = {"failed", "cancelled", "banned", "expired"}


class TripoError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TripoError("Tripo API redirect refused; credentials were not forwarded")


def validate_download_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (ValueError, TypeError):
        raise TripoError("Tripo returned a malformed model download URL") from None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise TripoError("Tripo model download requires a public HTTPS URL")
    if port not in (None, 443):
        raise TripoError("Unexpected model download port")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise TripoError("Non-public model download address refused")
    except OSError:
        raise TripoError("Model download host could not be resolved") from None


class DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class TripoClient:
    def __init__(self, root):
        self._key = api_key(root)
        self._api = urllib.request.build_opener(NoRedirect())
        self._downloads = urllib.request.build_opener(DownloadRedirect())

    def request(self, method, path, body=None, content_type="application/json"):
        if not path.startswith("/") or ".." in path or "?" in path:
            raise ValueError("Invalid Tripo API path")
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        headers = {"Accept": "application/json", "User-Agent": "asset-auto/0.1"}
        if data is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
        request.add_unredirected_header("Authorization", f"Bearer {self._key}")
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                with self._api.open(request, timeout=60) as response:
                    raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise TripoError("Oversized Tripo API response")
                envelope = json.loads(raw)
                if not isinstance(envelope, dict) or envelope.get("code") != 0:
                    raise TripoError("Tripo rejected the API request; inspect account/task status")
                data = envelope.get("data")
                if not isinstance(data, dict):
                    raise TripoError("Unexpected Tripo response structure")
                return data
            except urllib.error.HTTPError as error:
                if method == "GET" and error.code in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                    time.sleep(attempt + 1)
                    continue
                raise TripoError(f"Tripo API returned HTTP {error.code} for {method} {path}") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt + 1 < attempts:
                    time.sleep(attempt + 1)
                    continue
                raise TripoError(f"Tripo connection failed for {method} {path}; no POST retry was made") from None
            except (json.JSONDecodeError, UnicodeError):
                raise TripoError("Tripo returned an unreadable response") from None

    def balance(self):
        data = self.request("GET", "/account/balance")
        available = data.get("balance")
        if (
            not isinstance(available, (int, float)) or isinstance(available, bool)
            or not math.isfinite(available) or available < 0
        ):
            raise TripoError("Tripo did not return a valid available credit balance")
        return {"balance": available, "frozen": data.get("frozen"), "checked_at": now()}

    def upload(self, path):
        validate_image(path)
        boundary = "assetauto" + uuid.uuid4().hex
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        prefix = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"reference{path.suffix.lower()}\"\r\nContent-Type: {mime}\r\n\r\n"
        ).encode()
        body = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        data = self.request("POST", "/files", body, f"multipart/form-data; boundary={boundary}")
        token = data.get("file_token")
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise TripoError("Tripo upload did not return a file token")
        return token

    def create(self, mode, payload):
        return self.request("POST", f"/generation/{mode}", payload)

    def task(self, task_id):
        if not isinstance(task_id, str) or not task_id or len(task_id) > 200:
            raise TripoError("Invalid Tripo task ID")
        if any(not (character.isascii() and (character.isalnum() or character in "_-")) for character in task_id):
            raise TripoError("Invalid Tripo task ID")
        return self.request("GET", f"/tasks/{task_id}")

    def download(self, url, target):
        from .pipeline import validate_glb

        validate_download_url(url)
        # Separate opener and request: bearer credentials never accompany result URLs.
        request = urllib.request.Request(url, headers={"User-Agent": "asset-auto/0.1"})
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with self._downloads.open(request, timeout=120) as response, temporary.open("wb") as stream:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_MODEL_BYTES:
                        raise TripoError("Tripo result exceeds the 1 GB download limit")
                    stream.write(chunk)
            if total < 12:
                raise TripoError("Tripo returned an empty or truncated model")
            try:
                validate_glb(temporary)
            except ValueError:
                raise TripoError("Tripo downloaded an invalid GLB; resume the known task to retry downloading") from None
            temporary.replace(target)
        except (urllib.error.URLError, TimeoutError, OSError):
            # Signed URLs and HTTP error bodies must not appear in logs.
            raise TripoError("Tripo model download failed; resume the known task to retry downloading") from None


def validate_image(path):
    if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("Tripo input must be an existing PNG or JPEG file")
    if not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("Tripo input must be nonempty and no larger than 20 MB")


def inputs(root, spec):
    values = [(name, spec.views[name]) for name in VIEW_ORDER if spec.views and name in spec.views]
    if not values:
        values = [("image", spec.image)]
    result = []
    for name, value in values:
        path = Path(value).expanduser()
        path = path.resolve() if path.is_absolute() else (root / path).resolve()
        validate_image(path)
        result.append((name, path))
    return result


def plan(root, spec):
    if spec.provider != "tripo" or spec.tripo is None:
        raise ValueError("Tripo plan requires an explicit provider: tripo request")
    images = inputs(root, spec)
    return {
        "provider": "tripo",
        "mode": "multiview-to-model" if spec.views else "image-to-model",
        "model": spec.tripo.model,
        "inputs": [{"view": name, "path": str(path)} for name, path in images],
        "estimated_credits": ESTIMATED_CREDITS,
        "max_credits": spec.tripo.max_credits,
        "within_budget": spec.tripo.max_credits >= ESTIMATED_CREDITS,
        "budget_scope": "Client estimate guard; not a server-enforced spending cap",
        "price_source": PRICE_SOURCE,
        "price_checked": PRICE_CHECKED,
        "settings": {"texture": True, "pbr": True, "texture_quality": "standard", "geometry_quality": "standard"},
    }


def generate(root, spec: AssetSpec, out, *, resume=False, client=None, poll_timeout=300):
    from .pipeline import validate_glb

    checkpoint = out / "tripo.json"
    if resume:
        record = read_json(checkpoint)
        if not record.get("task_id"):
            raise TripoError("No recorded Tripo task ID; inspect the vendor dashboard before any new paid request")
    else:
        if checkpoint.exists():
            raise TripoError("Tripo submission already recorded; resume it instead of submitting again")
        proposed = plan(root, spec)
        if not proposed["within_budget"]:
            raise TripoError(f"Estimated Tripo cost is {ESTIMATED_CREDITS} credits, above tripo.max_credits")
        client = client or TripoClient(root)
        balance = client.balance()
        if balance["balance"] < ESTIMATED_CREDITS:
            raise TripoError("Insufficient available Tripo credits for the estimated request")
        local_inputs = inputs(root, spec)
        record = {
            "api_version": "v3",
            "model": spec.tripo.model,
            "mode": proposed["mode"],
            "estimated_credits": ESTIMATED_CREDITS,
            "max_credits": spec.tripo.max_credits,
            "budget_scope": proposed["budget_scope"],
            "price_checked": PRICE_CHECKED,
            "state": "uploading",
            "started_at": now(),
            "references": [],
        }
        write_json(checkpoint, record)
        tokens = []
        for name, path in local_inputs:
            local = out / f"reference-{name}{path.suffix.lower()}"
            local.write_bytes(path.read_bytes())
            record["references"].append(
                {"view": name, "file": local.name, "sha256": hashlib.sha256(local.read_bytes()).hexdigest()}
            )
            write_json(checkpoint, record)
            tokens.append((name, client.upload(local)))
        payload = proposed["settings"] | {
            "model": spec.tripo.model,
            "model_seed": spec.seed,
            "texture_seed": spec.seed,
            "texture_alignment": "original_image",
            "auto_size": False,
            "quad": False,
            "smart_low_poly": False,
            "generate_parts": False,
            "export_uv": True,
        }
        if spec.views:
            payload["inputs"] = [{name: token} for name, token in tokens]
        else:
            payload["input"] = tokens[0][1]
        record.update(state="submitting", request_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        write_json(checkpoint, record)
        try:
            data = client.create(proposed["mode"], payload)
            task_id = data.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise TripoError("Tripo submission returned no task ID")
        except (TripoError, OSError, ValueError):
            record.update(state="submission_unknown", updated_at=now())
            write_json(checkpoint, record)
            raise TripoError(
                "Tripo submission outcome is unknown; it was NOT retried. Check the vendor dashboard before resubmitting"
            ) from None
        record.update(task_id=task_id, state="queued", submitted_at=now())
        write_json(checkpoint, record)
    target = out / "generated.glb"
    # Reuse a verified raw result after a local Blender failure, without any new API calls.
    if target.exists() and record.get("download_sha256") == hashlib.sha256(target.read_bytes()).hexdigest():
        try:
            validate_glb(target)
        except ValueError:
            pass  # A previously cached invalid response must be downloaded again, not trusted forever.
        else:
            return record
    client = client or TripoClient(root)
    deadline = time.monotonic() + poll_timeout
    while True:
        task = client.task(record["task_id"])
        state = task.get("status")
        if state not in {"queued", "running", "success", *TERMINAL_FAILURES}:
            raise TripoError("Unknown Tripo task status; no new task was submitted")
        record.update(state=state, progress=task.get("progress"), updated_at=now())
        consumed = task.get("credits_consumed")
        if (
            isinstance(consumed, (int, float)) and not isinstance(consumed, bool)
            and math.isfinite(consumed) and consumed >= 0
        ):
            record["credits_consumed"] = consumed
            record["reported_over_budget"] = consumed > record["max_credits"]
        write_json(checkpoint, record)
        if state in TERMINAL_FAILURES:
            raise TripoError(f"Tripo task ended with status {state}; task ID is retained, no automatic retry")
        if state == "success":
            output = task.get("output") or {}
            if not isinstance(output, dict):
                raise TripoError("Successful Tripo task returned invalid output metadata")
            url = output.get("model_url")
            if not isinstance(url, str) or not url:
                raise TripoError("Successful Tripo task has no model_url")
            client.download(url, target)
            record.update(download_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), downloaded_at=now())
            write_json(checkpoint, record)
            return record
        if time.monotonic() >= deadline:
            record.update(state="waiting", updated_at=now())
            write_json(checkpoint, record)
            raise TripoError("Tripo is still processing; use resume-tripo with this asset/revision, not a new generation")
        time.sleep(2)
