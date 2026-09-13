"""Install Kimodo in its own Linux/WSL environment, without changing system tools."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from asset_auto.kimodo_runtime import MODEL_PINS, PYTHON_VERSION, SOURCE_REPO, SOURCE_REV, sha256

DEPENDENCIES = (
    "torch==2.7.0+cu128", "transformers==5.1.0", "peft==0.18.1", "numpy==1.26.4",
    "scipy==1.16.2", "cmake==3.31.6", "ninja==1.13.0", "pybind11==2.13.6", "setuptools==80.9.0",
    "wheel==0.45.1",
)


def run(args, *, capture=False, **kwargs):
    result = subprocess.run([str(arg) for arg in args], check=True,
                            stdout=subprocess.PIPE if capture else None, text=True, **kwargs)
    return result.stdout if capture else None


def normalized_freeze(value):
    return "\n".join("kimodo==1.0.0" if line.startswith("kimodo @") else line
                     for line in value.splitlines()) + "\n"


def download(root, runtime):
    from huggingface_hub import get_token, snapshot_download
    from huggingface_hub.errors import GatedRepoError

    token_file = root / ".secrets/hf_token"
    token = token_file.read_text(encoding="utf-8-sig").strip() if token_file.is_file() else get_token()
    records, gated = [], []
    for name, (repo, revision) in MODEL_PINS.items():
        folder = runtime / "models" / name
        print(f"Downloading pinned {repo}", flush=True)
        try:
            snapshot_download(repo, revision=revision, local_dir=folder, token=token or False,
                              allow_patterns=["*.json", "*.yaml", "*.safetensors", "stats/*", "LICENSE*", "USE_POLICY*"],
                              ignore_patterns=["original/*"], max_workers=4)
        except GatedRepoError:
            gated.append(repo)
            print(f"Model access required: {repo}; continuing public downloads", flush=True)
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".cache" not in path.relative_to(folder).parts:
                records.append({"path": path.relative_to(runtime).as_posix(), "size_bytes": path.stat().st_size,
                                "sha256": sha256(path)})
    if gated:
        (runtime / "model-files-partial.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        raise RuntimeError("Hugging Face access is required for " + ", ".join(gated) +
                           "; use an authorized read token in <runtime-root>/.secrets/hf_token and rerun setup")
    return records


def install(root, distro, skip_models):
    if sys.platform != "linux":
        raise RuntimeError("Kimodo requires Linux or the configured WSL distribution")
    runtime = root / ".runtime/kimodo"
    source = runtime / "source"
    runtime.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise RuntimeError("Install uv in the selected Linux user's environment first")
    if not shutil.which("g++"):
        raise RuntimeError("Kimodo MotionCorrection needs a C++ compiler in the selected Linux environment")
    if not source.exists():
        run(["git", "clone", "--no-checkout", SOURCE_REPO, source])
        run(["git", "checkout", "--detach", SOURCE_REV], cwd=source)
    if run(["git", "rev-parse", "HEAD"], cwd=source, capture=True).strip() != SOURCE_REV:
        raise RuntimeError("Preserving a Kimodo checkout with a different revision; reconcile it first")
    if run(["git", "-c", "core.autocrlf=true", "status", "--porcelain", "--untracked-files=no"],
           cwd=source, capture=True).strip():
        raise RuntimeError("Preserving local changes to the pinned Kimodo checkout")
    env = os.environ.copy()
    env.update(UV_CACHE_DIR=str(runtime / "cache/uv"), UV_PYTHON_INSTALL_DIR=str(runtime / "python"),
               UV_PYTHON_PREFERENCE="only-managed", HF_HOME=str(runtime / "cache/huggingface"))
    python = runtime / ".venv/bin/python"
    env["PATH"] = os.pathsep.join([str(runtime / ".venv/bin"), *[
        part for part in env.get("PATH", "").split(os.pathsep) if not part.startswith("/mnt/")]])
    if not python.exists():
        run([uv, "venv", "--python", PYTHON_VERSION, runtime / ".venv"], env=env)
    lock = root / "scripts/kimodo/requirements-linux.lock"
    target = root / ".runtime/installed/kimodo.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    freeze = normalized_freeze(run([uv, "pip", "freeze", "--python", python], capture=True, env=env))
    expected = {line for line in lock.read_text().splitlines() if line and not line.startswith("#")} if lock.exists() else set()
    reuse = (previous.get("environment_ready") and previous.get("source_revision") == SOURCE_REV and
             set(freeze.splitlines()) == expected | {"kimodo==1.0.0"})
    if reuse:
        print("Reusing the pinned Kimodo environment", flush=True)
    elif lock.exists():
        run([uv, "pip", "sync", "--python", python, lock, "--extra-index-url",
             "https://download.pytorch.org/whl/cu128", "--index-strategy", "unsafe-best-match"], env=env)
    else:
        run([uv, "pip", "install", "--python", python, *DEPENDENCIES, "--extra-index-url",
             "https://download.pytorch.org/whl/cu128", "--index-strategy", "unsafe-best-match"], env=env)
    # uv local-project URLs and Unix Makefiles mishandle '#' checkout paths.
    # Build the pinned source in a private Linux temporary directory, then keep the wheel.
    if not reuse:
        with tempfile.TemporaryDirectory(prefix="asset-auto-kimodo-") as temporary:
            build_source = Path(temporary) / "source"
            shutil.copytree(source, build_source, ignore=shutil.ignore_patterns(".git", "build", "*.egg-info"))
            run([python, "setup.py", "bdist_wheel"], cwd=build_source, env=env | {"CMAKE_GENERATOR": "Ninja"})
            wheel = next((build_source / "dist").glob("*.whl"))
            run([uv, "pip", "install", "--python", python, *(["--no-deps"] if lock.exists() else []), wheel], env=env)
            (runtime / "wheels").mkdir(exist_ok=True)
            shutil.copyfile(wheel, runtime / "wheels" / wheel.name)
    check = run([python, "-c", (
        "import json,torch,motion_correction,kimodo; "
        "x=torch.ones(8,device='cuda'); y=x@x; "
        "print(json.dumps({'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),"
        "'cuda_test_passed':bool(y.item()==8)}))"
    )], capture=True, env=env)
    versions = json.loads(check.strip().splitlines()[-1])
    freeze = normalized_freeze(run([uv, "pip", "freeze", "--python", python], capture=True, env=env))
    (runtime / "requirements-installed.txt").write_text(freeze, encoding="utf-8")
    installed = {"backend": "kimodo", "platform": "wsl" if distro else "linux", "wsl_distribution": distro,
                 "source_revision": SOURCE_REV, "source_repository": SOURCE_REPO, "versions": versions,
                 "models": {name: {"repository": repo, "revision": rev} for name, (repo, rev) in MODEL_PINS.items()},
                 "files": [], "environment_ready": True, "ready": False, "inference_verified": False,
                 "dependency_freeze_sha256": sha256(runtime / "requirements-installed.txt")}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(installed, indent=2), encoding="utf-8")
    if not skip_models:
        run([python, __file__, "--root", root, "--download-models"], env=env)
        installed["files"] = json.loads((runtime / "model-files.json").read_text(encoding="utf-8"))
        installed["ready"] = True
        target.write_text(json.dumps(installed, indent=2), encoding="utf-8")
    print(json.dumps({key: installed[key] for key in ("backend", "environment_ready", "ready", "versions")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--wsl-distribution", default="Ubuntu-24.04")
    parser.add_argument("--skip-models", action="store_true", help="Prepare the environment while HF access is pending")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--download-models", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.download_models:
        runtime = root / ".runtime/kimodo"
        records = download(root, runtime)
        (runtime / "model-files.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    elif os.name == "nt":
        prefix = ["wsl", "--distribution", args.wsl_distribution, "--exec"]
        linux_root = run([*prefix, "wslpath", "-a", root], capture=True).strip()
        run([*prefix, "python3", linux_root + "/scripts/bootstrap_kimodo.py", "--root", linux_root,
             "--worker", "--wsl-distribution", args.wsl_distribution, *(["--skip-models"] if args.skip_models else [])])
    else:
        install(root, args.wsl_distribution if args.worker else None, args.skip_models)


if __name__ == "__main__":
    main()
