"""Invoke the shared runtime from any game project or personal-skill junction."""

import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[4]
environment = os.environ.copy()
environment.setdefault("ASSET_AUTO_ROOT", str(root))
python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    raise SystemExit(f"Runtime environment missing; run uv sync in {root}")
result = subprocess.run([str(python), "-m", "asset_auto.cli", *sys.argv[1:]], env=environment, check=False)
raise SystemExit(result.returncode)
