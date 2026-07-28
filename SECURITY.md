# 보안

## 신고 경로

보안 문제는 이 저장소의
[GitHub Security Advisories](https://github.com/yakisoba0728/srt-mobile-api/security/advisories/new)
로 비공개 신고한다 — "Security" 탭 → "Report a vulnerability". 이 경로는 수정이
준비될 때까지 신고자와 저장소 소유자 사이에서만 열린다. 취약점으로 의심되는
사안을 공개 이슈로 열지 마라.

재현에 필요한 최소한의 정보만, 그것도 살균한 뒤에 적는다. 자격증명, 쿠키, 토큰,
NetFunnel 키, PNR, 서버 원본 응답, 운영 식별자는 공개 이슈·토론·로그·픽스처·커밋
어디에도 남기지 마라. 진단 출력을 공유하기 전에 그런 값을 지우거나 대체한다.

## 신고자가 지켜야 할 선

취약점을 확인하겠다고 실제 서비스 상태를 바꾸지 마라. 아래 넷 모두 금지다.

- **실제 상태 변경으로 재현하지 않는다.** 예약·취소·결제·환불을 실제로 일으켜서
  문제를 보이려 하지 마라. 재현은 `dry_run` 미리보기와 오프라인 테스트로 한다.
- **과금되는 카드를 쓰지 않는다.** 실카드 번호를 어떤 형태로도 보내지 마라.
- **본인 계정만 쓴다.** 타인 계정, 타인 승차권, 타인 PNR 을 대상으로 삼지 마라.
- **아래의 게이트를 우회하려 시도하지 않는다.** 허용 범위 밖 mutation 을
  실행하거나 승인 없는 운영 요청을 보내는 것도 마찬가지다.

## 이 패키지가 무엇을 막는가

상태를 바꾸는 요청은 범주별로 명시된 `MutationConsent` 가 있고 그 안에
`dry_run=False` 가 들어 있을 때만 나간다. 좌석 점유·좌석지정에는 클라이언트
메서드 자체가 없다. 예약(`reserve`), 취소(`cancel`), 카드결제(`pay_with_card`),
환불(`refund`) 네 가지는 각각 consent 로 잠긴 메서드를 가지며, 기본값은 미리보기다.
자기 범주에 대한 non-dry-run consent 가 있을 때만 실제로 전송된다.

전송 경로(`post_mutation_form`, 그 아래의 `_send_mutation_request`)는
`safety.SRT_LIVE_MUTATION_CATEGORIES` 밖의 범주를 전부 거부한다. 이 집합은 정확히
`{"reserve", "cancel", "payment", "refund"}` 다. 두 함수 모두 대상 라우트를
호출자의 범주에 묶으므로(`assert_mutation_route` 와
`assert_mutation_route_category`), 한 범주의 consent 로 다른 범주의 엔드포인트를
겨눌 수 없다. 읽기 전용 가드는 네 mutation 라우트를 allowlist 로 거부한다.

결제에는 두 겹이 더 있다. consent 는 `fake_card_only` 와
`real_card_acknowledged` 중 정확히 하나를 밝혀야 하고, `assert_no_card_secrets`
는 요청 **본문**에 대해 PAN·카드 비밀번호·유효기간·생년월일이 `payment` 로만
이동할 수 있게 강제한다. 본문을 보는 이 검사가 손으로 조립한 카드 폼이 읽기
라우트나 정상적인 `reserve`/`cancel` consent 를 타고 나가는 것을 막는다.

## 이 게이트들이 서 있는 근거의 범위

네 mutation 의 전문(wire shape)은 모두 srtgo 에서 왔고, v2.0.41 오프라인 번들
21,673 파일에서 0건이다. 실서버로 확인된 것은 각 범주당 한 번, 성인 1명·편도 1건
규모뿐이다. 그 한 번이 건드리지 않은 필드에는 정적 근거가 없다. 이 범위를 넘는
동작을 이 패키지가 보장한다고 읽지 마라.
