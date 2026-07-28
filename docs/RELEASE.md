# 릴리스 게이트

이 저장소가 릴리스 전에 매번 돌리는 빌드·검증 절차다. 이 게이트를 통과했다고
운영 서비스로 요청을 보낼 권한이 생기는 것은 아니다 — 그 승인은 아래에 따로
기록된 별개의 결정이다. 여기서 말하는 "검증"은 오프라인 테스트와 깨끗한 패키지
빌드를 뜻하며, `app.srail.or.kr` 로는 한 번도 요청하지 않는다.

## 전제

- 추적 파일에 변경이 없는 워크트리에서 시작한다.
- Python 3.11 이상을 쓰고, 테스트·빌드 도구를 로컬에 설치한다.
- 이 게이트 동안 라이브 테스트는 금지다. 자격증명, 로컬 라이브 설정, 쿠키, 토큰,
  운영 응답 데이터를 어느 것도 불러오지 마라.

## 테스트·빌드·검증

저장소 루트에서 실행한다.

```bash
set -euo pipefail

artifact_dir=""
venv_dir=""
outside_dir=""
checkout="$PWD"

cleanup() {
  cd "$checkout" 2>/dev/null || true
  if [[ -n "$artifact_dir" ]]; then rm -rf "$artifact_dir"; fi
  if [[ -n "$venv_dir" ]]; then rm -rf "$venv_dir"; fi
  if [[ -n "$outside_dir" ]]; then rm -rf "$outside_dir"; fi
  rm -rf "$checkout/build" "$checkout/dist"
  find "$checkout" -type d -name '*.egg-info' -prune -exec rm -rf {} +
}
trap cleanup EXIT

python3 -m pip install -e ".[test]"
python3 -m pip install build
PYTHONPATH="$PWD/src" pytest -q -m "not live"

artifact_dir="$(mktemp -d)"
venv_dir="$(mktemp -d)"
outside_dir="$(mktemp -d)"
python3 -m build --wheel --sdist --outdir "$artifact_dir" .
wheel_path="$(find "$artifact_dir" -maxdepth 1 -name '*.whl' -print -quit)"
sdist_path="$(find "$artifact_dir" -maxdepth 1 -name '*.tar.gz' -print -quit)"
python3 scripts/verify_distribution.py "$wheel_path" "$sdist_path"
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install "$wheel_path"

checkout="$PWD"
cd "$outside_dir"
unset PYTHONPATH
"$venv_dir/bin/python" - <<PY
from pathlib import Path
import srt_mobile_api
from srt_mobile_api import SrtClient

package_path = Path(srt_mobile_api.__file__).resolve()
assert "site-packages" in package_path.parts
assert Path("$checkout").resolve() not in package_path.parents
print(SrtClient.__name__, package_path)
PY
cd "$checkout"
cleanup
trap - EXIT
```

검증기에는 wheel 하나와 sdist 하나가 정확히 들어가야 한다. 새 가상환경에서의
import 는 체크아웃 밖의 `site-packages` 에서 풀려야 한다.

## 정리

`EXIT` 트랩이 성공·실패를 가리지 않고 임시 디렉터리와 로컬 빌드 산출물을 지운다.
마지막의 명시적 `cleanup` 은 모든 검사가 통과한 뒤에야 그 트랩을 해제한다.

끝으로 `git status --short` 와 `git diff --check` 를 확인한다.

## 버전 정책

`1.0.0` 부터 semantic versioning 을 따른다. 호환되는 수정은 patch, 공개 API 에
대한 하위 호환 추가는 minor, 공개 API 를 깨는 변경은 major 다.

이 약속의 대상은 **이 라이브러리의 Python API 뿐이다** — `srt_mobile_api.__all__`,
반환 객체의 모양, 발생시키는 예외. SRT(에스알) 자체에 대한 약속은 아니고, 될 수도
없다. 모바일 앱의 라우트·필드명·응답 모양·업무 규칙은 예고 없이 바뀔 수 있다.
SR 은 문서화된 API 를 제공하지 않고 이 프로젝트에 호환성 의무도 없다. 이쪽의
patch 릴리스가 이 프로젝트가 관여하지도 선택하지도 않은 저쪽 변경 때문에 강제될
수 있다.

## 공개 배포 차단 항목

공개 배포는 네 항목이 갖춰지고 검토될 때까지 막혀 있었다. 라이선스, 소유자
메타데이터, 정본 URL, 명시적 승인이다. 2026-07-27 기준으로 넷 다 충족됐다.

- **라이선스.** `LICENSE` 는 Apache-2.0 원문을 그대로 담고, `pyproject.toml` 은
  PEP 639 SPDX 형식으로 `license = "Apache-2.0"` /
  `license-files = ["LICENSE", "NOTICE"]` 를 명시한다. `NOTICE` 가 함께 들어가는
  것은 Apache-2.0 §4(d) 가 재배포자에게 저작자 표시를 이어 나르게 하는데 그 파일이
  빠진 wheel 로는 그럴 수 없기 때문이다.
- **소유자 메타데이터.** `pyproject.toml` 의 `authors` 가 저장소 소유자
  (`yakisoba0728`)와 연락처를 밝힌다.
- **정본 URL.** `pyproject.toml` 의 `[project.urls]` 가
  `github.com/yakisoba0728/srt-mobile-api` 아래로 Homepage, Repository, Issues,
  Changelog URL 을 명시한다.
- **명시적 승인.** 저장소 소유자가 2026-07-27 이 저장소를 Apache-2.0 으로 GitHub
  에 공개하는 것을 명시적으로 승인했다.

`scripts/verify_distribution.py` 가 앞의 셋을 이 게이트의 일부로 강제한다.
빌드된 wheel 과 sdist 를 `pyproject.toml` 의 라이선스·저자·URL 값과 정확히
대조하므로, 값이 어긋난 배포물은 조용히 나가지 못하고 게이트에서 걸린다.
