# 문제 해결

명령은 설치한 저장소 루트에서 실행합니다. 공통 첫 확인:

```sh
uv run --no-sync python -m asset_auto.cli doctor
```

기본 구성은 TRELLIS·모델·Blender입니다. Godot·웹은 선택 기능이며, 해당 도구가 없어도 생성과 로컬 PNG 검토는 진행할 수 있습니다. 반대로 TRELLIS가 없거나 이미지 입력이 빠졌다면 기본 새 모델 생성의 차단 요인입니다. 사용자가 명시적으로 선택한 Tripo는 로컬 GPU·모델 없이도 사용할 수 있지만 키·크레딧·Blender가 필요합니다. provider를 자동 전환하거나 Blender 절차적 모델링으로 조용히 대체하지 않습니다.

## 아이템 클릭 시 Failed to fetch / 사이트 연결 거부

브라우저에 목록이 남아 있어도 서버가 종료되면 GLB 요청은 실패할 수 있습니다. Windows에서는 `start-viewer.cmd`를 다시 실행하고 브라우저를 새로고침합니다. Linux에서는 `sh start-viewer.sh`를 실행한 터미널을 유지합니다.

현재 Windows 런처는 별도 백그라운드 서버를 시작하고 준비 상태를 확인합니다. 이미 같은 저장소의 서버가 실행 중이면 재사용합니다. 재부팅 후 자동 실행은 설정하지 않습니다.

Windows에서 서버 상태 확인:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/capabilities'
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
```

연결이 안 되면 `.work/viewer/`의 최신 `.stderr.log`를 읽습니다. 응답의 `root`가 다른 저장소라면 그 서버를 사용 중일 수 있습니다. 프로세스를 무조건 종료하지 말고 PID·명령줄·사용 목적을 확인합니다. 서버가 응답하는데 특정 모델만 실패한다면 해당 revision의 `asset.glb`와 로그를 확인합니다.

## 포트 8765가 이미 사용 중 / 서버를 중지해야 함

Windows 런처는 같은 저장소의 서버를 재사용하지만 다른 프로그램이 쓰는 포트를 강제로 빼앗지 않습니다. 다른 포트로 띄울 수 있습니다:

```sh
uv run --no-sync python -m asset_auto.cli serve --port 8766
```

이 명령은 foreground이므로 터미널을 유지하고 http://127.0.0.1:8766/를 엽니다. 중지는 해당 터미널에서 Ctrl+C입니다.

숨겨진 Windows 서버를 중지하거나 Python 환경을 업데이트할 때는 `Get-NetTCPConnection`의 `OwningProcess`와 `Get-CimInstance Win32_Process -Filter 'ProcessId = PID'`의 명령줄을 확인한 뒤, 확인한 **이 뷰어 프로세스만** `Stop-Process -Id PID`로 종료합니다. `PID`는 실제 숫자로 교체합니다. 모든 Python 프로세스를 종료하지 않습니다.

## Viewer build missing / 오래된 화면

```sh
npm --prefix web ci
npm --prefix web run build
```

빌드 후 브라우저를 새로고침합니다. `web/dist`가 없는 상태에서 서버를 처음 시작했다면 빌드 후 서버도 재시작합니다. 새 에셋은 페이지의 목록 새로고침으로 반영합니다. 새 clone에는 생성 모델이 포함되지 않으므로 라이브러리가 비어 있는 것이 정상입니다.

## Windows에서 uv sync가 실행 파일 사용 중 오류로 실패

실행 중인 뷰어·작업이 Python 환경의 파일을 사용하고 있을 수 있습니다. 확인한 프로세스가 종료된 뒤 `uv sync --locked`를 실행합니다. 설치 이후 일반 실행은 `uv run --no-sync python -m asset_auto.cli ...`를 사용해 불필요한 재설치를 피합니다. MCP extra를 사용하는 환경은 동기화 시 `--extra mcp`도 유지합니다.

## 도구 또는 모델이 없다고 나옴

누락한 구성 요소만 설치합니다. 이름은 `blender`, `godot`, `trellis`, `models` 중 선택합니다. 기본 핵심 구성 전체는 `--only core`이며 인자 없이 실행해도 같습니다:

```sh
uv run --no-sync python scripts/bootstrap.py --only blender
```

기존 설치를 쓰려면 [경로 설정](../INSTALL.md#6-existing-tools-and-configuration)을 확인합니다. 기본 설치는 TRELLIS가 true여야 하고 Godot는 false여도 됩니다. 명시적 Tripo 전용 설치에는 TRELLIS가 필요하지 않습니다. 파일 발견은 실행 성공을 뜻하지 않으므로 실제 생성으로 마무리합니다.

## 참조 이미지가 필요하다는 오류 / 기존 절차적 요청

provider를 생략하면 이제 `trellis`입니다. 이미지를 준비해 `image` 경로를 넣습니다. `image`와 `provider: "procedural"` 또는 `"import"`를 섞은 요청은 거절됩니다. 사용자가 명시적으로 절차적 생성을 요청한 경우만 `provider: "procedural"`과 recipe를 사용합니다. 저장된 기존 revision은 provider를 포함하므로 기존 모델 수정에는 이 기본값 변경이 영향을 주지 않습니다.

## 다운로드 403 / checksum mismatch

GitHub API의 익명 호출 한도라면 제한이 풀린 뒤 다시 시도하거나 설치 환경에 이미 승인된 `GITHUB_TOKEN`을 사용합니다. 토큰을 로그·JSON·Git에 넣지 않습니다. CI는 읽기 전용 토큰을 release metadata 조회에 사용합니다.

체크섬 불일치는 검증을 끄지 말고 네트워크·출처를 확인한 뒤 해당 구성 요소 다운로드를 다시 실행합니다. bootstrap은 유효한 해시의 캐시를 재사용합니다. 실패한 `.part`는 다음 다운로드에서 다시 작성됩니다. 모델 전체나 기존 에셋 폴더를 지울 필요가 없습니다.

## submitted인데 에셋이 안 보임 / 생성 중단

```sh
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`submitted`는 시작 응답입니다. 실제 상태와 오류는 `.assets/jobs/JOB_ID/job.json`, `worker.log`에 있습니다. revision 폴더의 `trellis.log`, `blender.log`도 확인합니다. `running` 중 GPU lock 대기일 수 있으므로 같은 작업을 중복 제출하지 않습니다. 완료 manifest가 없는 폴더는 라이브러리에 표시되지 않습니다.

