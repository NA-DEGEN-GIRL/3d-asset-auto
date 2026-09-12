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
        from .models import PostprocessRequest
        from .pipeline import postprocess_plan

        return postprocess_plan(root, PostprocessRequest.model_validate(spec))

    @server.tool()
    def process_tripo_asset(request: dict) -> dict:
        """Submit requested rig/animate/segment processing; creates a new revision, default credit guard 100."""
        return jobs.submit(root, "tripo-process", request)

    @server.tool()
    def resume_tripo_processing(asset_id: str, revision: str) -> dict:
        """Resume saved processing stages without resubmitting known paid tasks."""
        return jobs.submit(root, "resume-tripo-process", {"asset_id": asset_id, "revision": revision})

    @server.tool()
    def edit_asset(request: dict) -> dict:
        """Submit named-part edits against an exact existing revision; creates a new revision."""
        return jobs.submit(root, "edit", request)

    @server.tool()
    def asset_job_status(job_id: str) -> dict:
        """Read a submitted job's actual state and result. Poll this instead of resubmitting."""
        result = jobs.status(root, job_id)
        result.pop("payload", None)
        if "result" in result and "asset_id" in result["result"]:
            asset = result["result"]
            result["result"] = {
                key: asset[key] for key in (
                    "asset_id", "revision", "parent", "state", "asset_type", "inspection",
                    "remote_generation", "remote_processing", "animation_previews", "part_previews",
                ) if key in asset
            }
        return result

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
