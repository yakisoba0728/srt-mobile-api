<!--
실제 자격증명, 쿠키, NetFunnel 키, PNR, 카드 형태의 값, SRT 서버 원본 응답을 이
pull request 나 그 커밋에 붙여넣으면 안 됩니다. 공개됩니다. tests/fixtures/ 아래
픽스처는 살균하거나 재구성한 것이어야 하고 원본 캡처여서는 안 됩니다 —
CONTRIBUTING.md 의 "픽스처" 절을 보시면 됩니다.
-->

## 무엇을 바꾸는가

<!-- 한두 문장. -->

## 근거

<!--
CONTRIBUTING.md 의 "주장 말고 근거"에 따라, 라우트·필드·기본값·서버 동작에 관한
주장에는 번들 근거(file:line 인용), 실서버 검증(날짜 + 서버 확인 코드), 추론(그렇게
표시할 것) 중 하나가 필요합니다. 여기에 해당하는 등급을 밝혀 주십시오.
-->

## mutation consent·안전 모델을 건드리는가

<!--
`consent.py`, `safety.py`, `MutationConsent`, `assert_mutation_route`,
`assert_mutation_route_category`, `assert_no_card_secrets`,
`SRT_LIVE_MUTATION_CATEGORIES` — 하나도 건드리지 않았다면 이 절을 지우면 됩니다.
건드렸다면 CONTRIBUTING.md 의 "mutation consent·안전 모델을 바꿀 때" 절을 읽고
답해 주십시오.
-->

- [ ] 네 게이트(consent 객체 / `dry_run` / 범주별 opt-in / 전송 계층 차단 스위치)
      중 무엇을 어떻게 바꾸는가?
- [ ] `SRT_LIVE_MUTATION_CATEGORIES` 를 넓힌다면: 그것을 검증한 실서버 왕복의
      날짜와 확인 코드.
- [ ] 카드 비밀값을 나르는 필드를 더한다면: 같은 PR 안에서
      `assert_no_card_secrets` 와 `SENSITIVE_KEYS` 가 그것을 덮는지 확인.

## 체크리스트

- [ ] `python3 -m pytest -q -m "not live"` 가 로컬에서 통과합니다.
- [ ] 이 변경 과정에서 라이브 요청을 하지 않았습니다.
- [ ] 자격증명, 쿠키, NetFunnel 키, PNR, 카드 형태의 값, 원본 응답이 픽스처를
      포함해 이 diff 어디에도 없습니다.
- [ ] 새로 하드코딩한 개수(테스트 개수, 라우트 개수 등)는 손으로 유지하는 대신
      테스트가 유도합니다.
