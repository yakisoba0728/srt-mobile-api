# srt-mobile-api

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

SRT(수서고속철도) 안드로이드 앱이 쓰는 HTTP API 를 파이썬에서 그대로 부르는 클라이언트입니다.
앱과 같은 경로에 같은 폼 필드를 실어 조회·운임·좌석배치도를 읽고 예약·취소·결제·환불을 합니다.
설치 가능한 기본 읽기 전용 패키지이며, 상태를 바꾸는 요청은 호출마다 동의 객체를 명시하지
않으면 만들어지지도 않습니다.

> [!WARNING]
> - **리버스 엔지니어링 결과입니다.** SR 은 API 를 공개하지 않습니다. 경로·필드명·응답 형태는
>   SRT 앱 v2.0.41 디컴파일, 서버 렌더링 페이지, 서드파티 클라이언트 트래픽에서 복원했습니다.
> - **실서비스로 나갑니다.** 샌드박스는 없습니다. 요청은 당신의 실계정으로 `app.srail.or.kr`
>   에 가고, 여기서 만든 예약·결제·환불은 전부 진짜입니다.
> - **SR(에스알)과 무관합니다.** 제휴도 승인도 보증도 없습니다.

## 설치

| 항목 | 값 |
| --- | --- |
| 파이썬 | 3.11 이상 |
| 런타임 의존성 | `httpx` 하나 |
| 타입 | `py.typed` 동봉 |
| 라이선스 | Apache-2.0 |

PyPI 릴리스는 없습니다.

```bash
python3 -m pip install "srt-mobile-api @ git+https://github.com/yakisoba0728/srt-mobile-api"

# 고쳐 볼 생각이면 클론한 뒤
python3 -m pip install -e ".[test]"
python3 -m pytest -q -m "not live"      # 1769 passed, 1 deselected
```

빠진 하나는 `SRT_MOBILE_API_LIVE=1` 을 따로 요구하는 실서비스 테스트입니다. `-m "not live"`
는 CI 와 [docs/RELEASE.md](docs/RELEASE.md) 가 쓰는 게이트와 같습니다.

## 빠른 시작

전부 읽기입니다. 무엇도 만들지 않고 돈이 움직이지 않습니다.

```python
from srt_mobile_api import PassengerCounts, SrtClient, TrainSearchQuery

client = SrtClient()
client.login("you@example.com", "password")   # 이메일·휴대폰번호·회원번호 중 하나

query = TrainSearchQuery(
    departure_station_code="0551",            # 수서
    arrival_station_code="0015",              # 동대구
    departure_date="20260809",                # YYYYMMDD
    departure_time="060000",                  # HHMMSS — 이 시각부터 검색
    passengers=PassengerCounts(adult=1),
)
for train in client.search_trains(query).trains:
    print(train.train_no, train.departure_time,
          train.general_seat_availability_name)          # 예: "예약가능"

for reservation in client.get_reservations().reservations:   # 없으면 빈 리스트
    print(reservation.pnr_no)

client.close()
```

역 코드는 `srt_mobile_api.stations` 에 있습니다. `SrtClient()` 는 설정 없이 동작합니다.
`SrtConfig` 는 타임아웃·User-Agent·기기키용이며 `app.srail.or.kr` 와 NetFunnel
원점(`nf.letskorail.com`) 외의 주소는 거부합니다.

### 타입이 좁혀진 파라미터

셋은 export 된 `Literal` 별칭이라 오타가 타입 오류가 됩니다. 응답에서 읽어 온 코드는 좁히지
않고 `str` 그대로 둡니다.

| 별칭 | 값 |
| --- | --- |
| `SrtSeatAttrCode` | `"015"`, `"021"`, `"028"` |
| `SrtTrainGroupCode` | `"300"`, `"900"`, `"109"` |
| `MutationCategory` | `reserve`, `cancel`, `payment`, `refund`, `coupon` |

### `korail-mobile-api` 와 같이 쓸 때

