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
from asset_auto.resources import THREAD_ENV, ResourcePolicyError, apply_process_resources, child_env
from asset_auto.runtime_execution import reject_bridge, resource_guard

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


def setup_environment(root):
    """Keep setup children in Kimodo's environment and selected resource policy."""
    runtime = root / ".runtime/kimodo"
    env = child_env(root, "kimodo")
    env = os.environ.copy() if env is None else env.copy()
    # HF resolves its login token relative to HF_HOME unless HF_TOKEN_PATH is set.
    # Save that *path* before relocating the cache; never inspect its contents here.
    original_home = env.get("HF_HOME", str(Path(env.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) /
                                             "huggingface"))
    original_token_path = env.get("HF_TOKEN_PATH", str(Path(original_home) / "token"))
    env["HF_TOKEN_PATH"] = os.path.expandvars(os.path.expanduser(original_token_path))
    env.update(UV_CACHE_DIR=str(runtime / "cache/uv"), UV_PYTHON_INSTALL_DIR=str(runtime / "python"),
               UV_PYTHON_PREFERENCE="only-managed", HF_HOME=str(runtime / "cache/huggingface"),
               VIRTUAL_ENV=str(runtime / ".venv"), PYTHONNOUSERSITE="1")
    # The app's activated Python (usually 3.13) must not leak into this 3.11 build.
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PATH"] = os.pathsep.join([str(runtime / ".venv/bin"), *[
        part for part in env.get("PATH", "").split(os.pathsep) if not part.startswith("/mnt/")]])
    return env


def prepare_build_source(build_source, env):
    """Adapt only the disposable copy of the pinned upstream build script."""
    path = build_source / "setup.py"
    source = path.read_text(encoding="utf-8")
    python_argument = 'f"-DPYTHON_EXECUTABLE={sys.executable}",'
    jobs_argument = 'build_args += ["--", "-j4"]'
    if source.count(python_argument) != 1 or source.count(jobs_argument) != 1:
        raise RuntimeError("The pinned Kimodo build script changed; review the isolated Python build adapter")
    # Upstream does not consume CMAKE_ARGS. Its CMakeLists uses FindPython3, so
    # PYTHON_EXECUTABLE alone cannot override an activated parent environment.
    source = source.replace(python_argument, python_argument + '\n            '
                            'f"-DPython3_EXECUTABLE={sys.executable}",')
    threads = env.get("OMP_NUM_THREADS", "4")
    if not threads.isdecimal() or int(threads) < 1:
        raise ValueError("Kimodo build OMP_NUM_THREADS must be a positive integer")
    source = source.replace(jobs_argument, f'build_args += ["--", "-j{int(threads)}"]')
    path.write_text(source, encoding="utf-8")


