# 선택적 Tripo3D API

**한국어** | [English](TRIPO.en.md)

기본 생성기는 로컬 TRELLIS.2입니다. **사용자가 Tripo/Tripo3D 사용을 명시한 작업에만** `provider: "tripo"`를 선택합니다. 키가 있거나 GPU가 부족하거나 멀티뷰 이미지가 있다는 이유로 자동 전환하지 않습니다. Tripo는 입력 이미지를 외부 서비스로 업로드하고 유료 크레딧을 사용합니다.

이미지 생성 어댑터는 단일 이미지 또는 정면 포함 2–4방향 이미지로 정적 메시를 생성한 뒤, Blender 후처리·5방향 렌더·GLB 출력으로 연결합니다. **Tripo 생성 선택이 Tripo 편집 선택을 뜻하지는 않습니다.** 이후에는 [로컬 Blender 편집·클립 병합](BLENDER.md)이나 [리깅 초안·부품 분리](CHARACTERS.md)를 사용하고, 아래 유료 후처리는 별도로 명시한 경우에만 선택합니다. Godot나 웹 뷰어는 자동 실행하지 않습니다. 텍스트 직접 생성과 고급 생성 품질 옵션은 아직 제공하지 않습니다.

“Tripo로 만들어 줘”라는 요청이면 **요청한 에셋마다 표준 생성 1회**를 별도 크레딧 확인 없이 진행합니다. `tripo` 설정과 `max_credits`는 생략할 수 있으며 기본 예상 비용 한도는 작업당 100크레딧입니다. 표준 생성의 예상 비용은 30크레딧이며, 한도 100이 재시도 예산을 뜻하지는 않습니다. 단일 이미지와 멀티뷰 테스트를 둘 다 요청했다면 각각 1회가 요청 범위입니다. 사용자가 지정한 더 작은 예산은 우선하며, 요청하지 않은 추가 변형·품질 업그레이드·유료 재생성까지 포함하지는 않습니다.

## 설치와 키