두 패키지가 `TrainSearchQuery`, `DiscountCoupon`, `MutationCategory` 를 각자 export 하는데
호환되지 않습니다(`passengers` 는 여기 `PassengerCounts` / KORAIL `int`, `departure_time`
기본값은 여기 `"060000"` / KORAIL `"000000"`). 잘못 import 해도
타입 검사는 통과하고 요청만 틀리게 만들어지므로, 둘 다 쓴다면 `srt_mobile_api.TrainSearchQuery`
처럼 패키지를 붙여 써야 합니다.

## 무엇을 할 수 있나

전부 `SrtClient` 의 메서드이고, 각 docstring 이 근거(APK 파일·행 번호 또는 실 응답)를 답니다.

**읽기 — 동의가 필요 없습니다.**

| 메서드 | 하는 일 |
| --- | --- |
| `login` / `logout` / `clear_session` / `close` | 앱과 같은 순서의 로그인, 세션 종료, 로컬 상태 폐기, 연결 종료. |
| `search_trains` / `search_group_trains` / `search_transfer_trains` / `search_public_discount_trains` | 직통·단체(10명 이상)·환승·공공할인 조회. |
| `iter_train_search_pages(query, group=False, max_pages=10)` | 조회의 지연 페이지네이션. 커서가 끊기면 멈춥니다. |
| `get_timetable` / `get_fare` / `get_seat_page` / `get_seat_grid` | 정차역, 좌석 등급별 운임(여정 한 다리), 남은 호차, 좌석배치도. |
| `get_reservations` / `get_ticket_list` / `get_discount_coupons` / `get_public_discounts` | 예약 목록(타입이 붙은 유일한 읽기), 승차권 페이지, 보유 쿠폰, 승인받은 공공할인 자격. |
| `get_typed_notice_list` / `get_notice_list` / `get_main` / `get_station_selector` 외 | 공지(파싱본·원본)와 앱이 밟는 페이지·팝업 선택 화면들. |

