# Changelog

이 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따릅니다.
이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/) 을 따릅니다.

`1.0.0` 이전 기록은 당시 형식·언어 그대로 보존합니다.

## 1.0.0 - 2026-07-28

첫 공개 릴리스입니다. 읽기 전용이던 클라이언트에 consent 로 잠긴 mutation 이
들어왔고, 그중 네 범주가 실서버 왕복을 거쳐 실제 전송까지 열렸습니다.

### Added

- **Apache-2.0 라이선스와 배포 메타데이터.** PEP 639 SPDX 형식의 `license` 와
  `license-files = ["LICENSE", "NOTICE"]`, `setuptools>=77`,
  `Development Status :: 5 - Production/Stable`, 버전 `1.0.0`.
  `srt_mobile_api.__version__` 이 pyproject 와 같음을 테스트가 고정합니다.
- **consent 로 잠긴 mutation 다섯.** `reserve`(`/arc/selectListArc05013_n.do`),
  `cancel`(`/ard/selectListArd02045_n.do`), `pay_with_card`(31필드 카드결제 폼,
  `/ata/selectListAta09036_n.do`), `refund`(`/atc/selectListAtc02063_n.do`, 발권
  정보 조회는 `/atc/getListAtc14087.do`),
  `register_discount_coupon`(`/arb/selectListArb02A01_n.do`). 기본은
  미리보기입니다 — `MutationConsent` 는 아무것도 허가하지 않은 채 `dry_run=True`,
  `fake_card_only=True` 로 생성되고, `require_mutation_consent()` 가 요청을 만들기
  전에 `SrtMutationNotAllowedError` 를 올립니다.
- **결제 금액은 `rcvdAmt` 하나로 갑니다.** `totNewStlAmt` 와 `mnsStlAmt1` 양쪽에
  할인 후 실제 수납금액을 싣고 호출자 재정의는 없습니다. 금액이 없거나 0 이면
  기본값으로 때우지 않고 거부합니다.
- **환불의 두 단계는 일부러 별개 메서드입니다.** 거절당할 환불이 1단계를 쏘고
  나서야 2단계 거부에 부딪히지 않게 하려는 것입니다. 1단계 라우트는 읽기로
  등록돼 있고(분류는 추론입니다) "본문이 아예 없다"는 계약이 강제로 걸려 있습니다.
- **실제로 전송되는 범주는 넷.** `safety.SRT_LIVE_MUTATION_CATEGORIES` =
  `{"reserve", "cancel", "payment", "refund"}`, 즉 라이브 왕복이 답을 준 범주만
  들어 있습니다. `coupon` 은 밖에 있습니다 — 실검증에 필요한 진짜 쿠폰은 만들어
  낼 수 없고, `reserve` 나 `payment` 에 접어 넣으면 그쪽 consent 하나가 쿠폰
  소진까지 조용히 허가하게 됩니다.
- **예약 변형 넷.** 예약대기(`standby=True`)는 `jobId=1102` 에 `psrmClCd1=1` 을
  강제하고 `reserveType` 을 뺍니다(`ara1001l.js:1445-1448`). 객실 강제는 장식이
  아닙니다 — 강제가 없으면 기본 `GENERAL_FIRST` 가 특실로 풀려서, 대기표를
  부탁하면서 특실을 주문하게 됩니다. 왕복(`round_trip=True`)은 `rtnDv="1"` 만
  더하고 뒤바뀐 질의는 `TrainSearchQuery.for_return_leg()` 가 만듭니다. 좌석지정은
  `jobId=1103`(`ara0101v.js:866-882`), 환승은 `jrnyTpCd="14"` 와 `jrnyCnt="2"`
  (`ara0101v.js:302-311`).
- **환승 검색과 여정 짝짓기.** `search_transfer_trains` 는 짝지어 검증된
  `itineraries` 와 이유가 붙은 `unpaired` 를 함께 돌려줍니다. 짝짓기는 서버가
  아니라 이쪽의 추론이라 `parsers.pair_transfer_itineraries` 로 따로 내놓고, 다리
  순서는 행 순서가 아니라 역에서 유도합니다 — 뒤집힌 짝도 흠 없는 예약을 만들고
  그것은 거꾸로 가는 여정입니다.
