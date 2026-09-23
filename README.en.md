# 3D Asset Auto

[한국어](README.md) | **English**

Local tools for asking an LLM to generate, edit and review 3D assets. The default workflow is **reference image → TRELLIS.2 generation → Blender processing → agent review of measurements and renders → GLB delivery**. A destination game project is optional.

New meshes use TRELLIS.2 by default. **Tripo is a paid alternative only when the user explicitly selects Tripo/Tripo3D.** A configured key, missing GPU or failed local inference does not select it automatically. Do not replace requested image-to-3D inference with Blender primitives reconstructed from the reference. Procedural generation requires an explicit request; supplied meshes and existing revisions can be edited without generating a new mesh.

The agent uses a supplied image or an available image-generation tool. This runtime does not include a text-to-image service. **Godot checks are for relevant destination projects; an interactive viewer or browser check requires a user request.** The default review uses local renders without a browser.

Generation and editing are independent choices. Keep static props unrigged, use object animation for rigid parts, and choose an existing rig, a SkinTokens draft or Blender scripts when deformation needs one. Local scripts can edit rigs, weights, materials and custom motion, and compatible clips can be merged. GeoSAM2 segmentation and explicitly selected paid Tripo processing are additional options. Install learned models only when needed.

**Kimodo requires an explicit request such as “Generate this motion with Kimodo.”** Generic animation requests use existing clips, Blender authoring or local presets as appropriate. Installed weights or difficult edits do not authorize automatic Kimodo selection.

