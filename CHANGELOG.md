# Changelog

이 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따른다.
이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

`1.0.0` 이전 기록은 당시 형식·언어 그대로 보존한다.

## 1.0.0 - 2026-07-27

첫 공개 릴리스다. 읽기 전용이던 클라이언트에 consent 로 잠긴 mutation 이 들어왔고,
그중 네 범주가 실서버 왕복을 거쳐 실제 전송까지 열렸다.

### Added

- **Apache-2.0 라이선스와 배포 메타데이터.** `LICENSE` 는 원문 그대로이고,
  `pyproject.toml` 이 PEP 639 SPDX 형식으로 `license = "Apache-2.0"` 와
  `license-files = ["LICENSE", "NOTICE"]` 를 쓴다(`License ::` 분류자와는 함께
  쓸 수 없다). `NOTICE` 를 저장소 루트뿐 아니라 여기에도 이름 올린 것은
  Apache-2.0 §4(d) 가 재배포자에게 저작자 표시를 이어 나르게 하는데 그 파일이
  빠진 wheel 로는 그럴 수 없기 때문이다. `setuptools` 하한이 `>=69` 에서 `>=77`
  로 올라갔고(두 키를 이해하는 첫 릴리스), `Development Status` 는 `3 - Alpha`
  에서 `5 - Production/Stable` 로, 버전은 `0.2.0` 에서 `1.0.0` 이 됐다.
  `srt_mobile_api.__version__` 이 생겼고 pyproject 의 버전과 같음을 테스트가
  고정한다. `__all__` 에는 일부러 넣지 않았다.
- **consent 로 잠긴 mutation 다섯.** `reserve`(개인예약
  `/arc/selectListArc05013_n.do`), `cancel`(예약취소
  `/ard/selectListArd02045_n.do`), `pay_with_card`(31필드 카드결제 폼,
  `/ata/selectListAta09036_n.do`), `refund`(환불 `/atc/selectListAtc02063_n.do`,
  발권 정보 조회는 `/atc/getListAtc14087.do`),
  `register_discount_coupon`(할인쿠폰 등록 `/arb/selectListArb02A01_n.do`,
  `dscp_no` 와 `dscp_pwd` 두 필드). 기본은 미리보기다 — `MutationConsent` 는
  생성 시 아무 것도 허가하지 않고(`allow_*` 는 전부 `False`), `dry_run` 은
  `True`, `fake_card_only` 는 `True` 다. `require_mutation_consent()` 가 요청을
  만들기 전에 거부하며 `SrtMutationNotAllowedError` 를 올린다.
- **결제 금액은 `rcvdAmt` 하나로 간다.** 폼은 `totNewStlAmt` 와 `mnsStlAmt1` 양쪽에
  `rcvdAmt`(수납금액, 할인 후 실제로 받는 금액)를 싣고 **호출자 재정의는 없다**.
  금액이 없거나 0 이면 기본값으로 때우지 않고 거부한다. korail 선례
  (`h_tot_prc` 59,800 대 `h_tot_rcvd_amt` 83,700)를 보고 일부러 그렇게 정했다.
  한 가지가 미해결로 남는다 — 서버는 0 으로 채운 값을 보내고 ryanking13/SRT 는 그
  패딩을 그대로 되돌려 주는데 srtgo 는 `int` 로 캐스팅한다. 라이브 증언이 있는
  것은 srtgo 의 폼뿐이라 srtgo 의 맨 숫자를 보낸다.
- **환불의 두 단계는 일부러 별개 메서드다.** 거절당할 환불이 1단계를 쏘고 나서야
  2단계 거부에 부딪히는 대신 요청을 한 건도 내지 않게 하려는 것이다. 1단계
  라우트는 읽기로 등록돼 있는데 그 분류는 증명이 아니라 추론이고, allowlist 에
  있는 만큼 "본문이 아예 없다"는 계약이 문서가 아니라 강제로 걸려 있다 — 그래야
  허용된 경로로 카드나 환불 폼을 POST 하는 데 쓰이지 않는다.
- **실제로 전송되는 범주는 넷.** `safety.SRT_LIVE_MUTATION_CATEGORIES` 는
  `{"reserve", "cancel", "payment", "refund"}` 다. 라이브 왕복이 답을 준 범주만
  들어 있고 다른 이유로 들어온 것은 없다. `coupon` 은 밖에 있다 — 실검증에는
  아직 쓰지 않은 진짜 쿠폰이 필요한데 그것은 만들어 낼 수 없다. 쿠폰을 다섯 번째
  범주로 따로 둔 이유는, 쿠폰 등록이 계정 상태는 바꾸지만 예약도 결제도 아니어서
  `reserve` 나 `payment` 에 접어 넣으면 그쪽 consent 하나가 쿠폰 소진까지 조용히
  허가하게 되기 때문이다.
- **예약 변형 넷.** 예약대기(`reserve(train, standby=True)`)는 `jobId=1102` 를
  쓰고 `psrmClCd1=1` 을 강제하며 `reserveType` 을 뺀다 — 셋 다 `1102` 를 만드는
  한 분기에서 함께 나온다(`ara1001l.js:1445-1448`, 객실은 `:1431`). 객실 강제는
  장식이 아니다. 기본 `GENERAL_FIRST` 는 일반실이 "예약가능"이 아닐 때 특실로
  풀리는데 그것이 바로 예약대기 열차의 모습이라, 강제가 없으면 대기표를 부탁하면서
  조용히 특실을 주문하게 된다. 왕복(`round_trip=True`)은 `rtnDv="1"` 하나만
  더한다. SRT 는 왕복을 다구간 예약이 아니라 오는열차로 모델링하므로 공개 API 는
  보통의 `reserve` 두 번이고, 뒤바뀐 질의는 `TrainSearchQuery.for_return_leg()`
  가 만든다. 좌석지정(`designated_seats=`)은 `jobId=1103` 이고 본문이 필드마다
  번들 근거를 갖는다(`ara0101v.js:866-882`). 환승(`reserve_transfer`)은
  `jrnyTpCd="14"` 와 `jrnyCnt="2"` 를 한 번의 `lfn_setRsv` 호출에서 함께 세우는데
  (`ara0101v.js:302-311`), 그 호출이 v2.0.41 번들 전체에서 `jrnyCnt="2"` 를 쓰는
  유일한 곳이다.