- **읽기 라우트 다섯과 그 파서.** `get_reservations`, `get_seat_grid`,
  `get_discount_coupons`, `get_public_discounts`,
  `search_public_discount_trains`. `READ_ONLY_ROUTES` 는 26 라우트가 됐습니다. 뒤
  넷은 번들에 0-hit 이고, 인증된 세션에 서버가 렌더링해 주는 페이지에서 찾았습니다.
- **좌석배치도는 열차번호를 다섯 자리로 채워야 열립니다.** `trnNo=315` 는 alert
  껍데기를, `trnNo=00315` 는 좌석표를 돌려줍니다. 앱도 똑같이 채웁니다
  (`main.html:642-661`). `SeatGridSeat` 는 폼이 보내는 것과 상세가 되돌려 주는 것을
  `internal_seat_number` 와 `printed_seat_label` 로 갈라 둡니다.
- **할인 코드 테이블 `srt_mobile_api.discounts`.** `DISCOUNT_KIND_NAMES_BY_CODE`
  는 앱의 `js/commCode.js` 그대로 171 이 아니라 **173 코드**입니다.
  `PUBLIC_DISCOUNT_NAMES_BY_CODE`(`01`–`06`)는 번들에 0-hit 이고 승차인원선택
  팝업의 주석 대응표에서 왔으며, `07`·`08` 은 이름을 못 찾아 비워 뒀습니다. 이
  항목은 아무것도 전송하지 않습니다.
- **`PassengerCounts` 가 승객 유형 일곱을 담습니다.** `infant` 와 `youth` 를
  **뒤에 덧붙였으므로** 기존의 위치 인자 생성은 뜻이 그대로입니다. 유아는 자기
  `psgTpCd` 없이 접힌 뒤 두 번 선언되므로 `child_slot_count` 를 `child` 와 다른
  이름으로 두었습니다. 자격은 확인하지 않습니다 — payload 빌더가 평가할 수 없는
  계정 사실이고, 여기서 거부하면 그 유형이 필요한 계정을 잠급니다.
- **서버 실패의 분류.** 거의 모든 거부가 하나의 `SrtAppError` 로 와서, "매진"과
  "세션 만료"와 "대기열 거부"를 한국어 `msgTxt` 부분 일치 없이는 구분할 수
  없었습니다. 여섯 유형이 각각 자기가 좁히는 것을 상속하므로 기존 `except` 절의
  뜻은 바뀌지 않습니다. 분류 기준은 문구가 아니라 `msgCd` 입니다 — 앱이 그렇게 하기
  때문입니다(`ara1001l.js:1562-1573`).
- **NetFunnel 대기열 프로토콜 완성.** `getTidChkEnter`(5101)만 보내고 있어서,
  대기열이 실제로 걸리면(201 `kContinue`) 검색이 실패하고 자리도 반납되지
  않았습니다. 이제 `chkEnter` 폴링(20회 또는 60초)과 매 요청 뒤 `setComplete` 가
  있습니다. 반납 실패는 일부러 삼킵니다 — 호출자의 진짜 요청이 끝난 뒤에 도는
  것이라 `reserve` 에서는 PNR 을 가리게 됩니다.
- **운영자용 스크립트 둘.** `scripts/recover_hold.py` 는 PNR 문자열 하나만으로
  묶여 있는 미결제 예약을 풉니다(consent 는 `cancel` 만 줍니다).
  `scripts/verify_reserve_cancel_roundtrip.py` 는 라이브 플래그 위에
  `SRT_LIVE_MUTATION=1` 을 한 번 더 요구하고, 취소가 끝내 실패하면 PNR 을
  `recover_hold.py` 명령줄과 함께 인쇄합니다.
- **앱이 보내기 전에 하는 거부 셋.** 코레일 전용역과 국회의원 후급 회원의 왕복
  (`ara0101v.js:317-341`), 단체가 아닌 10명 이상 검색(`ara0101v.js:562-567`).
- **문서 사이트.** `mkdocs.yml` 이 `docs/` 아래 쪽을 만들고 API 레퍼런스는
  docstring 에서 생성합니다. 빌드 도구는 `docs` extra 이고 런타임 의존성은 늘지
  않습니다.