For selected humanoid work, first consider [reference review → rig checks → Kimodo draft → Blender finishing → final comparison](docs/KIMODO.en.md#workflow-for-selected-kimodo-work). Kimodo provides a 3D motion starting point; complete final clips against both technical stability and adopted expression targets.

## Documentation

| Task | Guide |
| --- | --- |
| Make a first asset in an installed runtime | [Quick start](QUICKSTART.en.md) |
| Install on another computer or delegate installation to an LLM | [Installation](INSTALL.md) |
| Use paid Tripo single-image or multiview generation | [Tripo](docs/TRIPO.en.md) |
| Rig, animate or segment an asset locally | [Character processing](docs/CHARACTERS.en.md) |
| Author custom motion, edit rigs or combine clips | [Blender editing](docs/BLENDER.en.md) |
| Diagnose damaged surfaces and reuse a finishing approach | [Finishing](docs/FINISHING.en.md) |
| Explicitly select local learned human motion | [Kimodo](docs/KIMODO.en.md) |
| Define functional criteria and review each motion | [Quality](docs/QUALITY.en.md) |
| Plan image/video references for difficult or creative motion | [Motion references](docs/MOTION_REFERENCES.en.md): initial design, optional Grok headless, frame review and Blender application |
| Author and preview fire, ice and lightning effects | [game-vfx skill](.agents/skills/game-vfx/SKILL.md), [design and execution](docs/GAME_VFX_DESIGN.en.md), [VFX authoring and experiments](docs/VFX.en.md): initial Blender ingredient authoring and reusable web effects |
| Maintain the repository | [Agent instructions](AGENTS.md) |
| Understand data flow and validation states | [Architecture](docs/ARCHITECTURE.en.md) |
| Resolve setup, generation or viewer failures | [Troubleshooting](docs/TROUBLESHOOTING.en.md) |
| Read the asset skill | [3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md) |
| Find documentation from an agent | [llms.txt](llms.txt) |

To delegate installation, provide the repository URL and ask:

> Read INSTALL.md and AGENTS.md. Install the default runtime in my chosen folder, connect the skill, generate a TRELLIS.2 model from a reference image, and inspect its rendered images.

## Implemented capabilities

| Capability | Current scope |
| --- | --- |
| Default image-to-3D | TRELLIS.2 through trellis.cpp; one reference image and an NVIDIA GPU |
| Explicit Tripo generation | One image or 2–4 named views including the front; paid standard PBR generation |
| Procedural modeling | Explicitly requested blockouts or dimension-based assemblies |
| Import | GLB/Blend; `character` preserves rigs/clips, `animated` preserves unrigged object/morph clips |
| Static edits | Named-object rename, size, position, material, normals and small-gap welding |
| Local rigging | Learned SkinTokens skeleton/weights transferred to the original mesh |
| Local motion presets | Procedural Blender IK `idle`, `walk`, `run`, preserving other clips |
| Explicit learned human motion | Kimodo `text-motion` applied to an existing rig using an observed bone map |
| Blender authoring | Object/custom motion and rig/weight/material edits in a new revision |
| Clip merging | Compatible revision or external GLB clips combined in one GLB |
| Clip preservation comparison | `compare-animations` compares time, interpolation, transforms and model data; no Blender required |
| Purpose-based assessment | Optional `assess`: usage/playback contracts, loop/activity checks, critical moments from multiple views and missing coverage |
| Local segmentation | Agent-selected points from rendered views → GeoSAM2 masks → review of each part |
| Explicit Tripo processing | Paid biped rigging, motion presets and beta semantic segmentation |
| Revisions and delivery | Preserved parents, editable Blend, self-contained GLB, five overview PNGs and inspection/provenance records |
| Optional project adapters | Godot import/mesh/material/collision checks; requested Three.js preview with orbit, zoom, wireframe, revision selection and downloads |
| Separate `game-vfx` skill | Blender noise/lightning-path authoring, reusable ice clips, fire/ice/lightning Three.js playback and requested web previews |
| Agent access | CLI, linked personal skill and optional stdio MCP |

`process` motion presets are procedural. Kimodo is a separate learned-motion path and its mapping-based application does not automatically solve target contacts, grips or seamless loops. Its text encoder requires Hugging Face model access. General automatic retarget solvers, TRELLIS multiview, automatic retopology and texture rebaking are not implemented. Tripo is the available multiview generation option. Inspect actual geometry, part boundaries, materials and motion; retain unclassified faces.

Numerical checks, visual review and engine/browser checks provide different evidence. An importer or renderer succeeding does not prove useful game motion or artistic quality.

Game VFX uses a separate [game-vfx skill](.agents/skills/game-vfx/SKILL.md) built around **Blender authoring, reusable effect components and target-renderer output**. The initial implementation provides a spatial fire shader, an existing ice-fracture clip, branching lightning and a [Three.js gallery](docs/GAME_VFX_DESIGN.en.md). Procedural fields, curves and particles are valid VFX production methods and need no TRELLIS. Use `3d-assets` when a separate physical model such as an ice chunk or meteor, or mesh animation, is needed.

The fire example is not fluid simulation, and the ice uses precomputed movement on a flat surface. Shaders, particles, lights and lifecycle do not all fit in a GLB. This is not a general VFX generation CLI/MCP, arbitrary-terrain collision system, cross-engine converter or commercial-quality guarantee. Existing [VFX experiments](docs/VFX.en.md) remain available, with references, multiview/playback review and repairs performed per effect. Launch a web preview only when requested.

For several motions, complete **references → authoring → multiview/playback review → repair and recheck for each clip**, then deliver them together. Repeated or side-swapped generated poses need diagnosis; use existing motion or video when images cannot resolve sequencing. Do not compress the entire requested set into one or two overview sheets. See [per-clip completion](docs/QUALITY.en.md#complete-each-requested-clip).

For difficult or creative motion, plan image and temporal references during initial design. Available tools such as Grok Imagine can animate a reference image, informing selected poses/timing in Blender after the reference's structure and contacts are inspected. Automatic video-to-3D motion extraction is not provided. Grok/FFmpeg are optional reference tools and are not added to the default installation.

After a scoped clip edit, [compare preservation](docs/BLENDER.en.md#editing-one-clip-and-comparing-preservation). A data change calls for diagnosis: the tool does not replace pose/timing comparison of resampled motion or visual review.

## Get started

Follow [INSTALL.md](INSTALL.md) on a new machine. The default installation contains **TRELLIS, its weights and Blender**. Godot, Node.js and the web build are optional. Add [local processing models](INSTALL.md#local-postprocessing-on-demand) only for the requested inference. Static edits, object motion, custom scripts and merging use the existing Blender installation.

An explicitly selected Tripo-only installation needs Python, Blender and a key, without local CUDA/TRELLIS weights. Images are uploaded to Tripo and credits are charged. An explicit standard-generation request covers one generation per requested asset without repeated credit approval. The estimated cost is 30 credits and the default estimate guard is 100; see the dated estimate and spending limits in the [Tripo guide](docs/TRIPO.en.md).

Prepare `.work/asset.json` from the [quick-start example](QUICKSTART.en.md), then run from the runtime root:

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli generate .work/asset.json --async
```

Inspect the completed local PNGs and deliver the GLB/source. For a requested web preview, complete the [optional installation](INSTALL.md#optional-project-checks-and-viewer), then use `start-viewer.cmd` or `sh start-viewer.sh`.

Example requests after connecting the skill:

> `$3d-assets` Make a wooden treasure chest within 12,000 triangles. Inspect the renders and deliver a GLB.

> `$3d-assets` Change only the grip of this existing sword to burgundy and preserve the previous revision.

> `$3d-assets` Use Tripo3D with these front/back images to make a chest and review the renders.

> `$3d-assets` Rig this character and add a walk. Inspect joint deformation before delivery.

> `$3d-assets` Segment this model locally and name the parts after inspecting their individual renders.

Copying the skill folder alone does not install the runtime. Follow the [skill-link procedure](INSTALL.md#4-connect-the-agent-skill) to use the shared checkout from another project.

For VFX, connect the separate `game-vfx` skill and follow [design and execution](docs/GAME_VFX_DESIGN.en.md). Existing Blender can author the ingredients; procedural fire/lightning work does not require installing TRELLIS weights. Example request: “`$game-vfx` Create a game fire pillar, refine it against references, and show it in a web preview.”

## Recorded validation

The v0.1 implementation has the following recorded results as of **2026-09-15**. These are development records, not mandatory steps for every asset:

- Existing Windows/Linux tests and web builds passed. Actual Blender processing, two types of edits, source preservation, GLB reimport and Godot checks passed on Windows and Linux CI.
- The 19 new clip-comparison tests cover data changes, resampling, interpolation, weights, morphs and CLI/MCP access. A real seven-clip GLB comparison distinguished one intended edit from six preserved clips and unchanged model data. This does not reapprove visual quality.
- One TRELLIS inference using F16 weights at resolution 512 took about 79 seconds on an RTX 5090. This excludes overall processing time and is not a performance guarantee for other hardware. Linux TRELLIS GPU inference remains untested.
- Browser checks loaded the sample chest, sword, AI chest and revisions. Remaining holes/color differences in the AI chest were recorded as a failed visual review.
- Real GeoSAM2 inference preserved 18,984 triangles and produced ten agent-observed names plus unclassified faces. Missed/misclassified regions remain; semantic part quality is a draft. The original mesh was an existing Tripo asset, while this processing used no API.
- SkinTokens inference and five-view static review passed on a 46-bone zombie and an unrelated 80-bone Microsoft Rocketbox adult model. Adult motion remains untested. The zombie's local presets passed a bounded prototype deformation review and floor checks; foot sliding, natural heel-to-toe gait and continuous collisions were not established. See [character validation](docs/CHARACTERS.en.md#review-and-recorded-validation).
- Kimodo generated a real text-conditioned four-second, 120-sample motion on an RTX 5090 and applied it to the existing zombie, preserving its four clips. Despite multiview review and local corrections, hand/head contact and arm deformation remained; visual quality was recorded as failed. See [Kimodo validation](docs/KIMODO.en.md#maintenance-and-recorded-validation).
- Live Tripo single-image generation used 30 credits; segmentation used 40 and yielded 13 inspected/named regions with fused areas/open cuts. Rigging used 25 credits and walking used 10. The remote walk itself penetrated the floor, so visual gait review failed. Live `idle`/`run`, multiview generation and quality/speed comparisons against TRELLIS remain untested. See [Tripo validation](docs/TRIPO.en.md#recorded-validation).

See [CI results](https://github.com/NA-DEGEN-GIRL/3d-asset-auto/actions/workflows/check.yml). Example specs are tracked; generated assets, references and local run records are not. A fresh clone has an empty library.

## Storage and dependencies

`.runtime/` holds portable tools/models, `.assets/` holds assets/jobs, `.work/` holds temporary specs and evidence, and `.secrets/` can hold private keys. They are excluded from Git. Back up `.assets/` separately to preserve generated work.

Core pins are in [bootstrap.py](scripts/bootstrap.py). Optional rigging, segmentation and Kimodo have separate pins/locks documented in their installation guides. Installed hashes/provenance are recorded under `.runtime/installed/`. The default TRELLIS model download is about 16.5 GB, plus tools, archives and output storage; optional models require more space.

- [Blender](https://www.blender.org/): modeling, inspection, rendering and GLB export.
- [trellis.cpp](https://github.com/pwilkin/trellis.cpp), [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [GGUF weights](https://huggingface.co/ilintar/trellis2-gguf): image-to-3D.
- [Tripo](https://developers.tripo3d.ai/en/docs): explicitly selected paid cloud generation.
- [SkinTokens](https://github.com/VAST-AI-Research/SkinTokens), [GeoSAM2](https://github.com/VAST-AI-Research/GeoSAM2): optional local rigging and segmentation.
- [Kimodo](https://github.com/nv-tlabs/kimodo): optional local text-to-human-motion and mapped application.
- [Godot](https://godotengine.org/), [Three.js](https://threejs.org/): optional integration checks.

Tools, model weights and components such as DINOv3/BiRefNet have their own terms. This repository does not redistribute binaries or model weights.

The new `game-vfx` [web example source](examples/game-vfx/LICENSE.txt) is MIT; its [Blender Python helper](.agents/skills/game-vfx/scripts/COPYING.txt) is GPL-3.0-or-later. These scoped notices do not relicense the rest of the repository, generated media or external inputs. Preserve dependency notices and check input-material terms when distributing outputs.
