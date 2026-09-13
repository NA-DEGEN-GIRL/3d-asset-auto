# 리깅·애니메이션·부품 분리

생성 provider와 이후 편집은 독립적이고 기본 편집은 **로컬**입니다. LLM이 모델과 요청을 보고 정적 유지, 리그 없는 object 동작, 기존 리그 활용, SkinTokens 리깅 초안, 사용자 Blender 스크립트 중 필요한 방식을 고릅니다. 이 문서는 `process`의 리깅·기본 동작·GeoSAM2 분리를 다룹니다. 사용자 동작·리그/가중치 수정·클립 병합은 [Blender 편집 가이드](BLENDER.md)를 사용합니다. API 키나 Tripo 크레딧은 필요하지 않고, 모델은 해당 추론이 필요할 때만 설치합니다.

사용자가 Tripo를 명시한 경우에만 `provider: "tripo"` 또는 기존 `tripo-process` 명령을 사용합니다. 설치 실패나 키 보유를 이유로 provider를 자동 전환하지 않습니다. 유료 옵션의 비용·리깅 방향·원격 복구는 [Tripo 가이드](TRIPO.md#리깅애니메이션부품-분리)를 참고합니다.

## 입력과 처리 방식

입력은 완료된 **정확한 `asset_id`와 부모 `revision`**입니다. TRELLIS·Tripo·import 등 원래 생성기와 후처리 provider는 독립적입니다. 결과는 부모·원본·해시를 보존한 새 revision에 저장합니다.

| operation | 기본 로컬 처리 | 필요한 입력 |
| --- | --- | --- |
| `rig` | SkinTokens가 골격·스킨 가중치를 추론하고 원본 메시로 전달 | 완료된 정적 GLB |
| `animate` | Blender의 실제 뼈에 절차적 이족 IK·회전 적용 | 완료된 리그, 확인된 뼈 이름 |
| `segment` | GeoSAM2의 학습된 점 프롬프트 마스크를 메시 면으로 전파 | 정적 GLB의 준비된 뷰, LLM이 지정한 부품별 점 |

SkinTokens는 학습된 리깅 초안이고 GeoSAM2는 학습된 마스크입니다. 수동 뼈 배치나 연결 성분 분할을 이 모델의 추론 결과로 기록하지 않습니다. `process`의 동작은 **절차적 이족 프리셋**입니다. 학습된 사람 모션은 별도 [Kimodo `text-motion`](KIMODO.md)을 사용하고, 사용자 동작·비이족 리그의 수정은 Blender 스크립트로 작성합니다. Kimodo의 관찰한 뼈 대응 기반 적용 외에 범용 자동 리타게팅 해법, 자동 리토폴로지·텍스처 재베이크는 제공하지 않습니다.

설치는 [로컬 후처리 설치](../INSTALL.md#local-postprocessing-on-demand)를 따릅니다. 리깅·분리 추론은 Linux 또는 Windows의 WSL에서 실행하고, 일반 후처리·렌더는 설치된 Blender를 사용합니다. 절차적 동작·Blender 편집에는 추가 AI 모델이 필요 없고, Kimodo 모션을 선택한 경우에만 해당 환경·모델을 설치합니다.

## 리깅

`.work/rig.json`에 정적 부모를 지정합니다. `provider`를 생략하면 로컬입니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "rig"
}
```

```sh
uv run --no-sync python -m asset_auto.cli process-plan .work/rig.json
uv run --no-sync python -m asset_auto.cli process .work/rig.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

SkinTokens는 선택한 현재 GLB를 입력으로 사용하고 `use_transfer`로 예측된 골격·가중치를 원본 메시로 전달합니다. 완료 응답만으로 리깅을 승인하지 않습니다. 출력의 스킨·무가중치 정점·뼈 계층과 실제 5방향 렌더를 읽고 원본 실루엣·재질이 유지되었는지 검사합니다. 추론한 `bone_숫자` 이름에 신체 부위 의미가 있다고 가정하지 않습니다. 필요하면 이 초안을 `blender-edit`로 다듬습니다.

## 애니메이션

로컬 이족 프리셋은 외부에서 가져온 리그나 Tripo 리그도 입력으로 사용할 수 있으며 원격 task ID가 필요하지 않습니다. 지원 입력은 하나의 armature, 모든 메시 정점의 유효한 가중치, 양수·균일 armature 스케일을 갖춘 리그입니다. 몸의 변형이 필요한데 리그가 없을 때 리깅 초안부터 만듭니다. 물체 전체나 분리된 뚜껑만 움직이면 [object keyframe](BLENDER.md#스크립트로-편집)을 사용합니다.

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "operation": "animate",
  "animation": "walk",
  "animate_in_place": true
}
```

`.work/walk.json`에 저장한 뒤 `process-plan`과 `process --async`를 사용합니다. `animation`은 `idle`·`walk`·`run`, 기본값은 `walk`이고 `animate_in_place`는 기본 `true`입니다. 로컬 결과는 **부모의 다른 클립을 유지하고 요청한 프리셋만 추가·교체한 새 GLB revision**입니다. `idle` 결과에 `walk`, 그 결과에 `run`을 추가하면 세 클립을 함께 전달할 수 있습니다. 별도 revision이나 외부 파일의 동작은 [클립 병합](BLENDER.md#여러-동작을-하나의-glb로)을 사용합니다.

알려진 뼈 이름은 자동 연결할 수 있습니다. 이름이 불분명하면 LLM이 검사 결과의 실제 `head_world`·`tail_world`·부모 계층을 읽고 `bone_map`을 작성합니다. 사용자가 뼈를 수동 지정해야 하는 작업으로 돌리지 않으며 숫자 이름으로 의미를 추측하지 않습니다. 다음은 형식 예시이고 값은 실제 이름으로 바꿉니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "operation": "animate",
  "animation": "walk",
  "bone_map": {
    "left_thigh": "observed_left_thigh",
    "left_shin": "observed_left_shin",
    "left_foot": "observed_left_foot",
    "right_thigh": "observed_right_thigh",
    "right_shin": "observed_right_shin",
    "right_foot": "observed_right_foot"
  }
}
```

`walk`·`run`은 양쪽 thigh→shin→foot의 실제 계층이 필요하고 `idle`은 chest가 필요합니다. 추가 역할은 `root`, `pelvis`, `chest`, `head`, 양쪽 `upper_arm`·`forearm`입니다. 이름 매핑과 입력 정면 `rig_forward_axis`를 실제 모델에 맞춥니다. 지원 이름 별칭의 기준은 [동작 worker](../src/asset_auto/blender_motion_worker.py)입니다.

전체 5방향 렌더, `animation-previews.json`의 샘플 PNG, `local-motion.json`의 조밀한 시간 샘플 바닥 검사를 확인합니다. `ground_checks`는 최종 `asset.glb`를 재가져와 검사한 결과이고 `generated_ground_checks`는 중간 출력의 결과입니다. 각 `artifact`의 파일명·단계·SHA256으로 대상을 구분하며 최종 결과는 검사 보고서와 manifest에도 보존됩니다. 절차적 IK의 접지 보정량·관절 도달 범위 제한과 실제 변형을 함께 검토합니다. 발 미끄러짐 방지·발뒤꿈치부터 발끝으로 구르는 동작·연속 자기 충돌 검사는 구현하지 않았으며 접지 보정이 자연스러운 보행을 보증하지는 않습니다.

자동 미리보기는 최대 8클립×3프레임입니다. import한 전체 클립은 보존되지만 `sampled_clips < total_clips`이면 나머지는 시각 미검토입니다. 샘플 프레임만으로 동작 전체 시간 구간을 검증했다고 보고하지 않습니다.

## 자동 부품 분리와 이름 확인

LLM이 준비된 모델 뷰를 보고 부품 이름과 점을 지정하며, GeoSAM2가 마스크를 다른 뷰와 메시 면으로 전파합니다. **최종 사용자에게 점이나 마스크를 그리라고 요구하는 흐름이 아닙니다.** 정적 부모에서 다음을 실행합니다:

```sh
uv run --no-sync python -m asset_auto.cli prepare-segment ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

결과의 `context`는 `.work/segment-contexts/` 아래 `context.json`입니다. 원본 GLB와 12개 뷰·기하 파일의 해시가 묶입니다. LLM은 1024×1024 `color_0000.png`부터 `color_0011.png`를 열어 부품이 잘 보이는 하나의 `segmentation_view`(0–11)를 선택하고, 그 이미지의 픽셀 좌표로 프롬프트를 작성합니다. 다음 좌표는 형식 예시이며 실제 관찰한 점으로 교체합니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "segment",
  "segmentation_context": "/absolute/runtime/.work/segment-contexts/CONTEXT_ID/context.json",
  "segmentation_view": 0,
  "segmentation_parts": [
    {"name": "head", "positive_points": [[512, 240]], "negative_points": [[512, 600]]},
    {"name": "torso", "positive_points": [[512, 540]], "negative_points": [[512, 240]]}
  ]
}
```

`.work/segment.json`에 저장한 뒤 `process-plan`과 `process --async`를 실행합니다. `positive_points`는 포함할 부위, `negative_points`는 제외할 부위이며 모두 선택한 원본 뷰 기준 `[x, y]` 픽셀입니다. 표시 크기가 줄어든 이미지를 보고 지정했다면 원래 1024 해상도로 좌표를 환산합니다. 원본 revision이나 context 파일이 바뀌었다면 다시 준비합니다.

이름을 지정해도 의미 분리 성공은 보장되지 않습니다. 불확실하거나 분류되지 않은 면은 `unclassified`로 남기고 누락시키지 않습니다. 분리 경로는 원본 삼각형·UV·재질·노멀·위치를 보존하며, 예산을 넘더라도 자동 감면하지 않고 보고합니다. 전체 5방향, 검사 보고서, `part-previews.json`의 개별 PNG로 경계·겹침·누락·텍스처 보존을 검사합니다. 연결되지 않은 기하를 나누는 것만으로 의미 부품이 확인되었다고 기록하지 않습니다.

확인한 정적 부품의 이름은 기존 `edit`로 바꿀 수 있습니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_SEGMENTED_REVISION",
  "description": "개별 렌더에서 확인한 왼팔 부품 이름 지정",
  "changes": [{"part": "actual_mesh_name", "rename": "left_arm"}]
}
```

부품 미리보기는 최대 32개입니다. `truncated: true`이면 나머지는 미검토로 보고합니다. 분리가 리깅이나 관절용 토폴로지를 만들어 주지는 않으며 열린 절단면·합쳐진 영역·재질 결함을 실제 결과대로 기록합니다.

## 캐릭터 파일 보존과 수정 제약

외부 리그를 가져오려면 `asset_kind: "character"`를 명시합니다:

```json
{
  "asset_id": "imported-character",
  "provider": "import",
  "asset_kind": "character",
  "source": "/absolute/path/character.glb"
}
```

리그 없는 object/morph 동작 파일에는 `asset_kind: "animated"`를 사용합니다. `character`는 리그, `animated`는 실제 클립이 있어야 합니다. 기본 `static` import는 리그·애니메이션을 거절합니다.

캐릭터 경로는 뼈·가중치·동작을 보존하고 정적 계층 평탄화·자동 감면을 하지 않습니다. 명시적 `target_height`가 있으면 공통 Empty 부모 변환으로 크기·바닥을 맞춥니다. 로컬 캐릭터 후처리는 기존 크기·위치를 유지하며, Tripo 출력의 방향 복원도 공통 부모를 사용합니다. 예산을 초과했다고 리그를 자동 감면하지 않습니다. 한 메시의 다중 Armature modifier 입력은 거절합니다.

정적 `edit`는 리그나 애니메이션이 있는 부모를 거절합니다. 리그·가중치·캐릭터 형상·재질·사용자 동작을 고칠 때는 [blender-edit](BLENDER.md)를 사용합니다. 기존 동작은 기본 보존하며 의도적으로 교체하는 경우 요청과 스크립트에서 그 범위를 지정합니다. 리깅 전에 형상을 크게 고치는 편이 적절하면 정적 부모를 수정한 뒤 새로 리깅할 수도 있습니다.

## 기록과 복구

```sh
uv run --no-sync python -m asset_auto.cli resume-process ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

