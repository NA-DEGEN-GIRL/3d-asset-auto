# 비공개 리소스 정책

**한국어** | [English](RESOURCES.en.md)

GPU 선택과 CPU 예산은 장비 운영자가 관리합니다. 공통 정책은 저장소 밖에 두어 `3d-assets`, `game-vfx`와 런타임 worker가 같은 제한을 사용하게 하고, 장비 식별자를 공개하거나 에셋 요청마다 장비 설정을 복사하지 않습니다. 사용자·운영자가 변경을 승인할 수 있지만, 에이전트가 막힌 작업을 실행하려고 보호 장치를 해제하거나 CPU 범위를 넓히거나 보호 GPU 사용을 허용해서는 안 됩니다.

리소스 정책이 없으면 기존 실행 인수·환경·프로세스 affinity를 유지합니다. 정책은 backend 설치, Kimodo·Tripo 선택, GPU 메모리 예약이나 VRAM 적합성을 보장하지 않습니다.

## 설정과 우선순위

실제 설정의 우선순위는 다음과 같습니다. 위쪽이 우선합니다.

1. 해당 항목의 `ASSET_AUTO_GPU`, `ASSET_AUTO_CPUS`, `ASSET_AUTO_THREADS`.
2. `ASSET_AUTO_RESOURCES_FILE`로 선택한 비공개 파일. 지정하지 않으면 `$XDG_CONFIG_HOME/codex-skill-runtimes/resources.json`, `XDG_CONFIG_HOME`도 없으면 `~/.config/codex-skill-runtimes/resources.json`.
3. `<runtime-root>/asset-system.local.json`의 `resources` 객체.
4. 기존 자동 동작.

실제 worker가 실행되는 호스트에 설정합니다. 호출한 Windows·SSH·WSL 환경의 설정만으로 다른 호스트의 제한 적용을 증명할 수 없습니다. 비공개 파일과 장비별 로컬 설정은 Git에 넣지 않으며, 재사용 예제에 자격 증명·호스트 주소·실제 GPU UUID를 복사하지 않습니다.

정책은 `version: 1`을 사용합니다. 운영자가 선택하지 않은 항목은 생략하고 실행 전에 해석된 계획을 확인합니다.

파일 계층은 이름 있는 런타임 재정의를 포함해 필드별로 병합합니다. 선택한 런타임의 값이 공통 값을 재정의하며 위의 세 환경 변수는 그보다 우선합니다. `ASSET_AUTO_GPU`는 `auto`·`cpu`·쉼표로 구분한 전체 UUID, `ASSET_AUTO_CPUS`는 CPU 범위 문자열, `ASSET_AUTO_THREADS`는 양의 정수를 받습니다.

| 항목 | 의미 |
| --- | --- |
| `gpu` | `"auto"`, `"cpu"` 또는 전체 NVIDIA GPU UUID 목록. 순서가 바뀔 수 있는 숫자 index 대신 UUID를 사용합니다. |
| `protected_gpus` | 일반 GPU 선택에서 제외할 전체 UUID 목록. |
| `cpus` | `"0-3"` 같은 범위로 지정한 허용 논리 CPU. 실제 worker에 허용된 범위를 선택합니다. |
| `threads` | 양수인 worker·스레드 라이브러리 예산. CPU affinity와는 별개입니다. |
| `nice` | -20부터 19까지의 Linux niceness. 적용 시 기존 수치를 낮추지 않으므로 스케줄링 우선순위를 높일 수 없습니다. |
| `oom_score_adj` | -1000부터 1000까지의 Linux OOM 선택 조정값. RAM 사용량 제한은 아닙니다. |
| `max_parallel_blender` | 같은 사용자의 세션·checkout 전체에서 정책을 통해 실행하는 Blender의 최대 동시 프로세스 수. |
| `wait_timeout_seconds` | 양수인 리소스 최대 대기 시간 또는 선택한 리소스를 계속 기다리는 `null`(기본값). |
| `poll_interval_seconds` | 양수인 리소스 대기 조회 간격. 기본값은 2초입니다. |
| `runtimes` | `trellis`, `kimodo`, `local_rig`, `local_parts`, `blender`별 `gpu`, `threads`, `allow_protected` 재정의. |
| `runtimes.kimodo.text_encoder_device` | `"cuda"`(기본값) 또는 `"cpu"`. 모션 네트워크에는 여전히 CUDA가 필요합니다. |

다음은 실제 장비 설정이 아닌 형식 예제입니다. 두 UUID를 운영자가 선택한 전체 UUID로 바꾸고 실제 worker에 허용된 CPU·예산을 선택합니다. 비공개 파일에는 객체를 그대로 넣으며, `asset-system.local.json`에서는 `resources` 아래에 넣습니다.

