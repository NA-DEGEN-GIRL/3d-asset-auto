"""Isolated GeoSAM2 inference and visibility-aware transfer to original faces.

Run this script with the separate local-parts Python, never the runtime Python.
Model masks are instance predictions. Agent-provided names are retained only for
those IDs; missing/occluded/conflicting surface evidence remains unclassified.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"

import cv2
import numpy as np
import torch
from PIL import Image


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def project_votes(vertices, faces, meta, context, label_maps, part_count):
    """Project seven deterministic interior samples per unchanged triangle.

    Views only vote when source depth agrees. Conflicts and absent masks do not
    vote for a part. Unknown faces are retained rather than filled geometrically.
    """
    barycentric = np.array([
        [1 / 3, 1 / 3, 1 / 3], [.6, .2, .2], [.2, .6, .2], [.2, .2, .6],
        [.45, .45, .1], [.45, .1, .45], [.1, .45, .45],
    ])
    normalized = vertices * float(meta["scaling_factor"]) + np.asarray(meta["translation"])
    points = np.einsum("sk,fkj->fsj", barycentric, normalized[faces])
    flat = points.reshape(-1, 3)
    votes = np.zeros((len(flat), part_count + 1), dtype=np.uint16)
    visibility = np.zeros(len(flat), dtype=np.uint16)
    resolution = int(meta.get("resolution", 1024))
    focal = 0.5 * resolution / math.tan(float(meta["camera_angle_x"]) / 2)
    for view, mapping in sorted(label_maps.items()):
        c2w = np.asarray(meta["transforms"][view], dtype=np.float64)
        camera = (flat - c2w[:3, 3]) @ c2w[:3, :3]
        camera_depth = -camera[:, 2]
        z = np.maximum(camera_depth, 1e-8)
        x = np.rint(camera[:, 0] * focal / z + resolution / 2 - .5).astype(np.int64)
        y = np.rint(-camera[:, 1] * focal / z + resolution / 2 - .5).astype(np.int64)
        inside = (camera_depth > 0) & (x >= 0) & (y >= 0) & (x < resolution) & (y < resolution)
        indices = np.nonzero(inside)[0]
        depth = cv2.imread(str(context / f"depth_{view:04d}.exr"), cv2.IMREAD_UNCHANGED)
        if depth is None:
            raise ValueError(f"Missing depth map for view {view}")
        if depth.ndim == 3:
            depth = depth[..., 0]
        observed = depth[y[indices], x[indices]]
        # A conservative two-pixel tolerance in the normalized scene.
        tolerance = np.maximum(0.002, 2 * camera_depth[indices] / focal)
        visible = np.isfinite(observed) & (observed > 0) & (np.abs(observed - camera_depth[indices]) <= tolerance)
        indices = indices[visible]
        visibility[indices] += 1
        labels = mapping[y[indices], x[indices]]
        valid = labels > 0
        np.add.at(votes, (indices[valid], labels[valid]), 1)
    face_votes = votes.reshape(len(faces), len(barycentric), part_count + 1).sum(axis=1)
    winners = face_votes.argmax(axis=1)
    ordered = np.sort(face_votes[:, 1:], axis=1)
    best = ordered[:, -1]
    second = ordered[:, -2] if part_count > 1 else np.zeros(len(faces), dtype=np.int64)
    support = face_votes[:, 1:].sum(axis=1)
    accept = (best >= 3) & (best > second) & (best >= 0.55 * np.maximum(support, 1))
    result = np.where(accept, winners, 0).astype(np.int32)
    evidence = {
        "method": "seven interior face samples; depth-tested multiview mask voting",
        "unknown_faces": int((result == 0).sum()), "faces": len(faces),
        "unknown_fraction": float((result == 0).mean()),
        "unseen_faces": int((visibility.reshape(len(faces), -1).sum(axis=1) == 0).sum()),
        "ambiguous_faces": int(((best > 0) & ~accept).sum()),
        "min_winning_votes": 3, "min_winning_fraction": .55,
        "samples_per_face": len(barycentric),
    }
    return result, evidence


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    context = Path(request["context"])
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    context_info = json.loads((context / "context.json").read_text(encoding="utf-8"))
    if context_info.get("source_sha256") != request["source_sha256"]:
        raise ValueError("Context source hash differs from request")
    if digest(context / "canonical.npz") != context_info["canonical_sha256"]:
        raise ValueError("Canonical topology changed after context preparation")
    meta = json.loads((context / "meta.json").read_text(encoding="utf-8"))
    if meta.get("resolution") != 1024 or len(meta["transforms"]) != 12:
        raise ValueError("Pinned GeoSAM2 requires 12 context views at 1024 pixels")
    parts = request["parts"]
    if not 1 <= len(parts) <= 32:
        raise ValueError("Provide between 1 and 32 observed parts")
    view = int(request["view"])
    if not 0 <= view < 12:
        raise ValueError("Prompt view must be in the context")
    alpha = np.array(Image.open(context / f"color_{view:04d}.png").convert("RGBA"))[..., 3]
    for part in parts:
        if not part["positive_points"]:
            raise ValueError("Every named part needs an observed positive point")
        for point in part["positive_points"] + part.get("negative_points", []):
            if len(point) != 2 or any(not isinstance(x, int) or not 0 <= x < 1024 for x in point):
                raise ValueError("Part points must be integer pixel coordinates within the context image")
        for x, y in part["positive_points"]:
            if alpha[y, x] == 0:
                raise ValueError(f"Positive point for {part['name']} is on the context background")
    result_path = output / "inference-report.json"
    labels_path = output / "face-labels.npy"
    if result_path.is_file() and labels_path.is_file():
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        if previous.get("binding_sha256") == request["binding_sha256"] and previous.get("labels_sha256") == digest(labels_path):
            print("Reused completed local inference with matching request and labels", flush=True)
            return
    sys.path.insert(0, str(Path(request["code"])))
    from sam2.build_sam import build_sam2_video_predictor_geosam2
    from sam2.utils import misc

    # The upstream loader hardcodes WebP; lossless PNG stores our context data.
    original_loader = misc._load_img_as_tensor

    def load_png(path, size):
        path = Path(path)
        return original_loader(str(path.with_suffix(".png") if path.suffix == ".webp" else path), size)

    misc._load_img_as_tensor = load_png
    torch.manual_seed(42)
    np.random.seed(42)
    if not torch.cuda.is_available():
        raise RuntimeError("Local GeoSAM2 inference requires the configured CUDA environment")
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    label_maps = {}
    frame_reports = []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        predictor = build_sam2_video_predictor_geosam2(
            "configs/geosam2.yaml", request["checkpoint"], device="cuda", apply_postprocessing=False,
        )
        state = predictor.init_state(video_path=str(context), video_id_list=list(range(12)), offload_video_to_cpu=True)
        for part_id, part in enumerate(parts, 1):
            positives = part["positive_points"]
            negatives = part.get("negative_points", [])
            predictor.add_new_points_or_box(
                inference_state=state, frame_idx=view, obj_id=part_id,
                points=np.asarray(positives + negatives, dtype=np.float32),
                labels=np.asarray([1] * len(positives) + [0] * len(negatives), dtype=np.int32),
            )
        for frame, ids, logits in predictor.propagate_in_video_v2(state, start_frame_idx=view):
            if not 0 <= frame < 12:
                raise ValueError("GeoSAM2 returned an out-of-range context frame")
            masks = logits[:, 0].float().cpu().numpy()
            foreground = masks > 0
            overlap = foreground.sum(axis=0) > 1
            # Multiple claimed masks remain unknown rather than picking a semantic name.
            label_map = np.zeros((1024, 1024), dtype=np.int32)
            for index, part_id in enumerate(ids):
                label_map[foreground[index] & ~overlap] = int(part_id)
            label_maps[int(frame)] = label_map
            np.save(output / f"mask_{frame:04d}.npy", label_map)
            rgb = np.array(Image.open(context / f"color_{frame:04d}.png").convert("RGB"))
            colors = np.array([[0, 0, 0]] + [[(i * 67 + 43) % 220 + 25, (i * 101 + 17) % 220 + 25,
                                               (i * 139 + 91) % 220 + 25] for i in range(1, len(parts) + 1)])
            overlay = rgb.copy()
            selected = label_map > 0
            overlay[selected] = (.4 * rgb[selected] + .6 * colors[label_map[selected]]).astype(np.uint8)
            overlay[overlap] = [255, 0, 255]
            Image.fromarray(overlay).save(output / f"mask-preview-{frame:04d}.png")
            frame_reports.append({"view": int(frame), "overlapping_pixels": int(overlap.sum()),
                                  "part_pixels": {str(i): int((label_map == i).sum()) for i in ids}})
            print(f"Predicted context view {frame}", flush=True)
    if len(label_maps) != 12:
        raise RuntimeError("GeoSAM2 did not return every context view")
    with np.load(context / "canonical.npz", allow_pickle=False) as canonical:
        labels, evidence = project_votes(canonical["vertices"], canonical["faces"], meta,
                                        context, label_maps, len(parts))
    np.save(labels_path, labels)
    report = {
        "binding_sha256": request["binding_sha256"], "labels_sha256": digest(labels_path),
        "provider": "local", "backend": "geosam2", "device": torch.cuda.get_device_name(0),
        "prompt_view": view, "semantic_review": "pending", "evidence": evidence,
        "parts": [{"id": i, "name": part["name"], "faces": int((labels == i).sum()),
                   "positive_points": part["positive_points"], "negative_points": part.get("negative_points", [])}
                  for i, part in enumerate(parts, 1)],
        "views": frame_reports[-12:],
        "warnings": ["Part names are agent-grounded prompts, not model-predicted semantic classes.",
                     "Unseen, conflicting or weakly supported faces stay unclassified.",
                     "Splitting preserves existing surfaces; cut boundaries remain open."],
    }
    write_json(result_path, report)
    print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    main()
