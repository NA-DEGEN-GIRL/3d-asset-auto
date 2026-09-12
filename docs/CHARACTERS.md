# 리깅·애니메이션·부품 분리

완료된 에셋에 **Tripo 리깅, 프리셋 애니메이션, 의미 기반 부품 분리**를 추가하는 선택 기능입니다. 원래 생성기가 TRELLIS·Tripo·import 중 무엇이었는지와 관계없이 사용할 수 있습니다. 기존 생성기의 기본값은 TRELLIS이며, 이 유료 후처리는 사용자가 Tripo 사용을 선택한 요청에만 실행합니다. 이미 요청한 작업은 비용 설정을 다시 묻지 않고 진행합니다.

현재 범위는 이족 리깅과 `idle`·`walk`·`run` 프리셋, 베타 부품 분리입니다. 일반적인 동물·괴물 리깅, 사용자 모션, 여러 클립을 합친 GLB, 자동 리토폴로지·텍스처 재베이크는 제공하지 않습니다. 리깅과 부품 분리는 서로 다른 작업이며 자동으로 함께 실행되지 않습니다.

## 입력과 비용

입력은 라이브러리에 완료된 **정확한 `asset_id`와 부모 `revision`**입니다. 새 작업 결과는 별도 revision에 저장하고 부모의 원본·내보낸 파일·해시는 보존합니다. 부품 분리는 현재 `asset.glb`를 그대로 업로드합니다. 리깅은 같은 모델의 형상·재질을 유지하면서 정면 방향만 Tripo 입력에 맞춘 사본을 업로드하고 원본·준비 사본 해시를 기록합니다. 두 작업 모두 원래 생성 이후의 로컬 수정을 입력에 반영합니다.

| operation | 처리 | 예상 비용 | 주요 제한 |
| --- | --- | --- | --- |
| `rig` | 무료 리깅 가능 검사 후 이족 리깅 | 25크레딧 | `rig_type: "biped"`, `rig_model: "v1.0-20240301"` |
| `animate` | 기존 Tripo 리그에 프리셋 적용 | 10크레딧 | `idle`·`walk`·`run`, 기본 `walk`; revision당 클립 하나 |
| `segment` | 의미 기반 베타 부품 분리 | 40크레딧 | 모델 `v2.0-20260430`, 정확한 이름·재질 보존은 별도 확인 |

