# SRT 감사 — 07: 환불·취소 (07-refund)

담당 영역: 미결제 취소(예약취소) / 결제후 환불(환불) 2단계 흐름 / 위약금·부분환불 유무 /
환불 응답의 업무실패 분류(dsOutput0 등) / 승차권·예약 목록 조회.

대상 저장소: `srt-mobile-api`

## 0. 방법론 메모

이 라이브러리는 이례적으로 자기 출처를 상세히 문서화한다 (client.py/payloads.py/parsers.py
docstring, docs/VERIFICATION.md, docs/analysis/ref-srtgo_plus.md, docs/analysis/
cross-validation-2026-07-21.md). 감사는 그 문서화된 주장을 다시 베끼는 대신, 각 주장을
**독립 아티팩트로 재검증**하는 데 집중했다: smali/jadx grep 재현, `tests/fixtures/*` 직접 열람,
`redaction.py`/`normalize_result_row` 실제 코드 실행. 아래 findings 는 전부 이 재검증 과정에서
나온 것이며, docstring 이 이미 밝힌 한계(예: "0-hit in bundle", "단일 소스 srtgo") 를 그대로
반복 보고하지 않았다.

## 1. 앱 기능 전체 목록 (담당 영역)

| # | 기능 | 엔드포인트 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|---|---|---|---|---|
| 1 | 예약/발권 목록 조회 (JSON) | `POST /atc/selectListAtc14016_n.do` | `analysis/jadx/sources/.../SRForegroundDialogActivity.java:31`, `analysis/apktool/smali/.../SRForegroundDialogActivity$a.smali:47` (WebView 진입점), `apktool/assets/offline/sub/ticketList.html:405` (data-url) — 필드명/응답봉투는 앱에 없음, srtgo 실측 + 2026-07-26 라이브 빈 목록 캡처 | `SrtClient.get_reservations` → `parsers.parse_reservation_list_response` (`client.py:284`, `parsers.py:2004`) | 있음 |
| 2 | 승차권 확인 (HTML, 원문 반환) | `GET /atc/selectListAtc14017_n.do` | `analysis/apktool/smali/.../SRWebActivity.smali:4257`, `jadx/sources/.../SRWebActivity.java` | `SrtClient.get_ticket_list` (`client.py:200`) — HTML 그대로 반환, 파싱 없음(의도) | 있음 (의도적 부분 구현) |
| 3 | 미결제 예약취소 (예약대기 취소 버튼 포함) | `POST /ard/selectListArd02045_n.do` | 앱 번들 0-hit; 실서버가 렌더링하는 승차권 목록 페이지의 인라인 `cncConfirm()` (docstring 인용, 아티팩트로 재확인 불가 — Finding 3) + 2026-07-25 라이브 캡슐 `SUCC`/`IRG000000` | `SrtClient.cancel` → `payloads.unpaid_reservation_cancel_payload` → `parsers.parse_unpaid_cancel_response` (`client.py:1417`) | 있음 |
| 4 | 환불 1단계: 원승차권 정보 조회 | `POST /atc/getListAtc14087.do` (본문 없음, Referer 로 PNR 전달) | 앱 번들 0-hit; srtgo 단독 출처; 2026-07-26 라이브: 존재하지 않는 PNR→`WRT300005`, 실제 티켓 1건 identity 응답 | `SrtClient.get_refund_ticket_info` → `parsers.parse_refund_ticket_info_response` (`client.py:1727`) | 있음 |
| 5 | 환불 2단계: 승차권 환불 실행 | `POST /atc/selectListAtc02063_n.do` | 앱 번들 0-hit; srtgo 단독 출처; 2026-07-26 라이브 `SUCC`/`IRT200277`, 이후 계정 재조회로 빈 상태 확인 | `SrtClient.refund` → `payloads.refund_payload` → `parsers.parse_refund_response` (`client.py:1788`) | 있음 |

