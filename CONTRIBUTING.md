# 기여 안내

## 시작하기 전에

이 클라이언트는 실제로 운영 중인 공공 서비스를 리버스 엔지니어링한 것이다.
mutation(`reserve`, `cancel`, `pay_with_card`, `refund`,
`register_discount_coupon`)에 닿는 코드를 쓰기 전에 [SECURITY.md](SECURITY.md)
와 [README.md](README.md) 의 "안전 모델" 절을 읽어라.
평소 개발 과정에서 `app.srail.or.kr` 로 실제 요청을 보내지 마라 — 이 저장소의
릴리스 절차 자체가 그것을 금지하며([docs/RELEASE.md](docs/RELEASE.md)), pull
request 에 실요청이 들어가서는 안 된다.

## 작업 흐름

1. Python 3.11 이상.
2. `python3 -m pip install -e ".[dev]"` — `dev` 는 `test` 에 아래 두 도구를 더한
   것이다. 테스트만 돌릴 거면 `".[test]"` 도 그대로 쓸 수 있다.
3. 변경한다.
4. pull request 를 열기 전에 세 게이트가 로컬에서 모두 통과해야 한다. CI 에는
   라이브 서비스 단계가 없고, 앞으로도 있어서는 안 된다.

   | 게이트 | 명령 | 통과 조건 |
   | --- | --- | --- |
   | 테스트 | `python3 -m pytest -q -m "not live"` | 전부 통과 |
   | Lint | `ruff check .` | 0건 |
   | 타입 | `pyright` | 오류 0 |

5. pull request 를 연다. CI 는 Linux 의 Python 3.11–3.14 와 macOS 1회, Windows
   1회에서 오프라인 테스트를 돌리고, 위 두 게이트와 배포물 빌드 검사를 함께
   돌린다. 전부 초록이어야 한다.

### lint·타입 게이트에 대해

둘 다 설정을 `pyproject.toml` 에서만 읽으므로, 편집기(Pylance + Ruff 확장,
`.vscode/extensions.json` 참고)가 CI 와 똑같은 것을 보여 준다. 규칙에 이견이
있으면 `[tool.ruff.lint]` 나 `[tool.pyright]` 의 해당 항목 옆 주석과 다퉈라.
주석마다 무엇을 측정했고 왜 그렇게 정했는지가 적혀 있다.

이미 정해진 것이 둘 있고, 조용히 뒤집지 마라.

- **`ruff format` 은 쓰지 않는다.** 이 코드베이스의 손으로 맞춘 주석 표와 근거
  블록이 곧 문서인데 포매터가 그것을 다시 쓴다. 게이트는 `ruff check` 이고
  포매팅은 게이트가 아니다.
- **pyright 는 `basic` 모드로 돌되 모듈 단위 `strict` 목록을 둔다.** 그 목록은
  취향이 아니라 이미 `strict` 에서 오류 0을 기록한 모듈 전부이며, 파일마다
  pyright 를 한 번씩 돌리면 다시 유도된다. 목록에 모듈을 추가하는 것은 환영이고,
  목록에 있는 모듈을 실패하게 만드는 것은 회귀다.

`-m "not live"` 는 정확히 테스트 하나를 뺀다. 라이브 서비스 스모크 테스트이고,
`SRT_MOBILE_API_LIVE=1` 과 실제 SRT 계정 자격증명을 따로 요구한다. CI 는 그
변수를 설정하지 않으며, pull request 도 이 테스트를 돌릴 필요가 없다.

## 주장 말고 근거

이 코드베이스의 라우트, 필드명, 기본값, 응답 모양에는 전부 출처가 달려 있고 새로
추가하는 것도 그래야 한다. 등급은 셋이며, 코드와 docstring 이 어느 등급인지
밝힌다.

- **번들 근거(bundle-evidenced)** — SRT 안드로이드 앱을 디컴파일해서 얻고
  `file:line` 으로 인용한다(예: `ara0101v.js:317-326`). 같은 APK 를 디컴파일하면
  누구나 재현한다.
- **실서버 검증(live-verified)** — 실제 서버로 확인했고, 날짜와 서버가 준 확인
  코드(예: `SUCC`/`IRG000000`)를 `docs/VERIFICATION.md` 나 `CHANGELOG.md` 에
  기록했다.
- **추론(inferred)** — 인접 근거(형제 필드의 철자, 참조 클라이언트의 전문 형식)
  에서 추론했고, 확정된 것처럼 쓰지 않고 *추론이라고 표시*한다. 한 본문에 등급이
  섞인 필드가 있을 때는 `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` 를 본떠라.

