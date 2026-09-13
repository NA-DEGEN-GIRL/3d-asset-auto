"""Install the pinned, isolated SkinTokens runtime (Linux, or Windows via WSL).

No system packages, drivers or global Python environments are changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_REPO = "https://github.com/VAST-AI-Research/SkinTokens.git"
SOURCE_REV = "273b691d35989d71cd17ff2895fdc735097b92d1"
MODEL_REPO = "VAST-AI/SkinTokens"
MODEL_REV = "79736cad0fd84de384d5eede659b4ebd24effe33"
QWEN_REV = "c1899de289a04d12100db370d81485cdf75e47ca"
PYTHON_VERSION = "3.11.13"
CHECKPOINTS = (
    "experiments/articulation_xl_quantization_256_token_4/grpo_1400.ckpt",
    "experiments/skin_vae_2_10_32768/last.ckpt",
)
DEPENDENCIES = (
    "torch==2.7.0+cu128", "torchvision==0.22.0+cu128", "torchaudio==2.7.0+cu128",
    "transformers==4.57.1", "diffusers==0.35.1", "bpy==4.2.0", "numpy==1.26.4",
    "open3d==0.19.0", "lightning==2.5.5", "python-box==7.3.2", "einops==0.8.1",
    "omegaconf==2.3.0", "addict==2.4.0", "fast-simplification==0.1.12",
    "trimesh==4.8.3", "huggingface-hub==0.35.3", "gradio==5.49.1",
    "bottle==0.13.4", "tornado==6.5.2", "requests==2.32.5", "scipy==1.16.2",
)


def run(args, *, cwd=None, capture=False, env=None):
    return subprocess.run(
        [str(x) for x in args], cwd=cwd, env=env, check=True,
        text=True, capture_output=capture,
    ).stdout


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def patch_source(source):
    """Apply only known patches to the pinned source, accepting our prior patch version."""
    replacements = {
        "src/server/bpy_server.py": [("host='0.0.0.0'", "host='127.0.0.1'")],
        "src/server/spec.py": [
            ("BPY_PORT = 59876", 'BPY_PORT = int(os.environ.get("ASSET_AUTO_BPY_PORT", "59876"))'),
            ('BPY_SERVER = f"http://localhost:{BPY_PORT}"',
             'BPY_SERVER = f"http://127.0.0.1:{BPY_PORT}"'),
        ],
    }
    prepared = []
    for relative, pairs in replacements.items():
        path = source / relative
        original = run(["git", "show", f"{SOURCE_REV}:{relative}"], cwd=source, capture=True)
        expected = original
        for before, after in pairs:
            if expected.count(before) != 1:
                raise RuntimeError(f"Pinned source patch no longer matches: {relative}")
            expected = expected.replace(before, after)
        previous = expected
        purpose = "loopback RPC isolation"
        if relative == "src/server/spec.py":
            # The Blender helper needs packet definitions, not the inference model and
            # its GPU dependencies. Future annotations retain get_model's return type.
            lazy_pairs = (
                ("from dataclasses import dataclass\n",
                 "from __future__ import annotations\n\nfrom dataclasses import dataclass\n"),
                ("from ..model.tokenrig import TokenRig\n", ""),
                (") -> TokenRig:\n    model = TokenRig.load_from_system_checkpoint",
                 (") -> TokenRig:\n    from ..model.tokenrig import TokenRig\n\n"
                  "    model = TokenRig.load_from_system_checkpoint")),
            )
            for before, after in lazy_pairs:
                if expected.count(before) != 1:
                    raise RuntimeError(f"Pinned source patch no longer matches: {relative}")
                expected = expected.replace(before, after)
            purpose += "; lazy TokenRig import for Blender helper"
        current = path.read_text(encoding="utf-8")
        if current not in (original, previous, expected):
            raise RuntimeError(f"Preserving unexpected local changes in {relative}; reconcile them first")
        prepared.append((relative, path, expected, purpose))
    # Refuse an unexpected edit in either file before changing the other one.
    patches = []
    for relative, path, expected, purpose in prepared:
        path.write_text(expected, encoding="utf-8")
        patches.append({"path": relative, "sha256": digest(path), "purpose": purpose})
    return patches


def install(root, distro):
    if sys.platform != "linux":
        raise RuntimeError("The worker requires Linux; on Windows select a working WSL distribution")
    runtime = root / ".runtime" / "local-rig"
    source = runtime / "source"
    runtime.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise RuntimeError("Install uv in this Linux user's environment before bootstrap")
    run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if not source.exists():
        run(["git", "clone", "--no-checkout", SOURCE_REPO, source])
        run(["git", "checkout", "--detach", SOURCE_REV], cwd=source)
    actual = run(["git", "rev-parse", "HEAD"], cwd=source, capture=True).strip()
    if actual != SOURCE_REV:
        raise RuntimeError("Existing local-rig checkout uses another revision; preserving it")
    patches = patch_source(source)
    python = runtime / ".venv/bin/python"
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(runtime / "cache/uv")
    env["UV_PYTHON_INSTALL_DIR"] = str(runtime / "python")
    env["UV_PYTHON_PREFERENCE"] = "only-managed"
    env["PATH"] = os.pathsep.join(
        item for item in env.get("PATH", "").split(os.pathsep) if not item.startswith("/mnt/")
    )
    env["HF_HOME"] = str(runtime / "cache/huggingface")
    if not python.exists():
        run([uv, "venv", "--python", PYTHON_VERSION, runtime / ".venv"], env=env)
    lock = root / "scripts/local_rig/requirements-linux.lock"
    if lock.is_file():
        run([uv, "pip", "sync", "--python", python, lock,
             "--extra-index-url", "https://download.pytorch.org/whl/cu128",
             "--index-strategy", "unsafe-best-match"], env=env)
    else:
        run([
            uv, "pip", "install", "--python", python, *DEPENDENCIES,
            "--extra-index-url", "https://download.pytorch.org/whl/cu128",
            "--index-strategy", "unsafe-best-match",
        ], env=env)
        abi = run([python, "-c", "import torch; print(str(torch._C._GLIBCXX_USE_CXX11_ABI).upper())"],
                  capture=True, env=env).strip()
        wheel = ("https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3.post1/"
                 f"flash_attn-2.8.3.post1%2Bcu12torch2.7cxx11abi{abi}-cp311-cp311-linux_x86_64.whl")
        run([uv, "pip", "install", "--python", python, wheel, "--no-deps"], env=env)
    download_code = (
        "from huggingface_hub import hf_hub_download, snapshot_download\n"
        f"files={CHECKPOINTS!r}\n"
        "for name in files:\n"
        f" hf_hub_download({MODEL_REPO!r}, name, revision={MODEL_REV!r}, local_dir='.')\n"
        f"snapshot_download('Qwen/Qwen3-0.6B', revision={QWEN_REV!r}, "
        "local_dir='models/Qwen3-0.6B', ignore_patterns=['*.bin','*.safetensors'])\n"
    )
    run([python, "-c", download_code], cwd=source, env=env)
    check = run([python, "-c", (
        "import json, torch, bpy, flash_attn; "
        "from flash_attn import flash_attn_func; "
        "q=torch.randn(1,32,4,64,device='cuda',dtype=torch.bfloat16); "
        "y=flash_attn_func(q,q,q); torch.cuda.synchronize(); "
        "print(json.dumps(dict(torch=torch.__version__, blender=bpy.app.version_string, "
        "flash_attn=flash_attn.__version__, gpu=torch.cuda.get_device_name(0), "
        "attention_finite=bool(torch.isfinite(y).all()))))"
    )], capture=True, env=env)
    versions = json.loads(check.strip().splitlines()[-1])
    freeze = run([uv, "pip", "freeze", "--python", python], capture=True, env=env)
    (runtime / "requirements-installed.txt").write_text(freeze, encoding="utf-8")
    manifest = {
        "provider": "local", "backend": "skintokens", "license": "MIT",
        "platform": "wsl" if distro else "linux", "wsl_distribution": distro,
        "source_repository": SOURCE_REPO, "source_revision": SOURCE_REV,
        "model_repository": MODEL_REPO, "model_revision": MODEL_REV,
        "qwen_revision": QWEN_REV, "python_version": PYTHON_VERSION,
        "patches": patches, "versions": versions,
        "checkpoints": [{"path": name, "sha256": digest(source / name),
                         "size_bytes": (source / name).stat().st_size} for name in CHECKPOINTS],
        "dependency_freeze_sha256": digest(runtime / "requirements-installed.txt"),
        "runtime_relative": ".runtime/local-rig", "ready": True,
    }
    target = root / ".runtime/installed/local-rig.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wsl-distribution", default="Ubuntu-24.04")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve()
    if os.name == "nt" and not args.worker:
        prefix = ["wsl", "--distribution", args.wsl_distribution, "--exec"]
        linux_root = run([*prefix, "wslpath", "-a", str(root)], capture=True).strip()
        script = linux_root + "/scripts/bootstrap_local_rig.py"
        run([*prefix, "python3", script, "--root", linux_root, "--worker",
             "--wsl-distribution", args.wsl_distribution])
    else:
        install(root, args.wsl_distribution if args.worker else None)


if __name__ == "__main__":
    main()
