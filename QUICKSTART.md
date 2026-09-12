# 빠른 사용 가이드

기본은 **이미지 준비 → TRELLIS.2 생성 → Blender 후처리 → LLM의 수치·렌더 검토 → GLB 전달**입니다. Godot와 웹 뷰어를 실행할 필요는 없습니다. 새 PC는 [INSTALL.md](INSTALL.md)의 기본 설치를 완료하고, 아래 CLI 명령은 저장소 루트에서 실행합니다.

## 1. 참조 이미지 준비

사용자가 준 이미지를 쓰거나, 텍스트 요청이면 LLM이 사용 가능한 이미지 생성 도구로 참조를 준비합니다. 런타임의 `prompt` 필드는 이미지 생성 명령이 아닙니다. 이미지와 이미지 생성 도구가 모두 없으면 참조가 필요한 상황을 알립니다.

**이미지를 보고 Blender 기본 도형을 조립하는 방식으로 TRELLIS 추론을 대체하지 않습니다.** 절차적 생성은 사용자가 그 방식을 명시적으로 요청한 경우의 대안입니다.

## 2. 생성 요청 저장

```sh
uv run --no-sync python -m asset_auto.cli doctor
```

`providers.trellis: true`, `models.missing: []`를 확인합니다. 이것은 설치 파일 발견 결과이며 실제 GPU 추론 성공은 다음 단계에서 확인합니다. Godot가 없거나 웹이 빌드되지 않은 것은 문제가 아닙니다.

`.work/` 폴더를 만들고 아래 JSON을 `.work/asset.json`에 UTF-8로 저장합니다. `image`는 **실제로 존재하는 참조 이미지의 절대 경로**로 바꿉니다. Windows JSON 경로는 `/`를 쓰면 이스케이프가 간단합니다.

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

provider를 생략해도 기본값은 `trellis`이며 참조 이미지를 요구합니다. `image`를 `procedural` 또는 `import`와 함께 넘기는 요청은 거절됩니다. 기존 절차적 JSON을 쓴다면 `provider: "procedural"`을 명시해야 합니다.

## 3. 실제 생성과 완료 확인

```sh
uv run --no-sync python -m asset_auto.cli generate .work/asset.json --async
uv run --no-sync python -m asset_auto.cli job JOB_ID
```

`JOB_ID`는 첫 명령이 반환한 값으로 교체합니다. `submitted`는 완료가 아닙니다. `state: succeeded`일 때 `result`의 `asset_id`, `revision`, `inspection`을 확인합니다. 실패·중단이면 로그를 읽고 원인을 해결합니다. 기다리는 동안 중복 제출하지 않습니다.

첫 생성 revision의 `.assets/my-chest-ai/REVISION/`에는 다음이 남습니다:

- `generation.json`, `trellis.log`, `generated.glb`: 실제 TRELLIS 호출·실행 기록·원시 출력.
- `source.blend`, `asset.glb`: Blender 후처리 원본과 내보낸 결과.
- `inspection.json`, 5방향 PNG: LLM이 확인할 수치와 이미지.
- `manifest.json`: provider, 요청, 파일 해시·도구 출처.

Blender 렌더가 있다는 사실만으로 TRELLIS를 실행했다고 판단하지 않습니다. 생성 기록과 `provider: "trellis"`도 확인합니다. 부분 수정 revision은 부모의 생성 기록으로 출처를 추적합니다.

## 4. LLM이 모델 확인

```sh
uv run --no-sync python -m asset_auto.cli inspect my-chest-ai REVISION
```

`REVISION`을 반환된 실제 값으로 바꿉니다. 수치 검사 결과를 읽고, LLM의 이미지 열기 도구로 `front.png`, `back.png`, `left.png`, `right.png`, `perspective.png`를 확인합니다. 구멍·실루엣·재질·참조 반영을 살핍니다. 좁은 범위의 수정에서는 변경 부위를 확인할 수 있는 뷰부터 검사하고 필요하면 확대합니다.

실제 관찰 내용을 기록합니다. `OBSERVATIONS`는 확인한 뷰와 발견 내용으로 바꾸고, 결함이 남으면 `--result fail`을 씁니다:

