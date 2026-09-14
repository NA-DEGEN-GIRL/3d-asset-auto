# Quick start

[한국어](QUICKSTART.md) | **English**

The default workflow is **reference image → TRELLIS.2 → Blender processing → agent review → GLB delivery**. No engine or web viewer is required. On a new computer, complete [installation](INSTALL.md). Run the following commands from the runtime root.

For paid Tripo, explicitly request “Use Tripo3D” and follow the [Tripo guide](docs/TRIPO.en.md). One standard generation per requested asset is covered without repeated credit approval; `max_credits` is optional. A configured API key does not change the default TRELLIS workflow.

## 1. Prepare a reference image

Use a supplied image or have the agent prepare one with an available image-generation tool. The runtime's `prompt` field does not generate an image. If neither an image nor a suitable tool is available, report the missing reference.

Do not replace inference by reconstructing the image from Blender primitives. Use TRELLIS or explicitly selected Tripo. Procedural generation is an explicitly requested alternative.

## 2. Save a generation request

```sh
uv run --no-sync python -m asset_auto.cli doctor
```

Check `providers.trellis: true` and `models.missing: []`. File readiness is not successful GPU inference. Missing Godot or a web build does not block the default workflow.

Save the following as UTF-8 `.work/asset.json`, replacing `image` with the absolute path of a real reference. Forward slashes simplify Windows JSON paths.

```json
{
  "asset_id": "my-chest-ai",
  "provider": "trellis",
  "image": "D:/references/chest.png",
  "prompt": "A 75 cm wooden treasure chest",
  "triangle_budget": 12000,
  "target_height": 0.75,
  "resolution": 512,
  "atlas": 1024,
  "seed": 42
}
```

Omitting `provider` still selects `trellis` and requires an image. Combining `image` with `procedural` or `import` is rejected. Explicitly requested procedural recipes must specify `provider: "procedural"`.

## 3. Generate and wait for completion

