# srt-mobile-api

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

SRT(수서고속철도) 안드로이드 앱이 쓰는 HTTP API 를 파이썬에서 그대로 부르는
클라이언트다. 앱과 같은 경로에 같은 폼 필드를 실어 열차를 조회하고, 운임과
좌석배치도를 읽고, 예약·취소·결제·환불을 하고, 할인쿠폰과 공공할인 자격을
확인한다. 설치 가능한 기본 읽기 전용 패키지이며, 상태를 바꾸는 요청은 호출마다
동의 객체를 명시하지 않으면 만들어지지도 않는다.

> [!WARNING]
> - **리버스 엔지니어링 결과다.** SR 은 API 를 공개하지 않는다. 여기 있는
>   경로·필드명·응답 형태는 SRT 안드로이드 앱 v2.0.41(21,673 파일)을 디컴파일하고,
>   로그인한 세션에 서버가 렌더링해 주는 페이지를 읽고, 둘 다 답하지 못한 곳은
>   서드파티 클라이언트의 실 트래픽에서 복원한 것이다.
> - **실서비스로 나간다.** 샌드박스는 없다. 요청은 당신의 실계정으로
>   `app.srail.or.kr` 에 가고, 이 라이브러리로 만든 예약·결제·환불은 전부 진짜다.
> - **SR(에스알)과 무관하다.** 제휴도 승인도 없고, 어떤 보증도 없으며, 이 중 무엇이
>   내일도 동작한다는 약속도 없다.

## 설치

Python **3.11 이상**. 런타임 의존성은 `httpx` 하나뿐이고, 패키지는 타입이 붙어
있으며 `py.typed` 를 함께 배포한다.

PyPI 릴리스는 없다. GitHub 에서 바로 설치한다.

```bash
python3 -m pip install "srt-mobile-api @ git+https://github.com/yakisoba0728/srt-mobile-api"
```

테스트와 문서까지 같이 두고 고칠 생각이면 클론해서 설치한다.

```bash
git clone https://github.com/yakisoba0728/srt-mobile-api
cd srt-mobile-api
python3 -m pip install -e ".[test]"
```

설치 확인은 네트워크를 쓰지 않는 오프라인 스위트로 한다.

```bash
python3 -m pytest -q -m "not live"
```

`HEAD` 에서 `1766 passed, 1 deselected` 가 나온다. 빠진 하나는 실서비스 테스트이며
그것만은 `SRT_MOBILE_API_LIVE=1` 을 따로 요구한다. `-m "not live"` 는 CI 와
[docs/RELEASE.md](docs/RELEASE.md) 가 쓰는 것과 같은 게이트다.

## 빠른 시작

로그인하고, 조회하고, 내 예약을 되읽는다. 아래는 전부 읽기다. 무엇도 만들지
않고 취소하지 않으며 돈이 움직이지 않는다.

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
    print(
        train.train_no,
        train.departure_time,
        train.arrival_time,
        train.general_seat_availability_name,  # 예: "예약가능"
    )

# 계정을 되읽는다. 예약이 하나도 없으면 빈 리스트이지 오류가 아니다.
for reservation in client.get_reservations().reservations:
    print(reservation.pnr_no)