담당 영역에서 발견된 엔드포인트는 5개이며 전부 라이브러리에 대응 메서드가 존재한다("없는 것"
없음). 문제는 구현의 **신뢰성/정확성** 쪽에서 발견되었다 — 아래 상세 참조.

부가로 확인/재확인한 것 (findings 아님, 참고용):
- `unpaid_reservation_cancel_payload` 의 3개 필드(`pnrNo`/`jrnyCnt`/`rsvChgTno`) — srtgo 출처,
  `jrnyCnt="1"` 은 `ara0101v.js:92` 로 앱 자체가 뒷받침. `rsvChgTno` 는 앱에 0-hit
  (`cross-validation-2026-07-21.md:229` 로 독립 확인).
- `refund_payload` 의 7개 필드와 `tkRetPwd`/`psgNm`/`pnr_no` 스펠링 — 앱의 로컬 오프라인 캐시
  (`webview/b.java:645-651`, smali `b.smali:145-185`) 는 다른 스펠링(`retPwd`/`buyPsNm`/`pnrNo`)을
  쓰지만, 이는 캐시 필드이지 API 필드가 아니라는 라이브러리의 주장을 b.java 직접 열람으로 확인함 —
  타당함.
- `redaction.SENSITIVE_KEYS` 가 `ogtkRetPwd`/`tkRetPwd`/`retPwd`/`buyPsNm`/`psgNm`/`pnrNo`/`pnr_no`
  전부를 포함하는지 코드로 직접 확인 (`redaction.py:21,60,70-77`) — 포함됨. 환불 1단계 파서의
  `safe_raw = redact_mapping(data)` (`parsers.py:1795`) 가 실제로 자격증명을 가린다는 docstring의
  핵심 안전 주장은 사실로 확인됨 — **문제 없음** (advisor 가 우려했던 지점이지만 재확인 결과
  이상 없음).
- `post_mutation_form`/`_send_mutation_request` 의 5중 게이트(consent, dry_run, live-category,
  card-kind, route/category 교차검증)를 cancel/refund 경로에서 추적 — 우회 경로 없음.
- 위약금 텍스트(`messages.js:10,13,211,221`, `ara1001l.js:1319,1397`)는 전부 **예매 전** 조기예매
  할인 안내 알럿이며 환불 응답 필드가 아님. `commCode.js` 의 `tkKndCd` 43/44
  (`취소수수료수납`/`취소수수료환불`, :1675-1683) 는 영수증 분류용 코드이며 환불 응답 필드가
  아님. `tkSttCd` (승차권상태코드, :1397-1471) 는 반환접수신청(05)/접수반환완료(06)/반환(09)/
  로칼반환(13) 등 티켓 상태 코드이나 부분(승객별) 환불이나 위약금 금액 필드는 어디에도 없음 —
  아래 Finding 4 참조.

---

## 2. Findings

### S7-01 [high, risk] `normalize_result_row` 컨테이너 우선순위가 환불/취소 응답의 업무실패 분류를 깨뜨릴 수 있음

- **app_evidence**: `analysis/apktool/smali` 전체에서 `Atc02063`/`Ard02045`/`getListAtc14087` 는
  0-hit (재확인 완료, 아래 명령 결과), 즉 앱 자체 아티팩트로는 이 두 엔드포인트의 실제 응답
  컨테이너 조합(‘resultMap 만’ 오는지, ‘outDataSets.dsOutput0’ 도 같이 오는지)을 검증할 수 없다.
  다만 **같은 `/atc/` 패밀리의 예약목록(`selectListAtc14016_n.do`) 응답**은 이미 하나의 실제
  응답 안에 `resultMap`(SUCC/IRZ000005) 과 `rsMap`(FAIL/WRT300005) 이라는 **서로 다른 결과를
  말하는 두 개의 병렬 컨테이너**를 동시에 담아 보낸 전례가 실측되어 있다
  (`parsers.py:2009-2037`, `docs/IMPLEMENTATION_PROGRESS.md:783-789`). 즉 이 백엔드 패밀리가
  "관련 없는/오래된 컨테이너를 곁다리로 얹어 보낸다"는 패턴은 이미 한 번 관측됐다.
