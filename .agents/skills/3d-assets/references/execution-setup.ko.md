# 실행 위치와 최초 설치

**한국어** | [English](execution-setup.md)

## 필요한 항목부터 확인

사용자가 새 컴퓨터에 설치·설정을 요청하면 OS, 기존 런타임, Python,
필요한 도구를 먼저 조사한다. 모델 설치를 선택한 경우에만 GPU·저장 공간까지
확인한다. 기존 설치와 사용 가능한 인증을 재사용하고, 아직 결정되지 않은
설치 위치·선택 모델·인증만 사용자에게 묻는다. 이미 승인된 설치 범위의
일반적인 준비 명령을 매번 다시 확인하지 않는다.

API 키는 채팅으로 받지 않는다. 사용자가 지정한 비공개 키 파일이나 환경변수를
사용하고 읽기 전용 조회로 확인한다. 다른 컴퓨터로 키를 복사하려면 사용자의
승인이 필요하다. 결과에는 키 내용 대신 설정·인증 성공 여부만 기록한다.
Windows 실행 경로가 이미 있으면 새 키를 요구하기 전에 그쪽 doctor를 확인한다.
Linux로 인증을 복사하지 않고 기존 Windows 인증 경로를 사용할 수도 있다.

기본 실행 환경과 선택 모델 설치를 구분한다. CPU 서버에 도구가 설치됐다고
CUDA 추론까지 가능하다고 보고하지 않는다. 설치 편의 때문에 사용자가 선택한
모델·공급자를 바꾸지 않는다.

## OS별 기본 설치

스킬 폴더만 복사하지 말고 전체 런타임 체크아웃을 준비한다. 기존 설정·에셋·
작업 중인 변경은 보존한다. Windows와 Linux에서 각각 가상환경을 만든다.

```text
uv sync --locked --python 3.13
python .agents/skills/3d-assets/scripts/assetctl.py runtime-configure --root <이 OS의 런타임 절대경로> --execution auto
python .agents/skills/3d-assets/scripts/assetctl.py runtime-status
python .agents/skills/3d-assets/scripts/assetctl.py --execution local doctor
```

Linux에서는 사용 가능한 python3로 래퍼를 실행해도 된다.
등록은 가상환경·pyproject 존재를 확인하며 도구 설치나 추론 성공을 대신하지 않는다.
설정은 사용자별 ~/.config/codex-skill-runtimes/3d-assets.json
(XDG_CONFIG_HOME 지정 시 해당 경로)에 저장되어 같은 호스트의 프로필이 함께 쓴다.

3D 편집·애니메이션·GLB 처리에는 Blender를 준비한다. 화면 없는 Linux에서도
Cycles CPU 렌더를 사용할 수 있지만 실제 설치 버전으로 가져오기·내보내기·
렌더를 검증해야 한다. TRELLIS/CUDA, SkinTokens, GeoSAM2 및 명시적으로 선택한
Kimodo/Tripo는 저장소 INSTALL.md의 해당 설치만 따른다.
Blender 후처리 준비와 GPU 모델 생성 준비는 별개다.
일부 배포판 Blender는 OpenImageDenoiser가 빠져 CPU 미리보기 렌더가 실패한다.
이 경우 python scripts/bootstrap.py --only blender로 검증된 공식 포터블 버전을
런타임의 .runtime 아래에 설치하고 실제 렌더를 다시 확인한다. 시스템 패키지는 유지한다.

## 실행 위치 선택과 고정

- --execution local: 현재 호스트에 등록된 런타임을 사용한다.
  등록이 없으면 연결된 체크아웃을 사용한다. Windows 브리지가 있어도 직접 실행한다.
- --execution windows: SSH에서 Windows 브리지를 사용한다.
  연결이 없으면 오류로 끝내며 다른 곳에서 자동 실행하지 않는다.
  Windows에서 지정하면 Windows의 로컬 런타임을 사용한다.
- auto: 명시적으로 등록한 로컬 런타임을 우선한다.
  등록이 없으면 SSH의 기존 Windows 브리지 동작을 유지한다.
  이는 설치 위치 선택이며 모든 모델의 사용 가능성을 보증하지 않는다.
  doctor와 작업별 plan을 보고 에이전트가 실행할 호스트를 고른다.

작업에 필요한 기능, 원본 에셋 위치, 파일 전송 비용을 기준으로 선택한다.
서버의 파일 편집은 Linux에서, Windows에만 설치된 GPU 모델은 Windows에서
수행하는 식이다. Linux에서 부족하면 제출하기 전에 Windows 경로를 준비한다.
실패했거나 제출 결과가 불확실한 작업을 다른 호스트에서 자동 재실행하지 않는다.

선택한 후에는 제출·job·resume·inspect·후속 편집에 같은 --execution 값을
명시하고 작업 ID와 런타임 호스트·경로를 함께 기록한다.
호스트별 에셋·작업 저장소는 별개이며 Linux 등록이 Windows 기록을 옮기지 않는다.
작업을 옮기려면 입력을 전달하거나 결과를 내보내어 가져오며 원본 출처를 보존한다.

Windows 요청은 windows-bridge.md대로 입력을 올리고 Windows 경로로 바꾼 후
실행한다. 결과는 작업 중인 SSH 프로젝트로 가져온다. Linux 직접 실행에는
Linux 경로를 쓴다. 코딩 작업의 호스트를 바꾸지는 않는다.
Linux 직접 실행은 Windows 없이 동작하고, Windows 실행은 관리앱·터널이 필요하다.

## 확인과 유지보수

status/doctor 후 임시 자료로 작은 가져오기·편집·내보내기를 실제 실행하고
파일·해시를 확인한다. 모델 추론이나 시청각 품질 검수와 구분해 보고한다.
실제 API·모델 생성은 요청 범위 안에서 별도 검증한다.

실행 위치 결정은 래퍼에서 런타임 호출 전에 수행한다.
관리앱이 배포하는 SSH 지침·래퍼와 실제 Linux 환경은 별도 경로이므로
문서 갱신이 설치 환경이나 결과를 덮어쓰지 않는다.
이 계약 변경 시 래퍼 테스트와 영문 안내도 함께 갱신한다.
네이티브 런타임 코드·의존성은 별도 버전으로 관리한다. 새 스킬이 새 명령을
요구하면 해당 설치를 갱신하고 실제 실행 검증을 다시 한다.
지침 파일 동기화만으로 런타임까지 업그레이드됐다고 판단하지 않는다.