- **환승 검색과 여정 짝짓기.** `search_transfer_trains` 는
  `TransferSearchResult` 를 돌려준다 — 짝지어 검증된 `itineraries`, 이유가 붙은
  `unpaired`, 손대지 않은 `search`, 그리고 `rows`/`raw`. 서버는 다리마다 한 행을
  보내고 `trnOrdrNo` 는 목록 안 위치가 아니라 여정 색인이다. 짝짓기는 서버가 아니라
  이쪽의 추론이라 `parsers.pair_transfer_itineraries` 로 이름 붙여 따로 내놓고,
  다리 순서는 행 순서가 아니라 역에서 유도한다 — 뒤집힌 짝도 흠 없는 예약을
  만들어 내고 그것은 거꾸로 가는 여정이다. 짝이 맞지 않는 묶음은 버리지도
  억지로 붙이지도 않고 이유와 함께 `unpaired` 로 간다. 행은 있는데 여정이 하나도
  안 나오면 `SrtProtocolError` 다 — 그 경우는 응답이 아니라 짝짓기 규칙이 틀린
  것이고, 빈 목록을 돌려주는 것이 유일하게 조용한 실패다.
  `TransferItinerary` 는 생성 시점에 첫 다리의 도착역이 둘째 다리의 출발역인지,
  둘째가 첫째보다 먼저 떠나지 않는지, 두 열차가 다른지를 검증한다. 환승 검색 행은
  평범한 `TrainSummary` 라서 `reserve(row)` 가 그것을 받아 환승역까지만 가는
  진짜 PNR 을 돌려줄 수 있고, 그래서 `reserve_transfer` 는 `TransferItinerary`
  만 받는다.
- **읽기 라우트 다섯과 그 파서.** `get_reservations`(예약 목록,
  `/atc/selectListAtc14016_n.do`), `get_seat_grid`(좌석배치도,
  `/arc/selectListArc02011_n.do`), `get_discount_coupons`(보유 할인쿠폰,
  `/apa/selectListApa03020_n.do`), `get_public_discounts`(공공할인 자격,
  `/common/ARA/ARA0301V/view.do`), `search_public_discount_trains`(할인 승차권
  검색, `/ara/selectListAra10131_n.do`). `READ_ONLY_ROUTES` 는 26 라우트가 됐다.
  뒤 넷은 v2.0.41 번들에 0-hit 이고, 인증된 세션에 서버가 렌더링해 주는 페이지를
  읽어서 찾았다 — 예를 들어 쿠폰 라우트는 모든 인증 페이지에 박히는 MY SRT 메뉴가
  `pageMove('/apa/selectListApa03020_n.do')` 로 이름을 대고 있었다.
- **좌석배치도는 열차번호를 다섯 자리로 채워야 열린다.** `trnNo=315` 는 147바이트
  짜리 alert 껍데기로 "출발 20분 전부터 좌석이 자동배정됩니다…" 를 돌려주고,
  `trnNo=00315` 는 좌석표를 돌려준다. 그 문구는 시간 규칙처럼 읽히지만 시간 규칙이
  아니고, 그렇게 믿은 것이 이 엔드포인트를 닫아 두고 있었다. 앱도 똑같이 채우고
  주석으로 그렇게 말한다("열차번호를 5자리로 채워서 가져옴", `main.html:642-661`).
  패딩은 `payloads.seat_grid_payload` 의 `SEAT_TRAIN_NUMBER_LENGTH` 옆에 있고
  안전 경계에서 `[0-9]{5}` 로 다시 검사된다. 좌석 한 칸은
  `choiceSeatNo('3', '1C', 'Y')` — 내부 좌석번호, 인쇄 라벨, 선택 가능 여부 — 라서
  `SeatGridSeat` 는 `internal_seat_number` 와 `printed_seat_label` 을 이름으로
  갈라 둔다. 폼이 보내는 것과 상세가 되돌려 주는 것이 서로 다른 식별자인 것은
  형제 korail 클라이언트가 이미 물린 자리다.
- **할인 코드 테이블 `srt_mobile_api.discounts`.** `DISCOUNT_KIND_NAMES_BY_CODE`
  는 앱 자신의 `js/commCode.js` 에 있는 `dcntKndCd` 구간을 그대로 옮긴 것으로
  **171 이 아니라 173 코드**다 — `133` 기본 특별할인(기준)과 `191` 정차역 할인은
  원본에서 `code_group_cd` 키 없이 `132` 와 `192` 사이에 들어 있다.
  `PUBLIC_DISCOUNT_NAMES_BY_CODE`(공공할인 `PBL_DISC_CD` `01`–`06`)는 필드명도
  값도 번들에 0-hit 이고, 승차인원선택 팝업이 자기 `setPassenger` 안에 주석
  블록으로 적어 둔 대응표에서 왔다. `07` 과 `08` 은 할인 승차권 페이지에 분기는
  있지만 이름을 어디서도 못 찾아서 추측 대신 비워 뒀다.
  `YOUTH_PASSENGER_TYPE_CODE = "6"` 은 `commCode.js` 두 사본 어디에도 없는
  `psgTpCd` 를 기록만 해 둔 상수다. 이 항목은 아무 것도 전송하지 않는다 —
  `dcntKndCd` 는 해독만 하고 설정하지 않는다.
- **`PassengerCounts` 가 앱의 승객 유형 일곱을 담는다.** `infant`(유아)와
  `youth`(청소년)를 **뒤에 덧붙였으므로** 기존의 위치 인자 생성은 뜻이 그대로다.
  유아는 자기 `psgTpCd` 가 없고 접힌 뒤 두 번 선언된다 — 어린이 슬롯 수가
  어린이+유아가 되고, `infantCnt` 가 유아를 다시 싣고, `totPrnb` 는 사람 수로 세고,
  `psgGridcnt` 는 유형으로 세지 않는다. 예약 페이지 `goRevFn` 의 규칙을 정리하지
  않고 그대로 구현한 것이다. `PassengerCounts.child_slot_count` 가 접힌 숫자이며
  `child` 와 이름이 다른 것은, 어떤 필드가 어느 쪽을 원하는지 호출자가 외우지
  않게 하려는 것이다. 청소년은 `psgTpCd` 6 을 받고 패딩된 검색 폼을 다섯 슬롯에서
  여섯으로 넓힌다. 자격은 확인하지 않는다 — 승차인원선택 팝업은 서버가
  `pblDiscCd == "04"` 를 렌더링할 때만 그 칸을 열지만 그것은 payload 빌더가
  평가할 수 없는 계정 사실이고, 여기서 거부하면 이 유형이 필요한 계정을 잠근다.
  `infant=0` 이고 `youth=0` 이면 모든 빌더가 이전과 정확히 같은 것을 낸다.
