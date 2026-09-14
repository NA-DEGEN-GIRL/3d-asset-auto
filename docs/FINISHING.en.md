# Surface diagnosis and reusable finishing

[한국어](FINISHING.md) | **English**

Use this guide when processing damages a surface or when adapting a successful finishing method to another asset. The examples generalize the user-supplied necromancer work record. Remeshing, rebaking and weight transfer are conditional authoring choices, not a mandatory pipeline. The agent implements selected operations with [Blender scripts](BLENDER.en.md); automatic retopology or rebaking has not been added to the runtime.

## Find the first damaged stage

Compare the available stages of **raw generation → cleanup/reduction → rigging/weight application → final export** in the same pose, camera and lighting. When needed, compare untextured and material views to separate geometry, normals and color. Find the first bad output and its preceding good input, then reconsider the responsible operation/order. If damage began early, restore that input instead of repeatedly smoothing the latest damaged result.

| Observation | Diagnosis and recovery decision |
| --- | --- |
| Many GLB boundary vertices but a continuous silhouette | Distinguish UV/normal vertex splits from real gaps. If needed, group coincident vertices on a diagnostic copy using a recorded distance appropriate to model scale and intentional gaps. Preserve the original UVs, normals and separate parts; do not deliver the diagnostic welded copy automatically. |
| Fragmentation/cracks after reduction | Compare raw and pre/post-reduction meshes for disconnected patches reduced independently. Reconsider cleanup/reduction order for regions confirmed to be one surface. Do not weld or close nearby independent parts or thin layers indiscriminately. |
| Remaining boundaries assumed to be holes in the body | Locate the connected component containing each boundary and inspect its position, size, material and silhouette. Body holes, intentional openings and floating fragments are different cases. Small components may be functional details or decoration. |
| Good rest shape, bad deformation when bent | Use [rig/weight/deformation diagnosis](QUALITY.en.md#staged-rig-and-motion-diagnosis). Separate skeletal motion from the deformed surface instead of repeatedly cleaning the mesh. |
| Good Blender scene, different GLB | Reimport the final GLB and inspect normals, materials, skinning, morphs, interpolation and exported corrections. A correct source scene does not replace export review. |

Numerical closure is only one kind of evidence. Do not require closed geometry when openings are intentional.

## Adapt a successful recovery

The recorded case improved by restoring the original generated mesh and changing its processing order instead of smoothing the reduced surface. Later boundary classification revised an initial body-hole diagnosis to isolated fragments. Reuse the **diagnosis → chosen operation → preserved information → verification evidence**, not a fixed voxel size or rotation limit.

| Chosen operation | Conditions and checks for another asset |
| --- | --- |
| Restore the last good input | Identify it from hashes, processing history and matching renders. Preserve separate sources for the existing rig, clips and textures. |
| Clean or reconstruct the surface | Repair the responsible connectivity/reduction order. Remesh only when cleanup is insufficient and shape change is acceptable; inspect thin features, silhouettes, decoration and intentional gaps. |
| Transfer textures to the new surface | Bake needed channels when changed topology/UVs invalidate the old layout. A base-color bake does not prove normals/roughness were retained. Inspect missed projection, color bleeding from other parts and seams. |
| Transfer existing skin weights | Use verified surface correspondence when the rig can be retained. Check correspondence distances, unweighted vertices and influential bones, especially near adjacent limbs/equipment. Existing morph targets are not automatically valid after topology changes. |
| Probe joints and correct each clip | Test the intended bending/twisting range, then contacts, deformation and transitions per clip. Shared mesh/weight changes require review even if clip channels are unchanged. |
| Export and verify preservation | Inspect required geometry, materials and motion in the final GLB. Use [clip comparison](BLENDER.en.md#editing-one-clip-and-comparing-preservation) to check the edit scope. Processing success, data preservation and actual quality are separate records. |

Reusable local notes should record input/script/output paths and hashes, selection reasons, model scale/conditions, actual parameters, failed attempts and recovery reasons, review coverage and remaining limits. Compare those conditions before choosing steps for another model. Do not promote one asset's distances, resolution, triangle count, angles or attempt count into universal defaults. Keep models, renders and source scripts local under the existing preservation rules.