### Changed

- **배포 검증기가 새 메타데이터를 금지하는 대신 검증합니다.** 규칙을 지우기만 하면
  릴리스를 막고 있던 그 메타데이터가 검사 없이 나가므로,
  `scripts/verify_distribution.py` 의 거부를 `Name`/`Version` 이 이미 받던 것과 같은
  정확값 검사로 뒤집었습니다. `License`, `Author`, `Home-page` 등은 계속 금지입니다.
- **`TrainSearchQuery.train_group_code` 기본값이 `"900"` 에서 `"109"` 로.** 앱 예약
  화면 자신의 기본값입니다(`ara0101v.js:85-86`, `:98-99`). 셋 다 전문상 유효하므로
  오류가 아니라 기본값 *선택*이고, `"300"` 과 `"900"` 은 그대로 만들 수 있습니다.
- **`get_seat_page` 가 `choiceSeatCount` 를 승객 총수에서 유도합니다.** 좌석 하나를
  하드코딩하고 있었습니다(`ara1001l.js:1511`). `passengers=` 가 생겼고
  `seat_count=` 는 명시적 재정의로 남습니다.
- **`personal_reservation_payload` 가 `arvDt1`(도착일자)을 보냅니다.** 통째로
  빠뜨리고 있었습니다(`ara1001l.js:1464`).
- **같은 빌더의 `runDt1` 이 출발일자가 아니라 운행일자를 싣습니다.** 앱은 같은
  블록에서 둘을 다른 필드로 씁니다(`ara1001l.js:1460`, `:1462`). 당일 운행에서는
  구별되지 않지만 자정을 넘기는 열차에서는 틀립니다.
- **예약 응답의 성공/실패 극성을 앱에 맞췄습니다.** 파서가 `strResult != "SUCC"` 로
  실패를 판정했는데 `ara1001l.js:1562` 는 `== "FAIL"` 입니다. 뒤집힌 검사가 salvage
  게이트에도 복제돼 있어서, 세 번째 상태값이 오면 `SrtAppError` 를 올리면서
  **동시에** PNR 구제를 막았습니다 — 그 서브시스템이 막으려고 존재하는 고아
  예약입니다.
- **검색 행 파서를 하나로 추출했습니다.** `_parse_search_train_rows` 를 일반 검색과
  할인 승차권 검색이 함께 씁니다.
- **`cancel` 의 `jrnyCnt` 재정의가 관대해졌습니다.** 0 패딩과 공백을 견디고
  (`"0001"` → `"1"`) 쓸 수 없는 값이면 `"1"` 로 되돌아갑니다. 정확히 `"1"` 을
  요구하던 빌더가 실제 `h_jrny_cnt="0001"` 을 거부해 미결제 예약을 묶어 버린
  korail 회귀(commit `3d7e8a5`)를 적용한 것입니다.

### Fixed

- **실패한 환불이 성공으로 읽힐 수 있었습니다.** `normalize_result_row` 가 어긋나는
  두 상태 행을 잘못 접었습니다. 이제 두 행이 엇갈리면 **실패 쪽**이 이깁니다.
- **자료가 없을 때 특실이 예약되고 휠체어석은 아예 예약되지 않았습니다.**
  `"예약가능" in (None or "")` 은 `False` 라서 좌석 여부 필드가 없는 행이 "일반실
  없음"으로 읽혔고 `GENERAL_FIRST` 가 조용히 특실을 잡았습니다 — 평범한
  `search_trains()` → `reserve()` 로 닿고 요금 차액은 호출자가 뭅니다. 따로, 두 예약
  빌더가 `"015"` 를 리터럴로 써서 021·028 재고는 검색되고 예약되지 않았습니다.
- **예약 식별자가 선행 0 을 잃었습니다.** JSON 숫자로 오면 06:30 출발이 `63000` 이
  되므로, 여섯 자리를 요구하는 결제 빌더에서 **10시 이전 출발이 전부 결제를 만들지
  못했습니다**. 고정폭 식별자 다섯 열을 다시 채웁니다(수량은 채우지 않습니다).