def probe_runtime(root, python, env):
    """Probe only the selected child CUDA environment; never try another GPU."""
    try:
        command = [python, "-c", (
            "import json,torch,motion_correction,kimodo; "
            "x=torch.ones(8,device='cuda'); y=x@x; "
            "print(json.dumps({'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),"
            "'cuda_test_passed':bool(y.item()==8)}))"
        )]
        with resource_guard(root, "kimodo", command) as launch:
            probe_env = env.copy()
            for key in ("CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "TEXT_ENCODER_DEVICE", *THREAD_ENV):
                if key in (launch["env"] or {}):
                    probe_env[key] = launch["env"][key]
            check = run(launch["command"], capture=True, env=probe_env)
            versions = json.loads(check.strip().splitlines()[-1])
            if not isinstance(versions, dict) or versions.get("cuda_test_passed") is not True:
                raise ValueError("CUDA probe did not pass")
            return versions
    except ResourcePolicyError:
        raise
    except (subprocess.CalledProcessError, OSError, ValueError, IndexError):
        raise RuntimeError(
            "Kimodo setup's isolated Python/CUDA probe failed. Check the Python 3.11 "
            "motion_correction extension in .runtime/kimodo/.venv and the selected GPU's CUDA driver/visibility. "
            "Correct the setup or private resource selection, then rerun scripts/bootstrap_kimodo.py; "
            "existing downloads are reused. No alternate GPU was tried."
        ) from None


def access_issue(error, gated_error_type):
    """Find HF permission errors even when a cache-miss exception wraps them."""
    pending, seen, issue = [error], set(), None
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        status = getattr(getattr(current, "response", None), "status_code", None)
        message = str(current).lower()
        if status == 403 and "fine-grained token settings" in message:
            return "token_scope"
        if isinstance(current, gated_error_type):
            issue = "model_access"
        elif status == 401 and issue is None:
            issue = "token_auth"
        pending.extend(cause for cause in (current.__cause__, current.__context__) if cause is not None)
    return issue


def download(root, runtime):
    from huggingface_hub import get_token, snapshot_download
    from huggingface_hub.errors import GatedRepoError

    token_file = root / ".secrets/hf_token"
    token = token_file.read_text(encoding="utf-8-sig").strip() if token_file.is_file() else get_token()
    records, blocked = [], {}
    for name, (repo, revision) in MODEL_PINS.items():
        folder = runtime / "models" / name
        print(f"Downloading pinned {repo}", flush=True)
        try:
            snapshot_download(repo, revision=revision, local_dir=folder, token=token or False,
                              allow_patterns=["*.json", "*.yaml", "*.safetensors", "stats/*", "LICENSE*", "USE_POLICY*"],
                              ignore_patterns=["original/*"], max_workers=4)
        except Exception as error:
            issue = access_issue(error, GatedRepoError)
            if issue is None:
                raise
            blocked[repo] = issue
            print(f"HF access blocked ({issue}): {repo}; continuing other model downloads", flush=True)
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".cache" not in path.relative_to(folder).parts:
                records.append({"path": path.relative_to(runtime).as_posix(), "size_bytes": path.stat().st_size,
                                "sha256": sha256(path)})
    if blocked:
        (runtime / "model-files-partial.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        advice = {
            "token_scope": "In HF token settings, enable 'Read access to contents of all public gated repos "
                           "you can access' for the saved fine-grained token; account approval alone is insufficient",
            "model_access": "Accept the model's terms and obtain access for the account that owns the saved token",
            "token_auth": "Use a valid authorized read token in <runtime-root>/.secrets/hf_token or HF login/HF_TOKEN",
        }
        raise RuntimeError("Hugging Face download access is required: " + "; ".join(
            f"{repo}: {advice[issue]}" for repo, issue in blocked.items()) +
            ". Rerun the same setup command after correcting access; completed downloads are reused.")
    return records


def install(root, distro, skip_models):
    if sys.platform != "linux":
        raise RuntimeError("Kimodo requires Linux or the configured WSL distribution")
    runtime = root / ".runtime/kimodo"
    source = runtime / "source"
    runtime.mkdir(parents=True, exist_ok=True)
    env = setup_environment(root)
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise RuntimeError("Install uv in the selected Linux user's environment first")
    if not shutil.which("g++"):
        raise RuntimeError("Kimodo MotionCorrection needs a C++ compiler in the selected Linux environment")
    if not source.exists():
        run(["git", "clone", "--no-checkout", SOURCE_REPO, source], env=env)
        run(["git", "checkout", "--detach", SOURCE_REV], cwd=source, env=env)
    if run(["git", "rev-parse", "HEAD"], cwd=source, capture=True, env=env).strip() != SOURCE_REV:
        raise RuntimeError("Preserving a Kimodo checkout with a different revision; reconcile it first")
    if run(["git", "-c", "core.autocrlf=true", "status", "--porcelain", "--untracked-files=no"],
           cwd=source, capture=True, env=env).strip():
        raise RuntimeError("Preserving local changes to the pinned Kimodo checkout")
    python = runtime / ".venv/bin/python"
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
            prepare_build_source(build_source, env)
            run([python, "setup.py", "bdist_wheel"], cwd=build_source, env=env | {"CMAKE_GENERATOR": "Ninja"})
            wheel = next((build_source / "dist").glob("*.whl"))
            run([uv, "pip", "install", "--python", python, *(["--no-deps"] if lock.exists() else []), wheel], env=env)
            (runtime / "wheels").mkdir(exist_ok=True)
            shutil.copyfile(wheel, runtime / "wheels" / wheel.name)
    versions = probe_runtime(root, python, env)
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
        reject_bridge(root, "kimodo")
        prefix = ["wsl", "--distribution", args.wsl_distribution, "--exec"]
        linux_root = run([*prefix, "wslpath", "-a", root], capture=True).strip()
        run([*prefix, "python3", linux_root + "/scripts/bootstrap_kimodo.py", "--root", linux_root,
             "--worker", "--wsl-distribution", args.wsl_distribution, *(["--skip-models"] if args.skip_models else [])])
    else:
        apply_process_resources(root)
        install(root, args.wsl_distribution if args.worker else None, args.skip_models)


if __name__ == "__main__":
    main()