라우트나 필드를 더하거나 서버 동작에 관해 주장하는 변경에는 이 셋 중 하나가
docstring 이나 커밋 메시지에 적혀 있어야 한다. "테스트가 통과한다"는 근거가
아니다. 전문 형식을 찾는 데 서드파티 참조 클라이언트(srtgo, srtgo_plus 등)를
썼다면 그렇다고 밝히고 `docs/analysis/ref-srtgo_plus.md` 가 하는 방식으로
인용하라 — *프로토콜에 관한 사실*의 출처로만 쓰고, 베껴 올 소스 코드로는 쓰지
않는다. 그 구분이 왜 여기서 중요한지는 `NOTICE` 에 있다.

## mutation consent·안전 모델을 바꿀 때

"보기엔 괜찮은데" 가 가장 통하지 않는 부분이다. `reserve`, `cancel`,
`pay_with_card`, `refund`, `register_discount_coupon` 은 독립된 네 겹(consent
객체, `dry_run`, 범주별 opt-in, 전송 계층 차단 스위치
`safety.SRT_LIVE_MUTATION_CATEGORIES`)으로 잠겨 있고, 그 구조는 README 의
"안전 모델" 에 있다. `consent.py`, `safety.py`,
`MutationConsent`, `assert_mutation_route`, `assert_mutation_route_category`,
`assert_no_card_secrets`, `SRT_LIVE_MUTATION_CATEGORIES` 중 하나라도 건드린다면

- **어느 게이트를 왜 바꾸는지** 코드 diff 가 아니라 네 겹 모델의 언어로 적어라.
  "이 변경은 `reserve` consent 가 닿을 수 있는 범위를 넓힌다" 정도가 리뷰어에게
  필요한 문장이다.
- **`SRT_LIVE_MUTATION_CATEGORIES` 를 넓히는 것** — 실제로 전송될 수 있는 범주를
  더하는 것 — 은 실서버 왕복 검증을 요구한다. 날짜와 확인 코드까지, `reserve`/
  `cancel`(2026-07-25)과 `payment`/`refund`(2026-07-26)가 들어올 때와 같은
  방식으로. 번들 근거만으로는 이 저장소의 pull request 가 받지 않는다. 그 집합을
  고정하는 canary 테스트는 이 변경이 눈에 띄는 의도적 행위가 되게 하려고, 지나가는
  손질이 되지 않게 하려고 있다.
- **카드 비밀값**(`stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`, `athnVal1`)은 호출자가
  어떤 라우트·범주를 의도했는지가 아니라 요청 본문에서 `assert_no_card_secrets`
  가 계속 감시해야 한다. PAN, 비밀번호, 유효기간, 생년월일을 나르는 필드를 새로
  더한다면 같은 커밋 안에서 그 검사와 redaction 용 `SENSITIVE_KEYS` 에도 넣어라.
- 건드린 게이트를 깨뜨리려 드는 적대적 테스트를 더하거나 확장하라. 게이트가
  거부해야 할 때 클라이언트에서 0바이트가 나갔음을 단언하는 MockTransport 프로브,
  즉 `test_mutation_live_paths.py` 와 `test_payment_mutation.py` 가 이미 쓰는
  형태다.

## 개수를 손으로 유지하지 마라

이 저장소는 사람이 손으로 갱신하기로 하고 갱신하지 않은 숫자를 문서에 두 번
내보냈다(라우트 개수 한 번, 오프라인 테스트 개수 한 번). 저장소에 관한 개수를
문서가 주장한다면 — 테스트가 몇 개 통과하는지, 라우트가 몇 개 allowlist 에
있는지 — 그 숫자를 원본(`len(READ_ONLY_ROUTES)`, `pytest --collect-only`)에서
유도해 문서가 그 숫자를 적고 있는지 단언하는 테스트를 써라.
`tests/test_release_readiness.py` 와
`tests/test_safety.py::test_route_registry_has_exact_expanded_size` 가 그 방식이다.
이미 하드코딩된 숫자가 있는데 사본을 하나 더 만들지 마라.

## 픽스처

`tests/fixtures/` 아래의 테스트 픽스처는 실제 서버 응답을 살균하거나 재구성한
것이다. 원본 응답, 실제 PNR, 실제 자격증명, 쿠키, NetFunnel 키를 커밋하지 마라.
SR 의 자바스크립트가 렌더링하는 것에서 픽스처를 만든다면 파서를 돌리는 데 필요한
것만 남겨라 — 식별자, 필드명, 라우트, 테스트가 grep 하는 구조적 HTML/JS — 그리고
검사 대상이 아닌 실행 가능한 함수 본문은 걷어내라.