복구 대상은 중단된 **새 자식 revision**입니다. `job`의 복구 대상과 오류를 확인하고 저장된 요청·provider로 이어갑니다. 로컬 모델 출력이 이미 저장되었다면 해시를 확인해 재사용하며, 추론이 끝나기 전 중단된 경우 계산을 다시 실행할 수 있습니다. source/context를 바꿔 기존 작업을 재개하지 않습니다.

원래 생성 provider는 manifest에 보존하고, 로컬 후처리는 `local_processing`, Tripo 후처리는 `remote_processing`에 별도로 기록합니다. Tripo 원격 단계는 저장된 task ID를 재사용하고 불명확한 POST 결과를 자동 재전송하지 않습니다. 완료 revision은 덮어쓰지 않습니다.

MCP는 `process_plan`, `process_asset`, `prepare_local_segmentation`, `resume_asset_processing`을 사용합니다. 실행·준비·복구의 job은 `asset_job_status`로 조회합니다. `tripo_process_plan`·`process_tripo_asset`·`resume_tripo_processing`은 명시적 유료 옵션으로 유지합니다.

## 검토와 현재 검증 범위

아래 기록은 당시의 제한된 검사 범위입니다. 새 기능·동작의 합격 조건은 [품질 명세](QUALITY.md)에서 사용 목적에 맞게 정합니다. 선택적 `assess`는 반복 경계, 조건부 저활동 구간·루트 이탈과 중요한 시점의 렌더를 추가하지만 접촉·자연스러움·게임 적용을 자동 승인하지 않습니다.