client.close()
```

역 코드는 앱 자신의 표를 그대로 옮긴 `srt_mobile_api.stations` 에 있다
(`STATION_NAMES_BY_CODE`, `station_name_by_code`). `SrtClient()` 는 설정 없이
동작한다. `SrtConfig` 는 타임아웃·User-Agent·기기키를 손대기 위해서만 있고,
`app.srail.or.kr` 와 NetFunnel 원점(`nf.letskorail.com`) 외의 주소를 가리키면
거부한다.

### 타입이 좁혀진 파라미터

세 가지는 `str` 이 아니라 `Literal` 별칭이라, 편집기가 값을 자동완성하고 오타는
요청이 아니라 타입 오류가 된다. 셋 다 export 되므로 직접 만든 래퍼에도 붙일 수
있다.

| 별칭 | 값 | 쓰이는 곳 |
| --- | --- | --- |
| `SrtSeatAttrCode` | `"015"`, `"021"`, `"028"` | `reserve`, `reserve_transfer` |
| `SrtTrainGroupCode` | `"300"`, `"900"`, `"109"` | `TrainSearchQuery.train_group_code`, `get_train_group_selector` |
| `MutationCategory` | `reserve`, `cancel`, `payment`, `refund`, `coupon` | `require_mutation_consent` |

이 밖에는 좁히지 않았다. 응답에서 읽어 온 코드는 `str` 그대로다. 서버는 언제든
새 값을 만들어 낼 수 있기 때문이다.

### `korail-mobile-api` 와 같이 쓸 때

두 패키지는 `TrainSearchQuery`, `DiscountCoupon`, `MutationCategory` 세 이름을
각자 export 하는데 서로 호환되지 않는다. 잘못 import 해도 타입 검사는 통과하고
요청만 틀리게 만들어진다. 예를 들어 여기의 `TrainSearchQuery.passengers` 는
`PassengerCounts` 이고 `departure_time` 기본값이 `"060000"` 인 반면, KORAIL 쪽은
`passengers` 가 `int`(기본 `1`)이고 기본 출발시각이 `"000000"` 이다.
`MutationCategory` 도 여기는 다섯 값, KORAIL 은 일곱 값이다. 한 모듈에서 둘 다
쓸 거면 `from ... import` 대신 `srt_mobile_api.TrainSearchQuery` 처럼 패키지를
붙여 쓴다.

## 무엇을 할 수 있나

전부 `SrtClient` 의 메서드다. 각 메서드의 docstring 이 그 근거(APK 파일·행 번호
또는 실 응답)를 들고 있다.

### 세션

| 메서드 | 하는 일 |
| --- | --- |
| `login(login_id, password)` | 로그인 페이지 → 로그인 POST → 메인 → 예약 페이지까지 앱과 같은 순서로 밟는다. |
| `logout()` | 서버 세션을 끊는다. |
| `clear_session()` | 서버를 부르지 않고 로컬 쿠키와 세션 상태만 버린다. |
| `close()` | HTTP 연결을 닫는다. |

### 조회

| 메서드 | 하는 일 |
| --- | --- |
| `search_trains(query)` | 직통 개인 조회. `TrainSummary` 한 페이지. |
| `search_group_trains(query)` | 단체(10명 이상)의 잔여석과 운임. |
| `search_transfer_trains(query)` | 환승. 짝지어진 `TransferItinerary` 와, 짝을 못 찾은 구간을 이유와 함께 돌려준다. |
| `iter_train_search_pages(query, group=False, max_pages=10)` | 개인·단체 조회의 지연 페이지네이션. 서버가 준 커서가 끊기면 멈추고, `max_pages` 로 상한이 걸린다. |
| `search_public_discount_trains(query, discount)` | 공공할인이 승인된 계정의 할인 승차권 조회. |

### 열차 하나 들여다보기

| 메서드 | 하는 일 |
| --- | --- |
| `get_timetable(train)` | 그 열차의 정차역 목록. |
| `get_fare(train, passengers)` | 인원 구성으로 매겨진 좌석 등급별 금액. 생략하면 성인 1명으로 묻는다. 여정 한 다리만 읽는다 — 환승의 둘째 다리는 이 요청으로 물을 수 없어 자리표시자로 오고, 그것은 버린다. |
| `get_seat_page(train)` | 아직 좌석이 남은 호차(`SeatSelectionPage.cars`). |
| `get_seat_grid(train, car_number)` | 한 호차의 좌석배치도. 좌석마다 인쇄된 라벨과 선택 가능 여부가 붙는다. |

### 계정 읽기

| 메서드 | 하는 일 |
| --- | --- |
| `get_reservations(page_no=0)` | 예약을 행 단위로 열거하는 유일한 읽기. 타입이 붙어 있다. |
| `get_ticket_list(page_no=0)` | 옆에 있는 승차권 HTML 페이지. |
| `get_discount_coupons()` | 보유한 할인쿠폰. |
| `get_public_discounts()` | 이 계정이 승인받은 공공할인 자격. |
| `get_typed_notice_list()` / `get_notice_list()` | 공지. 앞은 파싱된 형태, 뒤는 원본 페이지. |
| `get_mutual_verification()`, `get_main()`, `get_booking_page()` | 앱이 로그인 직후 밟는 페이지들. |
| `get_station_selector()`, `get_station_map_selector()`, `get_date_selector()`, `get_passenger_selector()`, `get_seat_option_selector()`, `get_train_group_selector()` | 앱의 팝업 선택 화면 여섯 개. |

### 상태를 바꾸는 것

상태를 바꾸는 메서드는 전부 `consent: MutationConsent` 를 키워드로 요구하며,
기본값 `dry_run=True` 에서는 보낼 폼을 만들어 `MutationPreview` 로 돌려주고 아무
것도 내보내지 않는다. [안전 모델](#안전-모델)을 먼저 읽어라.

| 메서드 | 하는 일 |
| --- | --- |
| `reserve(train, consent=...)` | 개인예약. 미결제 홀드 하나를 만들고 PNR 을 담은 `SrtReservationHold` 를 준다. |
| `reserve(train, standby=True, ...)` | 예약대기(`jobId=1102`). 조회 행이 예약대기를 제공하지 않으면 `ValueError`. |
| `reserve(train, round_trip=True, ...)` | 왕복(`rtnDv=1`). 두 번째 요청은 보내지 않는다 — 가는 편과 오는 편을 각각 한 번씩 부르고, 오는 편 질의는 `TrainSearchQuery.for_return_leg` 가 만들어 준다. `jrnyCnt` 는 두 번 다 `"1"` 이고(`"2"` 는 환승이다) PNR 두 개 다 호출자 몫이다. 코레일 전용역이 끼거나 국회의원 후급 회원이면 보내기 전에 거절한다(`ara0101v.js:317-341`). |
| `reserve(train, seat_attr_code="021", ...)` | 휠체어석. `"028"` 은 전동휠체어, `"015"` 는 일반석이다. 생략하면 그 행을 **찾아낸** 코드를 그대로 쓴다. 조회 쪽 `TrainSearchQuery.seat_attr_code` 는 검증 없는 `str` 이지만, 예약은 이 셋만 받는다. |
| `reserve(train, designated_seats=..., ...)` | 좌석지정(`jobId=1103`). `SeatGrid.choose("1B", "2C")` 로 만든 `SeatDesignation` 을 넘긴다. 좌석 수가 인원과 다르거나 `standby`·`round_trip` 과 섞이면 전송 전에 `ValueError`. |
| `reserve_transfer(itinerary, consent=...)` | 환승. 요청 하나에 두 여정. |
| `cancel(hold_or_pnr, consent=...)` | 미결제 홀드 해제. 홀드는 자기가 만들어진 `jrnyCnt` 를 기억하므로 환승 홀드도 알아서 맞는다. 맨 PNR 로 취소할 때만 `journey_count` 를 직접 준다. |
| `pay_with_card(reservation, card, consent=...)` | 미결제 홀드를 신용카드로 결제한다. 동의만으로는 부족하고 카드 종류 주장을 하나 더 요구한다(아래 안전 모델). 할부는 `SrtPaymentCard.installment_months` 로 지정한다. |
| `get_refund_ticket_info(pnr)` → `refund(ticket_info, consent=...)` | 환불. 앞은 동의가 필요 없는 읽기이고 뒤가 상태변경이다. 환불 대상을 암묵적으로 조회하는 일이 없도록 일부러 갈라 놓았다. |
| `register_discount_coupon(number, password, consent=...)` | 할인쿠폰 등록. 미리보기까지만 되고 전송은 막혀 있다. |

## 안전 모델

이 라이브러리의 정체성은 여기에 있다. 상태를 바꾸는 요청은 네 개의 독립된 관문을
전부 통과해야 나간다.

**1. 동의 객체가 없으면 아무 일도 일어나지 않는다.** 상태변경 메서드는 전부
키워드 전용 `consent: MutationConsent` 를 받는다. 갓 만든 `MutationConsent()` 는
아무것도 허용하지 않는다 — `allow_*` 플래그가 전부 `False` 다. 없거나, 타입이
틀렸거나, 다른 범주의 동의를 넘기면 **요청을 만들기도 전에**
`SrtMutationNotAllowedError` 다.

**2. `dry_run=True` 가 기본이고, 미리보기를 돌려준다.** 기본 동의로 부르면 POST 할
폼을 그대로 만들어 검증한 뒤 `MutationPreview` 로 반환하고 **보내지 않는다**.
미리보기의 payload 는 생성 시점에 가려진다. 카드번호·비밀번호·생년월일·PNR·쿠폰
번호·NetFunnel 키가 `[REDACTED]` 이고, `repr` 에서도 같은 값이 빠진다.

```python
from srt_mobile_api import MutationConsent