- **서버 실패의 분류.** 거의 모든 거부가 `NET000001` 만 특수 처리된 하나의
  `SrtAppError` 로 왔고, 호출자는 "매진"과 "세션 만료"와 "대기열 거부"를 한국어
  `msgTxt` 부분 일치 없이는 구분할 수 없었다 — `srtgo` 가 하는 방식이고
  (`srtgo/srtgo.py:721-744`), 문구가 바뀌는 날 깨진다. 여섯 유형이 각각 자기가
  좁히는 것을 상속하므로 기존 `except` 절의 뜻은 하나도 바뀌지 않는다:
  `SrtNoResultsError`·`SrtInvalidRequestError`·`SrtSeatUnavailableError` 는
  `SrtAppError` 아래, `SrtNetFunnelKeyError`·`SrtQueueRejectedError` 는
  `SrtNetFunnelError` 아래, `SrtIpBlockedError` 는 `SrtAuthError` 아래.
  분류 기준은 문구가 아니라 `msgCd` 다. 앱이 그렇게 하기 때문이다 — v2.0.41 번들
  21,673 파일에서 서버가 준 문자열로 분기하는 곳은 `resultMap.msgCd == "S111"`
  하나뿐이고(`ara1001l.js:1562-1573`), 나머지는 이유를 담지 않는
  `strResult == "FAIL"` 이나 `ErrorCode == -1` 이다. 각 예외는 원본 `.code` 와
  `.raw` 를 들고 있고, 지도에 없는 코드는 여전히 평범한 `SrtAppError` 다.
  `WRD000061`("직통열차는 없지만, 환승으로 조회 가능합니다.")은
  `SrtNoDirectTrainError` 로 `SrtNoResultsError` 를 한 겹 좁힌다. 환승 재검색을
  자동으로 보내지는 않는다 — 앱도 대화상자로 물어보고 기다리며, 이 라이브러리는
  호출자가 시킨 읽기 하나를 둘로 만들지 않는다.
- **NetFunnel 대기열 프로토콜 완성.** `getTidChkEnter`(5101)만 보내고 있었다.
  대기열이 실제로 걸리면(201 `kContinue`) 검색이 **실패**했고 — 설계대로 동작하는
  대기열이 오류처럼 보였다 — 자리도 시간이 다 될 때까지 반납되지 않았다. 이제
  `chkEnter` 폴링(20회 또는 벽시계 60초 중 먼저, 각 대기는 서버가 준 `ttl` 을 앱의
  1..5초 `TS_MAX_TTL` 로 자른 값이라 촘촘한 재시도 루프가 될 수 없다)과 매 요청 뒤
  `setComplete` 가 있다(번들의 `TS_AUTO_COMPLETE = true`). 반납 실패는 일부러
  삼킨다 — 호출자의 진짜 요청이 이미 성공하거나 실패한 뒤에 도는 것이라 그 결과를
  대신해서는 안 되고, 특히 `reserve` 에서는 PNR 을 가리게 된다. `/ts.wseq` 계약은
  opcode 마다 정확한 질의 모양 **셋**을 등록한다. 하나로 뭉뚱그릴 수 없는 이유가
  둘이다: `setComplete` 는 `sid` 도 `aid` 도 싣지 않고(네 빌더 중 유일하게),
  `chkEnter` 의 `ttl` 은 `prefix` 와 `sid` 사이에 상수가 아니라 서버가 준 값으로
  들어간다. `js=yes` 는 그대로다 — srtgo 와 ryanking13/SRT 는 둘 다 `js=true` 를
  보내지만 번들은 `yes` 라고 적는다.
- **운영자용 스크립트 둘.** `scripts/recover_hold.py` 는 PNR 문자열 하나만으로
  묶여 있는 미결제 예약을 푼다. 예약을 만든 실행이 이미 사라진 상황을 위한
  것이라 일부러 아무 객체도 상태도 요구하지 않는다. consent 는 명시적으로 만들고
  `cancel` 만 준다(예약도 결제도 환불도 아니다). `dry_run=False` 인 이유는 dry run
  이 미리보기만 하고 아무 것도 풀지 않기 때문이다.
  `scripts/verify_reserve_cancel_roundtrip.py` 는 `SRT_MOBILE_API_LIVE=1` 위에
  `SRT_LIVE_MUTATION=1` 을 한 번 더 요구한다 — "라이브 읽기는 괜찮다"가 예약을
  만들어도 된다는 뜻은 아니기 때문이다. 예약 성공 이후는 전부 `try`/`finally` 로
  감싸고, `finally` 는 아직 성공하지 않은 취소를 다시 시도하며, 그것마저 실패하면
  PNR 을 `recover_hold.py` 명령줄과 함께 놓치기 어려운 배너로 인쇄한다.
- **앱이 보내기 전에 하는 거부 셋.** 코레일 전용역과 국회의원 후급 회원의 왕복
  (`ara0101v.js:317-341`), 그리고 단체가 아닌 10명 이상 검색
  (`ara0101v.js:562-567`). 마지막 것이 payload 빌더가 아니라 클라이언트에 있는
  이유는 빌더가 개인 흐름과 단체 흐름을 구분할 수 없기 때문이다.

### Changed

- **배포 검증기가 새 메타데이터를 금지하는 대신 검증한다.**
  `scripts/verify_distribution.py` 는 `pyproject.toml` 의
  `license`/`authors`/`urls` 를 통째로 거부하고 `License-Expression`,
  `Author-email`, `Project-URL` 헤더를 블랙리스트에 두고 있었다. 규칙을 지우기만
  하면 릴리스를 막고 있던 바로 그 메타데이터가 검사 없이 나가므로, 각각을
  `Name`/`Version`/`Requires-Python` 이 이미 받던 것과 같은 정확값 검사로
  뒤집었다. `License`, `Author`, `Maintainer`, `Maintainer-email`, `Home-page`,
  `Download-URL` 은 계속 금지다 — 올바른 빌드는 이것들을 내지 않는다. `LICENSE`
  가 sdist 필수 문서에 들어갔고, 두 아카이브 모두 체크아웃의 라이선스 원문을
  바이트 단위로 실어야 한다. 새 검사마다 그것을 어기는 적대적 케이스가 있다.