가격은 2026-09-12 확인한 값이며 서버의 실제 청구액 보장은 아닙니다. 요청의 `max_credits`는 작업당 로컬 예상 한도이고 기본값은 100입니다. 작은 사용자 예산이 있으면 그 값을 우선합니다. 요청하지 않은 변형·업그레이드·유료 재시도는 한도가 남았다고 자동 실행하지 않습니다. [공식 가격](https://developers.tripo3d.ai/en/pricing).

Tripo 애니메이션을 요청했는데 리그가 없다면, 필요한 리깅 1회와 애니메이션 1회를 순서대로 진행합니다. 예상 합계는 35크레딧입니다. 리깅·애니메이션·부품 분리를 모두 요청했다면 각 1회 기준 합계는 75크레딧입니다. 총예산을 지정받았다면 작업별 기본 한도 외에 누적 예상 비용도 그 범위에 맞춥니다. 입력 준비·검사 실패를 유료 성공으로 간주하지 않습니다.

키는 [Tripo 가이드](TRIPO.md#설치와-키)의 환경 변수 또는 비공개 파일을 사용합니다. 로컬 CUDA와 TRELLIS 가중치는 후처리에 필요하지 않으며 Blender는 필요합니다.

## 리깅

`.work/rig.json`에 완료된 정적 부모 revision을 지정합니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "rig"
}
```

```sh
uv run --no-sync python -m asset_auto.cli tripo-process-plan .work/rig.json
uv run --no-sync python -m asset_auto.cli tripo-process .work/rig.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`tripo-process-plan`은 로컬 읽기 전용이며 업로드·API 호출을 하지 않습니다. 실제 처리 전에 잔액은 `tripo-balance`로 읽을 수 있습니다. `tripo-process`는 무료 리깅 가능 검사를 먼저 실행하고 통과한 입력에 유료 리깅을 적용합니다. 실패 사유가 부적합한 형상이라면 소스 형상·포즈를 고친 정적 revision에서 다시 시작합니다. 무료 검사 통과가 관절 변형 품질을 보장하지는 않습니다. [공식 리깅 검사](https://developers.tripo3d.ai/en/docs/animations-rig-check), [리깅](https://developers.tripo3d.ai/en/docs/animations-rig).

`rig_forward_axis`는 **입력 GLB의 실제 정면**이며 `+x`·`-x`·`+z`·`-z` 중 하나입니다. 기본값 `+z`는 런타임의 정면(Blender -Y → GLB +Z)에 대응합니다. 외부 파일의 정면이 다르면 실제 렌더로 확인해 지정합니다. 모델 이름으로 방향을 추측하거나 여러 yaw 값을 무작정 시도하지 않습니다.

어댑터는 GLB의 Y축 회전으로 입력 정면을 Tripo용 +X에 맞추고, 출력에서는 메시·리그 공통 부모 변환으로 그 회전을 되돌립니다. 스킨·재질·원본 메시를 바꾸는 조작이 아닙니다. 동일한 좀비 모델도 +Z 정면에서는 무료 검사가 거절되고 Y축 +90°만 적용하면 통과했으므로, 거절을 곧바로 형상 결함이라고 판단하지 않습니다.

완료 결과의 새 revision을 기록하고 뼈·가중치 검사와 5방향 렌더를 읽습니다. 작업 제출의 `JOB_ID`와 에셋 revision을 혼동하지 않습니다.

## 애니메이션

우리 런타임에서 완료한 Tripo `rig` 또는 `animate` revision을 부모로 사용합니다. 원격 `rig_task_id`가 필요하므로, 임의로 가져온 리그나 로컬에서 새로 편집한 리그를 그대로 Tripo 애니메이션의 부모로 사용할 수는 없습니다. 정면 방향과 복원 회전은 부모의 리깅 기록을 이어받으며, 같은 원격 리그 ID로 생성한 동작을 원래 방향에 맞춰 출력합니다.

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "operation": "animate",
  "animation": "walk",
  "animate_in_place": true
}
```

위 JSON을 `.work/walk.json`에 저장한 뒤 같은 계획·실행 명령을 사용합니다:

```sh
uv run --no-sync python -m asset_auto.cli tripo-process-plan .work/walk.json
uv run --no-sync python -m asset_auto.cli tripo-process .work/walk.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`animation`은 `idle`·`walk`·`run`, 기본값은 `walk`입니다. `animate_in_place` 기본값은 `true`이며 사용 목적에 따라 명시적으로 바꿀 수 있습니다. 결과는 **선택한 동작 한 클립을 담은 GLB와 새 revision**입니다. 여러 동작을 요청하면 각 결과 revision을 보존하며 하나의 다중 클립 GLB로 합쳤다고 보고하지 않습니다. [공식 애니메이션 적용](https://developers.tripo3d.ai/en/docs/animations-retarget).

전체 5방향 렌더와 `animation-previews.json`이 가리키는 실제 샘플 프레임 PNG를 엽니다. 팔·다리의 체적 붕괴, 관절 꺾임, 발 미끄러짐·교차, 바닥 관통, 요청한 동작을 검사합니다. 파일에 애니메이션 데이터가 존재한다는 사실과 움직임의 품질은 별도 판단입니다.

검사·프리뷰의 샘플 바닥 경고도 확인합니다. 동작을 자동으로 위로 밀어 경고를 숨기지 않으며, 원격 원본과 내보낸 결과를 비교해 생성 품질과 변환 오류를 구분합니다.

자동 미리보기는 최대 8클립에서 클립당 3프레임을 샘플링합니다. import한 전체 클립은 보존되지만 `sampled_clips`보다 `total_clips`가 크면 나머지 클립은 시각 미검토입니다. 3프레임만으로 동작 전체 시간 구간을 검증했다고 보고하지 않습니다.

## 자동 부품 분리와 이름 확인

분리는 리깅 이전의 정적 revision에서 진행하고, 분리·수정 결과를 다시 리깅하는 흐름으로 사용합니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "segment",
  "segmentation_granularity": "balanced"
}
```

`.work/segment.json`에 저장한 뒤 `tripo-process-plan`과 `tripo-process --async`로 실행합니다. `segmentation_granularity`는 `simple`·`balanced`·`detailed`, 기본값은 `balanced`입니다. 실제 서비스의 의미 분리 API를 사용하며, 단순히 서로 떨어진 기하를 나눈 결과를 의미 분리 성공이라고 기록하지 않습니다. [공식 메시 분리](https://developers.tripo3d.ai/en/docs/mesh-segment).

완료 후 `inspection.json`의 실제 오브젝트 목록, 전체 5방향 렌더, `part-previews.json`에 나열된 **개별 부품 PNG**를 검사합니다. 분리 경계·누락·부품 중복·재질 손실을 확인하고 각 이름이 실제로 어떤 부위를 가리키는지 판단합니다. `part_0`를 팔이라고 추측하거나 자동 이름을 정답으로 취급하지 않습니다.

개별 미리보기는 최대 32부품이며 `truncated: true`이면 목록에 없는 부품은 미검토입니다. 추가 확인 없이 전체 부품에 의미 이름을 지정하거나 모두 통과로 보고하지 않습니다.

확인한 정적 부품의 이름은 기존 `edit`로 새 revision에 반영할 수 있습니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_SEGMENTED_REVISION",
  "description": "개별 렌더에서 확인한 왼팔 부품의 이름 지정",
  "changes": [{"part": "actual_mesh_name", "rename": "left_arm"}]
}
```

`actual_mesh_name`을 실제 검사 결과로 바꾸어 `edit`에 제출합니다. 이름 변경은 정확한 부품 하나를 지정해야 하며 `part: "*"`로 할 수 없습니다. 부품 분리가 곧 리깅·가중치·관절용 토폴로지를 만들어 주는 것은 아닙니다. 재질이 사라졌거나 분리 품질이 나쁘면 해당 결함을 기록하고 통과로 승인하지 않습니다.

## 캐릭터 파일 보존과 수정 제약

외부에서 받은 리그·애니메이션 파일을 보존하려면 가져오기를 명시합니다:

```json
{
  "asset_id": "imported-character",
  "provider": "import",
  "asset_kind": "character",
  "source": "/absolute/path/character.glb"
}
```

`asset_kind: "character"`는 `provider: "import"`에서만 사용합니다. 이 경로와 리깅·애니메이션 출력 처리는 뼈·가중치·동작을 보존하며 정적 경로의 계층 평탄화와 자동 감면을 적용하지 않습니다. 높이·바닥 정렬이 필요하면 메시와 armature 전체에 공통 Empty 부모의 스케일·이동을 적용해 상대 바인드·애니메이션 변환을 유지합니다. 후처리는 정적 부모에서 이어진 크기를 사용하고, 캐릭터 import는 `target_height`가 없으면 기존 변환을 보존합니다. 삼각형 예산이 초과되어도 자동 감면으로 리그를 손상시키지 않으며 검사 결과를 보고합니다. 기본 `asset_kind: "static"` 가져오기는 리그가 있는 입력을 계속 거절합니다.

한 메시를 여러 Armature modifier가 동시에 변형하는 `.blend` 입력은 현재 지원하지 않아 거절합니다. 조용히 한 modifier만 내보내는 방식으로 원본 변형을 바꾸지 않습니다.

기존 `edit`는 정적 메시용이며 리그가 있는 부모를 거절합니다. 현재 런타임에는 로컬 리그·가중치·캐릭터 재질 편집 기능이 없습니다. 형상을 고칠 때는 정적 부모를 새 revision으로 수정한 뒤 다시 리깅합니다. 이전 리깅의 원격 ID를 편집된 메시의 ID처럼 재사용하지 않습니다.

## 기록과 복구

`tripo-process`는 부모가 연결된 새 revision을 만들고 manifest의 `remote_processing`에 처리 출처를 기록합니다. 리깅 가능 검사와 유료 작업은 단계별 원격 ID를 저장합니다. 중단되었다면 `job JOB_ID`의 복구 대상과 기록된 원격 작업을 확인하고 다음으로 이어갑니다:

```sh
uv run --no-sync python -m asset_auto.cli resume-tripo-process ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

복구 대상은 **진행하다 중단된 새 revision**이며 입력 부모 revision이 아닙니다. 저장된 단계와 task ID에서 이어가므로 이미 만든 유료 작업을 다시 제출하지 않습니다. 무료 검사만 완료된 단계에서 이어간다면 원래 요청에 포함된 유료 단계가 처음 제출될 수 있습니다. 제출 성공 여부가 불확실하면 자동 POST 재시도를 하지 않고 원격 대시보드와 기록을 대조합니다. 완료한 revision은 덮어쓰지 않습니다.

MCP 대응 도구는 `tripo_process_plan(spec)`, `process_tripo_asset(request)`, `resume_tripo_processing(asset_id, revision)`입니다. 실행·복구가 반환한 job은 `asset_job_status`로 완료 여부를 조회합니다.

## 검토와 현재 검증 범위

기본 전달물은 `source.blend`, `asset.glb`, 검사·관찰 결과입니다. 리깅·애니메이션·분리에 맞는 실제 렌더를 열어 검토한 뒤에만 `review`를 통과로 기록합니다. Godot·Three.js는 대상 프로젝트에 필요하거나 요청받았을 때 선택합니다. 현재 웹 뷰어에는 애니메이션 재생 제어가 없으므로 웹 로드를 움직임 검증으로 대신하지 않습니다.

2026-09-12 현재 확인한 결과:

- **의미 분리:** `cute-mint-zombie-tripo`에 실제 API를 실행해 40크레딧으로 13개 메시 영역·18,984삼각형 결과를 받았습니다. 전체 5방향과 개별 영역 13개 PNG를 검사했고, LLM이 확인한 이름을 새 revision에 지정했습니다. 조립된 모습과 재질·높이 1m는 보존되었습니다.
- **분리 품질 한계:** `left_arm_and_sleeve`, `right_boot_and_calf`처럼 여러 의미 부위가 합쳐진 영역과 열린 절단면이 남습니다. 13개의 독립적·밀폐된 의미 부품이 완성되었다고 판단하지 않습니다. `review.json`의 통과는 조립된 모습과 식별 가능한 영역의 검토 범위이며, `inspection.json`의 `segmentation.semantic_review: pending`은 최초 기록입니다. 최신 관찰은 review sidecar를 읽습니다.
- **리깅:** 입력 정면 보정 후 실제 유료 리깅이 25크레딧으로 완료되었습니다. 좀비 결과는 41뼈·1스킨·가중치가 있는 정점 15,693개·무가중치 정점 0개이며 18,984삼각형·높이 1m입니다. 실제 출력 GLB의 5방향 렌더를 확인해 원래 정면과 재질, 정지 모습 및 리그 존재를 승인했습니다. 관절 동작 전체의 품질 승인은 아닙니다.
- **걷기:** 실제 API 작업이 10크레딧으로 완료되어 리그와 1.875초 `walk` 클립을 담은 GLB를 받았습니다. 정지 5방향과 동작 샘플 3프레임에서 서로 다른 팔·다리 자세와 얼굴·재질 보존을 확인했습니다. 그러나 발이 정지 기준 바닥보다 약 0.32–0.35m 아래로 내려가므로 지면 보행 품질의 시각 검토는 실패로 기록했습니다. 원격 원본에도 같은 수직 편차가 있어 내보내기 오류와 구분했습니다. `idle`·`run`의 실제 API 결과는 미검증입니다.
- **입력 방향·사용량:** 같은 좀비 GLB는 +Z 정면에서 무료 검사가 거절되고 Y축 +90°만 적용하면 통과했습니다. 방향 변환과 출력 복원을 어댑터에 반영했습니다. 이번 후처리의 실제 사용량은 분리 40 + 리깅 25 + 걷기 10 = 75크레딧이며 무료 검사들은 0크레딧입니다. 리깅·애니메이션의 API부터 GLB까지 연결은 확인했지만, 동작의 시각 품질 전체가 통과한 것은 아닙니다.
- **로컬 검증:** 모의 API 테스트, 정적 Blender·Godot smoke, 부품 smoke가 통과했습니다. 캐릭터 Blender smoke에서는 기존 리그와 두 클립, 루트 이동·shape key 기본값 보존, 방향 복원과 샘플 렌더를 확인했습니다. 다중 Armature modifier·거의 0인 가중치 입력의 거절도 검사했습니다. 로컬 테스트와 실서버 동작 품질은 별도입니다.