- **환승 예약을 풀 수 없었고, 검색이 자기 도착역에서 출발할 수 있었습니다.**
- **좌석지정이 자기 좌석표가 어느 객실 것인지 잊었습니다.** 일반실을 등급으로
  보내면서 특실 호차·좌석 번호를 실었습니다 — 앱이 만들 수 없는 본문이라 서버 동작에
  근거가 없습니다. 이제 객실과 좌석 번호는 같은 객실을 가리켜야 합니다.
- **예약대기가 앱이라면 접수했을 행을 거부했습니다.** 객실이 예약대기 재정의보다
  먼저 결정되고 있었습니다.
- **클라이언트 쪽 가드가 올라갈 때마다 NetFunnel 자리가 샜습니다.** 이제 키는
  생기는 즉시 등록됩니다.
- **NetFunnel 우회(`kTsBypass` = 300)가 키 없이 받아들여집니다.** 우회된 대기열에는
  자리가 없으니 키도 없습니다. `kSuccess`(200)는 여전히 키를 요구합니다.
- **`parse_reservation_hold_response` 가 엄격 검증에 걸린 예약 응답을 버리지
  않습니다.** 라이브 예약은 파싱 전에 이미 예약을 만들 수 있으므로, 쓸 수 있는
  `reservListMap[0].pnrNo` 가 있으면 최소 `SrtReservationHold` 를 돌려줍니다. 업무
  실패와 세션 만료는 절대 구제하지 않습니다.
- **그 "절대 구제하지 않는다"를 실제로 참으로 만들었습니다.**
  `parse_reservation_attempt_response` 가 `strResult` 를 분류하기 **전에** `msgCd`
  를 엄격하게 읽어서, 살짝 어긋난 FAIL 이 하필 salvage 분기가 잡는 유일한 예외를
  올렸습니다. 없는 예약이 있다고 알려 주는 것은 있는 예약을 잃는 것만큼
  해롭습니다 — 복구를 그만두게 만듭니다.

### Removed

- **단체(group) 예약.** `SrtClient.reserve_group`,
  `payloads.group_reservation_payload`, `/arc/selectListArc06014_n.do` 의 mutation
  등록이 사라졌습니다. 만들던 요청은 맞았고, 범위 밖으로 보낸 것은 그 라우트가
  **무엇으로 답하는가** 때문입니다 — 단체 분기가 요구하는 `psgGridcnt="2"` 로
  보내면 `단체승차권 직통 / 예약내역 페이지` 가 올 뿐 **예약을 만들지 않습니다**.
  따라서 "풀 수 없는 단체 예약이 남을 수 있다"는 앞선 기록은 사실이 아니었습니다.
  읽기인 `search_group_trains` 는 남고,
  `SRT_LIVE_MUTATION_CATEGORIES` 는 움직이지 않았습니다.

### Security

- **전송 계층에서 범주를 막습니다.** `post_mutation_form` 과
  `_send_mutation_request` 가 `SRT_LIVE_MUTATION_CATEGORIES` 밖의 범주를
  거부합니다. 클라이언트 메서드에서만 막으면 `SrtClient.http` 로 직접 내려가는
  호출자가 우회합니다.
- **범주와 라우트가 양방향으로 묶입니다.** `SRT_MUTATION_ROUTE_CATEGORIES` 가
  라우트마다 정확히 한 범주를 지정하고 `assert_mutation_route` 와
  `assert_mutation_route_category` 가 둘을 함께 확인하므로, 한 범주의 consent 를
  다른 범주의 엔드포인트로 돌릴 수 없습니다. mutation 라우트는 `READ_ONLY_ROUTES`
  **밖**에 있습니다.
- **카드 비밀값을 라우트가 아니라 본문에서 막습니다.**
  `safety.CARD_SECRET_FIELDS`(`stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`,
  `athnVal1`)는 `payment` 로만 이동할 수 있습니다. 손으로 조립한 결제 본문을
  **허용된 다른** 라우트로 보내는 것은 범주 위반도 라우트 위반도 아니므로,
  `payment` 가 열린 뒤로 이 검사가 결제 라우트가 아닌 모든 경로에서 유일한
  자물쇠입니다.