`interrupted`는 worker가 사라진 상태이며 자동 재개되지 않습니다. TRELLIS는 로그를 읽고 원인을 해결한 뒤 의도적으로 새 작업을 제출합니다. GPU 메모리가 부족하면 다른 GPU 작업과 사용량을 확인하고 처음 검증은 resolution 512로 진행합니다. 모든 하드웨어에 성공을 보장하는 설정은 아닙니다.

Tripo 작업은 로컬 중단 뒤에도 원격 서버에서 계속될 수 있습니다. `tripo.json`에 알려진 task가 있으면 `resume-tripo ASSET_ID REVISION --async`로 이어갑니다. 제출 결과가 불명확하고 task ID가 없으면 대시보드에서 먼저 확인하고, `generate`를 반복하지 않습니다. 자세한 절차는 [Tripo 중단과 복구](TRIPO.md#중단과-복구)를 참고합니다.

## Tripo 키·잔액·예산·입력 오류

`tripo-plan SPEC`은 키 없이 로컬 입력과 예상 비용을 검사할 수 있습니다. API 인증·잔액은 `tripo-balance`로 확인합니다. 키를 출력하지 말고 실행 환경의 `TRIPO_API_KEY` 또는 키 파일 위치만 확인합니다. 기본 파일은 런타임 루트의 `.secrets/tripo_api_key`, 별도 경로는 `TRIPO_API_KEY_FILE`입니다.

`tripo` 설정과 `max_credits`는 생략할 수 있으며 기본 예상 비용 한도는 100, 표준 생성 예상 비용은 30입니다. 명시적인 Tripo 요청의 표준 생성에서 한도 입력이나 별도 크레딧 승인을 반복 요청한다면 최신 스킬을 다시 읽습니다. 사용자가 지정한 한도가 예상 비용보다 작으면 그 한도를 유지하며 오류를 없애려고 임의로 올리지 않습니다. 잔액 부족 시 자동 충전·새 provider 선택·재제출을 하지 않습니다. 입력은 최대 20 MB PNG/JPEG이며, `image`와 `views`는 동시에 쓸 수 없습니다. 멀티뷰는 `front`와 다른 이름의 뷰 1개 이상이 필요합니다. [지원 입력과 비용](TRIPO.md#지원-입력과-비용)을 참고합니다.

## Unknown part / armature 거절

`inspect ASSET_ID REVISION`으로 실제 오브젝트 이름을 읽습니다. AI 생성물이 `Mesh_0` 하나라면 의미별 손잡이·뚜껑이 분리된 상태가 아닙니다. 필요한 경우 기본 로컬 `prepare-segment` → 관찰한 부품 점 지정 → `process`로 분리하고 개별 PNG로 확인한 부품에만 `rename`을 적용합니다. 자동 라벨이나 떨어진 기하 자체를 의미 부품의 증거로 삼지 않습니다.

리그·동작이 있는 파일은 기본 정적 import에서 거절됩니다. 리그는 `provider: "import", asset_kind: "character"`, 리그 없는 object/morph 동작은 `asset_kind: "animated"`로 가져옵니다. 리그·동작이 있는 부모의 수정에는 정적 `edit` 대신 [blender-edit](BLENDER.md)를 사용합니다. [파일 보존 규칙](CHARACTERS.md#캐릭터-파일-보존과-수정-제약)을 참고합니다.

## 리깅·애니메이션·분리 실패

부모 `revision`이 완료되었는지와 요청이 정확한 모델을 가리키는지 확인합니다. 기본 `process`는 로컬이며 리깅·분리는 정적 부모, 이족 프리셋은 리그가 있는 부모를 사용합니다. 로컬 animate는 외부 import 리그도 사용할 수 있습니다. 리그 없는 object 동작이나 사용자 모션은 `blender-edit`를 사용합니다. Tripo를 명시한 animate에만 그 provider의 `rig_task_id`가 필요합니다.

로컬 모델이 없다면 [필요한 backend 설치](../INSTALL.md#local-postprocessing-on-demand)를 진행합니다. `doctor`의 준비 상태와 Linux/WSL의 CUDA·배포판을 확인하며, 설치 실패를 API 키 요청이나 Tripo 자동 전환으로 처리하지 않습니다. 설치 marker는 실제 모델 품질을 증명하지 않습니다.

알 수 없는 뼈 이름은 LLM이 실제 위치와 부모 계층에서 `bone_map`을 정합니다. 로컬 동작은 하나의 armature, 유효한 가중치, 양수·균일 armature 스케일을 요구합니다. `walk`·`run`은 양쪽 thigh→shin→foot, `idle`은 chest가 필요합니다. 리그 번호를 의미 이름으로 추측하거나 일반 뼈를 새로 만들어 오류를 숨기지 않습니다.

로컬 분리의 context는 정확한 원본과 12뷰 파일 해시를 포함합니다. 원본/파일이 바뀌면 다시 `prepare-segment`를 실행합니다. LLM이 선택한 뷰의 실제 픽셀을 관찰해 점을 지정하며 사용자에게 수동 마스크 작성을 요구하지 않습니다. 분류되지 않은 면은 보존하고 실제 결과를 검토합니다. 예산 초과는 원본을 자동 감면해 없애지 않습니다. 추론이 완료되어도 부품 누락·오분류가 있으면 의미 품질 검토는 실패로 남깁니다.

Tripo 리깅 가능 검사에서 거절되면 실제 정면과 `rig_forward_axis`부터 확인합니다. 기본 +Z는 런타임 기준이며 외부 파일의 방향을 보장하지 않습니다. provider +X 입력 변환은 Tripo 어댑터에서만 수행합니다. 중단된 후처리는 `resume-process ASSET_ID REVISION --async`로 저장된 **미완료 자식**을 이어가며, 원격 제출이 불명확한 경우에는 자동 재시도하지 않습니다. [후처리 복구](CHARACTERS.md#기록과-복구)를 참고합니다.

캐릭터는 리그를 보존하기 위해 자동 감면하지 않으므로 예산 초과를 리깅 실패와 혼동하지 않습니다. 분리 결과의 재질 누락, 이름 불일치, 애니메이션 관절 변형은 전체 렌더·개별 부품·샘플 프레임을 실제로 열어 판단합니다. 현재 웹 뷰어에는 동작 재생 제어가 없습니다.

걷기에서 발이 바닥 아래로 내려가면 검사·프리뷰와 provider 원본을 비교합니다. 로컬 동작은 `local-motion.json`의 최종 `ground_checks`와 중간 `generated_ground_checks`에서 `artifact`의 파일·SHA256을 확인하고 IK 제한·접지 보정량을 함께 읽습니다. Tripo 좀비 테스트에서는 원격 GLB에도 같은 편차가 있어 시각 검토를 실패로 기록했습니다. 수정·보정이 있다는 사실만으로 보행 품질을 승인하지 않습니다.

## 수치 통과인데 모델이 이상함

삼각형 수·파일 형식·엔진 로드와 시각 품질은 별도입니다. 5방향 렌더에서 구멍·명암·실루엣·색을 확인합니다. 발견한 결함은 실제 관찰 내용과 함께 기록하고 새 revision에서 수정합니다:

```sh
uv run --no-sync python -m asset_auto.cli review ASSET_ID REVISION --result fail --notes "OBSERVATIONS"
```

대문자 값은 실제 ID·revision·관찰 내용으로 교체합니다. 상세 예는 [빠른 가이드](../QUICKSTART.md#6-검토와-게임-프로젝트로-가져가기)를 참고합니다.

## 스킬이 안 보이거나 Runtime environment missing

개인 스킬 링크가 실제 checkout의 `.agents/skills/3d-assets`를 가리키는지 확인합니다. 스킬 폴더만 복사하면 상대 구조를 사용하는 래퍼가 런타임을 찾지 못합니다. checkout을 이동했으면 링크도 새 위치와 맞춥니다. `.venv`가 없으면 그 checkout에서 `uv sync --locked`를 실행합니다.

에이전트가 새 스킬을 재탐색해야 할 수 있으므로 새 세션에서 확인하거나 SKILL.md의 절대 경로를 지정합니다. CLI와 MCP가 다른 에셋 목록을 보이면 두 실행의 `ASSET_AUTO_ROOT` 및 `doctor` 결과를 비교합니다.
