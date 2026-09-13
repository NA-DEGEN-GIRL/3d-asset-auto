# Kimodo 로컬 텍스트 모션

[공식 Kimodo](https://github.com/nv-tlabs/kimodo)의 `Kimodo-SOMA-RP-v1.1`로 사람 동작을 생성하고, 이미 리깅된 에셋에 적용합니다. **문장 → 로컬 모션 추론 → 관찰한 뼈 대응으로 Blender 적용 → 기존 클립을 포함한 새 GLB → 다각도 검토** 흐름입니다. 메시 생성기와 독립적이며 Tripo API를 사용하지 않습니다. 새 메시 생성 기본값은 계속 TRELLIS.2입니다.

사람 모션의 초안이 필요하면 이 경로를 선택합니다. 정적인 소품, 강체·기계 동작, 정밀한 접촉 보정은 [Blender 편집](BLENDER.md)을 사용합니다. `process`의 `idle`·`walk`·`run`은 별도의 절차적 프리셋이며 Kimodo 추론과 구분합니다.

## 필요한 때 설치

Linux 또는 Windows WSL2, NVIDIA CUDA GPU와 C++ 컴파일러가 필요합니다. 공식 안내상 텍스트 인코더를 포함한 GPU 실행은 약 17GB VRAM을 사용합니다. 이 어댑터는 모델과 인코더를 같은 GPU에서 실행하며 CPU 인코더·원격 인코더 자동 전환을 제공하지 않습니다. 메인 `.venv`와 분리해 설치합니다.

```sh
uv run --no-sync python scripts/bootstrap_kimodo.py
uv run --no-sync python -m asset_auto.cli doctor
```

Windows 기본 WSL 배포판은 `Ubuntu-24.04`이며 `--wsl-distribution`으로 바꿀 수 있습니다. 선택한 Linux 사용자 환경에 `uv`, `g++`가 있어야 합니다. 설치 도중 `#`가 포함된 체크아웃 경로의 빌드 문제를 피하도록 고정 소스를 Linux 임시 디렉터리에서 wheel로 빌드합니다. 기존 프로젝트 파일이나 시스템 Python을 교체하지 않습니다.

텍스트 인코더는 [Meta-Llama-3-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) 기반 LLM2Vec입니다. 해당 모델 접근이 허용된 Hugging Face 계정의 읽기 토큰을 **`<runtime-root>/.secrets/hf_token`**에 키만 저장하거나 기존 HF 로그인/`HF_TOKEN`을 사용합니다. 접근 신청·약관 동의가 필요한 계정은 Hugging Face에서 처리합니다. 키를 요청 JSON, 로그, Git이나 채팅에 넣지 않습니다. 이후 추론은 고정된 로컬 파일만 사용하며 외부 인코더 서비스를 탐색하지 않습니다.

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

모션 핵심 시점과 전환을 같은 조건의 여러 각도로 검사합니다. 기본 3장 PNG는 한 카메라의 개요이며 승인 근거로 충분하지 않습니다. `assess`의 `views` 기본값은 `front`, `right`, `back`이고 총 24장 안에서 나눕니다. 가림, 빠른 변화, 접촉 문제에 따라 다른 각도·확대·재생을 선택하고 미검토 범위를 남깁니다. 자세·타이밍·접촉의 실제 결함은 수치 통과로 지우지 않습니다.

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

2026-09-13에는 RTX 5090에서 이 빈 조건 진단을 실제 실행했습니다. 2초·60샘플의 모션 추론부터 보정·출력까지 약 5.95초였으며 텍스트 인코더 시간은 포함하지 않습니다. 해당 출력을 기존 SkinTokens 46뼈 캐릭터에 적용하고 18장의 다각도 이미지를 생성해 시작·중간·끝의 정면/측면/후면 9장을 직접 검토했습니다. 원래 바닥보다 약 8.6cm 낮아진 문제를 발견하여 Blender의 새 revision에서 해당 클립만 높이 보정하고 같은 시점·각도를 재검사했습니다. 최종 GLB 63개 시간 샘플의 최저 Z는 약 +2.0mm였고, 기존 4개 클립의 sampler 데이터는 그대로 유지됐습니다. 바닥 수치는 접촉·발 미끄러짐 증거가 아니며 전체 재생·그립·게임 품질을 승인하지 않았습니다. Llama 접근은 401로 거절되어 **실제 문장 조건 추론은 미검증**입니다.
