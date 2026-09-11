from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssetId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
Vec3 = tuple[float, float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Material(StrictModel):
    color: tuple[float, float, float, float] = (0.5, 0.5, 0.5, 1)
    metallic: float = Field(0, ge=0, le=1)
    roughness: float = Field(0.5, ge=0, le=1)

    @model_validator(mode="after")
    def valid_color(self):
        if any(not 0 <= c <= 1 for c in self.color):
            raise ValueError("Color channels must be between 0 and 1")
        return self


class Part(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
    primitive: Literal["box", "cylinder", "sphere", "cone"] = "box"
    dimensions: Vec3
    location: Vec3 = (0, 0, 0)
    rotation_degrees: Vec3 = (0, 0, 0)
    material: str
    bevel: float = Field(0, ge=0, le=1)
    segments: int = Field(16, ge=3, le=64)

    @model_validator(mode="after")
    def positive_dimensions(self):
        if min(self.dimensions) <= 0:
            raise ValueError("Part dimensions must be positive")
        return self


class Recipe(StrictModel):
    materials: dict[str, Material]
    parts: list[Part] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_parts(self):
        names = [p.name for p in self.parts]
        if len(set(names)) != len(names):
            raise ValueError("Part names must be unique")
        if any(p.material not in self.materials for p in self.parts):
            raise ValueError("All part materials must be defined")
        return self


class AssetSpec(StrictModel):
    asset_id: AssetId
    prompt: str = ""
    provider: Literal["procedural", "trellis", "import"] = "procedural"
    recipe: Recipe | None = None
    image: str | None = None
    source: str | None = None
    triangle_budget: int = Field(12000, ge=12, le=1000000)
    target_height: float | None = Field(None, gt=0, le=10000)
    seed: int = Field(42, ge=0, le=2147483647)
    resolution: Literal[512, 1024] = 512
    atlas: Literal[512, 1024, 2048] = 1024

    @model_validator(mode="after")
    def required_input(self):
        if self.provider == "procedural" and self.recipe is None:
            raise ValueError("procedural requires recipe")
        if self.provider == "trellis" and not self.image:
            raise ValueError("trellis requires a reference image")
        if self.provider == "import" and not self.source:
            raise ValueError("import requires a GLB or .blend source")
        return self


class Edit(StrictModel):
    part: str = Field(min_length=1)
    scale: Vec3 | None = None
    offset: Vec3 | None = None
    color: tuple[float, float, float, float] | None = None
    metallic: float | None = Field(None, ge=0, le=1)
    roughness: float | None = Field(None, ge=0, le=1)
    merge_distance: float | None = Field(None, gt=0, le=0.01)
    shading: Literal["smooth", "flat"] | None = None

    @model_validator(mode="after")
    def has_change(self):
        if all(
            getattr(self, k) is None
            for k in ("scale", "offset", "color", "metallic", "roughness", "merge_distance", "shading")
        ):
            raise ValueError("At least one edit is required")
        if self.scale and min(self.scale) <= 0:
            raise ValueError("Scale factors must be positive")
        if self.color and any(not 0 <= c <= 1 for c in self.color):
            raise ValueError("Color channels must be between 0 and 1")
        return self


class EditRequest(StrictModel):
    asset_id: AssetId
    revision: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    changes: list[Edit] = Field(min_length=1)
    description: str = ""