preview = client.reserve(train, consent=MutationConsent(allow_reserve=True))
print(preview.route, preview.payload)
print(preview.note)      # "dry-run: not sent"
```

**3. 범주는 하나씩 켠다.** `reserve`, `cancel`, `payment`, `refund`, `coupon` 다섯
개다. `allow_reserve=True` 는 예약만 허가한다 — 취소도, 결제도, 쿠폰 등록도
아니다. 동의는 범주뿐 아니라 경로에도 묶이므로, `reserve` 동의를 환불
엔드포인트에 겨눌 수 없다.

**4. 전송 계층의 차단 스위치가 어떤 범주를 내보낼지 따로 정한다.**
`safety.SRT_LIVE_MUTATION_CATEGORIES` 는 상태변경 요청을 실제로 보낼 수 있는
단 두 곳에서, 동의와 무관하게 검사된다.

| 범주 | 전송 허용 | 실제로 확인된 범위 |
| --- | --- | --- |
| `reserve` | 예 | 성인 1명·1여정·일반실·직통 하나뿐. 다인원·다여정·예약대기·좌석지정은 미확인. |
| `cancel` | 예 | 위와 같은 성인 1명·1여정 홀드의 해제뿐. |
| `payment` | 예 | 성인 1명·1여정·일반실을 개인카드 일시불로 결제한 한 건뿐. 단체·법인카드·할부는 미확인. |
| `refund` | 예 | 위에서 결제한 그 승차권 한 건의 환불뿐. |
| `coupon` | **아니오** | 구현과 미리보기는 되지만, 답을 받아 본 적이 없다. |

이 집합에 든다는 것은 그 범주 자신의 전송 형식을 실서비스가 실제로 받아 주었다는
뜻이다. 할인쿠폰 등록은 미사용 쿠폰이 있어야 확인할 수 있는데 그런 쿠폰이 없어,
`dry_run=False` 쿠폰 호출은 전송 관문과 그 아래 송신 경계에서 두 번 거절된다. 이
집합은 전용 테스트가 고정하고 있으므로 넓히는 일은 의도적이고 눈에 보이는 행위가
된다.

그러니 실제로 보내는 코드는 이렇게 생겼고, **이 호출은 진짜로 좌석을 잡는다.**

```python
hold = client.reserve(
    train,
    passengers=PassengerCounts(adult=1),
    consent=MutationConsent(allow_reserve=True, dry_run=False),
)
print(hold.pnr_no)      # 실계정에 잡힌 미결제 홀드. 이제 당신 책임이다.
```

결제는 여기에 하나를 더 요구한다. 카드 종류를 모호하지 않게 밝혀야 한다 —
`fake_card_only=True`(과금되지 않는 테스트 카드, 기본값)와
`real_card_acknowledged=True`(실제 PAN, 돈이 움직임) 중 **정확히 하나**다. 둘 다
안 세워도 거절이고, 둘 다 세워도 거절이다.

그 아래에 경계가 둘 더 있다.

- **경로는 필터가 아니라 허용목록이다.** 검토된 읽기 전용 경로 26개가 목록의
  전부이고, 상태변경 경로 다섯 개는 일부러 그 바깥에 있다. 그래서
  `assert_read_only_request` 는 구조적으로 그것들을 거절한다. 상태변경 경로는
  각각 정확히 한 범주에 묶인다.
- **카드 비밀값은 경로가 아니라 본문에서 단속한다.** `stlCrCrdNo1`, `vanPwd1`,
  `crdVlidTrm1`, `athnVal1` 은 `payment` 로만 나갈 수 있다. 손으로 조립한 카드
  폼을 읽기 경로나 `reserve` 동의에 실어 빼돌릴 수 없다는 뜻이다.

마지막으로, 이 라이브러리는 NetFunnel 키를 한 번 다시 받는 경우를 빼면 스스로
재시도하지 않는다. 예약은 절대 재시도하지 않는다. 재시도한 예약은 이중예약이다.

## 에러 처리

실패는 메시지 문자열을 맞춰 보는 대신 이름 붙은 예외로 온다. 전부
`SrtApiError` 아래에 있고, 서버가 준 `.code` 와 `.raw` 를 그대로 들고 있다.

| 예외 | 상위 | 언제 |
| --- | --- | --- |
| `SrtApiError` | `Exception` | 이 패키지의 모든 실패의 뿌리. |
| `SrtTransportError` | `SrtApiError` | 연결·타임아웃 등 응답을 받지 못한 실패. |
| `SrtProtocolError` | `SrtApiError` | 응답이 약속된 형태가 아니거나, 등록되지 않은 경로로 보내려 했을 때. |
| `SrtAuthError` | `SrtApiError` | 인증 계열의 뿌리. |
| `SrtSessionExpiredError` | `SrtAuthError` | 세션이 끊겼다. 다시 로그인하라. |
| `SrtIpBlockedError` | `SrtAuthError` | 서버가 이 IP 를 막았다. |
| `SrtAppError` | `SrtApiError` | 서버가 정상 응답으로 돌려준 업무 오류. |
| `SrtNoResultsError` | `SrtAppError` | 요청은 정상이고 결과가 없다. |
| `SrtNoDirectTrainError` | `SrtNoResultsError` | 직통이 없다. 환승을 찾아라. |
| `SrtSeatUnavailableError` | `SrtAppError` | 좌석이 없다. |
| `SrtInvalidRequestError` | `SrtAppError` | 서버가 요청 자체를 거절했다. |
| `SrtNetFunnelError` | `SrtApiError` | 대기열 계열의 뿌리. |
| `SrtNetFunnelKeyError` | `SrtNetFunnelError` | 대기열 키를 얻지 못했다. |
| `SrtQueueRejectedError` | `SrtNetFunnelError` | 대기열이 통과를 거부했다. |
| `SrtMutationNotAllowedError` | `SrtApiError` | 동의·범주·경로·전송 관문 중 하나가 막았다. |

응답 본문의 코드를 예외로 옮기는 규칙은 `classify_app_error` 하나에 모여 있고,
그것도 export 되어 있다.

## 한계

SRT 앱은 **WebView 껍데기**다. 화면 대부분이 서버가 그때그때 렌더링하는 HTML 이고,
앱 자신의 결제 단계는 TransKey 보안 키패드와 RaonSecure FIDO SDK 를 지난다. 어느
HTTP 클라이언트도 그것을 재현할 수 없다. 그래서 이 패키지의 표면은 KORAIL 형제보다
좁고 고르지 않다. 정적으로 읽을 것이 아예 없는 자리가 있기 때문이다.

- **단체(group) 예약 — 일부러 뺐다.** 요청 자체는 맞았지만 엔드포인트가 돌려주는
  것은 취소 가능한 PNR 홀드가 아니라 `tmpJobSqno` 로 묶인 66 KB 짜리 서버 렌더링
  결제 페이지다. 결제 표면과 HTML 파서와 카카오페이 흐름이 따로 필요한 다른
  상품이다. 조회(`search_group_trains`)는 그대로 남아 있다.
- **예약대기와 왕복 — 구현되었고 실서비스로 확인된 적은 없다.** 둘 다 앱 번들에
  근거가 있고 미리보기도 정확하지만, 조건에 맞는 예약대기 열차를 만나지 못했고
  왕복은 아무도 돌려 본 적이 없다. 확인되지 않은 코드 경로로 취급하라.
- **환승 예약 — 조회는 확인되었고 예약 폼은 아니다.** 둘째 슬롯의 필드명 다섯 개는
  첫째 슬롯의 철자에서 유추한 것이다.
- **할인쿠폰 등록 — 구현되어 있으나 전송 관문이 닫혀 있다**(위 표 참조).
- **할인 승차권 조회 — 요청 형태에는 근거가 있고 효과는 확인되지 않았다.** 공공할인
  이 승인된 계정이 필요한데 이 프로젝트의 계정은 어느 자격도 갖고 있지 않아 여덟
  개 자격 플래그가 전부 비어 있다. 같은 이유로 청소년(`psgTpCd` 6)이 실제로
  예약되는지도 확인하지 못했다.
- **앱 자신의 WebView 결제 경로**(`Ard02017`/`Ard02018` + TransKey + FIDO), 네이티브
  브리지, 외부 코레일 좌석도는 통째로 제외했다. HTTP 클라이언트로 재현할 수 없다.

하나하나가 무엇을 하면 확인되는지까지 [docs/VERIFICATION.md](docs/VERIFICATION.md)
에 근거와 함께 적혀 있다.

운영상의 한계도 하나 있다. 조회는 NetFunnel 대기열 뒤에 있고, 이 클라이언트는
전선에서 앱과 구별되지 않는다. 반복문으로 조회를 두드리면 자신은 IP 차단을,
다른 사람들은 대기열 오염을 얻는다.

## 문서

| 문서 | 무엇이 들어 있나 |
| --- | --- |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | 검증 기록. 실서비스 실행마다 서버가 준 확인 코드, 그 실행이 확정하지 **못한** 것, 모든 경로의 정적 출처, 그리고 지우는 대신 남겨 둔 정정. |
| [docs/IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md) | 구현 로그. 무엇이 있고 무엇이 미뤄졌으며 각 표면을 왜 그렇게 만들었는지. |
| [docs/analysis/](docs/analysis/) | 정적 분석 산출물. 병합된 라이브러리 명세와 참조 클라이언트 대조 결과. |
| [docs/RELEASE.md](docs/RELEASE.md) | 릴리스 전에 돌리는 빌드·검증 게이트. |
| [docs/internal/](docs/internal/) | 개발 이력(감사, 폐기된 계획, 설계 명세). 사용자 문서가 아니다. |
| [SECURITY.md](SECURITY.md) | 자격증명 취급, 절대 커밋하면 안 되는 것, 문제 신고 방법. |
| [CHANGELOG.md](CHANGELOG.md) | 변경 이력. 항목은 고쳐 쓰지 않고 그 자리에서 갱신한다. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 오프라인 게이트 세 개(pytest, `ruff check`, pyright), 변경에 필요한 근거 등급, 안전 모델을 건드릴 때 추가로 요구되는 것. |
| [NOTICE](NOTICE) | 참조 클라이언트에서 무엇을 살펴봤고 왜 아무것도 복사하지 않았는지. |

운영용 스크립트는 `scripts/` 에 있다. `srt_app_api_smoke.py`(읽기 전용 스모크),
`capture_live_read_surface.py`(원본 응답 저장. 이 저장소 안에는 쓰기를 거부한다),
`verify_reserve_cancel_roundtrip.py`, 그리고 PNR 만으로 떠 있는 홀드를 풀어 주는
`recover_hold.py`(PNR 조차 잃었으면 계정의 예약을 열거해 준다).

## 라이선스

Apache License 2.0. [LICENSE](LICENSE) 와 [NOTICE](NOTICE) 를 보라. 이 프로젝트는
SR(수서고속철도)와 제휴·승인·후원 관계가 없으며, "SRT" 는 상호운용성을 설명하기
위해서만 쓰였다.