- **결제 consent 는 카드 종류를 정확히 하나 밝혀야 합니다.** `fake_card_only` 와
  `real_card_acknowledged` 중 하나이고 **둘 다도 둘 다 아님도 거부됩니다** — 애매한
  consent 는 결제를 실어 보내면 안 되는 상태입니다.
- **마스킹 구멍 둘을 막았습니다.** `pnr_no` 가 `SENSITIVE_KEYS` 에 없어서
  `redact_value` 가 실제 PNR 을 통과시켰고, 쿠폰 번호·비밀번호도 가려지지
  않았습니다 — `dscp_pwd` 는 리터럴 `password` 가 아니고 쿠폰 번호는 짧아 `CARD_RE`
  에 걸리지 않으므로, dry-run 미리보기가 쓸 수 있는 쿠폰을 통째로 인쇄했을
  것입니다. 환불 반환 비밀번호 세 철자, `buyPsNm`/`psgNm`, `SrtPaymentCard` 의 속성
  이름이 함께 들어갔습니다. `saleDt`/`saleWctNo`/`saleSqno` 는 일부러 가리지
  않습니다 — 비밀번호가 가려진 상태에서 아무것도 인가하지 않고, 전부 가려진
  미리보기는 아무 말도 하지 않습니다.
- **`MutationPreview` 는 payload 를 `redact_payload()` 로 통과시킵니다.**
- **`SrtPaymentResult.succeeded` 와 `.failed` 는 일부러 서로의 여집합이
  아닙니다.** 알아보지 못한 상태는 *모름*입니다. 눈감고 재시도하면 두 번
  청구됩니다.

### 근거

전송 가능한 라우트의 전문은 우리 번들이 아니라 srtgo 에서 왔고, 각각 라이브 왕복
한 번이 유일한 뒷받침입니다. 그 한 번이 건드리지 않은 필드에는 정적 근거가
없습니다.

- **취소 `/ard/selectListArd02045_n.do`.** 이 형태는 srtgo 에서 왔고 v2.0.41
  오프라인 번들 21,673 파일에서 0-hit 입니다(`jrnyCnt="1"` 값만 `ara0101v.js:92`
  가 일부 뒷받침합니다). 2026-07-25 라이브 서버로 예약→취소 왕복을 한 번
  돌렸습니다 — 수서→부산, 성인 1명, 일반실, 편도 1건. 예약은
  `strResult=SUCC`/`msgCd=IRR000018` 과 PNR 을, 취소는
  `strResult=SUCC`/`msgCd=IRG000000` 을 돌려줬고, 다시 읽은 승차권 목록에 흔적이
  없었습니다. 결제하지 않았으므로 청구된 것도 없습니다. 이 왕복이 확인해 주는 것은
  취소 라우트와 그 세 필드 본문(`pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"`), 그리고 열차
  검색과 같은 NetFunnel `act_10` 키 흐름입니다. 확인된 범위는 성인 1명·편도
  1건뿐이고 다구간·단체·예약대기는 건드리지 않았습니다.
- **결제 `/ata/selectListAta09036_n.do` 와 환불
  `/atc/selectListAtc02063_n.do`**(발권 정보 조회는 `/atc/getListAtc14087.do`).
  셋 다 srtgo 에서 왔고 v2.0.41 번들 21,673 파일에서 0-hit 입니다 — 번들에는
  `Atc02*` 계열 자체가 없습니다. 우리 앱은 이 경로로 결제하지 않고 서버 렌더링
  WebView 를 TransKey 키패드와 RaonSecure FIDO 로 청구합니다. 2026-07-26 검증은 두
  단계였습니다. 먼저 돈이 들지 않는 프로브 — 가짜 카드와 존재하지 않는 PNR 에 환불
  조회는 `msgCd=WRT300005`, 결제는 `msgCd=WRT100170` 이라는 정상 업무 봉투로
  답했으므로, 라우트 존재가 아무것도 쓰지 않고 확인됐습니다. 그다음 라이브 서버로
  실제 왕복 한 번 — 수서→동탄, 2026-08-09, 315 열차, 성인 1명, 편도 1건, 7,500원.
  결제는 `strResult=SUCC`/`msgCd=IRT000000`, 두 단계 환불은
  `strResult=SUCC`/`msgCd=IRT200277` 을 돌려줬고, 별도 세션에서 그 계정에 예약도
  승차권도 남지 않은 것을 확인했습니다. 확인된 범위는 성인 1명·편도 1건·일반실·개인
  카드 일시불 한 번뿐입니다. 이 왕복은 srtgo 의 환불 필드 철자
  `tkRetPwd`/`psgNm`/`pnr_no` 가 우리 앱의 로컬 캐시 철자
  (`retPwd`/`buyPsNm`/`pnrNo`, `webview/b.java:645,648`)보다 옳다는 것도
  정리했습니다. 단일 출처 필드명은 부류로 믿거나 불신할 것이 아니라 하나씩 시험해야
  합니다.
