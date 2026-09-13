"""Run the pinned Kimodo model locally; output motion and inspectable provenance."""

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def local_encoder(runtime, model_revision):
    """Resolve adapter metadata to pinned local base weights, never a mutable HF ref."""
    from kimodo.model.llm2vec.llm2vec_wrapper import LLM2VecEncoder

    source = runtime / "models/mntp"
    prepared = runtime / "cache/local-mntp" / model_revision
    prepared.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if not path.is_file():
            continue
        target = prepared / path.name
        if not target.exists():
            shutil.copy2(path, target)
    config = json.loads((source / "adapter_config.json").read_text())
    config["base_model_name_or_path"] = str(runtime / "models/base")
    save_json(prepared / "adapter_config.json", config)
    return LLM2VecEncoder(str(prepared), str(runtime / "models/supervised"), "bfloat16", 4096, device="cuda")


def generate(runtime, request_file):
    # The public loader defaults to probing an encoder service. This adapter is
    # strictly local and uses only explicitly downloaded pinned checkpoints.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TEXT_ENCODER_MODE="local",
                      HF_HOME=str(runtime / "cache/huggingface"))
    from filelock import FileLock

    out = request_file.parent
    with FileLock(runtime / "inference.lock", timeout=0), FileLock(out / "inference.lock", timeout=0):
        if (out / "kimodo-inference.json").is_file():
            return
        import numpy as np
        import torch
        from hydra.utils import instantiate
        from kimodo.exports.bvh import save_motion_bvh
        from kimodo.exports.motion_io import save_kimodo_npz
        from kimodo.tools import seed_everything
        from omegaconf import OmegaConf

        if not torch.cuda.is_available():
            raise RuntimeError("Kimodo CUDA runtime unavailable; CPU fallback is not implicit")
        record = json.loads(request_file.read_text(encoding="utf-8"))
        request = record["request"]
        seed_everything(request["seed"])
        started = time.monotonic()
        encoder = local_encoder(runtime, record["installation"]["models"]["mntp"]["revision"])
        model_path = runtime / "models/motion"
        conf = OmegaConf.load(model_path / "config.yaml")
        conf = OmegaConf.merge(conf, {"checkpoint_dir": str(model_path), "text_encoder": None})
        resolved = OmegaConf.to_container(conf, resolve=True)
        resolved.pop("checkpoint_dir", None)
        model = instantiate(resolved, device="cuda")
        model.text_encoder = encoder
        model.eval()
        with torch.inference_mode():
            result = model([request["prompt"]], [round(request["duration_seconds"] * model.fps)],
                           num_denoising_steps=request["diffusion_steps"], num_samples=1,
                           multi_prompt=True, post_processing=True, return_numpy=True)
        single = {key: value[0] if hasattr(value, "shape") and len(value.shape) and value.shape[0] == 1 else value
                  for key, value in result.items()}
        for name in ("global_rot_mats", "local_rot_mats", "root_positions", "posed_joints"):
            if not np.isfinite(single[name]).all():
                raise ValueError(f"Kimodo returned non-finite {name}")
        skeleton = model.output_skeleton
        save_kimodo_npz(str(out / "motion.npz"), single)
        save_motion_bvh(str(out / "motion.bvh"), torch.as_tensor(single["local_rot_mats"], device=skeleton.device),
                        torch.as_tensor(single["root_positions"], device=skeleton.device),
                        skeleton=skeleton, fps=model.fps, standard_tpose=True)
        data = {"fps": float(model.fps), "joint_names": list(skeleton.bone_order_names),
                "parents": skeleton.joint_parents.detach().cpu().tolist(),
                "neutral_joints": skeleton.neutral_joints.detach().cpu().tolist(),
                "global_rotations": single["global_rot_mats"].tolist(),
                "root_positions": single["root_positions"].tolist(),
                "foot_contacts": single["foot_contacts"].tolist(),
                "coordinate_system": "SOMA standard T-pose, Y-up meters, +Z forward"}
        save_json(out / "motion-data.json", data)
        files = [{"file": name, "sha256": digest(out / name)}
                 for name in ("motion.npz", "motion.bvh", "motion-data.json")]
        save_json(out / "kimodo-inference.json", {
            "backend": "kimodo", "learned_inference": True, "post_processing": True,
            "binding_sha256": record["binding_sha256"], "installation": record["installation"],
            "fps": data["fps"], "frames": len(data["root_positions"]), "seed": request["seed"],
            "prompt": request["prompt"], "elapsed_seconds": time.monotonic() - started,
            "gpu": torch.cuda.get_device_name(0), "files": files,
            "limitations": ["SOMA model uses 30 joints internally; 77 exported joints do not prove detailed finger motion.",
                            "Generated contact labels are not collision tests on the target character."]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    generate(args.runtime.resolve(), args.request.resolve())