- **`TrainSearchQuery.train_group_code` 기본값이 `"900"`(KTX+SRT)에서
  `"109"`(전체)로.** 앱 예약 화면 자신의 기본값이다(`ara0101v.js:85-86` 이
  선택기를 전체로 놓고 `:98-99` 가 `trnGpCd1="109"` 를 심는다). 세 코드 모두
  전문상 유효하므로 이것은 전문 오류가 아니라 기본값 *선택*이지만, 옛 값에는 근거
  주석이 없었고 같은 코드베이스의 다른 두 기본값과 어긋나 있었다. `"300"` 과
  `"900"` 은 그대로 만들 수 있다.
- **`get_seat_page` 가 `choiceSeatCount` 를 승객 총수에서 유도한다.** 좌석 하나를
  하드코딩하고 있었다. 앱은 `choiceSeatCount: lfn_getRsv("totPrnb")` 를 보내고
  (`ara1001l.js:1511`) `safety.SEAT_PAGE_VALUE_PATTERNS` 도 이미 그 이유로 이
  필드를 양의 정수로 검증하고 있었지만, 거기에 연결된 것이 없었다. 새 키워드 인자
  `passengers=` 가 생겼고 `seat_count=` 는 명시적 재정의로 남아 기본값이 `"1"`
  대신 `None` 이다. 둘 다 없으면 여전히 좌석 하나다.
- **`personal_reservation_payload` 가 `arvDt1`(도착일자)을 보낸다.** 통째로
  빠뜨리고 있었다. 앱은 이미 보내던 `dptDt1`/`dptTm1`/`arvTm1` 과 같은 블록에서
  그것을 쓰고(`ara1001l.js:1464`), srtgo 가 빼는 것은 `SRTTrain` 에 도착일자가
  없어서다. reserve 는 전문 모양을 정적으로 확인할 수 있는 유일한 mutation
  라우트라, 미확인으로 두는 대신 닫았다.
- **`personal_reservation_payload` 의 `runDt1` 이 출발일자가 아니라 운행일자를
  싣는다.** 앱은 같은 블록에서 둘을 검색 행의 다른 필드로 쓴다 —
  `ara1001l.js:1460` `"runDt1": item.runDt`(운행일자) 대 `:1462`
  `"dptDt1": item.dptDt`(출발일자). srtgo 가 둘 다 `dep_date` 를 보내는 것은
  `SRTTrain` 에 운행일자가 없기 때문이며, 당일 운행에서는 구별되지 않지만 자정을
  넘기는 열차에서는 틀린다. `runDt` 가 없는 행은 출발일자로 되돌아가고, 있으면서
  8자리 날짜가 아닌 값은 조용히 대체하는 대신 거부한다.
- **예약 응답의 성공/실패 극성을 앱에 맞췄다.** 파서가 `strResult != "SUCC"` 로
  실패를 판정했는데 `ara1001l.js:1562` 는 `if (resultMap.strResult == "FAIL")`
  이고, 그 밖의 값은 `reservListMap[0].pnrNo` 를 읽어 예약이 만들어진 것으로
  진행한다. 뒤집힌 검사가 salvage 게이트에도 복제돼 있어서 세 번째 상태값이 오면
  `SrtAppError` 를 올리면서 **동시에** PNR 구제를 막았다 — 그 서브시스템이 막으려고
  존재하는 바로 그 고아 예약이다. `WRP011002` 는 독립된 실패 신호로 남는다.
- **검색 행 파서를 하나로 추출했다.** `_parse_search_train_rows` 를 일반 검색과
  할인 승차권 검색이 함께 쓴다. 컨테이너 처리만 따로이고, 할인 파서는 일반
  `outDataSets` 컨테이너를 관대하게 받지 않고 거부한다.
- **`cancel` 의 `jrnyCnt` 는 `"1"` 기본이고 재정의는 관대하다.** 예약 응답에는
  좌석 수(`totSeatNum`)만 있고 여정 수가 없어 `SrtReservationHold` 에서 유도할
  것이 없다. `journey_count` 재정의는 숫자로 비교하고 0 패딩과 공백을 견디며
  (`"0001"` → `"1"`), 쓸 수 없는 값이면 예외 대신 `"1"` 로 되돌아간다. 정확히
  `"1"` 을 요구하던 빌더가 실제 `h_jrny_cnt="0001"` 을 거부해 미결제 예약을 묶어
  버린 korail 회귀(commit `3d7e8a5`)를 적용한 것이다. 만들 수 없는 취소 폼은 풀 수
  없는 예약이다.

### Fixed

- **실패한 환불이 성공으로 읽힐 수 있었다.** `normalize_result_row` 가 어긋나는 두
  상태 행을 잘못 접었다. 이제 `dsOutput0` 은 그 행이 실제로 쓸 수 있는 값을 들고
  있을 때만 우선하고, 두 행이 엇갈리면 **실패 쪽**이 이긴다. 일어나지 않은 환불이
  일어난 것처럼 돌아와서는 안 된다.
- **자료가 없을 때 특실이 예약되고 휠체어석은 아예 예약되지 않았다.**
  `"예약가능" in (None or "")` 은 `False` 라서, 좌석 여부 필드가 통째로 없는 검색
  행이 "일반실 없음"으로 읽혔고 `GENERAL_FIRST` 가 조용히 특실을 잡았다 — 평범한
  `search_trains()` → `reserve()` 로 닿고, 요금 차액은 호출자가 문다. 이제 없는
  필드와 매진을 구분해 추측 대신 거부한다. 따로, 두 예약 빌더가 `"015"` 를
  리터럴로 쓰는 동안 검색은 `TrainSearchQuery.seat_attr_code` 를 존중해서 021·028
  재고는 검색되고 예약되지 않았다. 예약은 이제 SRT 가 분기하는 세 코드로 검증하고,
  호출자가 아무 것도 지정하지 않으면 그 행을 찾은 코드를 물려받는다.
