"""Exercise pinned Kimodo CUDA inference/exports without testing its gated text encoder.

An empty, zero-embedded prompt is an unconditional diagnostic, not a substitute
for the user's text request. Outputs stay under .work and never enter the library.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


def worker(root, out):
    import numpy as np
    import torch

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts/kimodo"))
    import infer

    from asset_auto.authoring import binding
    from asset_auto.store import read_json, write_json

    class EmptyEncoder:
        def __call__(self, texts):
            assert all(text == "" for text in texts), "Diagnostic must never pretend to encode a real prompt"
            return torch.zeros((len(texts), 1, 4096), device="cuda"), [0] * len(texts)

    installed = read_json(root / ".runtime/installed/kimodo.json")
    record = {"operation": "unconditional-runtime-smoke", "text_conditioning_tested": False,
              "request": {"prompt": "", "duration_seconds": 2, "seed": 42, "diffusion_steps": 30},
              "installation": {key: installed[key] for key in ("source_revision", "models", "dependency_freeze_sha256")}}
    record["binding_sha256"] = binding(record)
    write_json(out / "motion-request.json", record)
    infer.local_encoder = lambda runtime, revision: EmptyEncoder()
    infer.generate(root / ".runtime/kimodo", out / "motion-request.json")
    motion = read_json(out / "motion-data.json")
    assert len(motion["joint_names"]) == 77 and len(motion["root_positions"]) == 60
    assert np.isfinite(motion["global_rotations"]).all()
    assert (out / "motion.bvh").read_text().startswith("HIERARCHY")
    npz = np.load(out / "motion.npz", allow_pickle=False)
    assert npz["global_rot_mats"].shape == (60, 77, 3, 3)
    inference = read_json(out / "kimodo-inference.json")
    write_json(out / "result.json", {
        "passed": True, "scope": "Actual learned motion inference with EMPTY conditioning; text encoder NOT tested",
        "learned_inference": True, "text_conditioning_tested": False,
        "source_revision": installed["source_revision"], "motion_model": installed["models"]["motion"],
        "gpu": inference["gpu"], "elapsed_seconds": inference["elapsed_seconds"],
        "checks": ["pinned model CUDA sampling", "native MotionCorrection", "finite 77-joint output",
                   "production NPZ/BVH/JSON exports"], "visual_review": "untested",
    })


def main():
    from filelock import FileLock

    from asset_auto.local_rig import wsl_path
    from asset_auto.store import read_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.worker:
        worker(root, args.output.resolve())
        return
    out = root / ".work" / ("smoke-kimodo-runtime-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    installed = read_json(root / ".runtime/installed/kimodo.json")
    script = Path(__file__).resolve()
    if os.name == "nt":
        distro = installed["wsl_distribution"]
        command = ["wsl", "--distribution", distro, "--exec", wsl_path(root, distro) + "/.runtime/kimodo/.venv/bin/python",
                   "-u", wsl_path(script, distro), "--worker", "--root", wsl_path(root, distro),
                   "--output", wsl_path(out, distro)]
    else:
        command = [str(root / ".runtime/kimodo/.venv/bin/python"), "-u", str(script), "--worker",
                   "--root", str(root), "--output", str(out)]
    lock = root / ".assets/.locks/trellis.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock, timeout=3600), (out / "worker.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
    print(json.dumps(read_json(out / "result.json") | {"directory": str(out)}, indent=2))


if __name__ == "__main__":
    if "--worker" in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    main()
