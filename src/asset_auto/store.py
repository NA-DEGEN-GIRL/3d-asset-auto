from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def child(root, *parts):
    for part in parts:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", part) or part in (".", ".."):
            raise ValueError("Invalid identifier")
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path outside asset store")
    return path


class Store:
    def __init__(self, root: Path):
        self.root = root / ".assets"

    def new_revision(self, asset_id):
        revision = "r" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        directory = child(self.root, asset_id, revision)
        directory.mkdir(parents=True, exist_ok=False)
        return revision, directory

    def revision(self, asset_id, revision):
        directory = child(self.root, asset_id, revision)
        if not (directory / "manifest.json").is_file():
            raise FileNotFoundError(f"Completed revision not found: {asset_id}/{revision}")
        return directory

    def list(self):
        entries = []
        for path in self.root.glob("*/*/manifest.json"):
            manifest = read_json(path)
            directory = path.parent
            for name in ("review.json", "godot.json"):
                if (directory / name).exists():
                    manifest[name.removesuffix(".json")] = read_json(directory / name)
            entries.append(manifest)
        return sorted(entries, key=lambda x: x["created_at"], reverse=True)
