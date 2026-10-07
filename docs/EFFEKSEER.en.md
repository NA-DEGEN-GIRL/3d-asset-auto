# Effekseer VFX

[한국어](EFFEKSEER.md) | **English**

Effekseer provides VFX authoring and playback for timed particles, ribbons, rings and models. It is an optional `game-vfx` path, not an AI generator or a mandatory dependency for every project. Consider it first when the user selects it or the destination has a suitable integration; existing engine effect systems remain valid choices.

## Scope and files

- Preserve editable `.efkefc` files together with referenced textures, models, materials and other resources. `.efkproj` can be a compatibility input, but load/convert it with the official tool and verify actual playback.
- Web playback needs an Effekseer WebGL runtime; Godot needs the matching plugin. An effect file does not automatically convert into native engine particles or GLB.
- Preserve relative resource paths and the dependency inventory. If the complete effect is requested as GLB, follow the existing [format guidance](../.agents/skills/game-vfx/references/workflow.md#delivery-format-constraints).

Consult the official [tool reference](https://effekseer.github.io/Help_Tool/en/ToolReference/index.html) for file and command-line contracts. When adapting bundled examples or existing projects, first define the intended layers and events; a palette change alone does not establish completion of newly requested behavior.

Keep an XML input's schema and version metadata consistent. Changing a legacy project's `ToolVersion` to the installed editor version without migrating its structure can produce a successful conversion with invisible nodes. Preserve compatible source metadata and let the official tool convert it; inspect actual playback rather than treating an output file as evidence that the nodes survived.

Check renderer enum values against the pinned format before authoring them numerically. In 1.80.7, billboard `2` is `Fixed` and `3` is `RotatedBillboard`; using the latter for a ground-contact plane can keep it facing the camera despite rotation settings. Confirm alignment from another camera angle.

## Installation and conversion

[`scripts/effekseer.py`](../scripts/effekseer.py) owns the **1.80.7** pins and download verification for native Windows/Linux x86_64 editors and the WebGL distribution. It installs under `.runtime/effekseer/1.80.7/` and does not automatically install a Godot plugin. Windows uses `editor/` and `editor.install.json`; Linux uses `editor-linux/` and `editor-linux.install.json`, preserving existing Windows installation records. Run these commands from the repository root.

```text
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> doctor
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> install --component all
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> export --input <absolute-source.efkproj> --output <absolute-new-output.efkefc>
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> model --input <absolute-existing-mesh.obj> --output <absolute-new-model.efkmodel> --scale 1
```

On Linux, these direct commands also work after setting up the project's virtual environment. The official Linux distribution bundles a self-contained .NET runtime; no separate .NET SDK, Mono or Wine is needed. Native shared libraries such as `libGLU.so.1` are still required; on Ubuntu, install a missing `libGLU.so.1` with `sudo apt-get install libglu1-mesa`. `doctor` checks executable permissions, hashes and native dependencies of the binaries and `libViewer.so`, which CUI also loads.

```bash
.venv/bin/python scripts/effekseer.py install --component all
.venv/bin/python scripts/effekseer.py doctor
```

Select only `install --component editor` or `webgl` when appropriate. `doctor` checks installation state; it does not replace visual review. An `.efkefc` `export` uses the official tool's `-cui -in … -o …` path. This plain conversion avoids GUI/graphics-device initialization and material-cache generation, and applies the global CPU policy. Actual Linux conversion was verified without `DISPLAY`. Thread environment variables do not enforce a hard cap on every native thread; do not report unsupported Windows CPU affinity as applied. Rendering requires the separate resource checks below.

`model` is a native Windows/Linux x86_64 CPU path through the official resource converter for an existing `.obj` or `.glb`. `--scale` must be positive; existing outputs and provenance files are not overwritten. Actual minimal-OBJ conversion and output-header checks were verified, but they do not establish arbitrary-model appearance, material or rig preservation. Author the model's materials, textures and renderer settings separately.

## GPU and private resource settings

| Stage | Resources and limits |
| --- | --- |
| Writing XML/resources and inspecting files | CPU and file operations; no CUDA model or GPU inference memory is needed. |
| Command-line conversion | The helper's plain conversion uses the CPU path. Do not generalize that to every `-cui` invocation or another tool's material-cache/recording operations. |
| Windows editor/preview | Official requirements include DirectX 11. Even ordinary particles consume graphics resources when drawn. |
| Linux editor/preview | Requires OpenGL and a display/graphics backend. Successful headless file conversion does not establish GUI launch or render verification. |
| WebGL playback | Uses the browser graphics context. CPU particle simulation is distinct from rendering without a GPU. |
| Effekseer's `GPU Particles` feature | A separate GPU simulation feature. The current official table marks WebGL and Godot integration unsupported, so use regular particles there and recheck the installed version's table. This is not a limitation on Godot's own GPU particle feature. |

Select against the official [environment requirements](https://effekseer.github.io/Help_Tool/en/overview.html) and [GPU particle support table](https://effekseer.github.io/Help_Tool/en/ToolReference/gpuParticles.html). Do not mix this repository's pinned version with an unrelated newer runtime.

The operator's [private resource policy](RESOURCES.en.md) still applies. Use the existing guarded Blender launcher; inspect DirectX/OpenGL/WebGL device selection for the Effekseer editor and browser separately. `CUDA_VISIBLE_DEVICES` and Blender CPU limits do not establish those renderers' GPU selection or concurrency enforcement. If the host cannot enforce a restriction, do not assume protected GPUs are excluded or relax the policy; distinguish verified CPU file work from the render verification status. Do not switch to another device when a selected device is busy.

## When a separate model is useful

Reuse an existing mesh for a meteor, distinctive ice chunk, summon or other standalone physical object. Request [`3d-assets`](../.agents/skills/3d-assets/SKILL.md) only when a new model is needed. Reference images and TRELLIS.2 are the default; Tripo requires explicit selection. Effekseer ribbons, rings, sprites and simple procedural VFX geometry do not require inference.

Refine needed meshes in Blender and inspect coordinates, units, origin, normals and UVs before converting to Effekseer model inputs. The official [model renderer](https://effekseer.github.io/Help_Tool/en/ToolReference/rendererModel.html) describes conversion from GLB, glTF, FBX, OBJ and other formats into `.efkmodel`. Preserve source and conversion outputs; verify scale, orientation, appearance and resource paths with the actual installed version. Do not assume complete GLB PBR materials, rigs and named animations play unchanged. Keeping a character in its engine and attaching effects to its sockets may be the suitable integration.

## Authoring, review and integration

Compose nodes to match adopted reference shapes, events and rhythm. Review activation, peak expression, contact and decay for every effect, inspecting the same moment from complementary angles. Planar sprites are valid ingredients, but one video plane cannot replace an entire requested spatial effect. Apply the existing [per-effect review loop](../.agents/skills/game-vfx/references/workflow.md#per-effect-quality-loop).

Verify loading, play/stop/restart, instance lifetime and shared-resource release in the destination runtime. Check depth, blending, distortion, post-processing and concurrent-effect cost in that project. Visual contact does not prove terrain collision or damage logic. Browser preview success and [Godot plugin](https://github.com/effekseer/EffekseerForGodot4) verification remain separate; integrate only the requested destination.

## Reproduce the four spell examples

[`examples/effekseer/author_demo.py`](../examples/effekseer/author_demo.py) adapts CC0 effects from the pinned distribution into fire, ice, lightning and arcane spells and authors a procedural crystal mesh for ice. It runs no new AI image/video generation or paid inference. It uses actual Effekseer effect files and the WebGL runtime; contact and shatter timing are authored presentation. Do not label them runtime physics or reconstructed reference-video motion.

Run from the repository root in Windows PowerShell, after the installation above and project web-dependency setup. Replace `revision-name` with a new work name; do not reuse an output directory to overwrite previous results.

```powershell
uv run --no-sync python examples/effekseer/author_demo.py --samples .runtime/effekseer/1.80.7/editor/Effekseer1.80.7Win/Sample --out .work/effekseer-demo/revision-name
uv run --no-sync python scripts/effekseer.py model --input .work/effekseer-demo/revision-name/effects/ice/Model/crystal.obj --output .work/effekseer-demo/revision-name/effects/ice/Model/crystal.efkmodel --scale 1
foreach ($effect in @('fire', 'ice', 'lightning', 'arcane')) {
    uv run --no-sync python scripts/effekseer.py export --input ".work/effekseer-demo/revision-name/effects/$effect/source.efkproj" --output ".work/effekseer-demo/revision-name/effects/$effect/effect.efkefc"
    if ($LASTEXITCODE -ne 0) { throw "Effect export failed: $effect" }
}
node examples/effekseer/build.mjs --runtime .runtime/effekseer/1.80.7/webgl --effects .work/effekseer-demo/revision-name --out .work/effekseer-demo/revision-name-site
python -m http.server 8784 --bind 127.0.0.1 --directory .work/effekseer-demo/revision-name-site
```

In Linux Bash, use the native distribution's `Sample` path. These authoring/conversion commands need no display and stop on a failed command.

```bash
set -e
.venv/bin/python examples/effekseer/author_demo.py --samples .runtime/effekseer/1.80.7/editor-linux/Effekseer1.80.7Linux/Sample --out .work/effekseer-demo/revision-name
.venv/bin/python scripts/effekseer.py model --input .work/effekseer-demo/revision-name/effects/ice/Model/crystal.obj --output .work/effekseer-demo/revision-name/effects/ice/Model/crystal.efkmodel --scale 1
for effect in fire ice lightning arcane; do
    .venv/bin/python scripts/effekseer.py export --input ".work/effekseer-demo/revision-name/effects/$effect/source.efkproj" --output ".work/effekseer-demo/revision-name/effects/$effect/effect.efkefc"
done
```

Continue only after each stage succeeds. Run the `node` build and HTTP server commands at the end of the PowerShell example only for a requested web preview. On Linux, use the same build command and start the server with `.venv/bin/python -m http.server …`. Choose a free port if needed and serve only the built site. [`build.mjs`](../examples/effekseer/build.mjs) copies playback effects/resources, runtime and license notices while excluding source XML/OBJ and private provenance JSON. Use a hidden window and readiness check when starting a background server on Windows.

This is a reproducible authoring/conversion/preview path, not automatic approval of example visual finish or real-game performance. Record actual per-effect playback and multi-angle review in the task's work records.

The example viewer seeks by rebuilding instances and advancing the whole context on the same 60 Hz simulation clock used for playback. This avoids a discrepancy observed with per-handle frame setting for short-lived models and multiple instances. Paused-event captures and normal playback still need separate inspection; a native render also does not establish the WebGL material appearance.

## Licensing and records

The repository's [Effekseer example source](../examples/effekseer/LICENSE.txt) is MIT; its notice is included in the built site. This does not relicense external effects, textures or models.

The official runtime uses MIT; the official distribution's effect and texture data are identified as CC0. Preserve distribution/dependency notices and the provenance of each reused resource. Do not extend those terms to community effects, separate textures, 3D models or provider outputs. [Official licensing guidance](https://effekseer.github.io/Help_Tool/en/overview.html#license)

Keep downloaded tools, models, generated effects and render/device records in local work directories rather than automatically adding them to Git. Report actual installation/conversion/render success, visual finish and other-engine compatibility separately.
