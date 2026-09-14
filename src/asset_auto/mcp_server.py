"""Optional stdio adapter; all tools call the same versioned runtime as the CLI."""

from . import jobs
from .settings import capabilities
from .store import Store, read_json


def build_server(root):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError("MCP extra is not installed. Run uv sync --extra mcp") from error

    server = FastMCP("3d-asset-auto")

    @server.tool()
    def asset_capabilities() -> dict:
        """Discover installed tools, available providers and current feature boundaries."""
        return capabilities(root)

    @server.tool()
    def text_motion_plan(request: dict) -> dict:
        """Check a mapped humanoid rig and local Kimodo readiness without running inference."""
        from .models import KimodoMotionRequest
        from .text_motion import plan

        return plan(root, KimodoMotionRequest.model_validate(request))

    @server.tool()
    def generate_text_motion(request: dict) -> dict:
        """Generate one local motion only when the user explicitly selects Kimodo.

        Uses an existing rig and preserves other clips in a new revision; not the default animation tool.
        """
        return jobs.submit(root, "text-motion", request)

    @server.tool()
    def resume_text_motion(asset_id: str, revision: str) -> dict:
        """Resume a saved local motion revision; completed inference and authoring checkpoints are reused."""
        return jobs.submit(root, "resume-text-motion", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def generate_asset(spec: dict) -> dict:
        """Submit a validated spec. Default TRELLIS; explicit Tripo uses a 100-credit estimate guard by default."""
        return jobs.submit(root, "generate", spec)

    @server.tool()
    def tripo_plan(spec: dict) -> dict:
        """Read-only local input and estimated-credit plan; no uploads or paid submissions."""
        from .models import AssetSpec
        from .tripo import plan

        return plan(root, AssetSpec.model_validate(spec))

    @server.tool()
    def tripo_balance() -> dict:
        """Read available account credits. Does not create a paid task or reveal the API key."""
        from .tripo import TripoClient

        return TripoClient(root).balance()

    @server.tool()
    def resume_tripo_asset(asset_id: str, revision: str) -> dict:
        """Continue a recorded remote task without creating a second paid generation."""
        return jobs.submit(root, "resume-tripo", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def tripo_process_plan(spec: dict) -> dict:
        """Read-only plan for explicit Tripo rig, animation or semantic segmentation of an exact revision."""
        from .pipeline import postprocess_plan

        return postprocess_plan(root, jobs.processing_request(spec, tripo_only=True))

    @server.tool()
    def process_tripo_asset(request: dict) -> dict:
        """Submit requested rig/animate/segment processing; creates a new revision, default credit guard 100."""
        return jobs.submit(root, "tripo-process", request)

    @server.tool()
    def resume_tripo_processing(asset_id: str, revision: str) -> dict:
        """Resume saved processing stages without resubmitting known paid tasks."""
        return jobs.submit(root, "resume-tripo-process", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def process_plan(spec: dict) -> dict:
        """Read-only rig/animate/segment plan. Defaults to local Blender; Tripo requires explicit provider selection."""
        from .pipeline import postprocess_plan

        return postprocess_plan(root, jobs.processing_request(spec))

    @server.tool()
    def process_asset(request: dict) -> dict:
        """Submit rig/animate/segment processing of an exact revision. Defaults to local processing without an API."""
        return jobs.submit(root, "process", request)

    @server.tool()
    def prepare_local_segmentation(asset_id: str, revision: str) -> dict:
        """Prepare local segmentation context and views for visual labeling; returns a job, not a completed asset."""
        return jobs.submit(root, "prepare-segment", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def resume_asset_processing(asset_id: str, revision: str) -> dict:
        """Resume an existing processing revision using its saved provider and request."""
        return jobs.submit(root, "resume-process", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def edit_asset(request: dict) -> dict:
        """Submit named-part edits against an exact existing revision; creates a new revision."""
        return jobs.submit(root, "edit", request)

    @server.tool()
    def edit_in_blender(request: dict) -> dict:
        """Run an agent-authored local Blender Python script on an exact revision, including rig edits and custom animation."""
        return jobs.submit(root, "blender-edit", request)

    @server.tool()
    def merge_asset_animations(request: dict) -> dict:
        """Merge selected clips from compatible GLBs or exact revisions into a new local revision; no retargeting."""
        return jobs.submit(root, "merge-animations", request)

    @server.tool()
    def compare_asset_animations(request: dict) -> dict:
        """Read-only GLB clip/model comparison, excluding declared clip edits from preservation claims.

        Returns data differences immediately without Blender, generation, new revisions or visual approval.
        """
        from .animation_compare import compare_request
        from .models import AnimationComparisonRequest

        return compare_request(root, AnimationComparisonRequest.model_validate(request))

    @server.tool()
    def resume_blender_edit(asset_id: str, revision: str) -> dict:
        """Resume a recorded local Blender edit with its saved script, parameters and input revision."""
        return jobs.submit(root, "resume-blender-edit", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def resume_animation_merge(asset_id: str, revision: str) -> dict:
        """Resume a recorded animation merge using the same source clips and pending revision."""
        return jobs.submit(root, "resume-merge-animations", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def asset_job_status(job_id: str) -> dict:
        """Read a submitted job's actual state and result. Poll this instead of resubmitting."""
        result = jobs.status(root, job_id)
        result.pop("payload", None)
        asset = result.get("result")
        if isinstance(asset, dict) and "asset_id" in asset and ("files" in asset or "inspection" in asset):
            result["result"] = {
                key: asset[key] for key in (
                    "asset_id", "revision", "parent", "state", "asset_type", "inspection",
                    "remote_generation", "remote_processing", "local_processing", "provenance",
                    "animation_previews", "part_previews",
                ) if key in asset
            }
        return result

    @server.tool()
    def assess_asset(request: dict) -> dict:
        """Assess declared usage on final GLB; bounded motion samples/critical frames, no automatic visual approval."""
        return jobs.submit(root, "assess", request)

    @server.tool()
    def asset_usage(asset_id: str, revision: str) -> dict:
        """Read a GLB-bound usage contract and latest assessment. Absent contracts are not inferred."""
        from .pipeline import completed_source
        from .usage import load_usage

        source, _, digest = completed_source(root, asset_id, revision)
        report = source.parent / "assessment.json"
        assessment = read_json(report) if report.exists() else None
        if assessment is not None and assessment.get("source_sha256") != digest:
            raise ValueError("Assessment belongs to different GLB bytes")
        return {"usage": load_usage(source.parent, digest), "assessment": assessment}

    @server.tool()
    def list_assets() -> list[dict]:
        """List completed revisions with IDs, triangle counts and numeric gate status."""
        return [
            {
                "asset_id": item["asset_id"],
                "revision": item["revision"],
                "state": item["state"],
                "triangles": item["inspection"]["triangles"],
            }
            for item in Store(root).list()
        ]

    @server.tool()
    def inspect_asset(asset_id: str, revision: str) -> dict:
        """Read measured geometry, real part names, and available skin/animation evidence for a completed revision."""
        return read_json(Store(root).revision(asset_id, revision) / "inspection.json")

    @server.tool()
    def validate_in_godot(asset_id: str, revision: str) -> dict:
        """Submit a real headless Godot import/mesh/material/collision check."""
        Store(root).revision(asset_id, revision)
        return jobs.submit(root, "godot", {"asset_id": asset_id, "revision": revision})

    return server


def serve(root):
    build_server(root).run(transport="stdio")