- **library_evidence**: `src/srt_mobile_api/parsers.py:1113-1117`
  ```python
  def normalize_result_row(data):
      out = data.get("outDataSets") or {}
      if isinstance(out, dict) and "dsOutput0" in out:
          return _first_row(out.get("dsOutput0"))
      return _first_row(data.get("resultMap"))
  ```
  이 함수는 `parse_unpaid_cancel_response`(`:1619`), `parse_refund_response`(`:1902`),
  `parse_card_payment_response`(`:1739`) 세 곳이 공유한다. `outDataSets` 안에 `"dsOutput0"`
  **키가 존재하기만 하면**(값이 `[]`/`None`이라도) `resultMap` 은 아예 보지 않는다.
- **detail**: 직접 실행으로 재현함 (아래는 실제 실행 결과):
  ```
  data = {"outDataSets": {"dsOutput0": []},
          "resultMap": [{"strResult": "FAIL", "msgCd": "WRT999999", "msgTxt": "환불 불가 - 위약금 초과"}]}
  parse_refund_response(data)  →  SrtProtocolError: SRT refund response must contain a resultMap result row

  data = {"outDataSets": {"dsOutput0": None},
          "resultMap": [{"strResult": "SUCC", "msgCd": "IRG000000", "msgTxt": "정상처리되었습니다"}]}
  parse_unpaid_cancel_response(data)  →  SrtProtocolError: SRT cancel response must contain a resultMap result row
  ```
  즉 서버가 실제로는 환불 성공/실패(또는 취소 성공)를 `resultMap` 에 정확히 담아 보냈더라도,
  그 옆에 **비어있거나 무관한** `outDataSets.dsOutput0` 를 하나만 곁들이면 라이브러리는 그
  진짜 결과를 전혀 읽지 않고 "응답 형식이 이상하다"는 `SrtProtocolError` 를 던진다. 호출자
  입장에서는 "환불됐는지 아닌지" 를 전혀 알 수 없는 예외로 바뀐다 — 이는 정확히 담당 영역에서
  요구된 "환불 응답의 업무실패 분류" 가 실패하는 시나리오다. 2026-07-25/26 라이브 실행 1건씩은
  이 조합을 우연히 트리거하지 않았을 뿐(그 응답들은 `outDataSets` 키 자체가 없었다는 것이
  docstring 의 일관된 서술), 실제로 SRT 서버가 이 조합을 보내는지는 **미검증**이다. 다만 같은
  API 패밀리(예약목록)에서 "여러 컨테이너를 동시에 보내고 그 중 하나만 신뢰해야 한다"는 패턴이
  실측되어 있으므로 개연성이 낮지 않다. `tests/test_cancel_mutation.py`,
  `tests/test_refund_mutation.py` 어디에도 "두 컨테이너 동시 존재" 케이스를 pin 하는 테스트가
  없다 (grep 으로 확인).
- **suggested_fix**: `normalize_result_row` 를 "dsOutput0 컨테이너가 **비어있지 않은 유효한 행을
  담고 있을 때만** 그것을 우선하고, 아니면 resultMap 으로 폴백"하도록 완화하거나, 최소한 cancel/
  refund 파서가 "resultMap 이 유효한 행을 갖고 있으면 그것을 우선"하도록 우선순위를 뒤집는
  헬퍼를 별도로 두는 것을 검토. 어느 쪽이든 "두 컨테이너 동시 존재, 서로 다른 status" 테스트를
  추가해 의도를 pin 해야 함.

### S7-02 [medium, doc-drift] 예약목록 "populated row" 라이브 검증 여부에 대한 코드 내부 모순

- **app_evidence**: 없음 (이 finding 은 앱 근거가 아니라 라이브러리 **자체 문서 간의 불일치**에
  관한 것 — 그래서 두 쪽 모두 라이브러리 근거로 제시함).
