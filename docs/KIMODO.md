# Kimodo 로컬 텍스트 모션

**한국어** | [English](KIMODO.en.md)

[공식 Kimodo](https://github.com/nv-tlabs/kimodo)의 `Kimodo-SOMA-RP-v1.1`로 사람 동작의 3D 초안을 생성하고, 관찰한 뼈 대응으로 이미 리깅된 에셋에 적용합니다. Kimodo가 자연스러움을 보장하지는 않으며, LLM은 참고 목표를 기준으로 Blender에서 캐릭터와 용도에 맞게 완성합니다. 메시 생성기와 독립적이며 Tripo API를 사용하지 않습니다. 새 메시 생성 기본값은 계속 TRELLIS.2입니다.

Kimodo는 캐릭터 메시를 자동 리깅하지 않습니다. 뼈와 스킨 가중치는 기존 리그 또는 [SkinTokens 리깅](CHARACTERS.md#리깅)으로 먼저 준비하고, 생성된 모션을 그 리그에 적용합니다.

**사용자가 Kimodo를 명시적으로 선택한 작업에서만 설치·추론합니다.** 일반 애니메이션 요청, 모델 설치 여부나 Blender 편집 실패를 근거로 자동 선택하지 않습니다. 일반 작업은 기존 클립·리그와 [Blender 편집](BLENDER.md)·`process`의 `idle`·`walk`·`run` 프리셋 중 용도에 맞게 처리합니다. 프리셋은 절차적 동작이며 Kimodo 추론과 구분합니다.

한 번 선택한 Kimodo 작업은 요청 범위 안에서 설치·생성·적용·검토를 매번 재확인하지 않고 진행합니다. 이미 생성한 Kimodo 클립의 접지·체형 보정은 Blender에서 수행할 수 있으며 새 추론을 요구하지 않습니다.

## 선택한 Kimodo 작업의 제작 흐름

사용자가 Kimodo를 선택한 인간형 캐릭터에는 **참고 검토 → 리그 확인 → Kimodo 초안 → Blender 보정 → 최종 비교** 흐름을 우선 검토합니다. 이는 선택된 작업의 제작 방식이며 일반 인간형 애니메이션의 자동 provider 선택 규칙이 아닙니다.

1. **클립별 참고와 표현 목표를 정합니다.** 초기 설계에서 참고 영상을 검토하고 [동작 참고 가이드](MOTION_REFERENCES.md#참고를-실제-수정으로-연결하기)에 따라 채택할 자세·궤적·부위 간 선후 관계·리듬을 고릅니다. 충분한 기존 자료를 재사용하고, 부족한 자료만 작업의 허용 범위에서 보완합니다.
2. **대상 리그를 확인하고 기본 동작을 생성합니다.** 필요한 관절 범위와 변형을 [사전 검사](QUALITY.md#리그와-동작의-단계별-진단)하고 실제 뼈 대응을 정한 뒤, `text-motion-plan` → `text-motion`으로 초안을 만듭니다. 생성 원본을 보존하고 원본부터 목표와 다른 부분과 대상 골격·메시·장비에 옮기면서 달라진 부분을 비교합니다. 적합한 기존 Kimodo 소스는 재사용하며 새 추론이 필요한지는 원본의 문제와 작업 예산으로 판단합니다.
3. **Blender에서 캐릭터에 맞게 완성합니다.** `blender-edit`로 자세·궤적·타이밍·접촉·관절 변형의 확인된 원인을 수정합니다. 원본 의미가 맞으면 추론을 유지하고 매핑·제약·리그·가중치 등 적용 단계의 문제를 고칩니다. 관통을 피하려고 목표한 움직임을 지나치게 줄이는 보정도 [표현 손실의 회귀](QUALITY.md#결함-수정과-종료-판단)로 재검사합니다.
4. **최종 GLB를 클립별로 비교하고 마무리합니다.** [참고와 대응하는 사건](MOTION_REFERENCES.md#참고와-최종-동작-비교)을 나란히 비교하고 같은 순간을 여러 방향에서 봅니다. 전환·리듬과 기술적 안정성·표현 목표를 각각 확인하며, 미충족 항목은 실제 작업 예산 안에서 수정·새 출력·재검토합니다. 해결하지 못한 클립은 차이를 명시해 미완료로 남깁니다. 완료한 클립은 보존을 확인해 하나의 최종 GLB에 모읍니다.

현재 어댑터의 추론 입력은 텍스트입니다. 이미지·영상은 LLM의 프롬프트 구체화와 Blender 수정 판단에 쓰며, Kimodo에 영상을 넣거나 자동으로 모션을 추출하는 기능을 뜻하지 않습니다.

## 필요한 때 설치

Linux 또는 Windows WSL2, NVIDIA CUDA GPU와 C++ 컴파일러가 필요합니다. 공식 안내상 텍스트 인코더를 포함한 GPU 실행은 약 17GB VRAM을 사용합니다. 이 어댑터는 모델과 인코더를 같은 GPU에서 실행하며 CPU 인코더·원격 인코더 자동 전환을 제공하지 않습니다. 메인 `.venv`와 분리해 설치합니다.

```sh
uv run --no-sync python scripts/bootstrap_kimodo.py
uv run --no-sync python -m asset_auto.cli doctor
```

Windows 기본 WSL 배포판은 `Ubuntu-24.04`이며 `--wsl-distribution`으로 바꿀 수 있습니다. 선택한 Linux 사용자 환경에 `uv`, `g++`가 있어야 합니다. 설치 도중 `#`가 포함된 체크아웃 경로의 빌드 문제를 피하도록 고정 소스를 Linux 임시 디렉터리에서 wheel로 빌드합니다. 기존 프로젝트 파일이나 시스템 Python을 교체하지 않습니다.

텍스트 인코더는 [Meta-Llama-3-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) 기반 LLM2Vec입니다. 해당 모델 접근이 허용된 Hugging Face 계정의 읽기 토큰을 **`<runtime-root>/.secrets/hf_token`**에 키만 저장하거나 기존 HF 로그인/`HF_TOKEN`을 사용합니다. 접근 신청·약관 동의가 필요한 계정은 Hugging Face에서 처리합니다. 키를 요청 JSON, 로그, Git이나 채팅에 넣지 않습니다. 이후 추론은 고정된 로컬 파일만 사용하며 외부 인코더 서비스를 탐색하지 않습니다.

계정의 모델 승인과 토큰 권한은 별개입니다. Fine-grained 토큰으로 403 `public gated repositories` 오류가 나면 [HF 토큰 설정](https://huggingface.co/settings/tokens)의 `Read access to contents of all public gated repos you can access`를 켭니다. 기존 토큰 권한을 수정했다면 키를 다시 복사할 필요는 없습니다. 설치 도구는 이 오류를 연결 오류와 구분하고, 다른 모델 다운로드를 계속한 뒤 재실행 방법을 안내합니다.

`--skip-models`는 환경만 준비합니다. `environment_ready`와 CUDA 확인은 전체 모델 준비나 추론 성공이 아닙니다. 다운로드가 완료되어야 `doctor.animation.text_to_motion.available`이 참이 됩니다. 401/403이면 모델 접근 권한을 해결한 뒤 같은 설치 명령을 실행하면 됩니다. 이미 받은 모델 파일은 재사용합니다.

소스·4개 모델 revision은 [kimodo_runtime.py](../src/asset_auto/kimodo_runtime.py), Python/빌드 절차는 [bootstrap_kimodo.py](../scripts/bootstrap_kimodo.py), 전체 Python 의존성은 [requirements-linux.lock](../scripts/kimodo/requirements-linux.lock)에 고정합니다. `.runtime/installed/kimodo.json`은 모델 파일 해시·크기와 환경 정보를 기록합니다. 코드·가중치·Llama 기반 인코더에는 각 출처의 사용 조건이 적용되며 이 저장소는 가중치를 재배포하지 않습니다.

## 기존 리그에 적용

먼저 `inspect`의 실제 뼈 위치·계층과 렌더에서 몸의 방향을 확인합니다. `bone_map` 키는 **SOMA 이름**, 값은 **현재 Blender 리그의 실제 이름**입니다. 아래는 형식 예시이며 다른 리그에 그대로 복사할 대응표가 아닙니다. 번호만 보고 부위를 추정하지 않습니다.

```json
{
  "asset_id": "my-character",
  "revision": "EXACT_RIGGED_REVISION",
  "prompt": "A person stands and waves hello with their right hand.",
  "clip_name": "wave_hello",
  "duration_seconds": 4,
  "seed": 42,
  "diffusion_steps": 100,
  "forward_axis": "-y",
  "in_place": false,
  "bone_map": {
    "Hips": "pelvis", "Chest": "chest", "Head": "head",
    "LeftArm": "left_upper_arm", "LeftForeArm": "left_forearm", "LeftHand": "left_hand",
    "RightArm": "right_upper_arm", "RightForeArm": "right_forearm", "RightHand": "right_hand",
    "LeftLeg": "left_thigh", "LeftShin": "left_shin", "LeftFoot": "left_foot",
    "RightLeg": "right_thigh", "RightShin": "right_shin", "RightFoot": "right_foot"
  }
}
```

```sh
uv run --no-sync python -m asset_auto.cli text-motion-plan .work/motion.json
uv run --no-sync python -m asset_auto.cli text-motion .work/motion.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`text-motion-plan`은 유료 호출·모델 추론 없이 원본 해시, 모델 준비, 필수 대응·계층, 보존할 클립, 대응되지 않은 뼈를 확인합니다. MCP는 `text_motion_plan`, `generate_text_motion`, `resume_text_motion`이며 생성·재개는 작업 ID를 반환합니다. 다른 프로젝트에서는 [스킬 wrapper](../.agents/skills/3d-assets/references/runtime.md)를 사용합니다.

입력은 하나의 humanoid armature와 유효한 스킨 가중치를 가진 완료 revision입니다. 위 15개 SOMA 역할은 필수이며 관찰한 척추·목·어깨·발끝 등의 대응을 추가할 수 있습니다. 대상 뼈 중복, 누락·역전된 계층, 기존 클립 이름 충돌은 거절합니다. Blender 적용은 양수·균일 armature 스케일과 기본 상속 변환을 전제로 하며 활성 제약은 먼저 정리하거나 bake해야 합니다.

`forward_axis`는 **Blender Z-up 월드에서 모델이 바라보는 방향**(`-y` 기본, `+y`, `+x`, `-x`)입니다. 기존 `process`의 GLB Y-up `rig_forward_axis`와 좌표 규약이 다릅니다. 모션 길이는 2–10초, seed는 0–2147483647, diffusion steps는 10–500입니다. 출력은 현재 Blender 시간 기준으로 변환하여 기존 클립 속도를 유지합니다. 새 클립은 시작·끝 자세를 보존하도록 길이를 가장 가까운 scene 프레임 수로 맞추며 최대 반 프레임의 길이 차이를 `retarget-map.json`에 기록합니다.

`in_place: true`는 루트의 수평 이동을 제거합니다. 수직 이동과 회전은 유지하며 접지 보정·제자리 보행 생성이나 루프 변환을 뜻하지 않습니다. 이동·반복 정책은 [usage 명세](QUALITY.md)에 별도로 기록합니다.

## 적용·검토·복구

SOMA 전역 회전을 대상 기준 자세와 뼈 계층에 맞춰 전달하고, 다리 길이 비로 이동량을 조정합니다. 손가락·말단 대응이 없으면 해당 뼈에는 별도 모션을 생성하지 않습니다. SOMA가 내부 30관절을 77관절로 내보내더라도 정교한 손가락 표현을 학습·검증했다는 뜻은 아닙니다. 서로 다른 체형의 관통·발 미끄러짐·도구 접촉이나 자연스러운 루프는 별도 수정이 필요합니다. 범용 IK 리타게팅 해법이나 자동 게임 동작 승인기는 아닙니다.

같은 에셋의 다음 동작은 직전 결과를 부모로 지정하고 새 `clip_name`으로 생성합니다. 기존 메시·리그·클립을 보존하며 **한 최종 GLB에 동작을 누적**합니다. 이름이 같으면 자동 덮어쓰기하지 않습니다. 기존 동작의 의도된 수정은 `blender-edit`, 호환되는 별도 결과의 조합은 `merge-animations`를 사용합니다.

여러 동작도 [클립별 완성 절차](QUALITY.md#여러-클립의-개별-완성)를 따릅니다. 참고가 필요한 클립은 각각 충분한 자료로 목표를 정하고 생성·적용 뒤 검토와 Blender 보정을 이어갑니다. 일부 생성 성공이나 공통 자세 시트만으로 다른 클립의 품질을 승인하지 않습니다.

`text-motion`은 Blender 적용 결과를 `retargeted.glb`에 남기고 **새 클립만 원래 GLB에 병합**합니다. 편집용 Blend와 원본 GLB의 프레임레이트가 달라도 기존 클립의 sampler 데이터를 다시 샘플링하지 않습니다. `animation-merge.json`에 보존·입출력 해시를 기록하며, 최종 검사와 렌더는 병합된 파일을 사용합니다. 체형 보정을 위해 새 클립을 별도 편집했다면 필요한 클립만 원본에 병합해 같은 보존 방식을 적용할 수 있습니다.

보정은 완료된 후보를 부모로 새 revision에서 수행합니다. 기존의 Kimodo 클립 자체를 수정할 때는 의도된 클립 변경이므로 `preserve_animations: false`를 사용하고, 스크립트에서 다른 클립을 보존한 뒤 실제 출력 데이터를 비교합니다. 같은 모델·리그를 유지한 별도 보정 클립은 `merge-animations`로 필요한 클립만 병합할 수 있습니다. 기존 이름을 교체한다면 `on_conflict: "replace"`를 해당 선택 클립에만 적용합니다. 리그·가중치 자체를 고쳤다면 그 변경이 포함된 새 모델을 최종 기준으로 사용하고 영향받는 기존 동작도 재검토합니다. 세부 계약은 [Blender 편집](BLENDER.md)을 따릅니다.

기본 3장 PNG는 한 카메라의 개요이며 승인 근거로 충분하지 않습니다. `assess`는 기본 front/right/back 총 24장 안에서 렌더합니다. [공통 품질 기준](QUALITY.md)에 따라 같은 핵심 시점의 여러 각도·필요한 확대와 전환·재생을 실제로 확인합니다. 기준을 충족하면 불필요한 수정 없이 종료하고, 보정 후에도 결함이 남으면 정한 예산 안에서 다시 진단·수정하거나 미완료로 보고합니다. 추론·출력 성공은 시각 품질 승인과 별개입니다.

중단 후에는 새 요청을 제출하지 말고 기록된 **자식 revision**을 재개합니다:

```sh
uv run --no-sync python -m asset_auto.cli resume-text-motion ASSET_ID CHILD_REVISION --async
```

`motion-request.json`이 부모 GLB/Blend, 추론·적용 스크립트, 모델 pin과 요청을 해시로 묶습니다. `kimodo-inference.json`이 완료되면 `motion.npz`, `motion.bvh`, `motion-data.json` 해시를 검사해 재사용합니다. `authored.blend` 이후 출력 실패는 스크립트를 재실행하지 않고 복구합니다. 완료 전 중단된 로컬 추론은 다시 실행할 수 있지만 완료된 결과나 변경된 스냅샷을 몰래 덮어쓰지 않습니다. 원래 생성 이력과 Kimodo `local_processing`을 구분해 보존합니다.

## 유지보수 검사

```sh
uv run --no-sync pytest -q tests/test_text_motion.py
uv run --no-sync python scripts/smoke_text_motion.py
uv run --no-sync python scripts/smoke_assessment.py
```

첫 검사는 mock 기반 요청·복구 검사이고, 뒤의 검사는 실제 Blender에서 합성 fixture로 기준 자세·월드 방향·클립 보존·출력 복구·다각도 이미지 예산을 확인합니다. **학습 모델의 실제 문장 추론이나 실제 캐릭터의 시각 품질을 증명하지 않습니다.** 설치 수락 시에는 별도로 작은 실제 문장 요청을 실행하고 새 GLB를 검토합니다. 검증 범위를 결과 보고서에 구분합니다.

`uv run --no-sync python scripts/smoke_kimodo_runtime.py`는 공개 Kimodo 가중치로 CUDA 추론·MotionCorrection·NPZ/BVH/JSON 출력을 확인하는 추가 진단입니다. 텍스트 인코더를 사용하지 않는 빈 조건 검사이며 요청한 문장의 대체 경로가 아닙니다. `.work/`에만 저장하고 `text_conditioning_tested: false`로 명시합니다.

2026-09-14에는 RTX 5090에서 **실제 문장 조건 추론을 실행**했습니다. 오른손으로 인사하고 왼팔은 내려두라는 요청으로 4초·120샘플의 모션과 NPZ/BVH를 생성했습니다. 런타임 측정 구간은 약 114초로 텍스트 인코더 로딩을 포함하며, Python 초기 import와 Blender 적용·렌더는 제외합니다. 별도 점검에서 MNTP와 supervised 보정 모델의 가중치가 각각 448개 모두 원본 checkpoint와 일치하고 서로 다른 문장이 서로 다른 유한 임베딩을 만드는 것도 확인했습니다.

기존 SkinTokens 46뼈 캐릭터에 적용하면서 큰 머리와 손의 간섭, 약 8.7cm의 바닥 관통을 발견했습니다. 원래 문장의 추론 결과를 보존하고 별도 Blender revision에서 체형에 맞는 팔 보정과 높이 보정을 수행했습니다. 기존 GLB와 편집용 Blend의 FPS 차이로 걷기 데이터가 재샘플링되는 문제도 발견해, 새 클립만 원본 GLB에 병합하도록 수정했습니다. 최종 파일의 기존 네 클립은 sampler 데이터까지 동일합니다. 체형별 자연스러움·접촉·발 미끄러짐·재생 품질은 모델 실행 성공과 별도로 검토해야 합니다.

최종 후보의 8개 시점 × 4방향 32장과 손·팔·얼굴 주변 확대 10장을 직접 검사했습니다. 60Hz 바닥 검사에서 메시의 최저 Z는 약 +2.0–2.85mm였습니다. **두 차례 국소 보정 후에도 손이 머리에 닿는 모습과 팔의 심한 주름이 남아 시각 품질은 실패로 기록했습니다.** 추가적인 리그·가중치·접촉 보정이 필요하며, 이 캐릭터의 게임 동작을 승인하지 않았습니다. 연속 재생·정밀 충돌·발 미끄러짐과 해당 클립의 엔진 적용은 미검증입니다.