```sh
uv run --no-sync python -m asset_auto.cli review my-chest-ai REVISION --result pass --notes "OBSERVATIONS"
```

이미지 확인 도구가 없으면 시각 검토가 미완료임을 알립니다. 엔진 로드 성공이나 웹 화면을 여는 것으로 이를 대신 통과시키지 않습니다. 현재 런타임은 생성·수정마다 5방향 렌더를 만들지만 Godot나 웹은 자동 실행하지 않습니다.

## 5. 기존 모델 수정

기존 revision의 실제 부품 이름을 `inspect`로 읽고 필요한 부분을 수정합니다. 수정에 TRELLIS를 다시 돌릴 필요는 없습니다. 생성물이 `Mesh_0` 하나이면 손잡이·뚜껑 같은 의미 부품은 자동으로 분리되어 있지 않습니다.

예를 들어 사용자가 명시적으로 절차적 검 예제를 요청했다면 `examples/sword.json`으로 생성한 후 `grip`만 수정할 수 있습니다. `.work/grip-edit.json`에 저장할 예:

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

새 revision을 검사하고 이전 원본은 보존합니다. 부품을 늘려도 연결된 부품의 위치는 자동 변경되지 않으므로 필요한 위치 변경은 같이 지정합니다. 전체 필드는 [스키마 안내](.agents/skills/3d-assets/references/specs.md)를 참고합니다.

## 6. 검토와 게임 프로젝트로 가져가기

기본 결과는 검토한 revision의 GLB와 편집 원본, 검사 내용입니다. 대상 프로젝트가 없으면 파일을 전달합니다. 통합을 요청했다면 그 프로젝트의 경로·크기·재질 규칙에 맞춰 복사하고, 변경이나 호환성 우려에 필요한 importer/loader 검사를 선택합니다. 특정 엔진을 알 수 없다는 이유로 임의로 Godot 프로젝트나 웹 앱을 만들지 않습니다.

GLB는 **Y-up·미터**, Blender의 레시피와 내부 수치는 **Z-up·미터**입니다. 생략한 엔진 검사는 미검증이며 에셋 생성 실패가 아닙니다.

## 선택: 대상 프로젝트의 Godot 검사

Godot 프로젝트 통합에 필요하거나 요청받았을 때 [선택 설치](INSTALL.md#optional-project-checks-and-viewer) 후 실행합니다:

```sh
uv run --no-sync python -m asset_auto.cli godot ASSET_ID REVISION
```

GLB를 실제로 가져와 장면·메시·재질·볼록 충돌체를 확인합니다. 다른 프로젝트에서 Godot를 설치할 이유는 없으며, 이 검사를 했다고 Three.js도 검사할 필요는 없습니다.

## 선택: 사용자가 원하는 웹 미리보기

회전 가능한 뷰어나 웹 렌더 검증을 요청한 경우, 기존 프로젝트의 앱을 우선 사용합니다. 별도 뷰어가 필요하면 [선택 설치](INSTALL.md#optional-project-checks-and-viewer) 후 Windows의 `start-viewer.cmd` 또는 Linux의 `sh start-viewer.sh`를 실행합니다.

[로컬 뷰어](http://127.0.0.1:8765/)에서 목록 새로고침 → 에셋 클릭 → 버전 선택으로 확인합니다. 회전·확대·와이어프레임·렌더 이미지·GLB 다운로드를 사용할 수 있습니다. Windows는 백그라운드 서버를 유지하고 Linux는 실행 터미널을 유지합니다. 연결 오류는 [문제 해결](docs/TROUBLESHOOTING.md)을 참고합니다.

## LLM 요청 예

> `$3d-assets` 이 이미지로 소품을 만들고 뒷면까지 검사해 줘. 결함은 새 버전으로 수정하고 GLB로 전달해 줘.

> `$3d-assets` 이 프로젝트에 맞는 나무 상자를 만들어 줘. 참조 이미지를 준비하고 TRELLIS로 생성한 뒤 결과를 직접 검토해 줘.

웹을 원할 때만 다음을 덧붙일 수 있습니다:

> 완성된 모델을 내가 회전하며 볼 수 있게 웹 뷰어도 열어 줘.
