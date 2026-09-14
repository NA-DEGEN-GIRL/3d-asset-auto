# 3D Asset Auto

LLM에게 3D 소품의 생성·수정·검토를 요청할 수 있는 로컬 도구입니다. 기본 흐름은 **참조 이미지 준비 → TRELLIS.2 생성 → Blender 후처리 → LLM의 수치·렌더 검토 → GLB 전달**입니다. 대상 프로젝트가 정해지지 않아도 사용할 수 있습니다.

새 모델 생성은 기본적으로 TRELLIS.2를 거칩니다. **사용자가 “Tripo3D로 만들어 줘”라고 명시한 경우에는 유료 Tripo API를 선택**할 수 있습니다. API 키가 있거나 로컬 추론이 실패했다는 이유로 자동 전환하지 않습니다. 어느 provider든 참조 이미지를 보고 Blender 도형으로 비슷하게 조립하는 방식으로 대체하지 않습니다. 절차적 생성은 사용자가 명시적으로 요청한 경우에만 사용하며, 기존 모델의 가져오기·부분 수정은 재생성 없이 처리합니다.

LLM은 제공된 이미지나 사용 가능한 이미지 생성 도구로 참조를 준비합니다. 런타임 자체에는 텍스트→이미지 서비스가 없습니다. **Godot 검사는 대상 프로젝트에 필요할 때, 웹 뷰어는 사용자가 인터랙티브 미리보기나 웹 검증을 요청할 때만** 사용합니다. LLM의 기본 모델 검토에는 브라우저가 필요하지 않습니다.

**생성 provider와 편집 방식은 별개입니다.** LLM이 요청과 모델을 보고 리그 없는 object 동작, SkinTokens 리깅 초안, Blender 스크립트로 리그·가중치·재질·사용자 동작 편집, 클립 병합을 선택합니다. 기본 편집은 API 없이 로컬에서 수행하며 필요한 모델만 설치합니다. Tripo 생성물을 고친다고 Tripo 후처리를 다시 호출하지 않습니다. GeoSAM2 부품 분리와 유료 Tripo 후처리는 필요한 작업에서 선택합니다.

**Kimodo는 사용자가 “Kimodo로 동작을 만들어 줘”라고 명시한 작업에서만 사용합니다.** 일반 애니메이션 요청은 기존 클립·리그와 Blender 편집·프리셋 중 용도에 맞게 처리합니다. Kimodo가 설치되어 있거나 편집이 어렵다는 이유로 자동 선택하지 않습니다.

## 문서

| 하려는 일 | 읽을 문서 |
| --- | --- |
| 설치된 시스템으로 첫 에셋 만들기 | [QUICKSTART.md](QUICKSTART.md) |
| 새 PC에 설치하거나 LLM에게 설치 맡기기 | [INSTALL.md](INSTALL.md) — Windows/Linux, 영어 |
| 유료 Tripo 단일 이미지·멀티뷰 사용하기 | [Tripo 가이드](docs/TRIPO.md) — 키 설정·비용·중단 복구 |
| 리깅·애니메이션·자동 부품 분리 | [캐릭터 후처리](docs/CHARACTERS.md) — 기본 로컬 처리·선택적 Tripo |
| 사용자 동작·리그 수정·클립 합치기 | [Blender 편집](docs/BLENDER.md) — 생성 provider와 독립적인 로컬 작업 |
| 표면 손상 원인 찾기·마감 방법 재사용 | [마감 진단](docs/FINISHING.md) — 원본·처리 단계 비교와 조건별 복구 예시 |
| 명시적으로 선택한 로컬 사람 모션 생성 | [Kimodo](docs/KIMODO.md) — 선택 설치·기존 리그 적용·클립 누적 |
| 기능·동작의 사용 조건과 품질 검사 | [품질 명세](docs/QUALITY.md) — 표현 방식·재생 정책·핵심 시점·검사 범위 |
| 저장소 수정·유지보수하기 | [AGENTS.md](AGENTS.md) — 에이전트 작업 지침 |
| 구성·데이터·검증 상태 이해하기 | [아키텍처](docs/ARCHITECTURE.md) |
| 연결·설치·생성 오류 해결하기 | [문제 해결](docs/TROUBLESHOOTING.md) |
| 에셋 요청을 처리하는 스킬 읽기 | [3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md) |
| LLM용 문서 목차 찾기 | [llms.txt](llms.txt) |

다른 LLM에게 설치를 맡길 때는 저장소 URL과 함께 이렇게 요청하면 됩니다:

> 이 저장소의 INSTALL.md와 AGENTS.md를 읽고, 내가 지정한 폴더에 기본 설치해 줘. 스킬을 연결하고 참조 이미지로 TRELLIS.2 모델을 만든 다음 렌더 이미지를 직접 검사해 줘.