- **예약 식별자가 선행 0 을 잃었다.** JSON 숫자로 도착하면 이미 없어져 있다 —
  06:30 출발이 `63000` 으로 온다 — 그래서 `str()` 만 거친 다섯 글자 시각이 정확히
  여섯 자리를 요구하는 결제 빌더로 갔고, **10시 이전 출발은 전부 결제를 만들지
  못했다**. 고정폭 식별자 다섯 열을 다시 채운다. `rcvdAmt` 같은 수량은 일부러
  채우지 않는다. `trnGpCd` 도 기본값 대신 행이 준 값으로 보낸다.
- **환승 예약을 풀 수 없었고, 검색이 자기 도착역에서 출발할 수 있었다.**
- **좌석지정이 자기 좌석표가 어느 객실 것인지 잊었다.** `seat_type` 이
  `GENERAL_FIRST` 기본인 채로 특실 좌석을 고르면 일반실을 등급으로 보내면서 그
  옆에 특실 호차·좌석 번호를 실었다 — 앱이 만들 수 없는 본문이라 서버가 그것을
  어떻게 다루는지에 대한 근거가 없다. 이제 객실과 좌석 번호는 같은 객실을 가리켜야
  한다.
- **예약대기가 앱이라면 접수했을 행을 거부했다.** 객실이 예약대기 재정의보다 먼저
  결정되고 있어서, 좌석 여부 요구가 들어온 뒤로는 `gnrmRsvPsbStr` 이 없는
  대기 가능 행이 재정의를 지나쳐 예외를 올렸다. 예약대기는 일반실을 강제하고 좌석
  여부를 아예 읽지 않으므로 그 판단이 먼저 온다.
- **클라이언트 쪽 가드가 올라갈 때마다 NetFunnel 대기열 자리가 샜다.** 예약 폼이
  `finally` 로 자리를 반납하는 `try` 바깥에서 만들어졌고, `_get_act10_key` 는
  폴링 루프가 끝난 뒤에야 자기 키를 기록해서 그 함수의 두 예외도 자리를 버렸다.
  이제 키는 생기는 즉시 등록된다.
- **NetFunnel 우회(`kTsBypass` = 300)가 키 없이 받아들여진다.** `SUCCESS_CODES`
  에는 `300` 이 있었지만 그 아래 키 검사가 무조건이라, 우회가 실제로 갖는 유일한
  응답 모양에서는 그 수용에 닿을 수 없었다. 우회된 대기열은 줄 서 있는 자리가
  없으니 키도 없다. `kSuccess`(200)는 여전히 키를 요구한다.
- **`parse_reservation_hold_response` 가 엄격 검증에 걸린 예약 응답을 버리지
  않는다.** 라이브 예약은 이쪽이 파싱하기 전에 이미 예약을 만들 수 있으므로,
  엄격 파싱이 프로토콜 오류를 올리면서 쓸 수 있는 `reservListMap[0].pnrNo` 가
  있으면 PNR 만 실은 최소 `SrtReservationHold` 를 돌려준다. PNR 이 없으면 원래
  오류를 다시 올리고, 업무 실패와 세션 만료는 절대 구제하지 않는다.
- **그 "절대 구제하지 않는다"를 실제로 참으로 만들었다.**
  `parse_reservation_attempt_response` 가 선언된 `strResult` 를 분류하기 **전에**
  `msgCd`/`msgTxt` 를 엄격하게 읽어서, 살짝 어긋난 FAIL(`msgCd` 없음, 정수
  `msgCd`, `msgTxt` 없음)이 `SrtProtocolError` 를 올렸고 그것이 하필 salvage
  분기가 잡는 유일한 예외였다. 그래서 서버가 방금 거절한 예약에 대해 최소 예약
  객체가 돌아왔다. 없는 예약이 있다고 알려 주는 것은 있는 예약을 잃는 것만큼
  해롭다 — 복구를 그만두게 만든다.

### Removed

- **단체(group) 예약.** `SrtClient.reserve_group`,
  `payloads.group_reservation_payload`, 그리고 `/arc/selectListArc06014_n.do` 의
  mutation 등록이 사라졌다. 만들던 요청은 맞았다. 단체 예약을 범위 밖으로 보낸
  것은 그 라우트가 **무엇으로 답하는가** 다. 실패의 원인은 계정 자격이 아니라
  `psgGridcnt` 였다 — 예약 페이지의 단체 분기는 `grpDv="1"` 과 `psgGridcnt="2"` 를
  함께 세우는데, 이 라이브러리는 `psgGridcnt` 를 서로 다른 승객 유형 수에서
  유도하므로 성인 열 명이면 `1` 이다. `psgGridcnt="2"` 로 보내면 66 KB 짜리 서버
  렌더링 페이지가 오고, 그것은 `단체승차권 직통 / 예약내역 페이지` 이며
  `/ata/selectListAta01033_n.do` 로 결제를 넘긴다. **예약을 만들지 않는다.** 앞서
  기록해 둔 "풀 수 없는 열 자리 단체 예약이 남을 수 있다"는 위험은 존재하지
  않았다 — 잡히는 것이 없으니 남을 것도 없다. `search_group_trains` 는 남는다.
  읽기이고, 동작하며, 이 클라이언트가 예약을 끝내지 못해도 단체 좌석과 운임은
  알아볼 값이 있다. 10명 하한이 살아 있는 것은 앱이 **검색**에도 같은 수를
  강제하기 때문이다(`ara0101v.js:551-566`). `SRT_LIVE_MUTATION_CATEGORIES` 는
  움직이지 않았다 — 단체는 `reserve` 범주를 타고 있었고, 그것이 없어졌다고 집합이
  줄어서는 안 된다.

### Security

- **전송 계층에서 범주를 막는다.** `post_mutation_form` 과 그 아래의
  `_send_mutation_request` 가 `SRT_LIVE_MUTATION_CATEGORIES` 밖의 범주를
  거부한다. 클라이언트 메서드에서만 막으면 `SrtClient.http` 로 직접 내려가는
  호출자가 우회한다.
- **범주와 라우트가 양방향으로 묶인다.** `SRT_MUTATION_ROUTE_CATEGORIES` 가
  라우트마다 정확히 한 범주를 지정하고, `assert_mutation_route` 와
  `assert_mutation_route_category` 가 둘을 함께 확인하므로 한 범주의 consent 를
  다른 범주의 엔드포인트로 돌릴 수 없다. mutation 라우트들은 `READ_ONLY_ROUTES`
  **밖**에 있고 `assert_read_only_request()` 가 전부 거부한다.
