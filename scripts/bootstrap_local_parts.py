"""Install pinned GeoSAM2 in a separate Linux/WSL environment, without API keys."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from asset_auto.local_parts import (
    CODE_REPO,
    CODE_REVISION,
    MODEL_BYTES,
    MODEL_NAME,
    MODEL_REPO,
    MODEL_REVISION,
    MODEL_SHA256,
)

PYTHON_VERSION = "3.11.13"
REQUIREMENTS = Path(__file__).resolve().parent / "local_parts" / "requirements-linux.lock"


def download(url, path, expected=None):
    if path.is_file() and expected:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    print(f"Downloading {path.name}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "asset-auto/local-parts"})
    with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as target:
        while block := response.read(4 * 1024 * 1024):
            target.write(block)
    with temporary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected and digest != expected:
        raise ValueError(f"Checksum mismatch: {path.name}")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wsl-distribution", default="Ubuntu-24.04")
    parser.add_argument("--uv-cache", help="Optional shared uv wheel cache, not an environment")
    args = parser.parse_args()
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"Missing pinned local segmentation dependency lock: {REQUIREMENTS}")
    root = args.root.resolve()
    runtime = root / ".runtime" / "local-parts"
    runtime.mkdir(parents=True, exist_ok=True)
    prefix = ["wsl.exe", "-d", args.wsl_distribution, "--exec"] if os.name == "nt" else []

    def linux_path(path):
        if os.name != "nt":
            return str(path)
        return subprocess.check_output([*prefix, "wslpath", "-a", "-u", path.as_posix()], text=True).strip()

    def run(command):
        subprocess.run([*prefix, "env", "PATH=/usr/local/bin:/usr/bin:/bin",
                        f"UV_PYTHON_INSTALL_DIR={linux_path(runtime / 'python')}", *command], check=True)

    uv = subprocess.check_output([
        *prefix, "python3", "-c",
        ("import os,shutil; p=shutil.which('uv') or os.path.expanduser('~/.local/bin/uv'); "
         "assert os.path.isfile(p), 'Install uv inside Linux/WSL before bootstrap_local_parts.py'; print(p)"),
    ], text=True).strip()
    archive = runtime / f"GeoSAM2-{CODE_REVISION}.tar.gz"
    if not archive.is_file():
        download(f"https://codeload.github.com/{CODE_REPO}/tar.gz/{CODE_REVISION}", archive)
    code = runtime / "GeoSAM2"
    if not (code / "sam2" / "build_sam.py").is_file():
        with tarfile.open(archive) as bundle:
            bundle.extractall(runtime, filter="data")
        (runtime / f"GeoSAM2-{CODE_REVISION}").rename(code)
    download(f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{MODEL_NAME}",
             runtime / MODEL_NAME, MODEL_SHA256)
    if (runtime / MODEL_NAME).stat().st_size != MODEL_BYTES:
        raise ValueError("Model size mismatch")
    env_dir = linux_path(runtime / ".venv")
    run([uv, "--managed-python", "venv", "--python", PYTHON_VERSION, "--allow-existing", env_dir])
    python = env_dir + "/bin/python"
    uv_prefix = [uv, "--cache-dir", linux_path(Path(args.uv_cache).resolve())] if args.uv_cache else [uv]
    run([*uv_prefix, "pip", "sync", "--python", python, "--require-hashes",
         "--index-url", "https://pypi.org/simple", linux_path(REQUIREMENTS)])
    probe = subprocess.check_output([
        *prefix, python, "-c", ("import json,torch; "
        "assert torch.cuda.is_available(), 'CUDA unavailable'; "
        "a=torch.ones(2,device='cuda'); assert float((a+a).sum())==4; "
        "print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,"
        "'gpu':torch.cuda.get_device_name(0)}))"),
    ], text=True).strip()
    record = {
        "backend": "geosam2", "license": "Apache-2.0", "code_revision": CODE_REVISION,
        "model_revision": MODEL_REVISION, "model_sha256": MODEL_SHA256,
        "wsl_distribution": args.wsl_distribution if os.name == "nt" else None,
        "python": PYTHON_VERSION, "requirements_lock": "scripts/local_parts/requirements-linux.lock",
        "requirements_sha256": hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest(),
        "device": json.loads(probe),
    }
    installed = root / ".runtime" / "installed" / "local-parts.json"
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