## 지금 되는 것

| 기능 | 현재 범위 |
| --- | --- |
| 기본 이미지→3D | trellis.cpp의 TRELLIS.2, 단일 참조 이미지, NVIDIA GPU |
| Tripo API (명시적 선택) | 단일 이미지 또는 정면 포함 2–4방향 참조, 유료 표준 PBR 모델 생성 |
| 절차적 모델링 | 사용자가 명시적으로 요청한 블록아웃·치수 기반 조립체 등의 대안 |
| 가져오기 | `.glb`, `.blend`; `character`로 리그·클립 보존, `animated`로 리그 없는 object/morph 동작 보존 |
| 부분 수정 | 정적 메시의 실제 부품 이름 기준 이름·크기·위치·재질·노멀·작은 간격 용접 |
| 기본 로컬 리깅 | SkinTokens의 학습된 골격·스킨 가중치 추론, 원본 메시 전달 |
| 기본 로컬 동작 | 실제 뼈에 Blender IK로 `idle`·`walk`·`run`, 다른 클립을 보존하며 누적 |
| 학습된 로컬 사람 모션 (명시적 선택) | Kimodo `text-motion`, 관찰한 뼈 대응으로 기존 리그에 적용·클립 보존; 별도 모델/인코더 설치 필요 |
| Blender 스크립트 편집 | object 동작·사용자 모션·리그·가중치·재질을 새 revision에서 작성 |
| 클립 병합 | 같은 모델/리그의 revision·외부 GLB 클립을 하나의 GLB로 전달 |
| 클립 보존 비교 | `compare-animations`: 수정 대상으로 선언한 클립 외의 시간·보간·변환과 모델 데이터 비교, Blender 불필요 |
| 용도별 품질 검토 | 선택적 `assess`: 기능·재생 명세, 루프·활동량 검사, 같은 핵심 시점의 다각도 렌더와 미검토 범위 |
| 기본 로컬 부품 분리 | LLM이 렌더에서 부품별 점 지정 → GeoSAM2 마스크 → 개별 결과 검토 |
| Tripo 후처리 (명시적 선택) | 유료 이족 리깅·프리셋 동작·의미 분리 베타 |
| 버전 보존 | 새 revision에 수정 결과 저장, 원본과 parent 연결 유지 |
| 결과물 | 편집 가능한 `.blend`, 자체 포함 GLB, 5방향 PNG, 검사·출처 기록 |
| Godot (선택) | 대상 프로젝트에 필요한 import·메시·재질·충돌체 검사 |
| Three.js 웹 (선택) | 요청한 경우 회전·확대, 와이어프레임, 버전 전환, GLB 다운로드 |
| 에이전트 연결 | CLI, 개인 스킬 연결, 선택적 stdio MCP 어댑터 |

**현재 제한:** `process` 동작은 절차적 이족 프리셋이고, Kimodo는 별도의 로컬 학습 모션 경로입니다. Kimodo의 대응 기반 적용은 체형에 따른 접지·그립·루프를 자동 해결하지 않으며 텍스트 인코더에 Hugging Face 모델 접근 권한이 필요합니다. 범용 자동 리타게팅 해법, TRELLIS 멀티뷰, 자동 리토폴로지·텍스처 재베이크는 제공하지 않습니다. 부품 이름·경계·재질과 동작 품질은 실제 렌더로 확인하며 분류하지 못한 면은 보존합니다. 멀티뷰 메시 생성은 Tripo 옵션에서만 지원합니다.

수치 검사 통과와 시각 품질 통과는 별도입니다. Godot import나 Three.js 렌더 성공도 실제 게임의 동작·아트 품질까지 보증하지 않습니다.