- **카드 비밀값을 라우트가 아니라 본문에서 막는다.**
  `safety.CARD_SECRET_FIELDS`(`stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`,
  `athnVal1`)는 `payment` 로만 이동할 수 있고, 이 규칙은
  `assert_read_only_request` 와 mutation 전송 경계 양쪽에서 검사된다. 손으로
  조립한 결제 본문을 **허용된 다른** 라우트로 — allowlist 에 있는 읽기나, 유효한
  `category="reserve"` consent 를 탄 예약 라우트로 — 보내는 것은 범주 위반도
  라우트 위반도 아니다. `payment` 가 실제로 열린 뒤로 이 검사는 결제 라우트가 아닌
  모든 경로에서 유일한 자물쇠다.
- **결제 consent 는 카드 종류를 정확히 하나 밝혀야 한다.** `fake_card_only`
  (과금되지 않는 시험 카드)와 `real_card_acknowledged`(실제 청구) 중 하나이고,
  **둘 다도 둘 다 아님도 거부된다** — 애매한 consent 는 결제를 실어 보내면 안 되는
  상태다. 이 플래그가 생기기 전에 쓰인 consent 는 뜻이 그대로다.
- **마스킹 구멍 둘을 막았다.** `pnr_no` 가 `SENSITIVE_KEYS` 에 없는데 `pnrNo` 와
  `pnr_number` 는 있어서, 필드 이름으로 데이터클래스를 가리는 `redact_value` 가
  `SrtReservationHold` 와 `SrtReservationSummary` 의 실제 PNR 을 그대로 통과시켰다.
  쿠폰 번호와 비밀번호도 어느 쪽도 가려지지 않았다 — `dscp_pwd` 는 리터럴
  `password` 가 아니고, 쿠폰 번호는 길어야 열 자리라 13–19 자리 연속을 보는
  `CARD_RE` 에 걸리지 않는다. 그래서 dry-run 미리보기가 쓸 수 있는 쿠폰을 통째로
  인쇄했을 것이다. 환불 반환 비밀번호는 세 철자 모두(`ogtkRetPwd`, `tkRetPwd`,
  `retPwd`), `buyPsNm`/`psgNm`, 그리고 `SrtPaymentCard` 의 속성 이름들이 함께
  들어갔다 — 2자리 PIN, `YYMM` 유효기간, `YYMMDD` 생년월일은 모두 `CARD_RE` 를
  빠져나간다. 환불의 `saleDt`/`saleWctNo`/`saleSqno` 는 일부러 가리지 않는다:
  비밀번호가 가려진 상태에서 그것들은 아무 것도 인가하지 않고, 전부 가려진
  미리보기는 아무 말도 하지 않는다.
- **`MutationPreview` 는 payload 를 `redact_payload()` 로 통과시킨다.** 미리보기가
  카드 데이터, 개인정보, PNR, NetFunnel 키를 담을 수 없다.
- **`SrtPaymentResult.succeeded` 와 `.failed` 는 일부러 서로의 여집합이 아니다.**
  알아보지 못한 상태는 *모름*이다. 눈감고 결제를 재시도하면 두 번 청구된다.

### 근거

전송 가능한 세 라우트의 전문은 우리 번들이 아니라 srtgo 에서 왔고, 각각 라이브
왕복 한 번이 유일한 뒷받침이다. 그 한 번이 건드리지 않은 필드에는 정적 근거가
없다.

- **취소 `/ard/selectListArd02045_n.do`.** 이 형태는 srtgo 에서 왔고 v2.0.41
  오프라인 번들 21,673 파일에서 0-hit 이다(`jrnyCnt="1"` 값만 `ara0101v.js:92`
  가 일부 뒷받침한다). 2026-07-25 라이브 서버로 예약→취소 왕복을 한 번 돌렸다 —
  수서→부산, 성인 1명, 일반실, 편도 1건. 예약은 `strResult=SUCC` 와
  `msgCd=IRR000018`("결제하지 않으면 예약이 취소됩니다.")과 PNR 을, 취소는
  `strResult=SUCC` 와 `msgCd=IRG000000`("정상처리되었습니다")을 돌려줬고, 이어서
  다시 읽은 승차권 목록에는 그 예약의 흔적이 없었다. 결제하지 않았으므로 청구된
  것도 없다. 이 왕복은 취소 라우트와 그 정확한 세 필드 본문
  (`pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"`), 그리고 예약 쪽의 라이브 배선 —
  열차 검색과 같은 NetFunnel `act_10` 키 흐름(`act_19` 가 아니다)과 클라이언트가
  보내는 referer — 을 확인해 준다. 확인된 범위는 그 한 번, 성인 1명·편도 1건이다.
  다구간, 단체, 예약대기는 건드리지 않았다.
- **결제 `/ata/selectListAta09036_n.do` 와 환불
  `/atc/selectListAtc02063_n.do`**(발권 정보 조회는 `/atc/getListAtc14087.do`).
  셋 다 srtgo 에서 왔고 v2.0.41 번들 21,673 파일에서 0-hit 이다 — 번들에는
  `Atc02*` 계열 자체가 없다. 우리 앱은 이 경로로 결제하지 않는다:
  `#rsvForm` 을 `Ard02017`/`Ard02018` 서버 렌더링 WebView 로 직렬화한 뒤
  TransKey 보안 키패드(`AndroidManifest.xml:143`)와 RaonSecure FIDO(`:315`)로
  청구한다. 2026-07-26 검증은 두 단계였다. 먼저 돈이 들지 않는 프로브 — 가짜 카드와
  존재하지 않는 PNR 을 두 라우트에 보냈고, 환불 조회는
  `strResult=FAIL`/`msgCd=WRT300005`("조회자료가 없습니다."), 결제는
  `strResult=FAIL`/`msgCd=WRT100170` 이라는 정상 업무 봉투로 답했다. 404 도 HTML
  오류 껍데기도 아니었으므로 라우트가 이 앱 버전에 존재한다는 사실이 아무 것도
  쓰지 않고 확인됐다. 그다음 라이브 서버로 실제 왕복 한 번: 수서→동탄
  (`0551`→`0552`, 가장 짧은 구간), 2026-08-09, 315 열차, 성인 1명, 편도 1건,
  7,500원. 결제는 `strResult=SUCC`/`msgCd=IRT000000`, 두 단계 환불은
  `strResult=SUCC`/`msgCd=IRT200277` 을 돌려줬고, 별도 세션에서 그 계정에 예약도
  승차권도 남지 않은 것을 확인했다. 확인된 범위는 성인 1명·편도 1건·일반실·개인
  카드 일시불 한 번뿐이다. 단체, 다구간, 예약대기, 법인 카드, 할부는 건드리지
  않았다. 이 왕복이 정리해 준 것이 하나 더 있다 — srtgo 의 환불 필드 철자
  `tkRetPwd`/`psgNm`/`pnr_no` 는 맞다. 우리 앱의 로컬 캐시 철자
  (`retPwd`/`buyPsNm`/`pnrNo`, `webview/b.java:645,648`)와 어느 쪽이 옳은지가
  미해결이었는데, 라이브 실행이 srtgo 쪽을 보냈고 서버가 환불했다. srtgo 는
  korail 의 `txtPrnNo` 에서는 틀렸고 여기서는 맞다. 단일 출처 필드명은 부류로
  믿거나 불신할 것이 아니라 하나씩 시험해야 한다.