기본 전달물은 `source.blend`, `asset.glb`, 검사·관찰 결과입니다. 실제 렌더를 검토한 범위만 `review`에 기록합니다. 엔진 검사는 프로젝트에 필요한 경우 선택하며 현재 웹 뷰어의 정적 로드를 애니메이션 검증으로 대신하지 않습니다.

로컬 GeoSAM2를 실제 설치·실행해 원본 18,984삼각형을 보존한 결과를 저장했습니다. LLM이 관찰해 지정한 10개 부품 이름과 `unclassified` 1개로 구성되며, 미분류 면은 2,283개(약 12%)입니다. 전체 5방향·개별 11개 이미지를 검토했습니다. 조립된 외관은 보존되었지만 눈·뒤머리·팔의 분류 누락, 작은 피부 조각 오분류, 열린 경계가 남아 **개별 의미 부품 품질은 초안·시각 검토 실패**로 기록했습니다. 마스크 추론 성공을 완전한 의미 분리 승인으로 간주하지 않습니다.

이 테스트 원본은 기존 Tripo 생성 모델이고, 이번 후처리만 로컬 GeoSAM2입니다. 이번 API 사용량은 0이며 원래 생성 출처와 `local_processing`을 구분합니다. 정적 분리의 실제 Blender 파이프라인 smoke에서 삼각형·UV·재질·노멀·변환 보존과 예산 초과 시 비감면도 확인했습니다.