- **두 참조 라이브러리는 출처가 둘이 아니라 하나입니다.** srtgo 의 결제 dict 는
  ryanking13/SRT 의 것과 주석만 걷어내면 글자 단위로 같고(커밋 `8423f90`
  "Internalize SRT"), 환불은 ryanking13/SRT 에 아예 없어서 srtgo 가 유일한
  출처입니다. 둘이 같은 것을 보낸다는 사실은 독립된 뒷받침이 아닙니다. 덧붙여 "이
  폼의 필드명은 전부 0-hit"이라는 뭉뚱그린 주장은 틀립니다 — `mbCrdNo`, `totPrnb`,
  `jrnyCnt`, `buyPsNm`, `saleWctNo`, `retPwd` 는 번들에 나옵니다. 이 라우트들의
  요청 필드로 나오지 않을 뿐입니다.
- **네 확인 코드가 형제 korail 앱의 것과 같습니다** — `IRR000018`, `IRG000000`,
  `IRT000000`, `IRT200277`. 두 사업자가 예약 플랫폼을 공유한다는 관찰이지, 백엔드에
  대해 증명된 주장은 아닙니다.
- **환승 검색 응답 모양은 2026-07-26 읽기 프로브로 확인됐습니다.** 직통 검색은
  `WRD000061` 로 답했고, 환승 검색은 열 행을 전부 `chtnDvCd="2"` 로 돌려줬으며 한
  여정의 두 다리가 `trnOrdrNo` 를 공유했습니다. **이 읽기는 근거 등급을 하나도
  옮기지 않았습니다** — 응답 열이 비어 있다는 것은 **요청** 폼이 그것을 채우기를
  원하는지에 대해 아무 말도 하지 않으므로,
  `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` 의 슬롯 2 키 다섯은 여전히 추론입니다.
- **좌석배치도 읽기는 2026-07-26 라이브로 확인됐습니다** — 수서→동탄, 20260812,
  315 열차, 좌석 칸 74개. 이 라우트와 `trnScarSeatFrm` 폼은 번들에 0-hit 입니다.
  둘 다 서버가 렌더링하는 것에만 존재하기 때문입니다.
- **`register_discount_coupon` 은 한 번도 보낸 적이 없습니다.** 라우트·필드명·응답
  키 모두 번들에서 0-hit 이고, 형태는 라이브 쿠폰 페이지의 `couponReg()` 그
  자체입니다. 응답도 관측된 적이 없어서 페이지 자신의 극성(`RTNCD == "N"` 이면
  실패)을 지키되 빈 `RTNCD` 는 `SrtProtocolError` 로 올립니다 — 그 극성에서는 코드가
  없는 것이 성공으로 읽히기 때문입니다.
- **`search_public_discount_trains` 도 한 번도 보낸 적이 없습니다.** 봉투도 채워진
  할인율도 관측된 적이 없어서 페이저를 **일부러 두지 않았습니다** — 멈출 조건을 본
  적이 없습니다. 이 경로의 두 다리 중 구현된 것은 두 번째(`#seatSearchForm` POST)
  뿐이고, 첫 번째는 추정이 아니라 측정했습니다 — 읽기 전용 GET 프로브 넷이 매번
  142,594바이트를 세션 id 만 빼고 같게 돌려줬습니다.