- **두 참조 라이브러리는 출처가 둘이 아니라 하나다.** srtgo 의 결제 dict 는
  ryanking13/SRT 의 것과 한국어 주석만 걷어내면 글자 단위로 같다 — 같은 키, 같은
  값, 알파벳순이 아닌 같은 순서, 같은 변수명, 같은 시그니처. srtgo 는 커밋
  `8423f90` "Internalize SRT"(2024-12-13)가 그것을 통째로 들여올 때까지
  `SRTrain` 에 의존했다. 환불은 더하다 — ryanking13/SRT 에는 환불이 아예 없어서
  srtgo 가 유일한 출처이고 대조할 상류가 없다. 두 클라이언트가 같은 것을 보낸다는
  사실은 독립된 뒷받침이 아니다. 덧붙여, "이 폼의 필드명은 전부 0-hit"이라는
  뭉뚱그린 주장은 틀리다 — 라우트와 특징적인 필드명은 정말로 번들에 없지만
  `mbCrdNo`, `totPrnb`, `jrnyCnt`(예약 JS)와 `buyPsNm`, `saleWctNo`, `saleSqno`,
  `retPwd`(로컬 `"ticketListOffline"` 캐시 핸들러, `webview/b.java:606-649`)는
  나온다. 이 라우트들의 요청 필드로 나오지 않을 뿐이다.
- **네 확인 코드가 형제 korail 앱의 것과 같다** — 예약 `IRR000018`, 취소
  `IRG000000`, 결제 `IRT000000`, 환불 `IRT200277`. 두 사업자가 예약 플랫폼을
  공유한다는 관찰이지, 백엔드에 대해 증명된 주장은 아니다.