```json
{
  "version": 1,
  "gpu": ["GPU-00000000-0000-0000-0000-000000000001"],
  "protected_gpus": ["GPU-00000000-0000-0000-0000-000000000002"],
  "cpus": "0-3",
  "threads": 4,
  "nice": 10,
  "oom_score_adj": 500,
  "max_parallel_blender": 1,
  "runtimes": {
    "blender": {"gpu": "cpu"},
    "kimodo": {"text_encoder_device": "cpu"}
  }
}
```

`allow_protected`는 해당 런타임에 대한 운영자의 명시적 예외이며 자동 재시도 옵션이 아닙니다. 선택 후 허용 GPU가 없으면 정책 오류로 중단합니다. 이를 우회하려고 정책을 변경하거나 다른 호스트·유료 provider를 자동 선택하지 않습니다. 허용된 리소스로 진행할 수 있는 독립 작업은 계속합니다.

CUDA worker에서 보호 GPU와 `gpu: "auto"`를 함께 사용하려면 상속한 GPU 선택이 전체 UUID로 명확해야 합니다. 그렇지 않으면 허용 UUID를 직접 지정합니다. 런타임이 index로 빈 장치를 추측하지 않습니다. OOM 조정도 기존 수치를 낮추지 않으므로 추가 OOM 보호를 부여할 수 없습니다. 요청 값을 바꾸지 않고 유지한 경우 적용 진단을 확인합니다.

허용 장치가 사용 중인 상태는 잘못된 설정·없는 장치와 다릅니다. GPU를 명시적으로 선택했다면 그 장치와 Blender 동시 실행 자리를 기다리며, 바쁘다는 이유로 다른 GPU로 옮기지 않습니다. 같은 제출 작업을 유지하고 대기가 불필요해지면 취소합니다. 잘못된 정책·존재하지 않는 선택 UUID는 즉시 실패합니다. 관리하는 작업과 관찰한 GPU 작업을 조정하는 기능이며 임의의 GPU·CPU 활동에 대한 OS 수준 독점권은 아닙니다.

GPU UUID 점유 기록과 Blender 자리는 `$XDG_CACHE_HOME/codex-skill-runtimes/locks`, 기본 `~/.cache/codex-skill-runtimes/locks`에서 같은 사용자의 세션·checkout이 공유합니다. 대기 시 외부 CUDA compute 프로세스를 확인하며 모든 그래픽 작업을 포괄하지는 않습니다. 다른 프로세스를 종료하거나 옮기지 않습니다. 확인 직후 외부 프로세스가 시작할 수 있으며 엄격한 FIFO 대기열이나 보안 경계는 아닙니다.

로컬 `*.resources.json` 기록에 실행·대기 증거를 저장합니다. 백그라운드 작업은 job 상태 `running`을 유지하면서 `resource_progress.state`에 `waiting_resources`를 표시합니다. 이를 중복 작업 제출의 근거로 삼지 않습니다.

## 실제 실행 경로 확인

런타임 루트에서:

```sh
uv run --no-sync python -m asset_auto.cli resources --runtime blender
uv run --no-sync python -m asset_auto.cli resources --runtime kimodo
uv run --no-sync python -m asset_auto.cli doctor
```

`resources`는 추론 없이 해석된 계획을 표시하고, `doctor`는 리소스 정책 진단을 포함합니다. 설정 출처·선택/제외 장치·지원하지 않는 제어를 확인합니다. 계획은 모델·렌더 실행 성공의 증거가 아닙니다. 다른 프로젝트에서는 기존 스킬 래퍼의 실행 경로를 유지하고 필요한 경우 명시적인 런타임 루트를 전달합니다.

스킬 래퍼의 `runtime-status`는 선택한 실행 경로에 맞는 `resource_policy.check_argv`를 포함합니다. 상태 조회 자체는 브리지 클라이언트에서 정책을 읽거나 런타임을 import하지 않습니다. 해당 검사 명령을 실행해 실제 worker 호스트의 정책을 확인합니다.

네이티브 Linux worker는 affinity·niceness·OOM 조정을 적용할 수 있습니다. Windows에서는 CUDA·스레드 환경 설정을 적용할 수 있지만 Linux OS 제어는 지원하지 않으며 그 상태를 보고해야 합니다. Windows·WSL·SSH 브리지는 장치 제한이 자동 적용된다고 주장하면 안 됩니다. worker가 실행되는 곳에 정책을 설정하거나, 활성 정책을 경계 너머로 적용할 수 없으면 실패해야 합니다.

