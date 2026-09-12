# 문제 해결

명령은 설치한 저장소 루트에서 실행합니다. 공통 첫 확인:

```sh
uv run --no-sync python -m asset_auto.cli doctor
```

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

누락한 구성 요소만 설치합니다. 이름은 `blender`, `godot`, `trellis`, `models` 중 선택합니다:

```sh
uv run --no-sync python scripts/bootstrap.py --only blender
```

기존 설치를 쓰려면 [경로 설정](../INSTALL.md#6-existing-tools-and-configuration)을 확인합니다. 기본 설치에서 TRELLIS가 false인 것은 정상입니다. 파일 발견은 실행 성공을 뜻하지 않으므로 실제 생성으로 마무리합니다.

## 다운로드 403 / checksum mismatch

GitHub API의 익명 호출 한도라면 제한이 풀린 뒤 다시 시도하거나 설치 환경에 이미 승인된 `GITHUB_TOKEN`을 사용합니다. 토큰을 로그·JSON·Git에 넣지 않습니다. CI는 읽기 전용 토큰을 release metadata 조회에 사용합니다.

체크섬 불일치는 검증을 끄지 말고 네트워크·출처를 확인한 뒤 해당 구성 요소 다운로드를 다시 실행합니다. bootstrap은 유효한 해시의 캐시를 재사용합니다. 실패한 `.part`는 다음 다운로드에서 다시 작성됩니다. 모델 전체나 기존 에셋 폴더를 지울 필요가 없습니다.

## submitted인데 에셋이 안 보임 / 생성 중단

```sh
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`submitted`는 시작 응답입니다. 실제 상태와 오류는 `.assets/jobs/JOB_ID/job.json`, `worker.log`에 있습니다. revision 폴더의 `trellis.log`, `blender.log`도 확인합니다. `running` 중 GPU lock 대기일 수 있으므로 같은 작업을 중복 제출하지 않습니다. 완료 manifest가 없는 폴더는 라이브러리에 표시되지 않습니다.

`interrupted`는 worker가 사라진 상태이며 자동 재개되지 않습니다. 로그를 읽고 원인을 해결한 뒤 의도적으로 새 작업을 제출합니다. GPU 메모리가 부족하면 다른 GPU 작업과 사용량을 확인하고 처음 검증은 resolution 512로 진행합니다. 모든 하드웨어에 성공을 보장하는 설정은 아닙니다.

## Unknown part / armature 거절

`inspect ASSET_ID REVISION`으로 실제 오브젝트 이름을 읽습니다. AI 생성물이 `Mesh_0` 하나라면 의미별 손잡이·뚜껑이 분리된 상태가 아닙니다. 이름을 추측해서 반복 요청하지 않습니다. armature가 있는 입력은 현재 정적 파이프라인에서 지원하지 않습니다.

## 수치 통과인데 모델이 이상함

삼각형 수·파일 형식·엔진 로드와 시각 품질은 별도입니다. 5방향 렌더에서 구멍·명암·실루엣·색을 확인합니다. 발견한 결함은 실제 관찰 내용과 함께 기록하고 새 revision에서 수정합니다:

```sh
uv run --no-sync python -m asset_auto.cli review ASSET_ID REVISION --result fail --notes "OBSERVATIONS"
```

대문자 값은 실제 ID·revision·관찰 내용으로 교체합니다. 상세 예는 [빠른 가이드](../QUICKSTART.md#6-검토와-게임-프로젝트로-가져가기)를 참고합니다.

## 스킬이 안 보이거나 Runtime environment missing

개인 스킬 링크가 실제 checkout의 `.agents/skills/3d-assets`를 가리키는지 확인합니다. 스킬 폴더만 복사하면 상대 구조를 사용하는 래퍼가 런타임을 찾지 못합니다. checkout을 이동했으면 링크도 새 위치와 맞춥니다. `.venv`가 없으면 그 checkout에서 `uv sync --locked`를 실행합니다.

에이전트가 새 스킬을 재탐색해야 할 수 있으므로 새 세션에서 확인하거나 SKILL.md의 절대 경로를 지정합니다. CLI와 MCP가 다른 에셋 목록을 보이면 두 실행의 `ASSET_AUTO_ROOT` 및 `doctor` 결과를 비교합니다.
