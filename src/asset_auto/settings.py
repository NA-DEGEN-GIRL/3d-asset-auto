import json
import os
import shutil
from pathlib import Path

from .models import TripoOptions
from .tripo_credentials import key_configured


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
    found = sorted(path for path in (root / ".runtime" / kind).rglob(patterns[kind]) if path.is_file())
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
        "default_processing_provider": "local",
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
    credential_present = key_configured(root)
    result["providers"]["tripo"] = result["tools"]["blender"]["available"] and credential_present
    result["tripo"] = {
        "key_configured": credential_present,
        "authentication_verified": False,
        "explicit_selection_required": True,
        "paid": True,
        "model": "v3.1-20260211",
        "default_max_credits": TripoOptions().max_credits,
    }
    result["multiview_generation"] = result["providers"]["tripo"]
    result["provider_features"] = {
        "trellis": {"multiview": False, "local": True},
        "tripo": {"multiview": True, "local": False},
    }
    from .local_parts import available as parts_available
    from .local_rig import capability as rig_available

    local_rig = rig_available(root)
    local_parts = parts_available(root)
    blender_available = result["tools"]["blender"]["available"]
    result["rigging"] = {
        "available": blender_available and local_rig["available"], "provider": "local", "backend": "skintokens",
        "installation": local_rig, "local_character_import": blender_available,
        "local_rig_editing": {"available": blender_available, "command": "blender-edit"},
        "tripo_option": {"available": result["providers"]["tripo"], "explicit_selection_required": True},
    }
    result["animation"] = {
        "available": blender_available, "provider": "local", "presets": ["idle", "walk", "run"],
        "preset_requires": "biped rig and observed bone map or recognized bone names",
        "preset_clips_per_request": 1,
        "preset_behavior": "add or replace one named clip while preserving other clips",
        "preset_method": "procedural inverse kinematics",
        "custom_authoring": {"available": blender_available, "command": "blender-edit",
                             "supports": ["skeletal animation", "rigid object animation", "multiple clips"]},
        "clip_merge": {"available": blender_available, "command": "merge-animations",
                       "requires": "compatible GLB node hierarchy and skin bind pose", "retargeting": False},
        "tripo_option": {"available": result["providers"]["tripo"], "explicit_selection_required": True},
    }
    result["blender_authoring"] = {
        "available": blender_available, "provider": "local", "command": "blender-edit",
        "requires": "completed source revision and agent-authored Blender Python script",
        "supports": ["mesh edits", "rig edits", "skin weights", "custom animation"],
        "preserves_source_revision": True, "preserves_animations_by_default": True,
    }
    result["segmentation"] = {
        "available": blender_available and local_parts["available"], "provider": "local", "backend": "geosam2",
        "installation": local_parts, "semantic_review_required": True,
        "requires": "prepare-segment context and named points on inspected render",
        "tripo_option": {"available": result["providers"]["tripo"], "explicit_selection_required": True},
    }
    result["models"] = {"directory": str(model_dir(root)), "missing": missing}
    return result