CPU 구현이 없는 CUDA 전용 backend는 `gpu: "cpu"`를 명시적으로 거절합니다. TRELLIS·학습된 로컬 리깅/분리·Kimodo 모션 네트워크에 해당하며, GPU를 숨긴다고 CPU 추론이 되는 것은 아닙니다.

일반 TRELLIS 생성 명령은 자체 `--threads` 예산도 설정하며, UUID 필터 뒤의 논리 장치 `--gpu 0`을 선택합니다. `resources --exec`로 직접 작성한 TRELLIS 명령에는 정책 환경과 Linux 프로세스 제한이 적용되므로, 대응하는 자체 `--threads`/`--gpu` 인수도 작성해야 합니다. 라이브러리 스레드 환경 변수만으로 모든 프로그램의 내부 스레드 풀을 제어할 수는 없습니다.

## Blender와 VFX

파이프라인뿐 아니라 사용자 Blender 저작·시뮬레이션에도 리소스 정책을 적용하는 실행기를 사용합니다. `<blender>`를 직접 실행하면 실행기의 제어·동시 실행 제한을 우회합니다. 새 시뮬레이션과 리소스 출처 기록은 로컬 작업 폴더에 보존합니다.

```text
uv run --no-sync python -m asset_auto.cli resources --runtime blender --exec -- <absolute-blender> --background --python <absolute-script> -- <script-arguments>
```

`resources --runtime blender --shell-prefix`는 해석된 루트와 `--exec --`를 포함한 CLI 실행 접두사를 출력합니다. Windows에서는 PowerShell의 `&`와 작은따옴표 인수를, POSIX에서는 셸 인용을 사용합니다. 해당 셸의 인용 규칙에 맞춰 전체 실행 파일과 인수를 뒤에 붙입니다. 단순 환경 변수 대입문이 아니며 제한 실행기를 우회하는 용도가 아닙니다.

Mantaflow 시뮬레이션은 CPU 작업 경로이므로 bake에 CPU affinity·스레드 예산을 적용합니다. 렌더는 별도 단계입니다. EEVEE·OpenGL은 CUDA와 별도로 장치를 선택할 수 있어 `CUDA_VISIBLE_DEVICES`만으로 보호 GPU를 제외할 수 없습니다. GPU 제외가 필요하면 실제로 제한된 CPU·소프트웨어 렌더 경로를 사용하고, 환경 변수만 보고 GPU 격리를 승인하지 않습니다. 보호를 적용한 분리 준비 경로는 GPU 제한이 활성화되면 Cycles CPU를 선택하고 소프트웨어 OpenGL을 요청합니다. 실제 실행 플랫폼이 그 설정을 적용하는지 확인해야 합니다.

리소스 제어는 신뢰한 Blender Python을 가두는 샌드박스가 아니라 실행기와 스크립트가 지켜야 하는 계약입니다. 스크립트도 선택된 renderer·장치 정책을 유지해야 합니다. 출력·시뮬레이션 성공과 실제 renderer·장치 증거는 구분해 검토합니다.

## Kimodo 인코더 배치

명시적인 정책 선택으로 Kimodo 모션 네트워크는 선택한 CUDA GPU에 두고 텍스트 인코더만 CPU에서 실행할 수 있습니다. 기본 인코더는 CUDA이며, GPU 오류가 나도 CPU·원격 인코더로 자동 전환하지 않습니다. 혼합 배치는 Kimodo 전체 CPU 실행 지원이 아닙니다.

전체 GPU 경로는 약 17 GiB VRAM, CPU 인코더와 함께 쓰는 모션 네트워크는 대략 2 GiB를 계획용 추정치로 참고합니다. 명시적 GPU 선택은 첫 번째 visible 장치의 전체 용량을 인코더 모드별 기준과 비교하며, 여러 GPU를 합산하거나 충분한 여유 메모리를 증명하지는 않습니다. 모델 버전·시퀀스 설정·CUDA 할당·다른 프로세스에 따라 실제 사용량이 달라집니다. CPU 인코더는 GPU 메모리를 줄이는 대신 큰 호스트 RAM과 느린 인코딩 시간을 요구합니다. 계획을 확인하고 승인된 실제 작업을 측정합니다. [Kimodo 설치·검증](KIMODO.md)을 참고하세요.

해석된 계획·실제 실행 설정·관찰한 실행 증거는 비공개 로컬 작업·출력 출처 기록에 보존합니다. 요청 제한·미적용 항목·관찰한 메모리를 구분해 보고하며, 계획이나 추론 성공은 시각 품질의 증거가 아닙니다. 에셋 공개 요청만으로 장비 세부 정보의 공개까지 승인된 것은 아닙니다.
