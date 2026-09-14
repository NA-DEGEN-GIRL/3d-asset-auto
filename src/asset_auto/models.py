from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

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


class TripoOptions(StrictModel):
    model: Literal["v3.1-20260211"] = "v3.1-20260211"
    max_credits: int = Field(100, gt=0, le=100000)


class AssetSpec(StrictModel):
    asset_id: AssetId
    prompt: str = ""
    provider: Literal["procedural", "trellis", "tripo", "import"] = "trellis"
    recipe: Recipe | None = None
    image: str | None = None
    views: dict[Literal["front", "left", "back", "right"], str] | None = None
    tripo: TripoOptions | None = None
    source: str | None = None
    asset_kind: Literal["static", "character", "animated"] = "static"
    triangle_budget: int = Field(12000, ge=12, le=1000000)
    target_height: float | None = Field(None, gt=0, le=10000)
    seed: int = Field(42, ge=0, le=2147483647)
    resolution: Literal[512, 1024] = 512
    atlas: Literal[512, 1024, 2048] = 1024

    @model_validator(mode="after")
    def required_input(self):
        if self.image and self.provider not in ("trellis", "tripo"):
            raise ValueError("Reference images require the trellis provider or explicit tripo provider")
        if (self.views is not None or self.tripo is not None) and self.provider != "tripo":
            raise ValueError("Tripo options and multi-view inputs require explicit provider: tripo")
        if self.provider == "tripo":
            if self.tripo is None:
                self.tripo = TripoOptions()
            if bool(self.image) == bool(self.views):
                raise ValueError("Tripo requires one image or named multi-view inputs, not both")
            if self.views and (
                "front" not in self.views or len(self.views) < 2 or any(not v.strip() for v in self.views.values())
            ):
                raise ValueError("Tripo multi-view requires front and at least one other nonempty view")
            if self.recipe is not None or self.source is not None:
                raise ValueError("Tripo requests cannot contain procedural recipes or import sources")
        if self.provider == "procedural" and self.recipe is None:
            raise ValueError("procedural requires recipe")
        if self.provider == "trellis" and not self.image:
            raise ValueError("trellis requires a reference image")
        if self.provider == "import" and not self.source:
            raise ValueError("import requires a GLB or .blend source")
        if self.asset_kind != "static" and self.provider != "import":
            raise ValueError("character/animated import requires provider: import; use processing for an existing asset")
        return self