- **library_evidence**:
  - 모순 A (검증됐다는 주장): `src/srt_mobile_api/parsers.py:1948-1952`
    > "LIVE 2026-07-26 settled what the non-empty row looks like, and several of its fields are
    > JSON NUMBERS ...  `{"pnrNo": "3202607...", "rcvdAmt": 7500, "jrnyCnt": 1, "tkSpecNum": 1,
    > "stlFlg": "N", "rsvChgTno": 0}`"
  - 모순 B (검증 안 됐다는 주장, 4곳):
    - `src/srt_mobile_api/parsers.py:2043` (`parse_reservation_list_response` docstring):
      "The NON-EMPTY shape remains UNVERIFIED by this repository."
    - `src/srt_mobile_api/models.py:618-627` (`SrtReservationSummary`):
      "the NON-EMPTY row shape has never been observed by this repository: the account used for
      live verification has no reservations..."
    - `src/srt_mobile_api/client.py:301-307` (`get_reservations`):
      "The populated shape is UNVERIFIED here and its row field names come from srtgo..."
    - `tests/test_reservation_list.py:12-13` (모듈 docstring): "The empty envelope is
      live-verified (2026-07-26); the populated row shape is not, and the tests that exercise it
      say so."
    - `docs/IMPLEMENTATION_PROGRESS.md:783-789`: "The POPULATED row shape is unverified: every row
      field name comes from srtgo (`srt.py:1069-1082`), and `payListMap`, `tkSpecNum`, `iseLmtTm`
      and `stlFlg` are 0-hit in the v2.0.41 bundle."
- **detail**: `parsers.py:1948` 의 "LIVE 2026-07-26 settled..." 문장과 구체적인 행 값
  (`rcvdAmt: 7500` 는 같은 날 카드결제 라이브런의 실제 결제 금액과 동일)은, 실제로는 그 결제/환불
  라운드트립 도중 `get_reservations` 를 호출해 관측한 진짜 캡처였을 가능성이 있다. 그러나
  `docs/VERIFICATION.md`, `docs/IMPLEMENTATION_PROGRESS.md` 어디에도 이 특정 캡처(PNR
  `3202607...`, rcvdAmt 7500, stlFlg "N") 가 기록되어 있지 않고, 오히려 라이브러리 안의 **4곳**이
  일관되게 "populated 케이스는 한 번도 관측된 적 없다"고 명시적으로, 그리고 반복적으로 못박고
  있다. 두 서술이 동시에 참일 수 없다 — 어느 한쪽은 틀렸다. 이 필드들(`rcvdAmt` 등)은 바로
  `pay_with_card` 의 결제 금액 산출에 쓰이므로(`payloads.py:2091` `_payment_amount`), "실측으로
  확정됐다"는 근거 없는 확신이 코드에 남아있으면 향후 유지보수 시 이 필드의 실제 신뢰도를
  오판할 위험이 있다. `tests/fixtures/` 에는 이 캡처를 뒷받침하는 파일이 없음(grep 으로 확인,
  0건).
- **suggested_fix**: 어느 쪽이 사실인지 원 저자에게 확인 후 한쪽으로 통일. 실측이 맞다면
  `parse_reservation_list_response`/`SrtReservationSummary`/`get_reservations`/
  `test_reservation_list.py`/`IMPLEMENTATION_PROGRESS.md` 5곳의 "UNVERIFIED" 서술을 갱신하고
  `docs/VERIFICATION.md` 에 그 캡처를 기록. 아니라면 `parsers.py:1948` 의 "LIVE 2026-07-26
  settled" 문구를 "example shape, srtgo-attested" 정도로 낮춰야 함.

### S7-03 [low, unverifiable] cancel 폼의 "서버 자신이 인라인으로 증명한다"는 근거가 저장소 어떤 아티팩트로도 재현되지 않음

