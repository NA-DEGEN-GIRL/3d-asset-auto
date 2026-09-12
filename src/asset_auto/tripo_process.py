"""Recoverable, explicitly selected Tripo processing of existing asset revisions."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .glb_transform import rotate_scene_y
from .store import now, read_json, write_json
from .tripo import (
    MAX_UPLOAD_MODEL_BYTES,
    PRICE_CHECKED,
    PRICE_SOURCE,
    TERMINAL_FAILURES,
    TripoClient,
    TripoError,
)

if TYPE_CHECKING:
    from .models import PostprocessRequest

SEGMENT_MODEL = "v2.0-20260430"
RIG_MODEL = "v1.0-20240301"
RIG_INPUT_YAWS = {"+z": 90, "-z": -90, "-x": 180, "+x": 0}
ORIENTATION_FIELDS = {"rig_forward_axis", "provider_forward_axis", "input_rotation_y_degrees", "output_yaw_degrees"}
STAGES = {
    "rig": [("rig-check", "/animations/rig-check", 0), ("rig", "/animations/rig", 25)],
    "animate": [("animate", "/animations/retarget", 10)],
    "segment": [("segment", "/mesh/segment", 40)],
}
PUBLIC_FIELDS = {
    "provider", "api_version", "operation", "model", "rig_task_id", "rig_model", "rig_type", "animation",
    "animate_in_place", "segmentation_granularity", "estimated_credits", "max_credits", "within_budget",
    "budget_scope", "price_source", "price_checked", "state", "started_at", "updated_at", "downloaded_at",
    "download_sha256", "credits_consumed", "credits_fully_reported", "reported_over_budget", "source_sha256",
    "prepared_file", "prepared_sha256",
} | ORIENTATION_FIELDS
PUBLIC_STAGE_FIELDS = {
    "name", "endpoint", "estimated_credits", "state", "task_id", "credits_consumed", "progress",
    "submitted_at", "updated_at", "riggable", "rig_type",
}


def _orientation(axis):
    if axis not in RIG_INPUT_YAWS:
        raise TripoError("Unsupported rig forward axis")
    yaw = RIG_INPUT_YAWS[axis]
    return {
        "rig_forward_axis": axis, "provider_forward_axis": "+x",
        "input_rotation_y_degrees": yaw, "output_yaw_degrees": -yaw,
    }


def _inherited_orientation(source_manifest):
    provenance = source_manifest.get("remote_processing") or {}
    if not isinstance(provenance, dict):
        raise TripoError("Animation requires recorded Tripo rig provenance")
    if not any(field in provenance for field in ORIENTATION_FIELDS):
        # Previously processed rigs had no input rotation or compensating output rotation.
        return _orientation("+x")
    expected = _orientation(provenance.get("rig_forward_axis"))
    if any(provenance.get(field) != value for field, value in expected.items()):
        raise TripoError("Parent rig orientation metadata does not match its forward axis")
    return expected


def plan(request: PostprocessRequest, source_manifest=None):
    """Estimate the requested operation locally, without credentials or network calls."""
    if request.provider != "tripo" or request.operation not in STAGES:
        raise ValueError("Postprocessing requires an explicit supported Tripo operation")
    stages = [
        {"name": name, "endpoint": endpoint, "estimated_credits": cost}
        for name, endpoint, cost in STAGES[request.operation]
    ]
    cost = sum(stage["estimated_credits"] for stage in stages)
    result = {
        "provider": "tripo", "api_version": "v3", "operation": request.operation,
        "stages": stages, "estimated_credits": cost, "max_credits": request.max_credits,
        "within_budget": cost <= request.max_credits,
        "budget_scope": "Client estimate guard; not a server-enforced spending cap",
        "price_source": PRICE_SOURCE, "price_checked": PRICE_CHECKED,
    }
    if request.operation == "segment":
        result.update(model=SEGMENT_MODEL, segmentation_granularity=request.segmentation_granularity)
    else:
        result.update(model=request.rig_model, rig_model=request.rig_model, rig_type=request.rig_type)
        if request.operation == "animate":
            result.update(animation=request.animation, animate_in_place=request.animate_in_place)
            if source_manifest is not None:
                result.update(_inherited_orientation(source_manifest))
        else:
            result.update(_orientation(request.rig_forward_axis))
    return result


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _task_id(value):
    if (
        not isinstance(value, str) or not value or len(value) > 200
        or any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in value)
    ):
        raise TripoError("Missing or invalid Tripo task ID; no replacement task was submitted")
    return value


def _credit(value):
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value >= 0
    )


def _accounting(record):
    stages = record["stages"]
    reported = [stage["credits_consumed"] for stage in stages if "credits_consumed" in stage]
    record["credits_consumed"] = sum(reported)
    record["credits_fully_reported"] = all(
        "credits_consumed" in stage for stage in stages if stage["estimated_credits"]
    )
    record["reported_over_budget"] = record["credits_consumed"] > record["max_credits"]


def _public(record):
    """The uploaded file token and vendor result URLs never leave the private checkpoint."""
    result = {key: value for key, value in record.items() if key in PUBLIC_FIELDS}
    result["stages"] = [
        {key: value for key, value in stage.items() if key in PUBLIC_STAGE_FIELDS}
        for stage in record["stages"]
    ]
    return result


def _persist(checkpoint, record):
    record["updated_at"] = now()
    _accounting(record)
    write_json(checkpoint, record)


def _prepared_rig_input(source, out, checkpoint, record):
    target = out / "rig-input.glb"
    if record.get("prepared_sha256"):
        if (
            record.get("prepared_file") != target.name or not target.is_file()
            or _file_digest(target) != record["prepared_sha256"]
        ):
            raise TripoError("Prepared rig input changed or is missing; cannot certify the recorded upload")
    else:
        if record.get("file_token") or any(stage.get("task_id") for stage in record["stages"]):
            raise TripoError("Recorded rig upload has no prepared input hash; cannot safely resume it")
        rotate_scene_y(source, target, record["input_rotation_y_degrees"])
        if target.stat().st_size > MAX_UPLOAD_MODEL_BYTES:
            raise ValueError("Prepared Tripo rig input must be no larger than 150 MB")
        record.update(prepared_file=target.name, prepared_sha256=_file_digest(target))
        _persist(checkpoint, record)
    return target


def _guard_next_stage(client, record, stage):
    estimate = stage["estimated_credits"]
    if not estimate:
        return
    # An absent vendor cost is not zero: reserve the completed stage's estimate.
    committed = sum(
        previous.get("credits_consumed", previous["estimated_credits"])
        for previous in record["stages"]
        if previous is not stage and previous.get("task_id")
    )
    if committed + estimate > record["max_credits"]:
        raise TripoError("Reported prior cost plus the next stage estimate exceeds max_credits; no next task submitted")
    if client.balance()["balance"] < estimate:
        raise TripoError("Insufficient available Tripo credits for the next processing stage")


def _submit(client, checkpoint, record, stage, payload):
    if stage.get("task_id"):
        _task_id(stage["task_id"])
        return
    if stage["state"] != "pending":
        raise TripoError(
            "Tripo stage submission outcome is unknown; inspect the vendor dashboard before any new request"
        )
    _guard_next_stage(client, record, stage)
    stage.update(state="submitting", request_sha256=_digest(payload), updated_at=now())
    record["state"] = "submitting"
    _persist(checkpoint, record)
    try:
        response = client.request("POST", stage["endpoint"], payload)
        if not isinstance(response, dict):
            raise TripoError("Tripo returned invalid submission metadata")
        task_id = _task_id(response.get("task_id"))
    except (TripoError, OSError, ValueError):
        # Includes malformed success responses. A killed process leaves "submitting",
        # which is equally ambiguous and must never be interpreted as safe to retry.
        stage.update(state="submission_unknown", updated_at=now())
        record["state"] = "submission_unknown"
        _persist(checkpoint, record)
        raise TripoError(
            "Tripo stage submission outcome is unknown; it was NOT retried. Reconcile it in the vendor dashboard"
        ) from None
    stage.update(task_id=task_id, state="queued", submitted_at=now())
    record["state"] = "queued"
    if stage["name"] == "rig":
        record["rig_task_id"] = task_id
    _persist(checkpoint, record)


def _poll(client, checkpoint, record, stage, deadline):
    while True:
        task = client.task(_task_id(stage.get("task_id")))
        if not isinstance(task, dict):
            raise TripoError("Tripo returned invalid processing task metadata")
        state = task.get("status")
        if state not in {"queued", "running", "success", *TERMINAL_FAILURES}:
            raise TripoError("Unknown Tripo processing status; no replacement task was submitted")
        stage.update(state=state, updated_at=now())
        if _credit(task.get("progress")):
            stage["progress"] = task["progress"]
        if _credit(task.get("credits_consumed")):
            stage["credits_consumed"] = task["credits_consumed"]
        record["state"] = state
        _persist(checkpoint, record)
        if state in TERMINAL_FAILURES:
            raise TripoError(f"Tripo processing ended with status {state}; the known task was not retried")
        if state == "success":
            output = task.get("output")
            if not isinstance(output, dict):
                raise TripoError("Successful Tripo processing returned invalid output metadata")
            if stage["name"] == "rig-check":
                stage["riggable"] = output.get("riggable") is True
                stage["rig_type"] = output.get("rig_type") if output.get("rig_type") == "biped" else "unsupported"
                _persist(checkpoint, record)
            return output
        if time.monotonic() >= deadline:
            record["state"] = "waiting"
            _persist(checkpoint, record)
            raise TripoError("Tripo is still processing; use resume-tripo-process for this revision, not a new request")
        time.sleep(2)


def _payload(request, record, stage):
    if stage["name"] == "rig-check":
        return {"input": record["file_token"]}
    if stage["name"] == "rig":
        return {
            "input": record["file_token"], "model": request.rig_model,
            "rig_type": request.rig_type, "spec": "tripo", "out_format": "glb",
        }
    if stage["name"] == "animate":
        return {
            "input": record["rig_task_id"], "animation": f"preset:biped:{request.animation}",
            "out_format": "glb", "bake_animation": True, "export_with_geometry": True,
            "animate_in_place": request.animate_in_place,
        }
    return {
        "input": record["file_token"], "model": SEGMENT_MODEL,
        "segmentation_granularity": request.segmentation_granularity, "split_by_connectivity": True,
    }


def process(
    root, request: PostprocessRequest, out, source_glb, source_manifest,
    *, resume=False, client=None, poll_timeout=300,
):
    """Download one processed GLB while retaining every task ID for safe recovery."""
    from .pipeline import validate_glb

    out, source_glb = Path(out), Path(source_glb)
    proposed = plan(request, source_manifest)
    if not proposed["within_budget"]:
        raise TripoError("Estimated Tripo processing cost exceeds max_credits")
    validate_glb(source_glb)
    if request.operation != "animate" and source_glb.stat().st_size > MAX_UPLOAD_MODEL_BYTES:
        raise ValueError("Tripo model input must be no larger than 150 MB")
    source_hash = _file_digest(source_glb)
    source_rig_id = None
    if request.operation == "animate":
        provenance = source_manifest.get("remote_processing") or {}
        if not isinstance(provenance, dict):
            raise TripoError("Animation requires a revision with recorded Tripo rig provenance")
        source_rig_id = _task_id(provenance.get("rig_task_id"))
        if provenance.get("rig_type", request.rig_type) != request.rig_type:
            raise TripoError("Animation requires a compatible biped rig revision")
        if provenance.get("rig_model", request.rig_model) != request.rig_model:
            raise TripoError("Animation requires a compatible Tripo rig model version")
    request_values = request.model_dump()
    if request.operation != "rig":
        request_values.pop("rig_forward_axis", None)
    binding = {"request": request_values, "source_rig_task_id": source_rig_id}
    if request.operation == "animate" and any(
        field in source_manifest.get("remote_processing", {}) for field in ORIENTATION_FIELDS
    ):
        binding["source_orientation"] = {field: proposed[field] for field in ORIENTATION_FIELDS}
    request_hash = _digest(binding)
    checkpoint = out / "postprocess-remote.json"
    if resume:
        record = read_json(checkpoint)
        if record.get("request_sha256") != request_hash or record.get("source_sha256") != source_hash:
            raise TripoError("Processing request or source changed; cannot resume this recorded operation")
        expected = [(s["name"], s["endpoint"], s["estimated_credits"]) for s in proposed["stages"]]
        actual = [(s.get("name"), s.get("endpoint"), s.get("estimated_credits")) for s in record.get("stages", [])]
        if actual != expected or record.get("max_credits") != request.max_credits:
            raise TripoError("Processing checkpoint does not match the requested stages or budget")
        if any(record.get(field) != proposed[field] for field in ORIENTATION_FIELDS if field in proposed):
            raise TripoError("Processing checkpoint orientation does not match the requested source")
        for stage in record["stages"]:
            if stage.get("task_id"):
                _task_id(stage["task_id"])
            elif stage.get("state") != "pending":
                raise TripoError("Tripo stage has no recorded task ID; reconcile the unknown submission before resuming")
    else:
        if checkpoint.exists():
            raise TripoError("Tripo processing is already recorded; resume it instead of submitting again")
        client = client or TripoClient(root)
        if client.balance()["balance"] < proposed["estimated_credits"]:
            raise TripoError("Insufficient available Tripo credits for the estimated processing request")
        record = proposed | {
            "state": "uploading" if request.operation != "animate" else "pending",
            "started_at": now(), "request_sha256": request_hash, "source_sha256": source_hash,
            "stages": [stage | {"state": "pending"} for stage in proposed["stages"]],
        }
        if source_rig_id:
            record["rig_task_id"] = source_rig_id
        _persist(checkpoint, record)
    upload_source = source_glb
    if request.operation == "rig":
        upload_source = _prepared_rig_input(source_glb, out, checkpoint, record)
    target = out / "generated.glb"
    if (
        target.is_file() and record["stages"][-1].get("state") == "success"
        and record.get("download_sha256") == _file_digest(target)
    ):
        try:
            validate_glb(target)
        except ValueError:
            pass
        else:
            return _public(record)
    client = client or TripoClient(root)
    if request.operation != "animate" and not record.get("file_token"):
        if client.balance()["balance"] < proposed["estimated_credits"]:
            raise TripoError("Insufficient available Tripo credits before model upload")
        record["state"] = "uploading"
        _persist(checkpoint, record)
        record["file_token"] = client.upload_model(upload_source)
        _persist(checkpoint, record)
    deadline = time.monotonic() + poll_timeout
    for stage in record["stages"]:
        if stage["name"] == "rig-check" and stage.get("state") == "success" and "riggable" in stage:
            output = {"riggable": stage["riggable"], "rig_type": stage.get("rig_type")}
        else:
            _submit(client, checkpoint, record, stage, _payload(request, record, stage))
            output = _poll(client, checkpoint, record, stage, deadline)
        if stage["name"] == "rig-check":
            if output.get("riggable") is not True or output.get("rig_type") != request.rig_type:
                record["state"] = "not_riggable"
                _persist(checkpoint, record)
                raise TripoError("Tripo rig check did not confirm a compatible biped; no paid rig task was submitted")
            continue
        url = output.get("model_url")
        if not isinstance(url, str) or not url:
            raise TripoError("Successful Tripo processing has no model_url; resume the known task")
        client.download(url, target)
        try:
            validate_glb(target)
        except ValueError:
            raise TripoError("Tripo processing result is not a valid GLB; resume the known task") from None
        record.update(state="success", download_sha256=_file_digest(target), downloaded_at=now())
        _persist(checkpoint, record)
    return _public(record)