이미 기본 시스템을 설치했다면 도구를 다시 받을 필요가 없습니다. Tripo 전용 설치는 [INSTALL의 Tripo 절차](../INSTALL.md#optional-tripo-cloud-provider)를 따릅니다. Python과 Blender가 필요하며, 로컬 NVIDIA GPU·CUDA·TRELLIS 가중치는 필요하지 않습니다.

아래 중 하나로 키를 설정합니다:

- 프로세스 환경 변수 `TRIPO_API_KEY`.
- 런타임 루트의 `.secrets/tripo_api_key` 파일에 **키만** 저장. `.secrets/`는 Git에서 제외됩니다.
- 다른 비공개 파일을 쓰려면 환경 변수 `TRIPO_API_KEY_FILE`에 그 절대 경로 지정.

키는 로컬 편집기나 비밀 관리 도구로 입력하고, 채팅·요청 JSON·명령 인자·로그·공유 MCP 설정에 붙여 넣지 않습니다. CLI/MCP 실행 환경이 해당 환경 변수 또는 파일을 읽을 수 있어야 합니다. `.env` 파일이 자동 로드된다고 가정하지 않습니다.

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli tripo-balance
```

`doctor`는 로컬 준비 상태를 확인합니다. `tripo-balance`는 API의 계정 잔액을 읽으며 생성 작업을 만들지 않습니다. 키가 아직 없으면 로컬 설정·명세 검증까지만 진행하고 실제 API 테스트는 미완료로 보고합니다.

## 지원 입력과 비용

| 항목 | 현재 어댑터 |
| --- | --- |
| 모델 | `v3.1-20260211` 지원, 기본값 |
| 단일 이미지 | `image`에 로컬 PNG/JPG/JPEG 파일 경로 |
| 멀티뷰 | `views`에 `front` 필수, `left`·`back`·`right` 중 1개 이상 추가 |
| 업로드 파일 | 이미지별 최대 20 MB, WebP 미지원 |
| 출력 설정 | 표준 geometry, texture 및 PBR 사용, 원본 이미지 기준 texture alignment |
| 시드 | 요청의 `seed`를 모델·텍스처 시드에 사용 |
| 비용 계획 | 단일 이미지·멀티뷰 모두 생성 1회 예상 30크레딧 |
| 비용 가드 | 선택 정수 `tripo.max_credits` (1–100000), 생략 시 100; 로컬 예상치와 비교 |

예상 30크레딧은 **2026-09-12 확인한 기본 생성 가격**이며 모델·서비스 가격이 바뀔 수 있습니다. `max_credits`는 한도를 넘는 예상 비용의 로컬 제출을 막는 값입니다. **Tripo 서버가 집행하는 지출 상한이나 실제 청구액 보장은 아닙니다.** 계정 전체 사용량이나 다른 작업의 지출도 제한하지 않습니다. [공식 가격](https://developers.tripo3d.ai/en/pricing).

멀티뷰는 같은 물체를 같은 디자인·색·비율로 보여주는 개별 이미지여야 합니다. 정면·좌측·후면·우측 이름에 맞춰 지정하며 콜라주 한 장을 여러 뷰로 취급하지 않습니다. 누락한 뷰를 다른 뷰의 복제로 채우지 않습니다. 현재 입력 형식은 [공식 파일 업로드](https://developers.tripo3d.ai/en/docs/files), [단일 이미지 생성](https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard), [멀티뷰 생성](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard)을 기준으로 제한했습니다.

## 요청 예시

사용자 요청 예:

> `$3d-assets` Tripo3D로 이 정면·후면 이미지의 상자를 만들어 주고 모델 렌더를 직접 검사해 줘.

단일 이미지 요청을 `.work/tripo.json`에 저장합니다. `image`는 실제 존재하는 파일의 절대 경로로 바꿉니다:

```json
{
  "asset_id": "chest-tripo",
  "provider": "tripo",
  "image": "/absolute/path/chest.png",
  "prompt": "75cm 나무 보물상자",
  "triangle_budget": 12000,
  "target_height": 0.75,
  "seed": 42
}
```

멀티뷰에서는 `image`를 없애고 `views`를 사용합니다. 앞·뒤 두 장만 있어도 됩니다:

```json
{
  "asset_id": "chest-tripo-multiview",
  "provider": "tripo",
  "views": {
    "front": "/absolute/path/chest-front.png",
    "back": "/absolute/path/chest-back.png"
  },
  "triangle_budget": 12000,
  "target_height": 0.75,
  "seed": 42
}
```

두 예시는 Tripo 기본 설정인 `model: "v3.1-20260211"`, `max_credits: 100`을 자동으로 사용합니다. 사용자가 다른 한도를 지정했다면 `tripo: {"max_credits": 20}`처럼 해당 값을 넣습니다. 예상 30크레딧보다 작으면 제출이 거절되며 임의로 올리지 않습니다.

`image`와 `views`는 함께 사용할 수 없습니다. `prompt`는 출처·의도 기록이며 이미지 생성이나 Tripo의 text-to-model 호출이 아닙니다. TRELLIS용 `resolution`·`atlas`는 Tripo 품질 설정으로 사용하지 않습니다. 로컬 `triangle_budget`은 Blender 후처리에 적용하므로 감면 후 실루엣과 텍스처를 다시 확인합니다.

## 계획 → 제출 → 검토

저장소 루트에서 실행합니다:

```sh
uv run --no-sync python -m asset_auto.cli tripo-plan .work/tripo.json
uv run --no-sync python -m asset_auto.cli tripo-balance
uv run --no-sync python -m asset_auto.cli generate .work/tripo.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`tripo-plan`은 **로컬 읽기 전용**으로 입력·모델·예상 비용을 확인하며 업로드나 API 호출을 하지 않습니다. LLM은 계획·잔액을 내부적으로 확인한 다음 `generate`로 이미지를 업로드하고 유료 작업을 제출합니다. 명시적인 Tripo 요청의 기본 범위에서는 `max_credits` 입력이나 크레딧 승인을 다시 물으며 멈추지 않습니다.

`JOB_ID`를 실제 반환값으로 바꾸어 완료까지 조회합니다. 느리다는 이유로 같은 생성 요청을 다시 제출하지 않습니다. 완료 후 [빠른 가이드의 렌더 검토](../QUICKSTART.md#4-llm이-모델-확인)를 따라 수치와 5방향 PNG를 검사하고 `review`로 관찰 내용을 기록합니다. Tripo를 썼다는 사실만으로 더 좋은 품질이나 빠른 처리를 보장하지 않습니다.

## 중단과 복구

revision의 `tripo.json`에는 원격 작업 ID와 진행·출처 기록이 저장됩니다. 로컬 worker가 사라져도 원격 생성은 계속될 수 있습니다. 완료 manifest가 없는 revision은 라이브러리에 나타나지 않으므로 `job JOB_ID`를 조회합니다. 원격 제출 전에 저장한 `recovery.asset_id`와 `recovery.revision`이 실패·중단 후에도 남으며, MCP의 `asset_job_status`에서도 읽을 수 있습니다. 동기 `generate` 오류에도 같은 ID가 포함됩니다. `recovery`는 revision의 위치이며 유료 작업이 이미 제출되었다는 증거는 아닙니다. 실제 resume에는 기록된 원격 task ID가 필요합니다.

**알려진 task ID가 있는 미완료 revision**은 다음으로 이어갑니다:

```sh
uv run --no-sync python -m asset_auto.cli resume-tripo ASSET_ID REVISION --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

이 명령은 기존 원격 작업을 조회하고 결과 다운로드·Blender 처리를 이어갑니다. 새 유료 task를 만들지 않습니다. 완료 revision은 덮어쓰지 않으며 정적 수정은 `edit`, 리그·동작·더 넓은 수정은 [blender-edit](BLENDER.md)로 새 revision에 저장합니다. 이 로컬 편집에는 Tripo 재호출이 필요하지 않습니다.

제출 요청의 응답을 받지 못해 **서버가 작업을 만들었는지 모르는 상태**라면 자동 POST 재시도를 하지 않습니다. Tripo 대시보드에서 생성 여부·청구 기록을 확인합니다. 알려진 task ID가 없는 상태에서 `generate`를 반복하면 중복 결제가 생길 수 있습니다. 원격 task 자체가 실패했거나 취소되었다면 resume이 성공 상태로 바꾸지는 못합니다. 새 생성은 별도 지출 판단입니다. [공식 작업 조회](https://developers.tripo3d.ai/en/docs/task-query), [계정 조회](https://developers.tripo3d.ai/en/docs/account).

## 리깅·애니메이션·부품 분리

일반 `process`는 로컬이므로, 사용자가 Tripo를 선택했다면 요청에 `provider: "tripo"`를 명시합니다:

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_STATIC_REVISION",
  "operation": "rig",
  "provider": "tripo"
}
```

```sh
uv run --no-sync python -m asset_auto.cli process-plan .work/tripo-rig.json
uv run --no-sync python -m asset_auto.cli process .work/tripo-rig.json --async
```

위 JSON을 `.work/tripo-rig.json`에 저장하고 실행합니다. 기존 `tripo-process-plan`·`tripo-process`는 명시적 Tripo 전용 별칭으로 유지하며, `provider: "local"` 요청을 유료로 바꾸지는 않습니다. 후처리의 `max_credits`는 최상위 선택 필드이고 기본값 100입니다. 요청한 단계는 재승인 없이 진행하되 작은 사용자 예산을 우선합니다.

| operation | 현재 지원 | 예상 비용 |
| --- | --- | --- |
| `rig` | 무료 가능 검사 → `biped`, `v1.0-20240301` 리깅 | 25크레딧 |
| `animate` | 우리 런타임의 Tripo rig/animate 부모, `idle`·`walk`·`run` 한 클립 | 10크레딧 |
| `segment` | `v2.0-20260430` 베타, `segmentation_granularity` simple/balanced/detailed | 40크레딧 |

리깅·분리는 정확한 완료 정적 부모를 사용합니다. 분리는 현재 GLB를 그대로 보내며, 리깅은 현재 형상·재질을 유지한 채 입력 정면을 Tripo +X로 회전한 사본을 업로드합니다. `rig_forward_axis`는 실제 입력 GLB의 정면(+x/-x/+z/-z, 기본 +z)이며, 렌더에서 확인합니다. 원본·준비 사본 해시를 기록하고 출력에서는 메시·스킨 공통 부모 변환으로 방향을 복원합니다. 같은 좀비 모델의 +Z 정면 거절이 Y축 +90°만으로 통과한 실측을 반영한 처리입니다.

Tripo 애니메이션은 부모의 `rig_task_id`와 방향 기록을 이어받습니다. 외부 import 리그를 그대로 사용할 수 있는 로컬 동작과 달리, 이 원격 ID가 없으면 먼저 Tripo로 리깅해야 합니다. 애니메이션 요청에 필요한 리깅+동작 각 1회 예상 합계는 35크레딧입니다. 세 기능을 모두 요청하면 각 1회 합계 75이며, 한도가 남았다는 이유로 추가 유료 변형·재시도를 실행하지 않습니다.

이 유료 어댑터는 요청한 한 클립을 반환합니다. 기존 동작과 함께 전달하려면 호환성을 확인하고 로컬 `merge-animations`로 합칩니다. 로컬 프리셋과 사용자 스크립트는 이 원격 task ID 없이도 사용할 수 있습니다.

Tripo 분리는 로컬 GeoSAM2용 context·점 프롬프트를 받지 않습니다. 결과의 자동 이름을 믿지 말고 개별 렌더로 확인해 `edit`/`rename`합니다. 분리 경계·동작 샘플·파일 보존 규칙은 [공통 후처리 가이드](CHARACTERS.md)를 따릅니다. [공식 리깅 검사](https://developers.tripo3d.ai/en/docs/animations-rig-check), [리깅](https://developers.tripo3d.ai/en/docs/animations-rig), [동작 적용](https://developers.tripo3d.ai/en/docs/animations-retarget), [메시 분리](https://developers.tripo3d.ai/en/docs/mesh-segment).

중단된 자식은 `resume-process ASSET_ID REVISION --async` 또는 `resume-tripo-process`로 저장된 단계부터 이어갑니다. 무료 검사만 끝났다면 원래 요청의 유료 단계가 처음 제출될 수 있지만 이미 알려진 유료 task를 중복 생성하지 않습니다. 제출 결과가 불명확한 단계는 대시보드와 대조합니다. MCP 전용 도구는 `tripo_process_plan`, `process_tripo_asset`, `resume_tripo_processing`입니다.

## 확인된 범위

로컬 모의 API 테스트와 Blender 4.5.13·Godot 4.7.2를 사용하는 유지보수 smoke 검사는 통과했습니다. 이 smoke 검사는 공통 처리 파이프라인을 검사하며 유료 Tripo API 성공을 뜻하지 않습니다. Godot도 실제 에셋마다 필수인 검사가 아닙니다.

단일 이미지로 `cute-mint-zombie-tripo`를 생성해 업로드 → 원격 완료 → GLB 다운로드 → Blender 처리를 확인했으며 실제 사용량은 30크레딧이었습니다. 다음 후처리는 Tripo에서 별도로 확인한 결과이며 로컬 모델의 검증은 아닙니다:

- 분리 40크레딧: 13영역·18,984삼각형, 전체 5방향과 13개별 렌더 검토 후 새 revision에 이름 지정. 합쳐진 팔/옷·부츠/종아리 영역과 열린 절단면이 남아 독립적인 밀폐 부품 13개가 완성된 상태는 아닙니다.
- 리깅 25크레딧: 41뼈·1스킨·무가중치 정점 0개, 원래 정면·재질·높이 1m와 정지 모습 검토 통과.
- 걷기 10크레딧: 1.875초 클립 출력과 샘플 자세를 확인했지만, 원격 원본에도 발이 바닥보다 약 0.32–0.35m 아래로 내려가 지면 보행 품질 검토는 실패했습니다. API 성공과 시각 품질 승인을 구분합니다.

후처리 사용량은 합계 75크레딧이며 무료 검사들은 0이었습니다. 관찰 기록은 각 revision의 `review.json`에 남고, inspection의 최초 `semantic_review: pending`과 구분합니다. `idle`·`run` 실서버 결과는 미검증입니다.

멀티뷰 실제 생성과 TRELLIS 대비 품질·속도 비교는 아직 미검증입니다. 로컬 테스트·원격 작업 성공·시각 품질을 구분해 보고하며, 사용자가 실제 테스트를 요청한 방식마다 1회로 확인합니다.