**상태변경 — `consent: MutationConsent` 가 키워드로 필요하고, 기본 `dry_run=True` 에서는
`MutationPreview` 만 돌려줍니다.** [안전 모델](#안전-모델)을 먼저 읽어야 합니다.

| 메서드 | 하는 일 |
| --- | --- |
| `reserve(train, consent=...)` | 개인예약. 미결제 홀드와 PNR. 선택 인자로 `standby=True`(예약대기 `jobId=1102`), `round_trip=True`(왕복 `rtnDv=1`), `designated_seats=`(좌석지정 `jobId=1103`), `seat_attr_code=`. |
| `reserve_transfer(itinerary, ...)` | 환승. 요청 하나에 두 여정. |
| `cancel(hold_or_pnr, ...)` | 미결제 홀드 해제. 맨 PNR 로 취소할 때만 `journey_count` 를 직접 줍니다. |
| `pay_with_card(reservation, card, ...)` | 신용카드 결제. 동의 외에 카드 종류 주장이 하나 더 필요합니다. |
| `get_refund_ticket_info(pnr)` → `refund(ticket_info, ...)` | 환불. 앞은 읽기, 뒤가 상태변경입니다. |
| `register_discount_coupon(number, password, ...)` | 쿠폰 등록. 미리보기까지만 됩니다. |

맞지 않는 조합(예약대기를 제공하지 않는 행, 인원과 다른 좌석 수, 코레일 전용역이 낀 왕복)은
전송 전에 `ValueError` 로 막습니다.

## 안전 모델

상태를 바꾸는 요청은 네 관문을 전부 통과해야 나갑니다.

| 관문 | 내용 |
| --- | --- |
| 동의 객체 | 상태변경 메서드는 키워드 전용 `consent` 를 받습니다. 갓 만든 `MutationConsent()` 는 `allow_*` 가 전부 `False` 이고, 없거나 범주가 다르면 요청을 만들기도 전에 `SrtMutationNotAllowedError` 입니다. |
| 범주 | `reserve`, `cancel`, `payment`, `refund`, `coupon` 을 하나씩 켭니다. 동의는 경로에도 묶입니다. |
| `dry_run=True`(기본) | 폼을 만들어 검증한 뒤 `MutationPreview` 로 돌려주고 보내지 않습니다. 카드번호·비밀번호·생년월일·PNR·쿠폰번호·NetFunnel 키는 `[REDACTED]` 이며 `repr` 에서도 빠집니다. |
| 전송 차단 스위치 | `safety.SRT_LIVE_MUTATION_CATEGORIES` 가 동의와 무관하게 아래 표대로 검사합니다. |

| 범주 | 전송 | 실제로 확인된 범위 |
| --- | --- | --- |
| `reserve` | 예 | 성인 1명·1여정·일반실·직통 하나뿐. 다인원·예약대기·좌석지정은 미확인. |
| `cancel` | 예 | 위와 같은 홀드의 해제뿐. |
| `payment` | 예 | 개인카드 일시불 한 건뿐. 단체·법인카드·할부는 미확인. |
| `refund` | 예 | 위에서 결제한 그 승차권 한 건뿐. |
| `coupon` | **아니오** | 구현과 미리보기는 되지만, 답을 받아 본 적이 없습니다. |

검토된 읽기 전용 경로 26개가 허용목록의 전부이고 상태변경 경로 다섯 개는 그 바깥에 있어서
`assert_read_only_request` 가 구조적으로 거절합니다. 카드 비밀값(`stlCrCrdNo1`, `vanPwd1`,
`crdVlidTrm1`, `athnVal1`)은 경로가 아니라 본문에서 단속하므로 `payment` 로만 나갑니다.

```python
from srt_mobile_api import MutationConsent

preview = client.reserve(train, consent=MutationConsent(allow_reserve=True))
print(preview.route, preview.payload, preview.note)   # "dry-run: not sent"

# 아래는 미리보기가 아니라 실계정에 진짜로 좌석을 잡는 호출
hold = client.reserve(train, consent=MutationConsent(allow_reserve=True, dry_run=False))
print(hold.pnr_no)      # 미결제 홀드 — 이제 호출자 책임
```

결제는 카드 종류 주장을 하나 더 요구합니다. `fake_card_only=True`(과금되지 않는 테스트 카드,
기본값)와 `real_card_acknowledged=True`(실제 PAN, 돈이 움직임) 중 **정확히 하나**여야 하며,
둘 다 비워도 둘 다 세워도 거절합니다.

이 라이브러리는 NetFunnel 키를 다시 받는 경우를 빼면 스스로 재시도하지 않습니다. 예약은 절대
재시도하지 않습니다 — 재시도한 예약은 이중예약입니다.

## 에러 처리

실패는 이름 붙은 예외로 옵니다. 전부 `SrtApiError` 아래에 있고 서버가 준 `.code` 와 `.raw`
를 들고 있으며, 응답 코드를 예외로 옮기는 규칙은 export 된 `classify_app_error` 에 있습니다.

| 예외 | 상위 | 언제 |
| --- | --- | --- |
| `SrtApiError` | `Exception` | 모든 실패의 뿌리. |
| `SrtTransportError` | `SrtApiError` | 연결·타임아웃 등 응답을 받지 못한 실패. |
| `SrtProtocolError` | `SrtApiError` | 응답이 약속된 형태가 아니거나, 등록되지 않은 경로로 보내려 했을 때. |
| `SrtAuthError` | `SrtApiError` | 인증 계열의 뿌리. |
| `SrtSessionExpiredError` | `SrtAuthError` | 세션이 끊겼습니다. 다시 로그인하면 됩니다. |
| `SrtIpBlockedError` | `SrtAuthError` | 서버가 이 IP 를 막았습니다. |
| `SrtAppError` | `SrtApiError` | 서버가 정상 응답으로 돌려준 업무 오류. |
| `SrtNoResultsError` | `SrtAppError` | 요청은 정상이고 결과가 없습니다. |
| `SrtNoDirectTrainError` | `SrtNoResultsError` | 직통이 없습니다. 환승을 찾으면 됩니다. |
| `SrtSeatUnavailableError` | `SrtAppError` | 좌석이 없습니다. |
| `SrtInvalidRequestError` | `SrtAppError` | 서버가 요청 자체를 거절했습니다. |
| `SrtNetFunnelError` | `SrtApiError` | 대기열 계열의 뿌리. |
| `SrtNetFunnelKeyError` | `SrtNetFunnelError` | 대기열 키를 얻지 못했습니다. |
| `SrtQueueRejectedError` | `SrtNetFunnelError` | 대기열이 통과를 거부했습니다. |
| `SrtMutationNotAllowedError` | `SrtApiError` | 동의·범주·경로·전송 관문 중 하나가 막았습니다. |

## 한계

SRT 앱은 **WebView 껍데기**입니다. 화면 대부분이 서버 렌더링 HTML 이고 앱 자신의 결제 단계는
TransKey 키패드와 RaonSecure FIDO SDK 를 지나므로, 어느 HTTP 클라이언트도 재현하지 못합니다.

- **단체 예약** — 일부러 뺐습니다. 엔드포인트가 PNR 홀드가 아니라 서버 렌더링 결제 페이지를
  돌려줍니다. 조회는 그대로 남아 있습니다.
- **예약대기·왕복** — 구현되었고 실서비스로 확인된 적은 없습니다.
- **환승 예약** — 조회만 확인되었고, 둘째 슬롯 필드명 다섯 개는 유추입니다.
- **할인쿠폰 등록** — 구현되어 있으나 전송 관문이 닫혀 있습니다.
- **할인 승차권·청소년 조회** — 요청 형태에는 근거가 있고 효과는 미확인입니다.
- **앱의 WebView 결제 경로**(TransKey + FIDO), 네이티브 브리지, 외부 코레일 좌석도 — 제외.

무엇을 하면 각각이 확인되는지는 [docs/VERIFICATION.md](docs/VERIFICATION.md) 에 있습니다.

조회는 NetFunnel 대기열 뒤에 있고 이 클라이언트는 앱과 구별되지 않습니다. 반복문으로 조회를
두드리면 자신은 IP 차단을, 다른 사람들은 대기열 오염을 얻습니다.

## 문서

| 문서 | 무엇이 들어 있나 |
| --- | --- |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | 검증 기록. 확인 코드, 확정하지 **못한** 것, 모든 경로의 정적 출처. |
| [docs/IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md) | 구현 로그. |
| [docs/analysis/](docs/analysis/) | 정적 분석 산출물과 참조 클라이언트 대조 결과. |
| [docs/RELEASE.md](docs/RELEASE.md) | 릴리스 전에 돌리는 빌드·검증 게이트. |
| [SECURITY.md](SECURITY.md) | 자격증명 취급, 커밋하면 안 되는 것, 문제 신고 방법. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 오프라인 게이트 세 개와 변경에 필요한 근거 등급. |
| [CHANGELOG.md](CHANGELOG.md) / [NOTICE](NOTICE) | 변경 이력 / 참조 클라이언트를 어떻게 다뤘는지. |

운영용 스크립트는 `scripts/` 에 있습니다 — 읽기 전용 스모크, 원본 응답 저장, 예약·취소 왕복
검증, 떠 있는 홀드를 풀어 주는 `recover_hold.py`.

## 라이선스

Apache License 2.0. [LICENSE](LICENSE) 와 [NOTICE](NOTICE) 를 보면 됩니다. 이 프로젝트는
SR(수서고속철도)와 제휴·승인·후원 관계가 없으며, "SRT" 는 상호운용성을 설명하기 위해서만
썼습니다.