- **공공할인 자격·할인쿠폰 목록 읽기는 2026-07-26 라이브로 확인됐습니다 — 자격도
  쿠폰도 없는 계정으로.** 자격 쪽은 여덟 플래그가 전부 비어 `is_eligible=False`
  이고, 그것은 예외가 아니라 반환값입니다. 쿠폰 쪽은 `ul.coupList` 가 비어
  있었습니다. 두 경우 다 **채워진 행 모양은 확인되지 않았고** docstring 이 그렇게
  밝힙니다. 쿠폰이 정규식이 아니라 파서인 이유는 라이브 페이지가 그럴듯한 숫자가 든
  템플릿을 `ul.coupList` **안에** 주석으로 싣고 있기 때문입니다 — 정규식이었다면 빈
  계정에서 쿠폰 두 개를 만들어 냈을 것입니다.
- **예약 목록 읽기는 2026-07-26 빈 경우만 확인됐습니다.** 여기서 빈 결과는 열차
  검색이 쓰는 `FAIL`/`WRG000000` 이 아니라 빈 *배열*이고, 같은 성공 응답이 두 번째
  봉투를 함께 싣는데 그것은 일부러 실패로 읽지 않습니다. 채워진 행 모양은
  **미확인**입니다 — 컨테이너 짝과 모든 행 필드명이 srtgo(`srt.py:1069-1082`)에서
  왔고 `payListMap`, `tkSpecNum`, `stlFlg` 는 번들에 0-hit 입니다.
- **NetFunnel 획득→반납 왕복은 2026-07-26 라이브로 확인됐습니다** — `5002:200`,
  이어서 `5004:200`. 201 폴링 경로는 확인되지 않았습니다. 그 실행이 픽스처로는 잡을
  수 없던 결함을 잡았습니다 — 키 모양 가드가 128자로 제한하고 있었는데 실제 키는
  256자라, 모든 `setComplete` 가 조용히 삼켜지고 있었습니다.
- **좌석지정의 제출 대상은 추론이며, 운영자가 정리해야 할 부분입니다.**
  `fn_submit()` 은 `ara0101v.js:882` 에서 호출되지만 정의는 서버가 렌더링하는 예약
  페이지에 있습니다. 이 라이브러리는 그다음 줄의 주석
  `//Sr.ara1001l.fn_callReserv();` 를 근거로 `/arc/selectListArc05013_n.do` 로
  POST 합니다(`ara1001l.js:1541-1550`). 라이브로 하나 보내기 전에
  `/ara/ara0101v.do` 를 받아 인라인 `fn_submit` 을 읽어야 합니다.
- **`seatNo1_*` 는 내부 좌석번호가 아니라 인쇄된 라벨을 싣습니다.** 앱은 그것을
  `scarSeatNm` 에서 만들고 `scarSeatNo` 는 쓰지 않습니다(`ara0101v.js:870-874`).

## 0.2.0 - 2026-07-15

- Normalized the two observed personal/group search wrapper casings strictly,
  added typed repr-safe search metadata and optional row availability details,
  and enriched missing station names only from hydrated request context.
- Preserved the legacy raw notice mapping and numeric-only fare item contracts;
  added typed uppercase notice results and all semantic fare rows through
  separate additive APIs/fields, and retained leading-empty timetable names.
- Aligned search details with sanitized 51-field personal and 43-field group
  shapes, including integer delay/order values, received fare, and five train
  composition codes.
- Added bounded, lazy personal and group train-search page iteration while
  preserving the existing single-page search methods.
- Reused the hydrated search form and NetFunnel key across continuation pages,
  with exact cursor validation, progress bounds, and one refresh/retry for only
  a continuation page rejected with `NET000001`.
- Kept the reviewed 20-route read-only boundary unchanged. A bounded live run
  verified two personal and two group pages without retaining response values.
- Added the pure offline `parse_reservation_attempt_response()` parser and the
  typed repr-safe `ReservationAttemptResult` for the documented
  reservation-attempt response shape. No reservation route, request builder,
  NetFunnel `act_19` flow, client method, or live call was added; the read-only
  boundary is unchanged.

## 0.1.0 - 2026-07-14

- Prepared the existing installable, typed, read-only SRT mobile API client for
  reproducible internal builds and offline verification.
- Retained the 20-route safety boundary, including the bounded seat-page read;
  mutation operations and physical-seat schemas remain excluded.
