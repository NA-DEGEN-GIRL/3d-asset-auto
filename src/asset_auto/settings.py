import json
import os
import shutil
from pathlib import Path


def root_path():
    return Path(os.environ.get("ASSET_AUTO_ROOT", Path.cwd())).resolve()


def config(root):
    path = root / "asset-system.local.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def executable(root, kind):
    conf = config(root)
    explicit = os.environ.get(f"ASSET_AUTO_{kind.upper()}") or conf.get(kind)
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError(f"Configured {kind} does not exist: {path}")
    windows = os.name == "nt"
    patterns = {
        "blender": "blender.exe" if windows else "blender",
        "trellis": "trellis-cli.exe" if windows else "trellis-cli",
        "godot": "*console.exe" if windows else "Godot*linux*x86_64",
    }
    found = sorted((root / ".runtime" / kind).rglob(patterns[kind]))
    if found:
        return str(found[0])
    value = shutil.which({"trellis": "trellis-cli", "godot": "godot", "blender": "blender"}[kind])
    if value:
        return value
    raise FileNotFoundError(f"{kind} unavailable. Run python scripts/bootstrap.py --only {kind}")


def model_dir(root):
    value = os.environ.get("ASSET_AUTO_MODELS") or config(root).get("models", ".runtime/models")
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def capabilities(root):
    result = {
        "root": str(root),
        "tools": {},
        "providers": {},
        "multiview_generation": False,
        "rigging": {"available": False, "reason": "Not installed; static-asset milestone"},
    }
    for kind in ("blender", "trellis", "godot"):
        try:
            result["tools"][kind] = {"available": True, "path": executable(root, kind)}
        except FileNotFoundError as error:
            result["tools"][kind] = {"available": False, "reason": str(error)}
    required = [
        "ss_flow",
        "ss_dec",
        "shape_flow_512",
        "shape_flow_1024",
        "shape_dec",
        "tex_flow_512",
        "tex_flow_1024",
        "tex_dec",
        "dinov3",
        "birefnet",
    ]
    missing = [n for n in required if not (model_dir(root) / f"{n}.gguf").is_file()]
    result["providers"]["procedural"] = result["tools"]["blender"]["available"]
    result["providers"]["trellis"] = (
        result["tools"]["trellis"]["available"] and result["tools"]["blender"]["available"] and not missing
    )
    result["models"] = {"directory": str(model_dir(root)), "missing": missing}
    return result
