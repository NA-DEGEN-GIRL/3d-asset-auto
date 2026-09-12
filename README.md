# 3D Asset Auto

LLM에게 게임용 3D 소품의 생성·수정·검증을 요청할 수 있는 로컬 도구입니다. **에이전트 스킬 → JSON 요청 → TRELLIS.2 / Blender → GLB → Godot·Three.js 검증**으로 연결됩니다.

자연어 해석은 LLM이 담당하고, 런타임은 검증된 JSON을 실행합니다. 웹은 에셋을 보고 다운로드하는 뷰어입니다. 웹 채팅이나 자체 텍스트→이미지 생성 기능은 포함하지 않습니다.

## 문서

| 하려는 일 | 읽을 문서 |
| --- | --- |
| 설치된 시스템으로 첫 에셋 만들기 | [QUICKSTART.md](QUICKSTART.md) |
| 새 PC에 설치하거나 LLM에게 설치 맡기기 | [INSTALL.md](INSTALL.md) — Windows/Linux, 영어 |
| 저장소 수정·유지보수하기 | [AGENTS.md](AGENTS.md) — 에이전트 작업 지침 |
| 구성·데이터·검증 상태 이해하기 | [아키텍처](docs/ARCHITECTURE.md) |
| 연결·설치·생성 오류 해결하기 | [문제 해결](docs/TROUBLESHOOTING.md) |
| 에셋 요청을 처리하는 스킬 읽기 | [3d-assets/SKILL.md](.agents/skills/3d-assets/SKILL.md) |
| LLM용 문서 목차 찾기 | [llms.txt](llms.txt) |

다른 LLM에게 설치를 맡길 때는 저장소 URL과 함께 이렇게 요청하면 됩니다:

> 이 저장소의 INSTALL.md와 AGENTS.md를 읽고, 내가 지정한 폴더에 기본 설치해 줘. 스킬을 연결하고 첫 상자를 생성해서 Godot와 웹에서 확인해 줘. GPU 생성까지 쓸 경우 TRELLIS와 모델도 추가 설치해 줘.

## 지금 되는 것

| 기능 | 현재 범위 |
| --- | --- |
| 절차적 모델링 | 상자·검 등 치수와 이름 있는 부품을 가진 소품 |
| 이미지→3D | trellis.cpp의 TRELLIS.2, 단일 참조 이미지, NVIDIA GPU |
| 가져오기 | 정적 `.glb`, `.blend` |
| 부분 수정 | 실제 부품 이름 기준 크기·위치·재질·노멀·작은 간격 용접 |
| 버전 보존 | 새 revision에 수정 결과 저장, 원본과 parent 연결 유지 |
| 결과물 | 편집 가능한 `.blend`, 자체 포함 GLB, 5방향 PNG, 검사·출처 기록 |
| Godot | 실제 import·인스턴스 생성·메시·재질·볼록 충돌체 검사 |
| Three.js 웹 | 회전·확대, 와이어프레임, 버전 전환, 렌더·검토 메모, GLB 다운로드 |
| 에이전트 연결 | CLI, 개인 스킬 연결, 선택적 stdio MCP 어댑터 |

**아직 없는 것:** 리깅, 애니메이션, 다중 이미지 조건 생성, 자동 의미 부품 분리, 애니메이션용 리토폴로지, 텍스처 재베이크. 생성된 메시가 단일 오브젝트라면 “손잡이만 수정” 같은 의미 기반 선택을 바로 할 수 없습니다.

수치 검사 통과와 시각 품질 통과는 별도입니다. Godot import나 Three.js 렌더 성공도 실제 게임의 동작·아트 품질까지 보증하지 않습니다.

## 빠르게 시작하기

처음 설치할 때는 [INSTALL.md](INSTALL.md)의 기본 설치부터 진행합니다. Blender와 Godot만으로 GPU 모델을 받지 않고 전체 소품 흐름을 확인할 수 있습니다. AI 생성은 이후 추가합니다.

설치가 끝났다면 저장소 루트에서:

```sh
uv run --no-sync python -m asset_auto.cli doctor
uv run --no-sync python -m asset_auto.cli generate examples/chest.json
```

Windows는 `start-viewer.cmd`, Linux는 `sh start-viewer.sh`로 뷰어를 켜고 **http://127.0.0.1:8765/**를 엽니다. Windows 런처는 숨겨진 백그라운드 서버를 실행하며, 이미 실행 중이면 재사용합니다. PC를 재부팅하면 다시 실행해야 합니다.

개인 스킬 연결 후 에이전트에 요청하는 예:

> `$3d-assets` 나무 보물상자를 12,000 삼각형 이하로 만들고 Godot와 웹에서 확인해 줘.

> `$3d-assets` 기존 검의 grip만 버건디색으로 바꾸고 이전 버전은 보존해 줘.

스킬 폴더만 복사하면 런타임이 설치되지는 않습니다. 다른 게임 프로젝트에서 쓰려면 [INSTALL의 스킬 연결 절차](INSTALL.md#4-connect-the-agent-skill)를 따릅니다.

## 검증 현황

2026-09-12 기준 v0.1 구현에서 확인한 결과:

- Python 테스트 15개, Windows/Linux 테스트 및 웹 빌드 통과.
- Windows 로컬과 Linux CI에서 실제 Blender 생성·두 종류 수정·원본 보존·GLB 재가져오기·Godot 검사 통과.
- RTX 5090에서 F16 모델, 해상도 512의 TRELLIS 생성 1회 약 79초. 전체 후처리 시간이나 다른 GPU의 성능 기준은 아닙니다.
- 실제 브라우저에서 상자·검·AI 생성 상자와 수정 버전 로드 확인. AI 상자의 남은 구멍·색 차이는 시각 검토 실패로 기록했습니다.
- Linux GPU 추론은 아직 검증하지 않았습니다.

[최근 CI 결과](https://github.com/NA-DEGEN-GIRL/3d-asset-auto/actions/workflows/check.yml)를 참고하세요. 예제 JSON은 Git에 포함하지만 생성된 모델·참조 이미지·로컬 실행 기록은 포함하지 않습니다. 새 clone의 에셋 목록은 비어 있습니다.

## 저장과 의존성

`.runtime/`에는 포터블 도구와 모델, `.assets/`에는 에셋과 작업 기록, `.work/`에는 임시 작업·검증 결과·뷰어 로그가 저장됩니다. 모두 Git에서 제외됩니다. 생성 결과를 보존하려면 `.assets/`를 별도로 백업합니다.

다운로드 버전과 모델 revision은 [scripts/bootstrap.py](scripts/bootstrap.py)에 고정되어 있고, 실제 SHA256·출처는 `.runtime/installed/`에 기록됩니다. 전체 설치는 약 16.5 GB의 모델 파일과 도구·압축파일·출력 공간이 추가로 필요합니다.

- [Blender](https://www.blender.org/): 모델링·검사·렌더·GLB 출력.
- [trellis.cpp](https://github.com/pwilkin/trellis.cpp) / [TRELLIS.2](https://github.com/microsoft/TRELLIS.2): 이미지 기반 생성.
- [GGUF 모델](https://huggingface.co/ilintar/trellis2-gguf): 고정 revision의 F16 가중치.
- [Godot](https://godotengine.org/) / [Three.js](https://threejs.org/): 엔진·웹 검증.

도구·모델 가중치와 DINOv3/BiRefNet 같은 구성 요소의 라이선스는 각각 확인해야 합니다. 이 저장소는 실행 파일이나 모델 가중치를 재배포하지 않습니다.