- **app_evidence**: `tests/fixtures/ticket_list_expired_session.html` — 이 파일 자체가
  "REDACTED excerpt of a REAL response, captured 2026-07-26 from GET
  /atc/selectListAtc14017_n.do" 라고 자기 서술하는, **바로 그 엔드포인트의 실제 캡처**
  (미인증 세션)다. 그러나 이 파일에는 `cncConfirm` 함수가 전혀 없고 `<ul id="ticketList"></ul>`
  이 빈 채로만 존재한다 (`grep -c cncConfirm` → 0). `analysis/` 전체(디컴파일 산출물)에서도
  `cncConfirm`/`Ard02045` 관련 인라인 스크립트는 0-hit (서버 렌더링이므로 당연히 예상되는 결과).
- **library_evidence**: `src/srt_mobile_api/payloads.py:1802-1819` (`unpaid_reservation_cancel_
  payload` docstring)와 `docs/VERIFICATION.md:1286-1297` 이 공통으로 주장:
  > "the ticket-list page the LIVE server renders ships the call inline (`function
  > cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt)` ...) ... **on both the authenticated and the
  > signed-out response**"
- **detail**: "signed-out response 에도 나온다"는 구체적 주장이 저장소 안의 **바로 그 signed-out
  캡처**로 반증되지는 않지만(리팩션 과정에서 "boilerplate" 로 분류되어 잘렸을 수 있음 — 파일
  주석에 "the bulk that is omitted is boilerplate menu/footer markup"), 최소한 **독립적으로
  재확인할 수 없다**. cncConfirm 캡처 자체가 기록되지 않은 라이브 오퍼레이터 세션에서 나온
  서술뿐이라, 이 project 의 다른 모든 라이브 검증(카드/환불/취소)처럼 재현 가능한 근거(스크립트,
  raw 캡처, fixture)가 없다. cancel 라우트/필드/응답봉투 자체는 2026-07-25 실제 취소
  성공(`SUCC`/`IRG000000`)으로 독립적으로 뒷받침되므로 기능 자체의 신뢰도 문제는 아니지만, "앱
  자신이 이 필드명들을 인라인으로 증명한다"는 부가 주장은 저장소 내 아티팩트로는 확인 불가로
  분류한다.
- **suggested_fix**: 다음 라이브 세션에서 `/atc/selectListAtc14017_n.do` 인증 응답을 캡처해
  `cncConfirm` 발췌를 fixture 나 docs/analysis 캡처로 저장 — 현재는 서술만 있고 재현 가능한
  근거가 없다.

### S7-04 [info] 위약금(취소수수료)·부분환불 필드는 이용 가능한 모든 아티팩트를 뒤져도 존재하지 않음 — 결함 아님, 확인된 부재

- **app_evidence**: `analysis/apktool/assets/offline/js/common/messages.js:10,13,211,221`,
  `analysis/apktool/assets/offline/js/ara/ara1001l.js:1319,1397` (조기예매 할인상품 반환수수료
  안내 얼럿 — **예약 전** 표시 문구, 환불 API 응답 필드 아님); `commCode.js:1675-1683`
  (`tkKndCd` 43/44 `취소수수료수납`/`취소수수료환불` — 영수증 분류 코드); `commCode.js:1397-1471`
  (`tkSttCd` 01-13 승차권상태코드, 05 반환접수신청/06 접수반환완료/09 반환/13 로칼반환 포함 —
  티켓 **상태** 코드이지 승객별 부분환불 선택자나 위약금 금액 필드가 아님);
  `apktool/assets/offline/sub/ticket_view.html`, `ticketList.html` (오프라인 캐시 뷰, 환불/취소
  액션 버튼 자체가 없음 — grep 0건).
- **library_evidence**: `src/srt_mobile_api/models.py:866-887` (`SrtRefundResult` — status/
  message_code/message/raw 만 보유, 금액·수수료 필드 없음); `src/srt_mobile_api/payloads.py:2133`
  (`refund_payload` — PNR 전체를 대상으로 하는 단일 취소사유 리터럴만 전송, 승객별/좌석별 부분
  선택 필드 없음).
- **detail**: 담당 영역 지시사항에 명시된 두 주제(위약금, 부분환불)를 위 아티팩트 전체에서
  검색했으나 환불 **응답**이나 환불 **요청**에 수수료 금액, 환불 예정 금액, 또는 승객별 부분
  환불을 선택하는 필드는 어디에도 없다. srtgo/srtgo_plus 레퍼런스(`docs/analysis/
  ref-srtgo_plus.md:365-379`)도 동일하게 `strResult`/`msgTxt` 봉투 이상을 파싱하지 않는다.
  따라서 "전체 티켓 단위 환불만 가능하고 수수료/부분환불 필드가 없다"는 현재 구현은 확보된 모든
  증거와 모순되지 않는다 — 결함이 아니라 **확인된 부재**로 기록한다 (사용자 지시: 발견 시
  "의도된 제외"로만 언급).
- **suggested_fix**: 해당 없음 (정보 제공용). 향후 부분환불/위약금 UI 가 실제 SRT 서버에
  존재한다는 증거(예: 새 라이브 캡처)가 나오면 재조사 필요.

### S7-05 [low] `SrtReservationSummary.settlement_flag` (`stlFlg`) 의미가 문서화되지 않아 cancel/refund 라우팅을 스스로 결정할 수 없음

- **app_evidence**: `analysis/apktool/assets/offline/js/commCode.js:1397-1471` 의 `tkSttCd`
  (승차권상태코드) 테이블에는 결제 여부를 나타내는 유사 개념이 없고, `stlFlg` 라는 이름 자체도
  앱 번들에 0-hit (`docs/IMPLEMENTATION_PROGRESS.md:788`, 독립 grep 재확인: 0건). 즉 "N" 이
  구체적으로 무엇을 뜻하는지(미결제/미정산/기타) 뒷받침할 앱측 근거가 전혀 없다.
- **library_evidence**: `src/srt_mobile_api/models.py:649` (`settlement_flag: str | None = None
  # stlFlg`) — 주석에 wire 필드명만 있고 의미 설명이 없음; `src/srt_mobile_api/parsers.py:1951`
  (`"stlFlg": "N"` 예시, Finding S7-02 로 인해 신뢰도 자체가 불확실) 외에는 라이브러리 어디에도
  `stlFlg` 값의 의미나 `is_paid`/`is_unpaid` 류의 파생 속성이 없음 (grep 재확인).
  `SrtClient.cancel`(미결제용, `/ard/selectListArd02045_n.do`)과
  `SrtClient.get_refund_ticket_info`+`refund`(결제완료용, `/atc/...`)는 서로 다른 consent
  카테고리로 완전히 분리된 별개의 흐름이다(`client.py:1417`, `:1727`, `:1788`).
- **detail**: `get_reservations()` 로 얻은 한 행이 "미결제 예약(→ cancel 로 해제)" 인지 "결제완료
  티켓(→ refund 2단계로 환불)" 인지, 호출자가 라이브러리 자체 API 만으로 판단할 방법이 없다.
  `stlFlg` 가 그 정보를 담고 있을 가능성이 높지만(필드명 자체가 "정산" 을 의미) 의미가 어디에도
  명시돼 있지 않고, 유일하게 관측됐다고 주장된 예시 값("N")조차 Finding S7-02 에서 지적한 대로
  출처가 불확실하다. 실무적으로는 이 라이브러리의 사용자가 "이 예약을 취소해야 하나 환불해야
  하나"를 스스로 추측하거나 `raw_pay` 를 직접 파싱해야 한다.
- **suggested_fix**: 다음 라이브 검증 때 결제 전/후 두 상태의 `get_reservations()` 행을 모두
  캡처해 `stlFlg` 의 실제 의미를 확정하고, 문서화하거나 `is_paid` 같은 파생 프로퍼티를 추가.
