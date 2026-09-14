# 빠른 사용 가이드

**한국어** | [English](QUICKSTART.en.md)

기본은 **이미지 준비 → TRELLIS.2 생성 → Blender 후처리 → LLM의 수치·렌더 검토 → GLB 전달**입니다. Godot와 웹 뷰어를 실행할 필요는 없습니다. 새 PC는 [INSTALL.md](INSTALL.md)의 기본 설치를 완료하고, 아래 CLI 명령은 저장소 루트에서 실행합니다.

유료 Tripo를 쓰려면 “Tripo3D로 만들어 줘”라고 명시하고 [Tripo 가이드](docs/TRIPO.md)의 키·요청 예시를 사용합니다. 에셋당 표준 생성 1회는 기본 설정으로 자동 진행하므로 `max_credits`를 직접 지정할 필요가 없습니다. 단일 이미지 또는 정면 포함 2–4방향 이미지를 지원하며, 나머지 Blender 처리·렌더 검토·GLB 전달은 같습니다. API 키가 있어도 아래 기본 흐름은 TRELLIS를 사용합니다.

## 1. 참조 이미지 준비

사용자가 준 이미지를 쓰거나, 텍스트 요청이면 LLM이 사용 가능한 이미지 생성 도구로 참조를 준비합니다. 런타임의 `prompt` 필드는 이미지 생성 명령이 아닙니다. 이미지와 이미지 생성 도구가 모두 없으면 참조가 필요한 상황을 알립니다.

**이미지를 보고 Blender 기본 도형을 조립하는 방식으로 추론을 대체하지 않습니다.** 기본 TRELLIS 또는 사용자가 선택한 Tripo를 실행합니다. 절차적 생성은 사용자가 그 방식을 명시적으로 요청한 경우의 대안입니다.

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

`REVISION`을 반환된 실제 값으로 바꿉니다. 수치 검사 결과를 읽고, LLM의 이미지 열기 도구로 `front.png`, `back.png`, `left.png`, `right.png`, `perspective.png`를 확인합니다. [품질 가이드](docs/QUALITY.md)에 따라 제작 전에 정한 기준으로 전체 모습과 필요한 확대·동작을 검토하고, 결함은 새 출력에서 같은 조건으로 재검사합니다. 좁은 수정은 변경 부위와 영향받는 범위부터 확인합니다.

실제 관찰 내용을 기록합니다. `OBSERVATIONS`는 확인한 뷰와 발견 내용으로 바꾸고, 결함이 남으면 `--result fail`을 씁니다:

```sh
uv run --no-sync python -m asset_auto.cli review my-chest-ai REVISION --result pass --notes "OBSERVATIONS"
```

이미지 확인 도구가 없으면 시각 검토가 미완료임을 알립니다. 엔진 로드 성공이나 웹 화면을 여는 것으로 이를 대신 통과시키지 않습니다. 현재 런타임은 생성·수정마다 5방향 렌더를 만들지만 Godot나 웹은 자동 실행하지 않습니다.

## 5. 기존 모델 수정

기존 revision의 실제 부품 이름을 `inspect`로 읽고 필요한 부분을 수정합니다. 수정에 TRELLIS를 다시 돌릴 필요는 없습니다. 생성물이 `Mesh_0` 하나이면 손잡이·뚜껑 같은 의미 부품은 자동으로 분리되어 있지 않습니다.

생성 provider와 편집 방식은 별개입니다. Tripo 생성물도 기본적으로 로컬에서 수정하며 새 유료 작업을 만들지 않습니다. 부품 분리가 필요하면 [기본 로컬 부품 분리](docs/CHARACTERS.md#자동-부품-분리와-이름-확인)로 진행하고 개별 렌더로 확인한 실제 이름을 사용합니다. 정적 부품은 아래 `edit`, 리그·가중치·사용자 동작·더 넓은 변경은 [blender-edit](docs/BLENDER.md)로 처리합니다.

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

## 선택: 리깅·애니메이션·부품 분리

LLM이 요청에 맞춰 방식을 고릅니다. 정적 소품은 리그 없이 유지하고, 문·뚜껑·떠 있는 물체는 [Blender object 동작](docs/BLENDER.md#스크립트로-편집)을 사용합니다. 몸의 변형이 필요하면 기존 리그나 [SkinTokens 초안](docs/CHARACTERS.md#리깅)을 활용하고 사용자 동작·리그·가중치를 로컬 스크립트로 다듬습니다.

기본 이족 `idle`·`walk`·`run`은 `process`로 추가하며 부모의 다른 클립을 유지합니다. 별도 결과의 동작은 [merge-animations](docs/BLENDER.md#여러-동작을-하나의-glb로)로 합칩니다. GeoSAM2 분리용 점과 뼈 이름 매핑은 LLM이 실제 뷰·검사 보고서를 보고 작성합니다. 해당 추론 모델만 설치하며 API 키는 필요하지 않습니다. Tripo 후처리는 별도로 명시한 경우에만 선택합니다. 애니메이션은 실제 샘플·검사 결과, 분리는 개별 렌더로 검토하며 웹 앱을 자동으로 만들지 않습니다.

여러 동작은 [클립별 완성 절차](docs/QUALITY.md#여러-클립의-개별-완성)에 따라 참고와 검토 범위를 따로 확보합니다. 하나를 수정할 때는 변경할 이름을 명시하고, [compare-animations](docs/BLENDER.md#개별-클립-수정과-보존-비교)로 나머지 시간·변환과 모델 데이터의 보존을 확인합니다. 후처리 중 표면이 망가졌다면 [마감 진단 예시](docs/FINISHING.md)로 손상이 처음 발생한 단계부터 찾습니다.

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

> `$3d-assets` Tripo3D로 이 정면·후면 이미지의 상자를 만들고 GLB와 렌더 검토 결과를 전달해 줘.

> `$3d-assets` 이 캐릭터를 리깅하고 걷기 동작을 넣어 줘. 팔·다리가 제대로 움직이는지 직접 검사해 줘.

> `$3d-assets` 이 리깅된 캐릭터에 Kimodo로 인사하는 동작을 만들어 줘. 기존 클립을 유지하고 같은 GLB에 추가한 뒤 주요 시점을 정면·측면·후면에서 검사해 줘.

Kimodo는 위처럼 사용자가 명시한 작업에서만 사용하며, 필요한 경우 그 작업 안에서 별도 로컬 환경과 모델을 설치합니다. 단순히 “걷기 동작을 넣어 줘”라고 요청하면 기존 클립·리그와 Blender 편집·프리셋 중에서 선택합니다. 한 번 Kimodo를 선택한 작업은 매 단계 재확인 없이 진행합니다. 텍스트 인코더 접근 설정과 `text-motion` 명령은 [Kimodo 가이드](docs/KIMODO.md)를 참고합니다. 생성된 동작의 접지·그립·루프는 별도 검토·수정 대상입니다.

> `$3d-assets` 이 Tripo 생성 드론은 리그 없이 떠 있게 해줘. 기존 캐릭터에는 idle을 남기고 손 흔들기 동작을 추가한 뒤 run 클립도 같은 GLB에 합쳐 줘.

> `$3d-assets` 이 정적 모델의 부품을 로컬에서 분리하고 개별 렌더에서 확인한 이름을 붙여 줘.

웹을 원할 때만 다음을 덧붙일 수 있습니다:

> 완성된 모델을 내가 회전하며 볼 수 있게 웹 뷰어도 열어 줘.