```sh
uv run --no-sync python -m asset_auto.cli generate .work/asset.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

Replace `JOB_ID` with the returned ID. `submitted` means the job started, not that the asset is complete. When `state` is `succeeded`, inspect the result's `asset_id`, `revision` and `inspection`. Read failure/interruption logs and do not submit duplicates while waiting.

The first revision under `.assets/my-chest-ai/REVISION/` contains:

- `generation.json`, `trellis.log`, `generated.glb`: inference request/log and raw generated model.
- `source.blend`, `asset.glb`: processed authoring source and delivery file.
- `inspection.json` and five overview PNGs: measurements and review images.
- `manifest.json`: provider, request, hashes and tool provenance.

Blender renders alone do not prove TRELLIS inference. Check generation records too. Edited revisions trace generation provenance through their parents.

## 4. Inspect the model

```sh
uv run --no-sync python -m asset_auto.cli inspect my-chest-ai REVISION
```

Replace `REVISION` with the actual result. Read the measurements and inspect `front.png`, `back.png`, `left.png`, `right.png` and `perspective.png` with the agent's image tool. Follow the [quality guide](docs/QUALITY.en.md): define observable criteria before authoring, review the whole model plus relevant close-ups/motion, and repair defects in a new revision under the same revealing conditions. A narrow edit needs checks for its affected scope.

Record actual observations. Replace `OBSERVATIONS`; use `--result fail` when required criteria remain unmet:

```sh
uv run --no-sync python -m asset_auto.cli review my-chest-ai REVISION --result pass --notes "OBSERVATIONS"
```

If images cannot be inspected, report visual review as incomplete. Engine loading or opening a browser does not substitute for it. The runtime creates five overview views during generation/edits, but does not automatically run Godot or a viewer.

## 5. Edit an existing model

Read actual object names with `inspect`. Editing does not require new TRELLIS inference. A generated model with one `Mesh_0` object does not already have semantic handles/lids separated.

Generation does not choose the editor: Tripo assets can be edited locally without new paid work. For parts, use [local segmentation](docs/CHARACTERS.en.md#segmentation-and-part-names) and inspect individual outputs. Use named `edit` for static parts and [blender-edit](docs/BLENDER.en.md) for rigs, weights, custom motion or broader changes.

For example, after explicitly requested generation of `examples/sword.json`, save `.work/grip-edit.json`:

```json
{
  "asset_id": "azure-sword",
  "revision": "REVISION",
  "description": "Change only the grip to burgundy",
  "changes": [{"part": "grip", "color": [0.19, 0.015, 0.035, 1]}]
}
```

```sh
uv run --no-sync python -m asset_auto.cli edit .work/grip-edit.json
```

Review the new revision and preserve the old source. Scaling one part does not reposition connected neighbors. See the [request reference](.agents/skills/3d-assets/references/specs.md).

## 6. Deliver or integrate

Default delivery is the reviewed GLB, authoring source and findings. For requested project integration, follow the project's naming, size, material and path conventions; choose relevant importer/loader checks. An unknown target does not justify creating a Godot project or web app.

GLB is **Y-up in meters**; Blender authoring/inspection coordinates are **Z-up in meters**. Unperformed optional engine checks are untested, not generation failures.

## Optional rigging, animation and segmentation

Keep static props unrigged. Use [object keyframes](docs/BLENDER.en.md#scripted-editing) for rigid moving parts. For deformation, use an existing rig or [SkinTokens draft](docs/CHARACTERS.en.md#rigging), then refine rigs/weights/motion in Blender.

Local `process` adds `idle`, `walk` or `run` while preserving other clips. Use [merge-animations](docs/BLENDER.en.md#several-motions-in-one-glb) for compatible separate outputs. The agent observes model data to create bone maps and segmentation points; it does not make the user annotate. Install only required models. Paid Tripo processing needs explicit selection.

Follow [per-clip completion](docs/QUALITY.en.md#complete-each-requested-clip) for multiple motions. Declare intended clip edits and use [compare-animations](docs/BLENDER.en.md#editing-one-clip-and-comparing-preservation) to check untouched timing/channel/model data. For surfaces damaged during processing, locate the first failing stage using the [finishing guide](docs/FINISHING.en.md).

## Optional Godot check

When relevant to a requested Godot integration, complete [optional setup](INSTALL.md#optional-project-checks-and-viewer), then run:

```sh
uv run --no-sync python -m asset_auto.cli godot ASSET_ID REVISION
```

This imports the GLB and checks scene/mesh/material/convex-collision data. It does not imply a Three.js check is also required.

## Optional interactive preview

For an explicitly requested viewer or web check, prefer the destination project's existing app. If a standalone viewer is needed, install the optional web components and run `start-viewer.cmd` on Windows or `sh start-viewer.sh` on Linux.

Open the [local viewer](http://127.0.0.1:8765/), refresh the library, select an asset and choose a revision. The shared viewer offers orbit, zoom, wireframe, renders and GLB download. Windows starts a background server; keep the launcher terminal open on Linux. See [troubleshooting](docs/TROUBLESHOOTING.en.md) for connection failures.

## Requests for an LLM

> `$3d-assets` Make a prop from this image. Inspect its back as well, repair defects in new revisions, and deliver a GLB.

> `$3d-assets` Create a wooden chest for this project. Prepare a reference image, generate it with TRELLIS, and inspect the actual result.

> `$3d-assets` Use Tripo3D with these front/back images and deliver the GLB with your review findings.

> `$3d-assets` Rig this character and add walking. Inspect the actual arm and leg deformation.

> `$3d-assets` Use Kimodo to make this rigged character wave. Keep existing clips, add the new one to the same GLB, and inspect important moments from front, side and back.

Kimodo is selected only by an explicit request. That task can include setup/inference without repeated confirmation. Generic animation requests use existing clips, authoring or presets. See [Kimodo](docs/KIMODO.en.md) for encoder access and commands; contacts, grips and loops require review and correction after generation.

> `$3d-assets` Animate this Tripo-generated drone hovering without a rig. Keep idle on the existing character, add a wave, and merge run into the same GLB.

> `$3d-assets` Segment this static model locally and name parts after inspecting each render.

When an interactive viewer is wanted, add:

> Open a web preview so I can rotate the completed model.
