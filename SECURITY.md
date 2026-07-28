# 보안

## 신고 경로

보안 문제는 이 저장소의
[GitHub Security Advisories](https://github.com/yakisoba0728/srt-mobile-api/security/advisories/new)
로 비공개 신고해 주시면 됩니다("Security" 탭 → "Report a vulnerability"). 수정이
준비될 때까지 신고자와 저장소 소유자 사이에서만 열리는 경로입니다. 취약점으로
의심되는 사안을 공개 이슈로 열어서는 안 됩니다.

재현에 필요한 최소한의 정보만, 살균한 뒤에 적어야 합니다. 자격증명, 쿠키, 토큰,
NetFunnel 키, PNR, 서버 원본 응답, 운영 식별자는 공개 이슈·토론·로그·픽스처·커밋
어디에도 남기면 안 됩니다.

## 신고자가 지켜야 할 선

취약점을 확인하겠다고 실제 서비스 상태를 바꾸면 안 됩니다. 아래 넷 모두
금지입니다.

- **실제 상태 변경으로 재현하지 않습니다.** 예약·취소·결제·환불을 실제로 일으켜
  문제를 보여서는 안 됩니다. 재현은 `dry_run` 미리보기와 오프라인 테스트로 합니다.
- **과금되는 카드를 쓰지 않습니다.** 실카드 번호는 어떤 형태로도 보내면 안 됩니다.
- **본인 계정만 씁니다.** 타인 계정, 타인 승차권, 타인 PNR 을 대상으로 삼으면
  안 됩니다.
- **아래의 게이트를 우회하려 시도하지 않습니다.** 허용 범위 밖 mutation 실행이나
  승인 없는 운영 요청도 마찬가지입니다.

## 이 패키지가 무엇을 막는가

| 겹 | 막는 것 |
| --- | --- |
| consent 객체 | 범주별 `MutationConsent` 에 `dry_run=False` 가 들어 있을 때만 상태를 바꾸는 요청이 만들어집니다. 기본값은 미리보기입니다. |
| 범주·라우트 결합 | `assert_mutation_route` 와 `assert_mutation_route_category` 가 대상 라우트를 호출자의 범주에 묶습니다. 한 범주의 consent 로 다른 범주의 엔드포인트를 겨눌 수 없습니다. |
| 전송 계층 | `post_mutation_form` 과 그 아래의 `_send_mutation_request` 가 `safety.SRT_LIVE_MUTATION_CATEGORIES`(정확히 `{"reserve", "cancel", "payment", "refund"}`) 밖의 범주를 전부 거부합니다. |
| 카드 비밀값 | consent 는 `fake_card_only` 와 `real_card_acknowledged` 중 정확히 하나를 밝혀야 하고, `assert_no_card_secrets` 가 요청 **본문**에서 PAN·카드 비밀번호·유효기간·생년월일이 `payment` 로만 이동하도록 강제합니다. |

좌석을 따로 잡거나 고르는 메서드는 없습니다 — 좌석지정은 `reserve` 의 인자이고
같은 라우트·같은 consent 를 탑니다. 읽기 전용 가드는 네 mutation 라우트를
allowlist 로 거부합니다. 마지막 겹이 본문을 보기 때문에, 손으로 조립한 카드 폼이
읽기 라우트나 정상적인 `reserve`/`cancel` consent 를 타고 나가지 못합니다.

## 이 게이트들이 서 있는 근거의 범위

네 mutation 의 전문(wire shape)은 모두 srtgo 에서 왔고, v2.0.41 오프라인 번들
21,673 파일에서 0건입니다. 실서버로 확인된 것은 각 범주당 한 번, 성인 1명·편도
1건 규모뿐입니다. 그 한 번이 건드리지 않은 필드에는 정적 근거가 없습니다. 이
범위를 넘는 동작을 이 패키지가 보장한다고 읽어서는 안 됩니다.
