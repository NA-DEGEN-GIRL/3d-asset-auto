from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .settings import capabilities
from .store import Store, child, now, write_json

PUBLIC_FILES = {
    "asset.glb",
    "source.blend",
    "inspection.json",
    "front.png",
    "back.png",
    "left.png",
    "right.png",
    "perspective.png",
    "review.json",
    "godot.json",
    "three.json",
}


class BrowserReport(BaseModel):
    meshes: int = Field(ge=1)
    triangles: int = Field(ge=1)
    draw_calls: int = Field(ge=1)
    three_version: str = Field(max_length=40)


def create_app(root: Path):
    app = FastAPI(title="Asset Auto local viewer")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    store = Store(root)

    @app.get("/api/capabilities")
    def doctor():
        return capabilities(root)

    @app.get("/api/assets")
    def assets():
        result = []
        for item in store.list():
            result.append(
                {
                    k: item[k]
                    for k in (
                        "asset_id",
                        "revision",
                        "parent",
                        "created_at",
                        "provider",
                        "prompt",
                        "state",
                        "inspection",
                        "renders",
                        "files",
                        "edits",
                    )
                }
                | {"review": item.get("review"), "godot": item.get("godot")}
            )
        return result

    @app.get("/assets/{asset_id}/{revision}/{filename}")
    def file(asset_id: str, revision: str, filename: str):
        if filename not in PUBLIC_FILES:
            raise HTTPException(404)
        try:
            directory = store.revision(asset_id, revision)
            path = child(directory, filename)
            if not path.is_file():
                raise FileNotFoundError(filename)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404) from None
        media = "model/gltf-binary" if filename.endswith(".glb") else None
        return FileResponse(path, media_type=media)

    @app.post("/api/assets/{asset_id}/{revision}/browser-report")
    def browser_report(asset_id: str, revision: str, report: BrowserReport, request: Request):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Same-origin request required")
        try:
            directory = store.revision(asset_id, revision)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404) from None
        write_json(
            directory / "three.json",
            report.model_dump()
            | {
                "passed": True,
                "tested_at": now(),
                "scope": "Browser-reported GLTFLoader load and WebGL draw; not visual approval",
            },
        )
        return {"saved": True}

    static = root / "web" / "dist"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="viewer")
    else:

        @app.get("/")
        def missing():
            raise HTTPException(503, "Viewer build missing. Run npm ci and npm run build in web/")

    return app