class SegmentationPart(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
    positive_points: list[tuple[int, int]] = Field(min_length=1, max_length=64)
    negative_points: list[tuple[int, int]] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def valid_points(self):
        if any(min(point) < 0 for point in self.positive_points + self.negative_points):
            raise ValueError("Segmentation points are nonnegative image pixel coordinates")
        if any(max(point) >= 1024 for point in self.positive_points + self.negative_points):
            raise ValueError("Segmentation points must be inside the 1024 by 1024 context image")
        return self


class PostprocessRequest(StrictModel):
    asset_id: AssetId
    revision: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    operation: Literal["rig", "animate", "segment"]
    provider: Literal["local", "tripo"] = "local"
    max_credits: int = Field(100, gt=0, le=100000)
    rig_type: Literal["biped"] = "biped"
    rig_model: Literal["v1.0-20240301"] = "v1.0-20240301"
    rig_forward_axis: Literal["+x", "-x", "+z", "-z"] = "+z"
    animation: Literal["idle", "walk", "run"] = "walk"
    animate_in_place: bool = True
    segmentation_granularity: Literal["simple", "balanced", "detailed"] = "balanced"
    segmentation_context: str | None = None
    segmentation_view: int = Field(0, ge=0, le=11)
    segmentation_parts: list[SegmentationPart] | None = Field(None, min_length=1, max_length=32)
    bone_map: dict[str, str] | None = None
    triangle_budget: int | None = Field(None, ge=12, le=1000000)

    @classmethod
    def for_tripo(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("Tripo processing requires a request object")  # noqa: TRY004 -- structured CLI validation
        if payload.get("provider", "tripo") != "tripo":
            raise ValueError("A Tripo-specific command requires provider: tripo; use process for local work")
        return cls.model_validate(payload | {"provider": "tripo"})

    @model_validator(mode="after")
    def processing_inputs(self):
        if self.provider == "tripo" and (
            self.segmentation_context is not None or self.segmentation_parts is not None or self.bone_map is not None
        ):
            raise ValueError("Local segmentation prompts and bone maps cannot be sent through Tripo processing")
        if self.provider == "local" and self.operation == "segment":
            if not self.segmentation_context or not self.segmentation_parts:
                raise ValueError("Local segmentation requires a prepared context and observed part prompts; use prepare-segment first")
            if len({part.name for part in self.segmentation_parts}) != len(self.segmentation_parts):
                raise ValueError("Segmentation part names must be unique")
        if self.bone_map is not None:
            if self.operation != "animate" or not self.bone_map or any(not k.strip() or not v.strip() for k, v in self.bone_map.items()):
                raise ValueError("bone_map must map motion roles to actual bone names for local animation")
            if len(set(self.bone_map.values())) != len(self.bone_map):
                raise ValueError("Each motion role must address a different bone")
        return self


class Edit(StrictModel):
    part: str = Field(min_length=1)
    rename: str | None = Field(None, pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
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
            for k in ("rename", "scale", "offset", "color", "metallic", "roughness", "merge_distance", "shading")
        ):
            raise ValueError("At least one edit is required")
        if self.scale and min(self.scale) <= 0:
            raise ValueError("Scale factors must be positive")
        if self.color and any(not 0 <= c <= 1 for c in self.color):
            raise ValueError("Color channels must be between 0 and 1")
        if self.rename and self.part == "*":
            raise ValueError("Renaming requires one exact part, not a wildcard")
        return self


class EditRequest(StrictModel):
    asset_id: AssetId
    revision: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    changes: list[Edit] = Field(min_length=1)
    description: str = ""


RevisionId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]+$")]
ClipName = Annotated[str, Field(min_length=1, pattern=r"^[^\x00]+$")]


class BlenderEditRequest(StrictModel):
    asset_id: AssetId
    revision: RevisionId
    script: str = Field(min_length=1)
    description: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    preserve_animations: bool = True
    require_animation: bool = False
    preview_clips: list[ClipName] | None = Field(None, min_length=1, max_length=8)
    triangle_budget: int | None = Field(None, ge=12, le=1000000)


class AnimationSource(StrictModel):
    asset_id: AssetId | None = None
    revision: RevisionId | None = None
    path: str | None = Field(None, min_length=1)
    clips: list[ClipName] | None = Field(None, min_length=1)
    rename: dict[ClipName, ClipName] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_source(self):
        if self.path is not None:
            if self.asset_id is not None or self.revision is not None:
                raise ValueError("Choose a GLB path or an exact asset revision, not both")
        elif self.asset_id is None or self.revision is None:
            raise ValueError("Animation source requires a GLB path or asset_id and revision")
        if self.clips is not None and len(self.clips) != len(set(self.clips)):
            raise ValueError("Selected clip names must be unique")
        return self


class MergeAnimationsRequest(StrictModel):
    asset_id: AssetId
    revision: RevisionId
    sources: list[AnimationSource] = Field(min_length=1, max_length=32)
    on_conflict: Literal["error", "replace"] = "error"
    description: str = ""
    preview_clips: list[ClipName] | None = Field(None, min_length=1, max_length=8)


class AnimationComparisonRequest(StrictModel):
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    changed_clips: list[ClipName] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_changes(self):
        if len(self.changed_clips) != len(set(self.changed_clips)) or any(
            not name.strip() for name in self.changed_clips
        ):
            raise ValueError("Declared changed clips must be unique and nonblank")
        return self


class UsageFeature(StrictModel):
    name: str = Field(min_length=1)
    representation: str = Field(min_length=1)
    intended_behavior: str = Field(min_length=1)
    acceptance: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MotionEvent(StrictModel):
    name: str = Field(min_length=1)
    time_seconds: float = Field(ge=0)


class MotionRules(StrictModel):
    position_tolerance_m: float = Field(0.001, gt=0)
    rotation_tolerance_degrees: float = Field(1, gt=0, le=180)
    scale_tolerance: float = Field(0.001, gt=0)
    morph_tolerance: float = Field(0.001, gt=0)
    max_linear_velocity_jump_mps: float | None = Field(None, ge=0)
    max_angular_velocity_jump_dps: float | None = Field(None, ge=0)
    max_still_seconds: float | None = Field(None, gt=0)
    still_position_speed_mps: float = Field(0.001, ge=0)
    still_rotation_speed_dps: float = Field(0.1, ge=0)
    still_value_speed: float = Field(0.001, ge=0)
    max_root_drift_m: float | None = Field(None, ge=0)


class ClipUsage(StrictModel):
    purpose: str = ""
    playback: Literal["unspecified", "loop", "once", "hold"] = "unspecified"
    motion: Literal["unspecified", "in_place", "root_motion", "none"] = "unspecified"
    root_target: str | None = None
    target_speed_mps: float | None = Field(None, ge=0)
    events: list[MotionEvent] = Field(default_factory=list, max_length=32)
    acceptance: list[str] = Field(default_factory=list)
    rules: MotionRules = Field(default_factory=MotionRules)

    @model_validator(mode="after")
    def valid_motion(self):
        if self.motion == "root_motion" and not self.root_target:
            raise ValueError("Root motion assessment requires an observed root_target")
        if self.rules.max_root_drift_m is not None and not self.root_target:
            raise ValueError("Root drift checks require an observed root_target")
        return self


class AssetUsage(StrictModel):
    purpose: str = ""
    assumptions: list[str] = Field(default_factory=list)
    features: list[UsageFeature] = Field(default_factory=list, max_length=64)
    clips: dict[ClipName, ClipUsage] = Field(default_factory=dict)


class AssessmentRequest(StrictModel):
    asset_id: AssetId
    revision: RevisionId
    usage: AssetUsage | None = None
    clips: list[ClipName] | None = Field(None, min_length=1, max_length=16)
    sample_rate: int = Field(30, ge=2, le=120)
    max_samples_per_clip: int = Field(1201, ge=5, le=10001)
    render: bool = True
    max_render_frames: int = Field(24, ge=0, le=128)
    views: list[Literal["front", "back", "left", "right", "perspective"]] = Field(
        default_factory=lambda: ["front", "right", "back"], min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_clips(self):
        if self.clips and len(self.clips) != len(set(self.clips)):
            raise ValueError("Assessment clip names must be unique")
        if len(self.views) != len(set(self.views)):
            raise ValueError("Assessment views must be unique")
        return self


class KimodoMotionRequest(StrictModel):
    asset_id: AssetId
    revision: RevisionId
    prompt: str = Field(min_length=1, max_length=2000)
    clip_name: ClipName
    duration_seconds: float = Field(4, ge=2, le=10)
    seed: int = Field(42, ge=0, le=2147483647)
    diffusion_steps: int = Field(100, ge=10, le=500)
    bone_map: dict[str, str] = Field(min_length=1, max_length=77)
    forward_axis: Literal["+x", "-x", "+y", "-y"] = "-y"
    in_place: bool = False
    description: str = ""

    @model_validator(mode="after")
    def valid_mapping(self):
        if not self.prompt.strip() or not self.clip_name.strip():
            raise ValueError("Motion prompt and clip_name must not be blank")
        if any(not key.strip() or not value.strip() for key, value in self.bone_map.items()):
            raise ValueError("Map SOMA joint names to observed target bone names")
        if len(set(self.bone_map.values())) != len(self.bone_map):
            raise ValueError("Target bones must be unique in the motion mapping")
        if "Hips" not in self.bone_map:
            raise ValueError("Motion mapping requires SOMA Hips as the translation root")
        return self