여러 애니메이션은 **클립별로 필요한 참고 → 제작 → 다각도·재생 검토 → 수정·재검사**를 진행하고 한 GLB에 모읍니다. 생성 자세 시트에서 같은 자세가 반복되거나 좌우·접촉 순서가 모순되면 부족한 자료를 보완하고, 이미지로 판단하기 어려운 부분은 기존 모션·영상으로 확인합니다. 동작 수가 많다는 이유로 전체 참고를 한두 장에 압축하지 않습니다. [품질 가이드](docs/QUALITY.md#여러-클립의-개별-완성)를 참고하세요.

개별 클립 수정 후에는 [보존 비교](docs/BLENDER.md#개별-클립-수정과-보존-비교)로 나머지 동작과 모델의 변경 여부를 확인할 수 있습니다. 데이터가 달라졌다는 결과는 원인을 살펴볼 신호이며, 재샘플링된 동작의 실제 자세·타이밍 비교나 시각 검토를 대신하지 않습니다.

## 빠르게 시작하기

처음 설치할 때는 [INSTALL.md](INSTALL.md)를 따릅니다. 기본 설치는 **TRELLIS + 모델 가중치 + Blender**이며, Godot·Node.js·웹 빌드는 포함하지 않습니다.

학습된 리깅 초안·분리가 필요할 때 [로컬 후처리 모델](INSTALL.md#local-postprocessing-on-demand)을 추가합니다. 정적 수정·object 동작·사용자 스크립트·클립 병합은 기존 Blender로 실행합니다. 모든 소품에 리그를 만들거나 모델을 다운로드하지 않습니다.

사용자가 Tripo 전용 설치를 선택하면 Python·Blender·API 키만으로 사용할 수 있어 로컬 CUDA와 TRELLIS 가중치는 필요하지 않습니다. 입력 이미지가 Tripo로 업로드되며 유료 크레딧이 소모됩니다. “Tripo로 만들어 줘”라고 요청하면 에셋당 표준 생성 1회를 자동 진행합니다. 예상 비용은 30크레딧, 기본 비용 가드는 100이며 별도 입력·재승인이 필요하지 않습니다. 상세 범위는 [Tripo 가이드](docs/TRIPO.md)에 있습니다.

설치가 끝났다면 [QUICKSTART.md](QUICKSTART.md)의 참조 이미지 요청 JSON을 `.work/asset.json`에 준비하고 저장소 루트에서:

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli generate .work/asset.json --async
```

완료 후 로컬 PNG를 LLM이 확인하고 GLB·편집 원본을 전달합니다. 웹 미리보기를 원할 때만 [선택 설치](INSTALL.md#optional-project-checks-and-viewer) 후 `start-viewer.cmd` 또는 `sh start-viewer.sh`를 실행합니다.

개인 스킬 연결 후 에이전트에 요청하는 예:

> `$3d-assets` 나무 보물상자를 12,000 삼각형 이하로 만들고, 렌더를 직접 확인해서 GLB로 전달해 줘.

> `$3d-assets` 기존 검의 grip만 버건디색으로 바꾸고 이전 버전은 보존해 줘.

> `$3d-assets` Tripo3D로 이 정면·후면 이미지를 사용해 상자를 만들고 렌더를 검사해 줘.

> `$3d-assets` 이 캐릭터를 리깅하고 걷기 동작을 넣어 줘. 관절 움직임을 검사해서 GLB로 전달해 줘.

> `$3d-assets` 이 모델의 부품을 자동으로 분리하고 직접 렌더를 보고 이름을 붙여 줘.

스킬 폴더만 복사하면 런타임이 설치되지는 않습니다. 다른 게임 프로젝트에서 쓰려면 [INSTALL의 스킬 연결 절차](INSTALL.md#4-connect-the-agent-skill)를 따릅니다.

## 검증 현황

2026-09-15 기준 v0.1 구현에서 확인한 결과:

- 기존 Windows/Linux 테스트 및 웹 빌드 통과. 검사 항목은 CI에서 확인할 수 있습니다.
- 클립 비교 도구의 변경·재샘플링·보간·가중치·morph·CLI/MCP 테스트 19개를 통과했습니다. 실제 7클립 캐릭터 GLB의 수정 전후 비교에서도 의도된 1클립 변경과 나머지 6클립·모델 데이터 보존을 구분했습니다. 데이터 보존 검사이며 시각 품질 재승인은 아닙니다.
- Windows 로컬과 Linux CI에서 실제 Blender 생성·두 종류 수정·원본 보존·GLB 재가져오기·Godot 검사 통과.
- RTX 5090에서 F16 모델, 해상도 512의 TRELLIS 생성 1회 약 79초. 전체 후처리 시간이나 다른 GPU의 성능 기준은 아닙니다.
- 실제 브라우저에서 상자·검·AI 생성 상자와 수정 버전 로드 확인. AI 상자의 남은 구멍·색 차이는 시각 검토 실패로 기록했습니다.
- Linux의 TRELLIS GPU 추론은 아직 검증하지 않았습니다.
- 로컬 GeoSAM2 실제 추론에서 원본 18,984삼각형을 보존하고 10개 관찰 이름과 미분류 영역을 저장했습니다. 전체·개별 렌더 검토에서 일부 누락·오분류가 남아 의미 부품 품질은 초안으로 기록했습니다. 원본은 기존 Tripo 모델이고 이번 후처리는 API 없이 실행했습니다.
- SkinTokens는 좀비 모델(46뼈)과 Tripo와 무관한 Microsoft Rocketbox 성인 모델(80뼈)에서 실제 추론·전 정점 가중치·원본 보존·5방향 정지 외관 검토를 통과했습니다. 성인 모델의 동작은 아직 실행하지 않았습니다.
- 좀비의 로컬 `idle`·`walk`·`run`은 최종 GLB의 조밀한 바닥 검사와 9개 동작 렌더에서 프로토타입 외관·변형 검토를 통과했습니다. 짧은 보폭의 기본 동작이며 발 미끄러짐 방지·발뒤꿈치부터 구르는 보행·연속 충돌 검사는 구현하지 않았습니다. [로컬 검증 상세](docs/CHARACTERS.md#검토와-현재-검증-범위)를 참고하세요.
- Kimodo는 RTX 5090에서 실제 문장으로 4초·120샘플의 모션을 생성하고 기존 46뼈 캐릭터에 적용했습니다. 기존 네 동작과 새 인사를 한 GLB로 전달하며 원본 클립 데이터를 그대로 보존합니다. 4방향·확대 검토와 보정을 수행했으나 테스트 캐릭터의 손·머리 간섭과 팔 변형은 남아 시각 품질 실패로 기록했습니다. [검증 범위](docs/KIMODO.md#유지보수-검사)를 참고하세요.
- Tripo 단일 이미지 생성 1회(실제 30크레딧)와 의미 분리 1회(40크레딧)를 실행했습니다. 분리된 13개 영역을 전체·개별 렌더로 확인하고 새 revision에서 이름을 지정했습니다. 일부 영역은 서로 붙어 있거나 절단면이 열려 있습니다.
- Tripo 리깅(25크레딧)과 걷기(10크레딧)는 실제 API부터 GLB 출력까지 확인했습니다. 41뼈·스킨·걷기 클립과 렌더는 정상 출력되었지만, 걷기의 바닥 관통은 원격 원본에도 남아 시각 품질 실패로 기록했습니다. `idle`·`run`, 멀티뷰, TRELLIS 대비 품질·속도 비교는 미검증입니다. [후처리 검증 상세](docs/CHARACTERS.md#검토와-현재-검증-범위)를 참고하세요.

[최근 CI 결과](https://github.com/NA-DEGEN-GIRL/3d-asset-auto/actions/workflows/check.yml)를 참고하세요. 예제 JSON은 Git에 포함하지만 생성된 모델·참조 이미지·로컬 실행 기록은 포함하지 않습니다. 새 clone의 에셋 목록은 비어 있습니다.

위 Godot·웹·절차적 예제 검사는 구현을 확인한 개발 기록이며 모든 에셋 작업에 반복할 단계가 아닙니다.

## 저장과 의존성

`.runtime/`에는 포터블 도구와 모델, `.assets/`에는 에셋과 작업 기록, `.work/`에는 임시 작업·검증 결과·뷰어 로그가 저장됩니다. Tripo 키 파일은 `.secrets/`에 둘 수 있습니다. 모두 Git에서 제외됩니다. 생성 결과를 보존하려면 `.assets/`를 별도로 백업합니다.

코어 다운로드 버전과 모델 revision은 [scripts/bootstrap.py](scripts/bootstrap.py)에 고정되어 있고, 선택적 리깅·분리·Kimodo는 각 설치 가이드의 별도 pin과 의존성 lock을 사용합니다. 실제 SHA256·출처는 `.runtime/installed/`에 기록됩니다. 기본 TRELLIS 설치는 약 16.5 GB의 모델 파일과 도구·압축파일·출력 공간이 추가로 필요하며 선택 모델은 별도입니다.

- [Blender](https://www.blender.org/): 모델링·검사·렌더·GLB 출력.
- [trellis.cpp](https://github.com/pwilkin/trellis.cpp) / [TRELLIS.2](https://github.com/microsoft/TRELLIS.2): 이미지 기반 생성.
- [GGUF 모델](https://huggingface.co/ilintar/trellis2-gguf): 고정 revision의 F16 가중치.
- [Tripo API](https://developers.tripo3d.ai/en/docs): 명시적으로 선택하는 유료 클라우드 생성.
- [SkinTokens](https://github.com/VAST-AI-Research/SkinTokens) / [GeoSAM2](https://github.com/VAST-AI-Research/GeoSAM2): 필요할 때 설치하는 로컬 리깅·부품 분리 모델.
- [Kimodo](https://github.com/nv-tlabs/kimodo): 선택 설치하는 로컬 텍스트→사람 모션 모델과 기존 리그 적용.
- [Godot](https://godotengine.org/) / [Three.js](https://threejs.org/): 엔진·웹 검증.

도구·모델 가중치와 DINOv3/BiRefNet 같은 구성 요소의 라이선스는 각각 확인해야 합니다. 이 저장소는 실행 파일이나 모델 가중치를 재배포하지 않습니다.
