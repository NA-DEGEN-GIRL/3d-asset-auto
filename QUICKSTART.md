# 빠른 사용 가이드

새 PC라면 먼저 [설치 가이드](INSTALL.md)를 완료합니다. 아래 CLI 명령은 **저장소 루트**에서 실행합니다. 현재 개발 PC의 경로는 `D:\#programming\3d-asset-auto`이며 다른 PC에서는 실제 clone 위치를 사용합니다.

## 1. 도구 확인과 첫 상자 만들기

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli generate examples/chest.json
```

`doctor`에서 `providers.procedural: true`이면 Blender 경로를 찾은 상태입니다. 이 명령은 실제 GPU 추론을 시험하지 않습니다. `generate` 결과의 `asset_id`, `revision`, `inspection.passed`를 확인합니다. 같은 예제를 다시 실행하면 새 버전이 추가됩니다.

예제 상자는 GPU 없이 생성됩니다. 출력 경로는 `.assets/oak-chest/반환된_revision/`이며, `asset.glb`가 게임·웹용 파일이고 `source.blend`는 편집 원본입니다.

## 2. 웹에서 보기

Windows:

```powershell
.\start-viewer.cmd
```

Linux:

```sh
sh start-viewer.sh
```

[로컬 뷰어](http://127.0.0.1:8765/)에서 **목록 새로고침 → 에셋 클릭 → 버전 선택** 순서로 확인합니다. 드래그는 회전, 스크롤은 확대, 우클릭 드래그는 이동입니다. 와이어프레임·5방향 렌더·검토 메모를 확인하고 GLB를 다운로드할 수 있습니다.

Windows는 실행창이 닫혀도 서버가 유지됩니다. Linux 런처는 터미널을 유지해야 합니다. 브라우저만 열어서는 서버가 시작되지 않습니다. 연결이 끊기면 [문제 해결](docs/TROUBLESHOOTING.md)을 참고하세요.

## 3. Godot에서 검사하기

`REVISION`은 1단계에서 반환된 실제 값으로 교체합니다. 문자열 `REVISION` 자체를 실행하지 않습니다.

```sh
uv run --no-sync python -m asset_auto.cli godot oak-chest REVISION
```

`passed: true`와 같은 버전의 `godot.json`을 확인합니다. 이 검사는 임시 Godot 프로젝트에서 GLB를 실제로 가져와 장면을 만들고 재질·충돌체를 확인합니다. 실제 게임 프로젝트의 플레이 검사는 별도로 필요합니다.

## 4. 기존 검의 손잡이만 바꾸기

```sh
uv run --no-sync python -m asset_auto.cli generate examples/sword.json
uv run --no-sync python -m asset_auto.cli list
uv run --no-sync python -m asset_auto.cli inspect azure-sword REVISION
```

검사 결과에 `grip` 부품이 있는지 확인합니다. `.work/` 폴더를 만들고 다음 내용을 `.work/grip-edit.json`에 UTF-8로 저장합니다. `revision`은 수정할 검의 실제 값으로 교체합니다.

```json
{
  "asset_id": "azure-sword",
  "revision": "REVISION",
  "description": "손잡이만 버건디색으로 변경",
  "changes": [{"part": "grip", "color": [0.19, 0.015, 0.035, 1]}]
}
```

```sh
uv run --no-sync python -m asset_auto.cli edit .work/grip-edit.json
```

새 `revision`이 반환되며 이전 원본은 보존됩니다. 웹 목록을 새로고침하고 버전을 전환해 비교합니다. 부품을 길게 늘려도 연결된 부품이 자동으로 이동하지 않으므로 위치 변경은 함께 지정해야 합니다.

## 5. 이미지로 AI 생성하기

[GPU 추가 설치](INSTALL.md#3-add-trellis-gpu-generation-optional) 후 `doctor`에서 `providers.trellis: true`를 확인합니다. `.work/chest-ai.json`에 다음 내용을 저장하고 `image`를 **실제로 존재하는 이미지의 절대 경로**로 바꿉니다. Windows JSON 경로는 `/`를 쓰면 이스케이프가 간단합니다.

```json
{
  "asset_id": "my-chest-ai",
  "provider": "trellis",
  "image": "D:/references/chest.png",
  "prompt": "75cm 나무 보물상자",
  "triangle_budget": 12000,
  "target_height": 0.75,
  "resolution": 512,
  "atlas": 1024,
  "seed": 42
}
```

```sh
uv run --no-sync python -m asset_auto.cli generate .work/chest-ai.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`JOB_ID`는 첫 명령이 반환한 `job_id`로 교체합니다. 제출 응답은 완료가 아닙니다. `state: succeeded`일 때 `result`에서 revision을 확인하고, `failed` 또는 `interrupted`면 작업 로그를 확인합니다. 기다리는 동안 같은 작업을 다시 제출하지 않습니다.

`prompt`는 요청 기록입니다. 이미지를 생성하는 명령이 아니므로 참조 이미지가 반드시 필요합니다. 생성 메시에는 의미별 부품 이름이 없을 수 있습니다.

## 6. 검토와 게임 프로젝트로 가져가기

1. `inspection.json`의 수치와 경고를 읽습니다.
2. front/back/left/right/perspective PNG를 열어 구멍·실루엣·재질·요청 반영을 살핍니다.
3. 확인한 내용을 구체적인 문장으로 기록합니다. 아래 `OBSERVATIONS`는 실제 관찰 내용으로 교체하고, 결함이 남으면 `--result fail`을 사용합니다.

```sh
uv run --no-sync python -m asset_auto.cli review ASSET_ID REVISION --result pass --notes "OBSERVATIONS"
```

선택한 revision의 GLB를 게임 프로젝트의 에셋 폴더에 복사하고 그 프로젝트에서 확인합니다. GLB는 **Y-up·미터**, Blender의 레시피와 내부 수치 검사는 **Z-up·미터**입니다. Godot와 Three.js 모두 GLB를 사용할 수 있지만 씬 배치·크기·게임 동작은 대상 프로젝트에 맞춰 검증합니다.

## LLM에게 맡기는 예

[개인 스킬 연결](INSTALL.md#4-connect-the-agent-skill)을 마친 에이전트에서:

> `$3d-assets` 이 게임의 기존 색감에 맞는 상자를 만들어 줘. 12,000 삼각형 이하, 높이 0.75m로 하고 Godot와 웹에서 확인해 줘.

> `$3d-assets` 이 이미지를 참조해서 소품을 만들고 뒷면까지 검사해 줘. 결함이 있으면 새 버전으로 수정해 줘.

상세 필드는 [요청 스키마 안내](.agents/skills/3d-assets/references/specs.md), 전체 명령과 파일은 [런타임 안내](.agents/skills/3d-assets/references/runtime.md)를 참고합니다.