SkinTokens도 같은 좀비 모델에서 실제 추론을 완료했습니다. 46뼈·가중치가 있는 정점 15,741개·무가중치 정점 0개를 확인했고, 원본 해시와 전체 5방향 정지 렌더에서 외관 보존을 확인했습니다.

이 리그에 로컬 `idle`·`walk`·`run`을 각각 생성하고 최종 GLB의 동작 PNG 9개를 검토했습니다. 몸이 크게 뭉개지거나 텍스처가 사라지는 현상 없이 **프로토타입 외관·변형 범위에서 통과**했습니다. 걷기·달리기는 짧은 보폭과 대체로 평평한 발바닥을 사용하는 기본 동작입니다. 자연스러운 보행이나 전체 시간 구간의 자기 충돌·발 미끄러짐 부재를 확인한 결과는 아닙니다.

최종 GLB를 재가져와 작성 프레임과 반 프레임마다 검사했습니다. `idle`·`walk`·`run`의 121·61·41개 샘플에서 최대 바닥 침범은 각각 0·0.128·0.661mm로 이 모델의 허용치 2mm 이내였습니다. 정지 정점 위치 최대 편차는 약 2.58×10⁻⁷m, 정규화한 스킨 가중치의 최대 L1 편차는 약 3.73×10⁻⁸이었고 재질·이미지 바이트도 보존했습니다. 원본은 기존 Tripo 모델이지만 이번 리깅·세 동작 생성에는 API를 사용하지 않았습니다.

Tripo와 무관한 Microsoft Rocketbox의 MIT 성인 정적 모델도 SkinTokens 리깅을 완료했습니다. 원본 해시를 보존하고 7,440삼각형·약 1.8m·80뼈·가중치 정점 4,803개·무가중치 정점 0개를 확인했습니다. 전체 5방향 정지 렌더의 외관과 숫자 검사는 통과했고 성인 모델의 동작은 아직 실행하지 않았습니다.

Windows 전체 단위 검사와 Linux 프로세스 수명 검사, Ruff·웹 빌드, 정적 Blender/Godot·캐릭터·로컬 동작·로컬 분리 smoke가 통과했습니다. 설치·GPU 준비·모의 테스트·실제 추론·시각 품질을 각각 구분해 보고합니다.

기존 Tripo에서는 단일 이미지 생성 30크레딧, 부품 분리 40, 리깅 25, 걷기 10을 실제 실행했습니다. 분리된 13영역은 전체·개별 렌더로 확인해 이름을 지정했지만 합쳐진 영역과 열린 면이 남습니다. 걷기의 원격 원본에도 바닥 관통이 있어 지면 보행 품질 검토는 실패했습니다. 자세한 결과는 [Tripo 검증 기록](TRIPO.md#확인된-범위)을 참고합니다.