- **환승 검색 응답 모양은 2026-07-26 읽기 프로브로 확인됐다.** 동대구(0015)→
  광주송정(0036), 20260809 080000. 직통 검색은 `WRD000061`("직통열차는 없지만,
  환승으로 조회 가능합니다.")로 답했고, 환승 검색은 평범한 `dsOutput1` 열 행을
  전부 `chtnDvCd="2"` 로 돌려줬으며, 한 여정의 두 다리가 `trnOrdrNo` 를 공유했다:
  `1` → 382(동대구→오송) + 411(오송→광주송정), `2` → 14(동대구→천안아산) +
  475(천안아산→광주송정), `3` → 316 + 655. `...2` 열은 모든 행에 있고 전부 빈
  문자열이다 — 둘째 다리가 열이 아니라 별도의 행이기 때문이다. **이 읽기는 근거
  등급을 하나도 옮기지 않았다.** `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` 의
  추론된 슬롯 2 키 다섯(`stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`,
  `dptStnRunOrdr2`, `arvStnRunOrdr2`)은 여전히 추론이다. 응답의 열이 비어 있다는
  것은 **요청** 폼이 그것을 채우기를 원하는지에 대해 아무 말도 하지 않는다.
  이름이 같은 응답 열과 요청 필드는 서로 다른 것이고, 요청 쪽은 예약 캡처만이
  정리할 수 있다. 환승 검색과 환승 예약은 이 라이브러리에서 한 번도 보낸 적이
  없다.
- **좌석배치도 읽기는 2026-07-26 라이브로 확인됐다** — 수서→동탄, 20260812,
  315 열차, 25,930바이트, 좌석 칸 74개. 이 라우트와 그것이 직렬화하는
  `trnScarSeatFrm` 폼은 v2.0.41 번들에 0-hit 이다. 둘 다 서버가 렌더링하는
  것에만 존재하기 때문이다.
- **`register_discount_coupon` 은 한 번도 보낸 적이 없다.** 라우트, 필드명,
  응답 키 모두 v2.0.41 번들 21,673 파일에서 0-hit 이고, 번들에는 `/arb/` 라우트
  자체가 없다. 형태는 라이브 쿠폰 페이지의 `couponReg()` 그 자체다 — `#couponInfo`
  (입력 둘, PNR 없음, 회원번호 없음, NetFunnel 키 없음)를 직렬화해 JSON 으로
  보내고 `resultMap[0].RTNCD`/`.MSG` 를 읽는다. 번들이 뒷받침하는 것은 전문 양쪽의
  어휘뿐이다 — `messages.js:111-113` 이 이 흐름의 검증 거부 둘과 성공 문구
  (`mysrt006`/`007`/`008`)를, `sub/main.html:475` 가 회원 플래그 `DSCP_YN` 을
  담고 있다. 응답 역시 관측된 적이 없어서 `SrtCouponRegistrationResult` 는
  페이지 자신의 극성(`RTNCD == "N"` 이면 실패)을 지키되 한 곳에서만 더 엄격하다 —
  빈 `RTNCD` 나 없는 `RTNCD` 는 `SrtProtocolError` 다. 그 극성에서는 코드가 없는
  것이 성공으로 읽히기 때문이다.
- **`search_public_discount_trains` 도 한 번도 보낸 적이 없다.** 이 라우트의
  응답은 봉투도, 채워진 할인율도, `gdNo` 왕복도 관측된 적이 없어서 페이저를
  **일부러 두지 않았다** — 멈출 조건을 본 적이 없다. 이 경로에는 다리가 둘이고
  검색하는 것은 하나다: `goSubmit()` 은 `method="get"` 폼을 이쪽으로 돌려놓고
  **화면을 이동**시키며, 돌아온 조회결과 페이지가 `#seatSearchForm` 을 *같은
  경로*로 POST 해서 JSON 에서 행을 그린다. 구현된 것은 두 번째뿐이고, 첫 번째는
  추정이 아니라 측정했다: 읽기 전용 GET 프로브 넷(146필드 전체 여정, 같은 여정에
  `PBL_DISC_CD="04"`, 맨 `?type=`, 중복 제거한 여정)이 매번 142,594바이트를
  세션 id 만 빼고 바이트 단위로 같게 돌려줬고, 여덟 개 `var s*` 수화 슬롯과 세 개
  `pblDisc*` 입력이 매번 비어 있었다. 새 행 열 둘 `gnrmBkclDcntRt` 와
  `sprmBkclDcntRt`(일반실·특실 공공할인율, 정수 퍼센트)가 이 검색의 요점이고,
  둘 다 v2.0.41 번들에 0-hit 이다.
- **공공할인 자격 읽기는 2026-07-26 라이브로 확인됐다 — 아무 것도 승인되지 않은
  계정으로.** 206,268바이트, `var dataNCheck` 여덟 플래그 전부 비어 있음,
  `is_eligible` 은 `False`. 그것은 예외가 아니라 반환값이다. 페이지는 거부처럼
  반응하지만("당신은 하나도 갖고 있지 않다"), 그것이 곧 질문에 대한 답이다.
  코드와 슬롯의 대응은 추론이며 모델 docstring 이 그렇게 밝힌다 — 무엇도
  `PBL_DISC_CD` 를 `dataNCheck` 옆에 쓰지 않고, 둘을 잇는 것은 플래그 둘을 한꺼번에
  읽는 유일한 분기에 달린 페이지 자신의 주석
  ("다자녀(01)와 임산부(02)가 신청이 승인된 경우")뿐이다.
- **할인쿠폰 목록 읽기는 2026-07-26 라이브로 확인됐다 — 쿠폰이 하나도 없는
  계정으로.** 77,056바이트, `ul.coupList` 가 있고 비어 있으며 "보유한 쿠폰이
  없습니다." 채워진 행 모양은 확인되지 않았고 `DiscountCoupon` 의 docstring 이
  그렇게 말한다. 여섯 필드명은 페이지 자신의 주석 처리된 디자이너 템플릿에서 왔고,
  모든 값은 파싱한 숫자가 아니라 표시 문자열로 남는다 — "23%" 를 숫자로 바꾸는 것은
  서버가 내는 것을 아무도 본 적 없는 모양에 구조를 지어내는 일이다. 이것이 정규식이
  아니라 파서인 이유도 그 템플릿이다: 라이브 페이지는 그럴듯한 숫자가 든 두 쿠폰
  템플릿을 `ul.coupList` **안에** 주석으로 싣고 있고, `html.parser` 는 주석 안
  마크업을 파싱하지 않지만 정규식은 빈 계정에서 쿠폰 두 개를 만들어 냈을 것이다.
- **예약 목록 읽기는 2026-07-26 빈 경우만 확인됐다.** `resultMap[0].strResult=SUCC`,
  `IRZ000005`, "조회할 자료가 없습니다.", `trainListMap: []`, `payListMap: []`,
  `rowCnt: 0`, `totPageCnt: 0`. 여기서 빈 결과는 열차 검색이 쓰는
  `strResult=FAIL`/`WRG000000` 이 아니라 빈 *배열*이고, 같은 성공 응답이
  `rsMap[0]` 에 `FAIL`/`WRT300005` 라는 두 번째 봉투를 함께 싣는데 그것은 일부러
  실패로 읽지 않는다. 채워진 행 모양은 **미확인**이다 — 컨테이너 짝과 모든 행
  필드명이 srtgo(`srt.py:1069-1082`)에서 왔고, `payListMap`, `tkSpecNum`,
  `iseLmtTm`, `stlFlg` 는 v2.0.41 번들에 0-hit 이다. 우리 번들이 뒷받침하는 것은
  라우트와 `pageNo` 뿐이며 그것도 WebView GET 으로서다
  (`SRForegroundDialogActivity.java:31`, `sub/ticketList.html:405`). JSON-over-POST
  철자는 srtgo 의 것이고, allowlist 에 오른 것은 POST 뿐이다.
- **NetFunnel 획득→반납 왕복은 2026-07-26 라이브로 확인됐다** — 256자 키와
  `ttl=0`/`nwait=0` 을 실은 `5002:200`, 이어서 `5004:200`. 201 폴링 경로는
  확인되지 않았다. 평상시 부하에서는 대기열이 걸리지 않고, 걸리게 하려고 부하를
  만들지는 않았다. 그 실행이 어떤 픽스처도 잡지 못했을 결함을 잡았다 — 키 모양
  가드가 키를 128자로 제한하고 있었는데 실제 키는 256자라, 모든 `setComplete` 가
  가드에 걸려 조용히 삼켜지고 있었다.
- **좌석지정의 제출 대상은 추론이며, 운영자가 정리해야 할 부분이다.**
  `fn_submit()` 은 `ara0101v.js:882` 에서 호출되고 번들 어디에도 정의가 없다 —
  정의는 서버가 렌더링하는 예약 페이지에 있다. 이 라이브러리는 그다음 줄에 주석
  처리된 `//Sr.ara1001l.fn_callReserv();` 를 근거로
  `/arc/selectListArc05013_n.do` 로 POST 한다. 그 함수가 `#rsvForm` 을 정확히 그
  URL 로 직렬화하기 때문이다(`ara1001l.js:1541-1550`). 라이브로 하나 보내기 전에
  `/ara/ara0101v.do` 를 받아 인라인 `fn_submit` 을 읽어라 — 좌석배치도를 연 것과
  같은 방법이다. 다른 곳을 겨눈다면 본문은 그대로 맞고 라우트만 움직인다.
- **`seatNo1_*` 는 내부 좌석번호가 아니라 인쇄된 라벨을 싣는다.** 앱은 그것을
  `scarSeatNm` 에서 만들고 `scarSeatNo` 는 쓰지 않는다(`ara0101v.js:870-874`).
  `seatNo` 라고 적힌 필드가 이름을 전송한다.

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
