# 로컬 Blender 편집과 클립 병합

생성 provider와 편집 방식은 별개입니다. TRELLIS·Tripo·import 어느 모델이든 기존 결과를 로컬에서 수정할 수 있습니다. 정적 소품에는 리그를 추가하지 않고, 문·뚜껑·떠 있는 물체는 object keyframe으로 움직입니다. 몸의 변형이 필요하면 기존 리그를 사용하거나 [SkinTokens 리깅 초안](CHARACTERS.md#리깅)을 만든 뒤 필요한 뼈·가중치·동작을 Blender에서 다듬습니다. LLM이 요청과 실제 모델을 보고 방식을 고릅니다.

`blender-edit`는 완료된 부모의 원본과 LLM이 작성한 Python 스크립트를 복사해 새 revision에서 실행합니다. 임의의 로컬 `bpy` 코드를 실행하므로 샌드박스가 아닙니다. 요청 범위에 맞게 작성·검토한 스크립트를 사용하며 웹 뷰어에는 실행 API가 없습니다. 기존 모델을 수정하는 기능을 새 메시의 TRELLIS/명시적 Tripo 추론 우회에 사용하지 않습니다.

## 스크립트로 편집

외부 object/morph 애니메이션은 먼저 `provider: "import", asset_kind: "animated"`로 가져옵니다. 리그가 있는 모델은 `asset_kind: "character"`를 사용합니다. 기본 `static` import와 정적 `edit`는 리그·동작을 거절하므로 움직이는 결과를 수정할 때는 계속 `blender-edit`를 사용합니다.

실제 객체 이름은 `inspect`로 확인합니다. 아래는 리그 없이 단일 object 소품에 `hover` 클립을 추가하는 형식 예시입니다. 여러 부품을 함께 움직일 때는 공통 root/Empty를 대상으로 삼고 기존 배치를 유지합니다. `.work/hover.py`로 저장합니다:

```python
import bpy
from mathutils import Vector

obj = context.objects[context.parameters["object"]]
rest = obj.location.copy()
scene = bpy.context.scene
frames = max(2, round(scene.render.fps / scene.render.fps_base))
context.new_action(obj, "hover")
for frame, height in [(1, 0.0), (1 + frames // 2, 0.08), (1 + frames, 0.0)]:
    obj.location = rest + Vector((0.0, 0.0, height))
    obj.keyframe_insert(data_path="location", frame=frame)
context.stash_action(obj)
```

`.work/hover.json`에는 정확한 부모 revision, 스크립트 절대 경로, 실제 object 이름을 지정합니다:

```json
{
  "asset_id": "my-prop",
  "revision": "EXACT_PARENT_REVISION",
  "script": "/absolute/runtime/.work/hover.py",
  "description": "기존 소품에 짧은 부유 클립 추가",
  "parameters": {"object": "ACTUAL_OBJECT_NAME"},
  "require_animation": true,
  "preview_clips": ["hover"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli blender-edit .work/hover.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

스크립트는 원본 장면을 수정하며 출력·검사·렌더는 런타임이 담당합니다. `preserve_animations`의 기본값은 `true`로 기존 action 변경·삭제와 출력 클립 누락을 거절합니다. 기존 동작의 속도도 보존하려면 FPS와 `fps_base`를 유지합니다. 기존 클립을 수정하거나 의도적으로 재타이밍하는 요청이면 명시적으로 `false`로 설정하고 남길 클립을 스크립트에서 유지합니다. `require_animation`은 기본 `false`, `preview_clips`는 확인할 실제 이름 최대 8개, `triangle_budget`은 생략하면 부모 값을 사용합니다. 예산 초과로 리그를 자동 감면하지 않습니다.

스크립트에 주입되는 `context`의 주요 계약은 다음과 같습니다. 전체 구현은 [authoring tools](../src/asset_auto/blender_authoring_tools.py)에 있습니다.

| 항목 | 용도 |
| --- | --- |
| `objects`, `armatures` | 실제 scene 이름→object 매핑과 armature 목록 |
| `parameters`, `source`, `output` | 요청 JSON과 복사된 원본·출력의 절대 `Path` |
| `capture_rest()` | 의도적으로 object 기본 변환·morph 기본값을 바꾼 뒤, keyframe 전에 새 정지 상태 기록 |
| `reset_pose()` | 클립을 유지한 채 기록된 object·morph·bone 기본 자세로 복귀 |
| `new_action(owner, name)` | 기존 클립을 보관하고 고유 이름의 action/slot 시작 |
| `stash_action(owner, name=None)` | active action/slot을 내보낼 클립으로 보관 |
| `bake_action(owner, name, frame_start, frame_end)` | 준비한 constraint·리타게팅 결과를 object/pose keyframe으로 bake |

좌표는 Blender Z-up·미터입니다. 뼈의 edit-mode 구조·메시 좌표·가중치·재질 변경에는 `capture_rest()`가 필요하지 않습니다. 임의의 리그 수정과 사용자 동작을 작성할 수 있지만, 학습된 동작 생성이나 자동 리타게팅 해법이 제공되는 것은 아닙니다. constraint는 최종 GLB에서 재현되도록 bake하고 실제 출력의 변형·클립을 확인합니다.

## 여러 동작을 하나의 GLB로

한 에셋에 여러 동작을 요청하면 기본 최종 전달물은 요청한 이름의 클립이 모두 들어 있는 **GLB 하나**입니다. Tripo 등에서 동작별 GLB가 나와도 호환성을 확인해 병합하고 최종 클립 목록을 검사합니다. 사용자가 별도 파일을 요청한 경우에만 나누어 전달하며 중간 revision은 보존합니다.

제작은 [클립별 완성 절차](QUALITY.md#여러-클립의-개별-완성)를 따릅니다. 필요한 참고 자료와 목표를 각 클립에 충분히 마련하고 제작·검토·수정을 이어갑니다. 여러 동작을 압축한 개요 이미지나 병합 성공만으로 전체 요청을 완료 처리하지 않습니다.

기본 로컬 `process`의 `idle`·`walk`·`run`은 부모의 다른 클립을 유지하고 요청한 이름만 교체합니다. 예를 들어 `idle` 결과에 `walk`, 그 결과에 `run`을 적용하면 최종 GLB에 세 클립이 남습니다. 각각의 수정은 새 revision입니다.

이미 별도로 만든 클립은 `merge-animations`로 가져옵니다. 기준 모델의 완료 revision을 고르고, source마다 정확한 revision 또는 외부 GLB 절대 경로 중 하나를 지정합니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_BASE_REVISION",
  "sources": [
    {"asset_id": "my-character", "revision": "EXACT_WALK_REVISION", "clips": ["walk"]},
    {"path": "/absolute/path/compatible-run.glb", "clips": ["run"], "rename": {"run": "sprint"}}
  ],
  "preview_clips": ["walk", "sprint"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli merge-animations .work/merge.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

위 JSON을 `.work/merge.json`에 저장합니다. source는 1–32개이며 `clips`를 생략하면 해당 source의 모든 이름 있는 클립을 선택합니다. `rename`은 원래 이름→최종 이름입니다. 기본 `on_conflict: "error"`는 중복을 거절하며, 의도적으로 같은 이름을 교체할 때만 `"replace"`를 지정합니다.

병합은 기준 모델의 메시·스킨·정지 기하를 유지하고 호환되는 클립 데이터만 가져옵니다. 이름만 비슷한 다른 리그를 자동으로 맞추지 않습니다. 노드 계층·정지 변환·skin/morph 호환성이 맞지 않으면 먼저 `blender-edit` 스크립트에서 실제 뼈 대응과 constraint를 작성·bake한 뒤 병합합니다. 애니메이션 확장 데이터는 지원하지 않으며, 알려지지 않은 동작 의미를 버리고 통과시키지 않습니다.

## 개별 클립 수정과 보존 비교

수정 전에 변경할 클립 이름과 의도한 범위를 정합니다. `blender-edit`는 완료 부모의 해시가 확인된 `source.blend`를 기본 입력으로 사용합니다. 스크립트 안에서 다시 GLB를 가져오거나 다른 FPS로 전체 동작을 다시 만들면 불필요한 재샘플링이 생길 수 있으므로, 해당 원본의 action·시간 기준을 활용합니다. 의도된 기존 클립 수정에만 `preserve_animations: false`를 쓰고 나머지는 스크립트에서도 보존합니다. 이 옵션과 `preview_clips`는 변경 허용 클립 목록을 자동 집행하는 기능이 아닙니다.

최종 GLB 두 개를 비교하는 `compare-animations`는 Blender·GPU·API 호출 없이 즉시 JSON을 반환합니다. 다음 요청에서 `changed_clips`는 의도적으로 추가·수정·제거할 클립이며, 생략하면 모든 기존 클립을 보호 대상으로 비교합니다. 실제 두 입력 어디에도 없는 이름과 중복 선언은 거절합니다. 외부 파일은 절대 경로, 런타임 안의 파일은 루트 기준 경로를 사용할 수 있습니다.

```json
{
  "before": "/absolute/runtime/.assets/my-character/BEFORE_REVISION/asset.glb",
  "after": "/absolute/runtime/.assets/my-character/AFTER_REVISION/asset.glb",
  "changed_clips": ["cast"]
}
```

```sh
uv run --no-sync python -m asset_auto.cli compare-animations .work/compare-clips.json
```

위 JSON을 `.work/compare-clips.json`에 저장합니다. MCP `compare_asset_animations(request)`도 같은 검사를 수행합니다. 결과를 보존할 때는 입력 해시와 함께 로컬 작업 기록에 저장합니다. 원본·revision·review를 변경하지 않으며 비교 실행 성공 자체가 보존 통과는 아닙니다.

- `clips`: 이름별 추가·삭제·변경 여부, 시작/끝/길이(초), 키 수와 시간·보간·변환/morph 데이터 차이. 버퍼 위치나 sparse/interleaved 저장 방식이 달라도 읽어낸 데이터로 비교하며, cubic tangent도 포함합니다.
- `model_context`: 메시·가중치·바인드·노드 기본값/계층·재질·이미지 등 core glTF 모델 데이터 비교. 클립이 같아도 이 문맥이 바뀌면 같은 변형·외관으로 승인하지 않습니다. 지원하지 않는 확장은 `unverified`입니다.
- `preservation_status`: 보호 클립과 모델 문맥이 같으면 `preserved`, 예상 밖의 클립 또는 모델 변경이면 `changed`, 문맥을 확인할 수 없으면 `unverified`, 보호할 기존 클립이 없으면 `no_protected_clips`입니다. 선언한 수정 동작의 품질은 별도 검토합니다.

이 도구는 정확한 데이터 보존 검사입니다. 재샘플링·쿼터니언 표현 변경·노드 순서 변경처럼 결과 동작이 같을 가능성이 있어도 `changed`로 보수적으로 보고할 수 있습니다. 필요한 경우 같은 초 단위 시점의 관절·변형 메시를 Blender에서 비교하고, 변형 정점 대응이 달라졌다면 그에 맞는 비교 방법과 허용 오차를 정합니다. 길이·시작 시각을 먼저 비교하고, 끝 자세나 정규화된 진행률만 맞춰 타이밍 변화를 숨기지 않습니다. 실제 재생·접촉·시각 품질과 `usage.json`의 사용 정책은 이 도구가 판정하지 않습니다.

모델·리그 변경 없이 보정 클립만 바뀌었다면 필요한 클립만 기존 GLB에 명시적으로 병합해 다른 클립의 재내보내기를 피할 수 있습니다. 공유 메시·리그·가중치를 고쳤다면 그 수정이 포함된 모델을 기준으로 삼고 영향받는 동작을 다시 검토합니다. 보존 수치를 맞추려고 수정 전 모델로 되돌리지 않습니다.

## 검토와 중단 복구

기능이 있는 부품이나 중요한 동작은 [품질 명세와 assess](QUALITY.md)로 사용 범위·재생 정책·조건부 수치 검사·핵심 시점 렌더를 추가합니다. 복잡하거나 반복해 실패하는 동작은 [참고 자료](QUALITY.md#동작-참고-자료-활용)에서 목표 자세·접촉 사건을 정리하고 실제 포즈와 비교해 수정합니다. 리그·동작의 결함은 [단계별 진단](QUALITY.md#리그와-동작의-단계별-진단)으로 원본 모션·대상 골격·메시·장비·출력을 비교하고 원인에 맞는 부분을 수정합니다. 병합과 편집은 해시로 묶인 `usage.json`의 의도를 이어받고 품질 증거는 새로 확인합니다.

`authoring-request.json`에 요청·입력의 해시를 묶고 `input.glb`·`input.blend`·`script.py` 또는 병합용 `animation-N.glb` 사본을 보존합니다. 기존 생성 출처를 유지하며 완료 manifest의 `local_processing`에 편집 방식·입력·해시를 기록합니다. 정지 5방향과 `animation-previews.json`의 실제 PNG를 검토합니다. 최대 8클립×3프레임이므로 `preview_clips`로 이번에 바뀐 동작을 선택하고, 나머지는 미검토로 보고합니다. 프리셋의 조밀한 바닥 검사와 달리 임의 스크립트에 자연스러운 동작·접지·연속 충돌 검증이 자동 제공되지는 않습니다.

```sh
uv run --no-sync python -m asset_auto.cli resume-blender-edit ASSET_ID CHILD_REVISION --async
uv run --no-sync python -m asset_auto.cli resume-merge-animations ASSET_ID CHILD_REVISION --async
```

`job`의 실패 원인과 새 자식 revision을 확인해 해당 작업만 재개합니다. 스크립트 실행 후 `authored.blend`와 해시 체크포인트가 저장되었다면 렌더·출력 실패 후에도 스크립트를 다시 실행하지 않습니다. 체크포인트 이전에 중단되었다면 원본 사본에서 실행이 다시 필요할 수 있으므로 스크립트의 외부 부작용을 확인합니다. 입력이나 스크립트를 바꾸려면 기존 복구 요청을 변조하지 말고 새 편집을 시작합니다.

MCP는 `edit_in_blender`, `merge_asset_animations`, `resume_blender_edit`, `resume_animation_merge`를 사용하고 반환 job을 `asset_job_status`로 확인합니다. Godot·뷰어는 대상 프로젝트의 필요나 명시적 미리보기 요청이 있을 때만 사용합니다.
