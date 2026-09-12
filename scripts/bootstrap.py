"""Install pinned portable tools and verified TRELLIS weights into .runtime.

Defaults to TRELLIS, its models and Blender. Godot is an optional component.
Run with Python 3.11+; no admin access or global configuration changes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import shutil
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
BLENDER = "4.5.13"
TRELLIS = "v0.6.0"
GODOT = "4.7.2-stable"
MODEL_REV = "a57397bd3d351599d9729fc144b3f87c3f87d65b"


def request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "asset-auto/0.1"})
    parsed = urllib.parse.urlsplit(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token and parsed.scheme == "https" and parsed.netloc == "api.github.com":
        # Authenticate release metadata only; never forward credentials on redirects.
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=90)


def read_json(url):
    with request(url) as response:
        return json.load(response)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, expected_hash=None, size=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if (
        path.exists()
        and (size is None or path.stat().st_size == size)
        and expected_hash
        and sha256(path) == expected_hash
    ):
        print(f"Verified cached: {path.name}", flush=True)
        return path
    temp = path.with_name(path.name + ".part")
    print(f"Downloading: {path.name}", flush=True)
    with request(url) as response, temp.open("wb") as out:
        shutil.copyfileobj(response, out, 4 * 1024 * 1024)
    if size is not None and temp.stat().st_size != size:
        raise ValueError(f"Incomplete download: {path.name}")
    actual = sha256(temp)
    if expected_hash and actual != expected_hash:
        raise ValueError(f"SHA256 mismatch: {path.name}")
    temp.replace(path)
    print(f"Downloaded: {path.name} sha256={actual}", flush=True)
    return path


def extract(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                destination = (target / member.filename).resolve()
                if not destination.is_relative_to(target.resolve()):
                    raise ValueError("Unsafe archive path")
            bundle.extractall(target)
            if os.name != "nt":
                for member in bundle.infolist():
                    mode = (member.external_attr >> 16) & 0o777
                    if mode:
                        (target / member.filename).chmod(mode)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")


def github_tool(repo, version, name, target):
    metadata = read_json(f"https://api.github.com/repos/{repo}/releases/tags/{version}")
    item = next(x for x in metadata["assets"] if x["name"] == name)
    digest = item.get("digest", "") or ""
    checksum = digest.removeprefix("sha256:") if digest.startswith("sha256:") else None
    archive = download(item["browser_download_url"], RUNTIME / "downloads" / name, checksum, item["size"])
    extract(archive, target)
    return {"version": version, "source": item["browser_download_url"], "sha256": sha256(archive)}


def blender(system):
    suffix = "windows-x64.zip" if system == "Windows" else "linux-x64.tar.xz"
    name = f"blender-{BLENDER}-{suffix}"
    # Official primary and mirror first; university mirror only if they are unavailable.
    bases = [
        "https://download.blender.org/release/Blender4.5/",
        "https://mirror.blender.org/release/Blender4.5/",
        "https://mirrors.nju.edu.cn/blender/release/Blender4.5/",
    ]
    for base in bases:
        try:
            with request(base + f"blender-{BLENDER}.sha256") as response:
                checksums = response.read().decode()
            checksum = next(line.split()[0] for line in checksums.splitlines() if line.endswith(name))
            archive = download(base + name, RUNTIME / "downloads" / name, checksum)
            extract(archive, RUNTIME / "blender")
            return {"version": BLENDER, "source": base + name, "sha256": checksum}
        except Exception as error:  # noqa: BLE001 -- isolate a failed download source
            print(f"Blender source unavailable: {base}: {error}", flush=True)
    raise RuntimeError("Could not download Blender from any configured source")


def models():
    info = read_json(
        f"https://huggingface.co/api/models/ilintar/trellis2-gguf/revision/{MODEL_REV}?blobs=true"
    )
    items = [x for x in info["siblings"] if "/" not in x["rfilename"] and x["rfilename"].endswith(".gguf")]

    def fetch(item):
        name = item["rfilename"]
        download(
            f"https://huggingface.co/ilintar/trellis2-gguf/resolve/{MODEL_REV}/{name}",
            RUNTIME / "models" / name,
            item["lfs"]["sha256"],
            item["size"],
        )
        return {"name": name, "size": item["size"], "sha256": item["lfs"]["sha256"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(fetch, items))
    return {"repository": "ilintar/trellis2-gguf", "revision": MODEL_REV, "files": files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=["core", "blender", "trellis", "godot", "models", "all"],
        default="core",
        help="Default core: Blender, TRELLIS and models. Godot is opt-in; all includes it.",
    )
    args = parser.parse_args()
    system = platform.system()
    if system not in ("Windows", "Linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("This portable installer supports Windows/Linux x64")
    tasks = {"blender": lambda: blender(system), "models": models}
    tasks["trellis"] = lambda: github_tool(
        "pwilkin/trellis.cpp",
        TRELLIS,
        "trellis-cuda-windows-x64.zip" if system == "Windows" else "trellis-cuda-linux-x64.tar.gz",
        RUNTIME / "trellis",
    )
    tasks["godot"] = lambda: github_tool(
        "godotengine/godot",
        GODOT,
        f"Godot_v{GODOT}_win64.exe.zip" if system == "Windows" else f"Godot_v{GODOT}_linux.x86_64.zip",
        RUNTIME / "godot",
    )
    if args.only == "all":
        chosen = tasks
    elif args.only == "core":
        chosen = {name: tasks[name] for name in ("blender", "trellis", "models")}
    else:
        chosen = {args.only: tasks[args.only]}
    records = RUNTIME / "installed"
    records.mkdir(parents=True, exist_ok=True)
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        pending = {pool.submit(task): name for name, task in chosen.items()}
        for future in concurrent.futures.as_completed(pending):
            name = pending[future]
            try:
                record = future.result()
                (records / f"{name}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
                print(f"Installed: {name}", flush=True)
            except Exception as error:  # noqa: BLE001 -- collect every component's installation result
                failures.append(name)
                print(f"FAILED {name}: {error}", flush=True)
    if failures:
        raise SystemExit("Failed components: " + ", ".join(failures))


if __name__ == "__main__":
    main()
