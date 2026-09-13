"""Headless SkinTokens entrypoint with deterministic sampling and bounded child lifetime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def write_receipt(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def probe(directory):
    import fcntl

    with (directory / "local-rig-child.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("busy")
        else:
            print("free")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--probe-lock":
        probe(Path(sys.argv[2]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-beams", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    args.input = args.input.resolve()
    args.output = args.output.resolve()
    if args.run_id:
        run_with_receipt(args)
    else:
        run_model(args)


def run_with_receipt(args):
    import fcntl

    directory = args.output.parent
    metadata = json.loads((directory / "local-rig.json").read_text(encoding="utf-8"))
    if metadata.get("run_id") != args.run_id:
        raise RuntimeError("Local rig worker request was replaced before launch")
    with (directory / "local-rig-child.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = {key: metadata[key] for key in (
            "run_id", "source_sha256", "source_revision", "model_revision", "request_sha256",
        )}
        if metadata.get("runtime_fingerprint") is not None:
            receipt["runtime_fingerprint"] = metadata["runtime_fingerprint"]
        receipt.update(state="running", pid=os.getpid(), started_at=datetime.now(UTC).isoformat())
        path = directory / "local-rig-child.json"
        write_receipt(path, receipt)
        final_output = args.output
        args.output = directory / f"generated-{args.run_id}.partial.glb"
        try:
            if digest(args.input) != metadata["source_sha256"]:
                raise RuntimeError("Source GLB changed before rig inference")
            run_model(args)
            with args.output.open("rb") as stream:
                header = stream.read(12)
            if len(header) != 12 or struct.unpack("<4sII", header) != (b"glTF", 2, args.output.stat().st_size):
                raise ValueError("SkinTokens returned an invalid GLB")
            if digest(args.input) != metadata["source_sha256"]:
                raise RuntimeError("Source GLB changed during rig inference")
            if final_output.exists():
                raise FileExistsError("A rig output appeared during inference; preserving both results")
            receipt.update(state="exported", output_sha256=digest(args.output),
                           completed_at=datetime.now(UTC).isoformat())
            write_receipt(path, receipt)
            args.output.rename(final_output)
            receipt["state"] = "completed"
            write_receipt(path, receipt)
        except BaseException:
            receipt.update(state="failed", completed_at=datetime.now(UTC).isoformat())
            write_receipt(path, receipt)
            raise


def run_model(args):
    os.chdir(args.source_root)
    sys.path.insert(0, str(args.source_root))
    os.environ.update({
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "GRADIO_ANALYTICS_ENABLED": "False",
        "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
        "PYTHONUNBUFFERED": "1",
    })
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        os.environ["ASSET_AUTO_BPY_PORT"] = str(listener.getsockname()[1])

    def interrupted(signum, frame):
        raise TimeoutError(f"SkinTokens interrupted by signal {signum}")

    for name in ("SIGTERM", "SIGINT", "SIGALRM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    if hasattr(signal, "alarm"):
        signal.alarm(args.timeout)

    import random

    import numpy as np
    import torch

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    import demo

    helper = Path(__file__).with_name("helper.py")
    process = subprocess.Popen([
        sys.executable, "-u", str(helper), "--source-root", str(args.source_root),
        "--parent-pid", str(os.getpid()),
    ])
    try:
        import requests

        deadline = time.monotonic() + 300
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"SkinTokens Blender helper exited with code {process.returncode}")
            try:
                response = requests.get(f"{demo.BPY_SERVER}/ping", timeout=1)
                if response.status_code == 200 and response.text == "pong":
                    break
            except requests.ConnectionError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("SkinTokens Blender helper did not become ready within 300 seconds")
            time.sleep(0.5)
        if process.poll() is not None:
            raise RuntimeError("SkinTokens Blender helper exited before inference")
        demo.load_model(demo.MODEL_CKPTS[0], None)
        demo.model.eval()
        with torch.inference_mode():
            demo.run_rig(
                filepaths=[args.input], output_paths=[args.output],
                top_k=5, top_p=0.95, temperature=1.0, repetition_penalty=2.0,
                num_beams=args.num_beams, use_skeleton=False, use_transfer=True,
                use_postprocess=False, model_ckpt=demo.MODEL_CKPTS[0], hf_path=None,
            )
        if not args.output.is_file():
            raise RuntimeError("SkinTokens completed without its GLB output")
    finally:
        if hasattr(signal, "alarm"):
            signal.alarm(0)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
