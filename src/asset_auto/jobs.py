"""Persistent jobs. Each submission runs in its own process and survives the caller."""

import os
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

import psutil

from .models import AssetSpec, EditRequest, PostprocessRequest
from .pipeline import edit_asset, generate, postprocess, resume_postprocess, resume_tripo, validate_godot
from .store import Store, child, now, read_json, write_json


def job_dir(root, job_id):
    return child(root / ".assets" / "jobs", job_id)


def processing_request(payload, *, tripo_only=False):
    """Keep legacy Tripo entrypoints explicit after the model default becomes local."""
    return PostprocessRequest.for_tripo(payload) if tripo_only else PostprocessRequest.model_validate(payload)


def validate_processing_resume(root, payload, *, tripo_only=False):
    directory = child(root / ".assets", payload["asset_id"], payload["revision"])
    saved = dict(read_json(directory / "processing.json")["request"])
    # Checkpoints written before provider selection existed contain Tripo work.
    saved.setdefault("provider", "tripo")
    return processing_request(saved, tripo_only=tripo_only)


def submit(root, operation, payload):
    if operation == "generate":
        payload = AssetSpec.model_validate(payload).model_dump()
    elif operation == "edit":
        payload = EditRequest.model_validate(payload).model_dump()
    elif operation in ("process", "tripo-process"):
        payload = processing_request(payload, tripo_only=operation == "tripo-process").model_dump()
    elif operation in ("resume-process", "resume-tripo-process"):
        validate_processing_resume(root, payload, tripo_only=operation == "resume-tripo-process")
    elif operation == "prepare-segment":
        Store(root).revision(payload["asset_id"], payload["revision"])
    elif operation == "resume-tripo":
        directory = child(root / ".assets", payload["asset_id"], payload["revision"])
        if read_json(directory / "generation.json").get("provider") != "tripo":
            raise ValueError("Only an existing Tripo generation can be resumed")
    elif operation != "godot":
        raise ValueError("Unsupported operation")
    job_id = uuid.uuid4().hex
    directory = job_dir(root, job_id)
    directory.mkdir(parents=True)
    record = {
        "job_id": job_id,
        "operation": operation,
        "payload": payload,
        "state": "queued",
        "created_at": now(),
    }
    write_json(directory / "job.json", record)
    environment = os.environ.copy()
    environment["ASSET_AUTO_ROOT"] = str(root)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (directory / "worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "asset_auto.cli", "_worker", job_id],
            cwd=root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
    return {"job_id": job_id, "pid": process.pid, "state": "submitted"}


def status(root, job_id):
    path = job_dir(root, job_id) / "job.json"
    record = read_json(path)
    if record["state"] == "running" and record.get("process_created_at"):
        try:
            process = psutil.Process(record["pid"])
            alive = (
                process.create_time() == record["process_created_at"]
                and process.status() != psutil.STATUS_ZOMBIE
            )
        except psutil.NoSuchProcess:
            alive = False
        if not alive:
            # Re-read in case completion was written while checking the process.
            record = read_json(path)
            if record["state"] == "running":
                record.update(
                    state="interrupted",
                    error="Worker process exited before recording completion",
                    finished_at=now(),
                )
                write_json(path, record)
    return record


def run(root: Path, job_id):
    directory = job_dir(root, job_id)
    record = read_json(directory / "job.json")
    if record["state"] != "queued":
        raise ValueError("Job has already started; submit a new job to retry")
    record.update(
        state="running", pid=os.getpid(), started_at=now(), process_created_at=psutil.Process().create_time()
    )
    write_json(directory / "job.json", record)

    def save_recovery(recovery):
        record["recovery"] = recovery
        write_json(directory / "job.json", record)

    try:
        if record["operation"] == "generate":
            result = generate(root, AssetSpec.model_validate(record["payload"]), on_revision=save_recovery)
        elif record["operation"] == "edit":
            result = edit_asset(root, EditRequest.model_validate(record["payload"]))
        elif record["operation"] in ("process", "tripo-process"):
            request = processing_request(record["payload"], tripo_only=record["operation"] == "tripo-process")
            result = postprocess(root, request, on_revision=save_recovery)
        elif record["operation"] in ("resume-process", "resume-tripo-process"):
            validate_processing_resume(root, record["payload"], tripo_only=record["operation"] == "resume-tripo-process")
            result = resume_postprocess(root, **record["payload"])
        elif record["operation"] == "prepare-segment":
            from .pipeline import prepare_segmentation

            result = prepare_segmentation(root, **record["payload"])
        elif record["operation"] == "resume-tripo":
            result = resume_tripo(root, **record["payload"])
        elif record["operation"] == "godot":
            result = validate_godot(root, **record["payload"])
        else:
            raise ValueError("Unsupported operation")
        record.update(state="succeeded", result=result)
    except Exception as error:  # noqa: BLE001 -- persist worker failures at the process boundary
        record.update(state="failed", error=str(error))
        traceback.print_exc()
    record["finished_at"] = now()
    write_json(directory / "job.json", record)
    return record
