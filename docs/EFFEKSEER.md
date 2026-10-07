# Effekseer VFX

**한국어** | [English](EFFEKSEER.en.md)

Effekseer는 입자·리본·링·모델의 형태와 시간 흐름을 편집하는 VFX 제작 도구와 재생 런타임입니다. `game-vfx`의 선택 경로로 사용하며, AI 생성 모델이나 모든 프로젝트의 필수 의존성으로 취급하지 않습니다. 사용자가 선택하거나 대상 프로젝트에 적합한 통합이 있을 때 우선 검토하고, 기존 엔진 효과 시스템도 계속 활용할 수 있습니다.

## 적용 범위와 파일

- 편집 가능한 `.efkefc`와 참조 텍스처·모델·재질 등을 함께 보존합니다. `.efkproj`는 호환 입력으로 사용할 수 있으나, 공식 도구로 읽기·변환하고 실제 재생까지 확인합니다.
- 웹에는 Effekseer WebGL 런타임, Godot에는 해당 버전의 플러그인이 필요합니다. 효과 파일이 있다는 이유로 엔진 기본 입자 시스템이나 GLB로 자동 변환되지는 않습니다.
- 재생에 필요한 상대 경로와 리소스 목록을 유지합니다. 효과 전체가 GLB라는 요청이면 기존 [형식 선택 지침](../.agents/skills/game-vfx/references/workflow.md#delivery-format-constraints)을 따릅니다.

파일 형식과 명령행의 공식 계약은 [도구 참조](https://effekseer.github.io/Help_Tool/en/ToolReference/index.html)를 확인합니다. 공급된 예제·기존 프로젝트를 바탕으로 제작할 때는 의도한 레이어와 사건을 먼저 정하고, 색상 변경만으로 요청한 새 동작을 완성했다고 판단하지 않습니다.

XML 입력의 스키마와 버전 메타데이터는 서로 맞아야 합니다. 구조를 이전하지 않고 구형 프로젝트의 `ToolVersion`만 설치한 편집기 버전으로 바꾸면, 변환은 성공해도 노드가 보이지 않을 수 있습니다. 호환되는 원본 메타데이터를 유지해 공식 도구로 변환하고, 출력 파일의 존재 대신 실제 재생에서 노드가 유지됐는지 확인합니다.

렌더러 enum을 숫자로 작성할 때는 고정한 버전의 형식을 확인합니다. 1.80.7의 billboard `2`는 `Fixed`, `3`은 `RotatedBillboard`입니다. 지면 접촉 평면에 후자를 쓰면 회전값을 지정해도 카메라를 향할 수 있으므로 다른 시점에서 정렬을 확인합니다.

## 설치와 변환

[`scripts/effekseer.py`](../scripts/effekseer.py)가 네이티브 Windows·Linux x86_64 편집기와 WebGL 배포의 **1.80.7** 버전 및 다운로드 검증을 관리합니다. 설치는 `.runtime/effekseer/1.80.7/`에 보관하며, Godot 플러그인을 자동 설치하지 않습니다. Windows는 `editor/`와 `editor.install.json`, Linux는 `editor-linux/`와 `editor-linux.install.json`을 사용해 기존 Windows 설치 기록을 보존합니다. 아래 명령은 저장소 루트에서 실행합니다.

```text
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> doctor
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> install --component all
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> export --input <absolute-source.efkproj> --output <absolute-new-output.efkefc>
uv run --no-sync python scripts/effekseer.py --root <absolute-runtime-root> model --input <absolute-existing-mesh.obj> --output <absolute-new-model.efkmodel> --scale 1
```

Linux에서 프로젝트 가상환경을 준비한 뒤에는 다음처럼 직접 실행할 수도 있습니다. 공식 Linux 배포에 자체 포함 .NET 런타임이 들어 있으므로 별도 .NET SDK·Mono·Wine은 필요하지 않습니다. `libGLU.so.1` 등 네이티브 공유 라이브러리는 필요하며, Ubuntu에서 이 파일이 누락되면 `sudo apt-get install libglu1-mesa`로 설치합니다. `doctor`는 실행 파일과 CUI에서도 로드하는 `libViewer.so`의 해시·네이티브 의존성, 실행 권한을 검사합니다.

```bash
.venv/bin/python scripts/effekseer.py install --component all
.venv/bin/python scripts/effekseer.py doctor
```

필요한 경우 `install --component editor` 또는 `webgl`만 선택합니다. `doctor`는 설치 상태를 확인할 뿐 시각 검수를 대신하지 않습니다. `export`의 `.efkefc` 출력은 공식 도구의 `-cui -in … -o …`를 사용합니다. 이 순수 변환 경로는 GUI·그래픽 장치 초기화·재질 캐시 생성을 하지 않으며 전역 CPU 정책을 적용합니다. Linux에서 `DISPLAY` 없이 실제 변환을 확인했습니다. 스레드 환경변수는 모든 네이티브 스레드 수를 강제하는 장치가 아니고, 지원되지 않는 Windows CPU affinity도 적용됐다고 보고하지 않습니다. 렌더링은 아래의 별도 자원 확인이 필요합니다.

`model`은 기존 `.obj` 또는 `.glb`를 공식 리소스 변환기로 처리하는 네이티브 Windows·Linux x86_64 CPU 경로입니다. `--scale`은 양수이며 기존 출력과 provenance 파일의 덮어쓰기를 거부합니다. 최소 OBJ의 실제 변환과 출력 헤더 검사를 확인했지만, 이는 임의 모델의 외형·재질·리그 보존 검증을 대신하지 않습니다. 모델용 재질·텍스처·렌더러 설정은 별도로 구성합니다.

## GPU와 개인 자원 설정

| 단계 | 자원과 주의점 |
| --- | --- |
| 소스 XML·리소스 작성, 파일 검사 | CPU·파일 작업입니다. CUDA 모델이나 GPU 메모리 추론이 필요하지 않습니다. |
| 명령행 변환 | 위 helper의 순수 변환은 CPU 경로입니다. 일반적인 `-cui` 사용이나 다른 도구의 재질 캐시·녹화까지 GPU를 쓰지 않는다고 일반화하지 않습니다. |
| Windows 편집기·미리보기 | 공식 요구사항에 DirectX 11이 포함됩니다. 일반 입자도 화면에 그리는 그래픽 자원을 사용합니다. |
| Linux 편집기·미리보기 | OpenGL과 디스플레이·그래픽 백엔드가 필요합니다. 헤드리스 파일 변환의 성공은 GUI 실행이나 렌더 검증을 뜻하지 않습니다. |
| WebGL 재생 | 브라우저의 그래픽 컨텍스트를 사용합니다. CPU에서 입자를 계산하는 것과 GPU 없이 렌더링하는 것은 다릅니다. |
| Effekseer의 `GPU Particles` 기능 | 별도 GPU 시뮬레이션 기능입니다. 현재 공식 지원표에서 WebGL·Godot 통합은 미지원이므로, 이 경로에서는 일반 입자를 사용하고 설치한 버전의 지원표를 다시 확인합니다. 이는 Godot 자체의 GPU 입자 기능에 대한 제한이 아닙니다. |

[실행 환경 요구사항](https://effekseer.github.io/Help_Tool/en/overview.html)과 [GPU 입자 지원표](https://effekseer.github.io/Help_Tool/en/ToolReference/gpuParticles.html)를 기준으로 선택합니다. 이 저장소의 고정 버전과 다른 최신 런타임을 혼용하지 않습니다.

[개인 자원 정책](RESOURCES.md)은 그대로 적용합니다. Blender는 기존 보호 실행기를 사용하며, Effekseer 편집기와 브라우저의 DirectX/OpenGL/WebGL 장치 선택은 별도로 확인해야 합니다. `CUDA_VISIBLE_DEVICES`나 Blender의 CPU 제한은 이들 렌더러의 GPU 선택·동시 실행을 보장하지 않습니다. 제약을 강제할 수 없는 호스트에서 보호 GPU를 사용하지 않는다고 추정하거나 정책을 완화하지 말고, 확인 가능한 CPU 파일 작업과 렌더 검증 상태를 구분해 보고합니다. 지정 장치가 바쁘면 다른 장치로 우회하지 않습니다.

## 별도 모델이 필요할 때

운석·특징적인 얼음 덩어리·소환물처럼 독립된 실체 메시가 필요하면 기존 모델을 먼저 재사용합니다. 새 모델이 필요한 경우에만 [`3d-assets`](../.agents/skills/3d-assets/SKILL.md)로 연결합니다. 참조 이미지와 TRELLIS.2가 기본이며 Tripo는 명시적 선택이 필요합니다. Effekseer의 리본·링·스프라이트나 단순 VFX용 절차 형상을 만들기 위해 추론을 강제하지 않습니다.

Blender에서 필요한 메시를 다듬고 좌표·단위·원점·노멀·UV를 확인한 뒤 Effekseer의 모델 입력으로 변환합니다. 공식 [모델 렌더러](https://effekseer.github.io/Help_Tool/en/ToolReference/rendererModel.html)는 GLB·glTF·FBX·OBJ 등을 `.efkmodel`로 변환하는 경로를 설명합니다. 원본과 변환 파일을 보존하고, 실제 사용 버전에서 크기·방향·외형·리소스 경로를 검증합니다. 일반 GLB의 전체 PBR 재질·리그·이름 있는 애니메이션이 그대로 재생된다고 가정하지 않습니다. 캐릭터는 엔진에 그대로 두고 효과를 장착점에 붙이는 구성이 적합할 수 있습니다.

## 제작·검토·통합

참고 자료에서 채택한 형태·사건·리듬에 맞춰 노드를 구성합니다. 효과마다 발동·최대 표현·접촉·소멸을 검토하고, 같은 순간을 여러 각도에서 확인합니다. 평면 스프라이트는 유효한 재료지만 공간 효과 전체를 한 장의 영상으로 대체하지 않습니다. 기존 [효과별 검토 루프](../.agents/skills/game-vfx/references/workflow.md#per-effect-quality-loop)를 그대로 적용합니다.

대상 런타임에서 로딩, 재생·정지·재시작, 인스턴스 수명과 공유 리소스 해제를 확인합니다. 깊이·블렌딩·왜곡·포스트프로세싱 및 동시 효과 비용도 대상 프로젝트에서 검증합니다. 화면상의 충돌 효과는 실제 지형 충돌이나 피해 판정의 증거가 아닙니다. 웹 미리보기 성공과 [Godot 플러그인](https://github.com/effekseer/EffekseerForGodot4) 검증은 별도이며, 요청한 대상만 연결합니다.

## 네 가지 마법 예제 재현

[`examples/effekseer/author_demo.py`](../examples/effekseer/author_demo.py)는 고정 배포에 포함된 CC0 효과를 변형해 불·얼음·번개·비전 마법을 구성하고, 얼음용 절차적 결정 메시를 작성합니다. 새 AI 이미지·영상이나 유료 추론은 실행하지 않습니다. 실제 Effekseer 효과 파일과 WebGL 런타임을 사용하며, 효과의 접촉·파쇄 시점은 저작된 연출입니다. 런타임 물리 충돌이나 참조 영상 복원으로 보고하지 않습니다.

Windows PowerShell에서 저장소 루트를 기준으로 실행합니다. 위의 설치와 프로젝트 웹 의존성 준비가 선행되어야 합니다. `revision-name`은 새 작업 이름으로 바꾸고, 출력 폴더를 재사용해 이전 결과를 덮어쓰지 않습니다.

```powershell
uv run --no-sync python examples/effekseer/author_demo.py --samples .runtime/effekseer/1.80.7/editor/Effekseer1.80.7Win/Sample --out .work/effekseer-demo/revision-name
uv run --no-sync python scripts/effekseer.py model --input .work/effekseer-demo/revision-name/effects/ice/Model/crystal.obj --output .work/effekseer-demo/revision-name/effects/ice/Model/crystal.efkmodel --scale 1
foreach ($effect in @('fire', 'ice', 'lightning', 'arcane')) {
    uv run --no-sync python scripts/effekseer.py export --input ".work/effekseer-demo/revision-name/effects/$effect/source.efkproj" --output ".work/effekseer-demo/revision-name/effects/$effect/effect.efkefc"
    if ($LASTEXITCODE -ne 0) { throw "Effect export failed: $effect" }
}
node examples/effekseer/build.mjs --runtime .runtime/effekseer/1.80.7/webgl --effects .work/effekseer-demo/revision-name --out .work/effekseer-demo/revision-name-site
python -m http.server 8784 --bind 127.0.0.1 --directory .work/effekseer-demo/revision-name-site
```

Linux Bash에서는 네이티브 배포의 `Sample` 경로를 사용합니다. 아래 명령은 디스플레이 없이 제작·변환하며, 각 명령의 실패 시 중단합니다.

```bash
set -e
.venv/bin/python examples/effekseer/author_demo.py --samples .runtime/effekseer/1.80.7/editor-linux/Effekseer1.80.7Linux/Sample --out .work/effekseer-demo/revision-name
.venv/bin/python scripts/effekseer.py model --input .work/effekseer-demo/revision-name/effects/ice/Model/crystal.obj --output .work/effekseer-demo/revision-name/effects/ice/Model/crystal.efkmodel --scale 1
for effect in fire ice lightning arcane; do
    .venv/bin/python scripts/effekseer.py export --input ".work/effekseer-demo/revision-name/effects/$effect/source.efkproj" --output ".work/effekseer-demo/revision-name/effects/$effect/effect.efkefc"
done
```

각 단계가 성공한 뒤 다음 단계로 진행합니다. 예제의 웹 미리보기가 요청된 경우에만 PowerShell 예제 마지막의 `node` 빌드와 HTTP 서버 명령을 실행합니다. Linux에서도 같은 빌드 명령을 쓰고 서버는 `.venv/bin/python -m http.server …`로 실행합니다. 포트가 사용 중이면 빈 포트를 선택하고, 서버에는 빌드한 site만 제공합니다. [`build.mjs`](../examples/effekseer/build.mjs)는 효과·리소스·런타임과 라이선스 고지를 복사하며 원본 XML·OBJ와 비공개 provenance JSON은 제외합니다. Windows에서 백그라운드 서버를 띄울 때는 숨김 창과 readiness 확인을 사용합니다.

이 절차는 재현 가능한 제작·변환·미리보기 경로이며, 예제의 시각적 완성도나 실제 게임 성능이 자동 승인됐다는 뜻은 아닙니다. 효과별 실제 재생과 다각도 검토 결과는 해당 작업 기록에 남깁니다.

예제 뷰어의 시간 이동은 인스턴스를 다시 만들고 정상 재생과 같은 60 Hz 시뮬레이션 시계로 전체 컨텍스트를 진행합니다. 수명이 짧은 모델과 여러 인스턴스에서 개별 핸들의 프레임 설정이 다른 결과를 내던 문제를 피합니다. 정지된 사건 시점과 정상 재생은 여전히 각각 확인해야 하며, 네이티브 렌더 결과만으로 WebGL 재질 표현까지 확인했다고 판정하지 않습니다.

## 라이선스와 기록

이 저장소의 [Effekseer 예제 소스](../examples/effekseer/LICENSE.txt)는 MIT이며, 빌드한 사이트에도 해당 고지를 포함합니다. 이 고지는 외부 효과·텍스처·모델의 라이선스를 바꾸지 않습니다.

공식 런타임은 MIT이고 공식 배포의 효과·텍스처 데이터는 CC0로 안내됩니다. 배포물의 라이선스·의존성 고지와 실제 사용한 자료의 출처를 보존합니다. 커뮤니티 효과, 별도 텍스처, 3D 모델이나 생성 서비스 출력까지 같은 조건이라고 일반화하지 않습니다. [공식 라이선스 안내](https://effekseer.github.io/Help_Tool/en/overview.html#license)

다운로드한 도구, 모델, 생성 효과와 렌더·장치 기록은 로컬 작업 폴더에 두고 자동으로 Git에 추가하지 않습니다. 실제 설치/변환/렌더 성공, 시각적 완성도, 다른 엔진의 호환성을 구분해서 보고합니다.
