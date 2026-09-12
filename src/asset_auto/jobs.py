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
from .store import child, now, read_json, write_json


def job_dir(root, job_id):
    return child(root / ".assets" / "jobs", job_id)


def submit(root, operation, payload):
    if operation == "generate":
        payload = AssetSpec.model_validate(payload).model_dump()
    elif operation == "edit":
        payload = EditRequest.model_validate(payload).model_dump()
    elif operation == "tripo-process":
        payload = PostprocessRequest.model_validate(payload).model_dump()
    elif operation == "resume-tripo-process":
        directory = child(root / ".assets", payload["asset_id"], payload["revision"])
        PostprocessRequest.model_validate(read_json(directory / "processing.json")["request"])
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
        elif record["operation"] == "tripo-process":
            result = postprocess(root, PostprocessRequest.model_validate(record["payload"]), on_revision=save_recovery)
        elif record["operation"] == "resume-tripo-process":
            result = resume_postprocess(root, **record["payload"])
        elif record["operation"] == "resume-tripo":
            result = resume_tripo(root, **record["payload"])
        else:
            result = validate_godot(root, **record["payload"])
        record.update(state="succeeded", result=result)
    except Exception as error:  # noqa: BLE001 -- persist worker failures at the process boundary
        record.update(state="failed", error=str(error))
        traceback.print_exc()
    record["finished_at"] = now()
    write_json(directory / "job.json", record)
    return record
