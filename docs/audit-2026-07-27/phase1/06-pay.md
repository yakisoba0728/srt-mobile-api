# SRT 결제 영역 감사 (06-pay)

담당 영역: 결제 경로 전체(카드결제/환불/취소/예약목록 읽기/쿠폰등록), 카드 필드,
할부, 카드정보 마스킹(redaction.py), 안전게이트(consent.py, safety.py, http.py).

대상 저장소: `/Users/yakisoba/Documents/GitHub/srt-mobile-api`

## 방법

- `src/srt_mobile_api/payloads.py`(카드결제·환불·취소·쿠폰 폼 빌더), `models.py`(카드/결제/환불
  타입), `parsers.py`(응답 파서), `client.py`(`pay_with_card`/`refund`/`cancel`/`get_reservations`/
  `register_discount_coupon`), `safety.py`(라우트 화이트리스트·카드시크릿 가드), `consent.py`
  (MutationConsent/카드종류 클레임), `redaction.py`(마스킹)를 전수 정독.
- `analysis/apktool/AndroidManifest.xml`, `analysis/jadx/sources/kr/co/srail/newapp/webview/b.java`,
  `analysis/apktool/assets/offline/js/common/messages.js`로 앱 근거 교차검증.
- `docs/analysis/ref-srtgo_plus.md`(§6 결제, §7 환불/취소), `docs/VERIFICATION.md`,
  `docs/IMPLEMENTATION_PROGRESS.md`, `CHANGELOG.md`로 라이브 검증 이력 확인.
- `tests/test_payment_mutation.py`(877줄), `tests/test_refund_mutation.py`(664줄) 테스트 커버리지 확인.
- 실제 `SrtPaymentCard`/`SrtReservationSummary`로 `card_payment_payload` 를 빌드하고
  `redact_payload`/`redact_value`/`repr()` 결과를 직접 실행해 마스킹 여부를 실측.

## 총평

이 라이브러리의 결제 경로는 이 프로젝트에서 감사한 영역 중 가장 자기검증이 철저한 부분이다.
카드 시크릿 필드(PAN/PIN/유효기한/생년월일)는 (a) 필드명 기반 상시 마스킹(redaction.py,
`SENSITIVE_KEYS`), (b) 모든 mutation 전송 경로에 대한 `assert_no_card_secrets` 바디 검사,
(c) route/category 이중 바인딩(`assert_mutation_route_category`), (d) `fake_card_only` /
`real_card_acknowledged` 상호배타 클레임까지 4중으로 방어되어 있고, 이를 실측 코드 실행으로도
확인했다 (아래 "실행 검증" 참조) — 마스킹을 빠져나가는 경로는 발견하지 못했다.

카드결제(`/ata/selectListAta09036_n.do`, 31필드)와 환불 2단계는 2026-07-26 실서버 라운드트립으로
검증되어 있고, 필드 순서·값까지 `docs/analysis/ref-srtgo_plus.md` §6 의 표와 1:1 일치함을
직접 대조했다 (완전 일치, 불일치 없음). 이 부분은 "있는 것"으로만 집계했다.

findings 는 4건이며 가장 심각한 것도 `medium`이다: (1) OK캐쉬백 포인트/전자지갑/복합결제라는,
앱 자신의 메시지 리소스(`messages.js`)가 실재를 증언하는 결제수단이 라이브러리에 전혀 없음(low),
(2) `SrtReservationSummary` 클래스 docstring의 컨테이너 역할 설명이 실제 필드 배치와 뒤바뀌어
보임(파서 코드 자체는 필드별 주석과 일치하여 버그는 아님, low), (3) 카드 필드의 "검증 규칙" 자체는
앱 자신의 메시지 리소스로 뒷받침되는데 provenance 주석은 다소 비관적으로 서술됨(info), (4)
`get_reservations`의 비어있지 않은 행 스키마가 문서(srtgo)와 다르면 `pay_with_card`가 프리뷰
단계부터 예외로 실패함 — 다만 실패 방향이 안전한 쪽(fail-closed)이라 medium(risk). 안전게이트를
우회하는 구멍이나, 금액/카드 필드 이름·타입 불일치, 마스킹 우회 같은 critical/high 결함은
찾지 못했다.

## 앱 기능 전체 목록 (결제 영역)

| # | 기능 | 엔드포인트 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|------|-----------|---------|-----------------|------|
| 1 | 카드결제 (평문 JSON, 31필드) | `POST /ata/selectListAta09036_n.do` | 0-hit in APK bundle; `docs/analysis/ref-srtgo_plus.md:296-328`; 2026-07-26 실서버 라운드트립 `SUCC`/`IRT000000` | `payloads.card_payment_payload`, `client.SrtClient.pay_with_card`, `parsers.parse_card_payment_response` | 있음 (구현·검증됨) |
| 2 | 카드결제 WebView 경로 (실제 앱이 쓰는 경로: `#rsvForm`→`Ard02017`/`18` + TransKey 보안키패드 + RaonSecure FIDO) | `POST /ard/selectListArd02017_n.do` (개인) / `Ard02018` (단체) | `AndroidManifest.xml:72,134-142`(TransKey/RaonSecure/FIDO 액티비티); `ara1001l.js:1596-1626`; `payloads.py:1878-1884` 주석 | 미구현 (구조적으로 HTTP 클라이언트로 자동화 불가 — TransKey/FIDO는 별도 네이티브 SDK) | 확인불가/구현불가 (설계상 배제, 결함 아님) |
| 3 | 예약대기·미결제 예약 취소 | `POST /ard/selectListArd02045_n.do` | srtgo 단독 출처, 0-hit; `atc14017` 페이지 인라인 `cncConfirm()`; 2026-07-25 실서버 `SUCC`/`IRG000000` | `payloads.unpaid_reservation_cancel_payload`, `client.SrtClient.cancel` | 있음 (구현·검증됨) |
| 4 | 예약/발권 목록 읽기 (결제 대상 PNR·rcvdAmt·tkSpecNum 조회) | `POST /atc/selectListAtc14016_n.do` | srtgo `srt.py:1069-1082`; 2026-07-26 실서버로 EMPTY 케이스만 검증 | `client.SrtClient.get_reservations`, `parsers.parse_reservation_list_response`, `models.SrtReservationSummary` | 있음 (빈 응답만 검증, 비어있지 않은 행 스키마는 srtgo 단독 출처 — 저자가 이미 여러 곳에서 명시) |
| 5 | 환불 1단계: 발권 승차권 식별정보 조회 | `POST /atc/getListAtc14087.do` (무본문) | srtgo 단독 출처, 0-hit; 2026-07-26 실서버 `WRT300005`(존재하지 않는 PNR) 및 실제 환불 라운드트립 | `client.SrtClient.get_refund_ticket_info`, `parsers.parse_refund_ticket_info_response` | 있음 (구현·검증됨) |
| 6 | 환불 2단계: 승차권 환불 실행 | `POST /atc/selectListAtc02063_n.do` | srtgo 단독 출처(ryanking13/SRT 에는 아예 없음), 0-hit; 2026-07-26 실서버 `SUCC`/`IRT200277` | `payloads.refund_payload`, `client.SrtClient.refund`, `parsers.parse_refund_response` | 있음 (구현·검증됨) |
| 7 | 할인쿠폰 등록 | `POST /arb/selectListArb02A01_n.do` | 라이브 쿠폰 페이지 `couponReg()`, 2026-07-26 읽음; `tests/fixtures/discount_coupons_held.html:68-69` 로 필드명 재확인 | `payloads.coupon_registration_payload`, `client.SrtClient.register_discount_coupon`, `parsers.parse_coupon_registration_response` | 있음 (빌드·프리뷰만 가능, 전송은 의도적으로 비활성 — `SRT_LIVE_MUTATION_CATEGORIES`에 미포함) |
| 8 | 할인쿠폰 목록 조회 | `GET /apa/selectListApa03020_n.do` | 라이브 메뉴 `pageMove(...)`, 2026-07-26 읽음 | `client.get_discount_coupons`, `parsers.parse_discount_coupon_page` | 있음 |
| 9 | 공공할인(할인승차권) 검색 | `POST /ara/selectListAra10131_n.do` | 라이브 조회결과 페이지 `#seatSearchForm`, 2026-07-26 읽음 | `payloads.public_discount_search_payload` | 있음 |
| 10 | 할부 결제(개월수 선택) | `ismtMnthNum1` (카드결제 폼 내 필드) | `messages.js:50` `pay029`("할부선택에 대한 정보가 없습니다"); srtgo `INSTALLMENT` 옵션 | `models.SrtPaymentCard.installment_months`, `INSTALLMENT_MONTH_OPTIONS = {0,2..12,24}` | 있음 |
| 11 | 카드 종류 구분 (개인 `J` / 법인 `S`) | `athnDvCd1`, `athnVal1`(생년월일 6자리 또는 사업자등록번호 10자리) | `messages.js:50` `pay027`("주민번호 앞 6자리..."); srtgo 시그니처 | `models.SrtPaymentCard.card_type`, `__post_init__` 길이검증 | 있음 |
| 12 | 카드 비밀번호 앞 2자리 검증 | `vanPwd1` | `messages.js:49-50` `pay024`/`pay025`("비밀번호 앞 2자리...") | `models.SrtPaymentCard.card_password`, 2자리 검증 | 있음 |
| 13 | OK캐쉬백 포인트 결제 | 미확인 (서버렌더링, 번들에 라우트 없음) | `messages.js:29-38` `pay010`~`pay018`("포인트번호", "포인트비밀번호", "사용가능한 포인트..." 등 9개 메시지) | 없음 | **없음 (미구현)** |
| 14 | 전자지갑 결제 | 미확인 (서버렌더링) | `payloads.py:1930` 자체 주석 `PAYMENT_CARD_INPUT_WAY` — "@ 신용카드/OK포인트, "" 전자지갑"; `stlMnsCd` 11 | 없음 | **없음 (미구현)** |
| 15 | 복합결제(카드+포인트 분할결제) | 미확인 (서버렌더링) | `messages.js:39-40` `pay017`("1,000원 이하로 분할 하여 결제 할 수 없습니다"), `pay018`("복합결제 시 포인트는 100원 단위로 사용가능") | 없음 (`ststlGridcnt`/`inrecmnsGridcnt` 는 라이브러리에서 항상 `"1"` 고정) | **없음 (미구현)** |
| 16 | 자주쓰는 카드(저장된 카드) 등록/사용 | 미확인 | `messages.js:44` `pay019`("자주쓰는 카드명에 대한 정보가 없습니다. 등록하시겠습니까?") | 없음 | **없음 (미구현, 편의기능)** |
| 17 | 단체(그룹) 결제 | `POST /ard/selectListArd02018_n.do` (WebView), `Ata01033`(JSON, srtgo 미보유) | `ara1001l.js:1599-1605`; `cross-validation-2026-07-21.md:194,283` | 없음 | 의도된 제외 (사용자 지시: 단체예약 범위 제외) |
| 18 | 카드정보 마스킹(프리뷰/redact) | — | — | `redaction.py` `SENSITIVE_KEYS`(카드 4종 시크릿 필드명+모델 속성명), `CARD_RE`, `redact_payload`/`redact_value` | 있음, 실행 검증 완료(아래) — 우회 경로 미발견 |
| 19 | 결제 안전게이트(consent/route/category) | — | — | `consent.py`(MutationConsent, require_card_kind_claim), `safety.py`(CARD_SECRET_FIELDS, assert_mutation_route_category), `http.py`(`post_mutation_form`/`_send_mutation_request` 이중 검사) | 있음, 정독 결과 우회 경로 미발견 |

위 표는 19개 행이다. "있음" 항목(1,3,4,5,6,7,8,9,10,11,12,18,19 = 13개)은 코드·테스트·문서
근거가 모두 일치하여 문제로 분류하지 않았다. 2번(WebView 결제)은 "구현 불가"(HTTP 클라이언트로는
TransKey/FIDO를 대신할 수 없음), 17번(단체결제)은 사용자 지시에 따른 "의도된 제외"이며 둘 다
결함이 아니다. 나머지 13~16번(포인트/전자지갑/복합결제/자주쓰는카드) 4개가 "없음(미구현)"이다.
`app_functions_extracted = 19`, `implemented_count = 13`.

## 실행 검증 (redaction)

`SrtPaymentCard`(PAN `4111111111111111`, PIN `12`, 생년월일 `990101`, 유효기한 `2612`, 할부 3개월,
`card_type="J"`) + `SrtReservationSummary`(pnr `RN12345678`, `rcvdAmt=36900`, `tkSpecNum=1`,
`dptTm=070000`, `arvTm=090000`)로 `card_payment_payload(...)` 를 빌드하여 31개 필드를 실제로
생성하고, `redact_payload()` 및 `redact_value(card)`, `repr(card)` 를 직접 실행했다.

- `stlCrCrdNo1`(PAN), `vanPwd1`(비번), `crdVlidTrm1`(유효기한), `athnVal1`(생년월일/사업자번호),
  `athnDvCd1`(카드구분), `ismtMnthNum1`(할부), `mbCrdNo`(회원카드번호), `pnrNo` 모두
  `[REDACTED]`로 치환됨을 실측 확인.
- `repr(card)` 는 `installment_months`/`card_type` 만 노출하고 4개 시크릿 필드는 숨김을 확인.
- `redact_value(card)` (dataclass 필드명 기반 마스킹)도 4개 시크릿 필드 모두 `[REDACTED]`.
- `totNewStlAmt`/`mnsStlAmt1`(금액), `stlDmnDt`(결제요청일)는 마스킹되지 않음 — 이는 환불 폼의
  `saleDt`/`saleWctNo`/`saleSqno` 를 의도적으로 비마스킹하는 것과 같은 설계(금액은 신원증명이
  아니므로 프리뷰 가독성을 위해 남김)이며, 결함이 아니다.
- 별도로 `redact_text()`에 구분자 없이 21자리로 이어붙인 숫자열(`4111111111111111` +
  `22334455`)을 넣으면 `CARD_RE`(`\b(?:\d[ -]*?){13,19}\b`)가 매칭하지 못해 그대로 통과됨을
  확인했다 — 그러나 이는 `redaction.py` 자체 주석이 이미 "CARD_RE는 13-19자리만 매칭하며 필드명
  기반 마스킹이 1차 방어"라고 명시한 한계이고, 알려진 카드 필드는 전부 필드명으로 우선 마스킹되므로
  실질적 우회 경로로 보지 않았다(findings 미포함).

## Findings

### S6-01 — OK캐쉬백 포인트 / 전자지갑 / 복합결제 결제수단 미구현 (missing, low)

**앱 근거**: `analysis/apktool/assets/offline/js/common/messages.js:29-40` (`pay010`~`pay018`).
9개의 실제 UI 메시지가 결제 화면의 포인트 결제 기능을 증언한다:
```
pay010: "포인트번호(휴대폰번호)와 포인트비밀번호를 입력해주세요...OK캐쉬백 포인트 중 충전포인트..."
pay011: "포인트 번호를 입력해 주세요."
pay012: "포인트 비밀번호를 입력해 주세요."
pay015: "사용가능한 포인트보다 크므로 다시 입력해 주시기 바랍니다."
pay016: "사용하실 포인트 금액이 결제금액보다 많으므로 다시 입력해 주시기 바랍니다."
pay017: "1,000원 이하로 분할 하여 결제 할 수 없습니다."
pay018: "복합결제 시 포인트는 100원 단위로 사용가능합니다."
```
참고로 `payloads.py:1929-1930`(**라이브러리 자체 주석**, 앱 근거 아님 — 출처는 참조 구현으로
추정됨)이 `stlMnsCd`(결제수단코드) 값 체계를 `02 신용카드, 11 전자지갑, 12 포인트`,
`crdInpWayCd1` 값 체계를 `@ 신용카드/OK포인트, "" 전자지갑`으로 기록해 두었다 — 이는 앱 근거가
아니라 라이브러리 저자의 메모이므로 이 finding의 근거로 카운트하지 않았다. 이 finding의 유일한
**앱** 근거는 `messages.js`의 9개 메시지뿐이다.

**라이브러리 근거**: `src/srt_mobile_api/payloads.py` 전체에 포인트/전자지갑 빌더 없음.
`card_payment_payload`(`payloads.py:2018-2124`)는 `stlMnsCd1`을 상수 `PAYMENT_MEANS_CREDIT_CARD
= "02"` 로 고정하고, `ststlGridcnt`/`inrecmnsGridcnt`/`stlMnsSqno1` 을 모두 `"1"`로 고정하여
단일 카드결제만 표현 가능하다. `grep -rn "포인트|point|wallet|전자지갑" src/` 결과 매치 0건.

**detail**: `messages.js`의 `pay0xx` 토큰은 오프라인 번들의 어느 JS/jadx 소스에서도 참조되지 않는다
(별도 grep으로 확인, 0-hit) — 즉 이 메시지들을 실제로 사용하는 페이지는 서버 렌더링 결제 페이지이며
번들에는 없다. 따라서 정확한 wire 필드명(포인트번호/포인트비밀번호가 어떤 파라미터명으로 전송되는지)
은 이 저장소의 근거로는 확인할 수 없다 — 이 부분은 "확인불가"로 유지한다. 다만 **기능 자체가
존재한다는 사실**과 **`stlMnsCd`/`crdInpWayCd1` 값 체계에 포인트·전자지갑 자리가 이미 마련되어
있다는 사실**은 앱 자신의 근거로 뒷받침된다. srtgo/ryanking13 참조 구현에도 포인트결제는 없으므로
"참고 라이브러리에 없어서 안 만들었다"는 설명은 가능하지만, 현재 코드 어디에도 이 기능이 스코프
밖이라는 명시적 결정 기록은 없다(단체예약처럼 "제외 결정"으로 문서화되어 있지 않음).

**suggested_fix**: 결함이 아니라 기능 격차이므로 수정을 요구하지 않되, `docs/RELEASE_GAP_PLAN.md`
또는 payloads.py 모듈 주석에 "포인트/전자지갑/복합결제는 서버 렌더링 페이지에만 존재하고 필드명이
캡처되지 않아 미구현"이라는 명시적 스코프 기록을 남기면, 향후 감사자가 "왜 없는지"를 다시 조사하지
않아도 된다.

---

### S6-02 — `SrtReservationSummary` docstring의 컨테이너 역할 설명이 실제 필드 배치와 반대로 읽힘 (doc-drift, low)

**앱 근거**: 해당 없음 (라이브러리 문서 자체의 내적 일관성 문제이며, 이 컨테이너의 비어있지 않은
행 스키마는 애초에 앱/번들 어디에도 없고 srtgo 단독 출처임 — `docs/VERIFICATION.md:200-204`).

**라이브러리 근거**: `src/srt_mobile_api/models.py:607-651` (클래스 docstring, 특히 610-612줄)
대 `parsers.py:2098-2124`(`parse_reservation_list_response`의 실제 필드 배정).

**detail**: 클래스 docstring은 "zipping two parallel containers by index —
`trainListMap[i]` (journey identity) with `payListMap[i]` (settlement state)" 라고 설명한다.
그런데 실제 필드 배정(`parsers.py:2107-2124`, `models.py:634-651` 인라인 주석)은:
- `trainListMap[i]` → `received_amount`(rcvdAmt, 수납금액), `ticket_special_number`(tkSpecNum),
  `seat_number` — 이것들은 **결제/좌석 정보**이지 "journey identity"(여정 식별)라 부르기 어렵다.
- `payListMap[i]` → `service_class_code`, `train_no`, `departure_date/time`,
  `departure_station_code`, `arrival_time`, `arrival_station_code`, `payment_limit_date/time`,
  `settlement_flag` — 이것들은 대부분 **열차/여정 식별 정보**이지 "settlement state"(정산 상태)
  라 부르기엔 절반(`iseLmtDt`/`iseLmtTm`/`stlFlg` 만 정산 상태)만 맞다.

즉 두 컨테이너에 붙인 영어 설명(journey identity / settlement state)이 실제로 그 컨테이너가
담고 있는 데이터의 성격과 뒤바뀐 것처럼 읽힌다. **코드 자체(파서와 필드별 인라인 주석)는 서로
일치하므로 파싱 버그는 아니다** — `card_payment_payload`가 이 모델을 소비할 때 실제로 잘못된
컨테이너에서 값을 읽어오는 문제는 없다. 다만 이 필드 배치 전체가 "NEVER OBSERVED... 비어있지 않은
행 스키마는 srtgo 단독 출처"(models.py:617-627)로 명시된, 라이브러리 최대의 미검증 가정이라는
점을 고려하면, 클래스 docstring의 오해를 부르는 요약은 향후 유지보수자가 이 미검증 가정을 다시
점검할 때 혼란을 줄 수 있다.

**suggested_fix**: 클래스 docstring의 괄호 설명을 "trainListMap[i] (결제/티켓 식별: rcvdAmt,
tkSpecNum, seatNum)" / "payListMap[i] (여정 및 정산상태: trnNo, dptDt/Tm, arvTm, stlbTrnClsfCd,
iseLmtDt/Tm, stlFlg)" 식으로 실제 필드 목록에 맞춰 재작성.

---

### S6-03 — 카드 필드 검증 규칙(2자리 비밀번호, 생년월일 6자리)이 앱 자신의 메시지로 뒷받침됨에도 provenance 주석이 "전부 srtgo 단독 출처"로만 서술됨 (doc-drift, info)

**앱 근거**: `analysis/apktool/assets/offline/js/common/messages.js:49-52`:
```
pay024: "비밀번호 앞 2자리에 대한 정보가 없습니다."
pay025: "비밀번호 앞2자리를 올바르게 입력하여 주십시오."
pay027: "주민번호 앞 6자리에 대한 정보가 잘못 입력 되었습니다."
pay029: "할부선택에 대한 정보가 없습니다."
```

**라이브러리 근거**: `src/srt_mobile_api/payloads.py:1869-1923` (카드결제 모듈 주석, 특히
1909-1923줄 "WHAT THE BUNDLE DOES AND DOES NOT CORROBORATE" 단락)과
`src/srt_mobile_api/models.py:755-758`(`SrtPaymentCard` docstring, "카드 비밀번호는 PIN 앞 2자리",
"card_type별 생년월일 6자리/사업자등록번호 10자리" 규칙).

**detail**: `payloads.py`는 카드 관련 필드가 "genuinely 0-hit"(와이어 **필드명** 기준)이라고
정확하게 서술하고 있고, 이것 자체는 사실이다(`stlCrCrdNo1` 등 리터럴 문자열은 실제로 번들에 없음).
그러나 `SrtPaymentCard.__post_init__`이 강제하는 **검증 규칙**(비밀번호 앞 2자리만 받음, 개인카드는
생년월일 6자리, 할부 옵션 존재)은 `messages.js`의 `pay024/025/027/029`가 정확히 같은 규칙을
증언하고 있다 — 이는 필드명이 아니라 필드의 **의미/형식**에 대한 독립적인 앱 자체 근거이며,
현재 provenance 주석에는 인용되어 있지 않다. 결과적으로 "이 폼은 전부 srtgo/ryanking13 하나의
출처에 의존한다"는 서술이 실제보다 다소 비관적이다(필드 이름은 맞지만, 형식 규칙은 앱이 스스로
증언한다는 뉘앙스가 빠짐).

**suggested_fix**: `payloads.py`의 카드결제 provenance 주석에 "`messages.js`의 `pay024/025/027/029`
가 비밀번호 2자리·생년월일 6자리·할부선택이라는 형식 규칙을 독립적으로 뒷받침한다(필드 **이름**은
여전히 srtgo 단독 출처)"는 한 줄을 추가하면 provenance 서술의 정확도가 올라간다. 기능적 변경은
불필요.

---

### S6-04 — `pay_with_card` 는 `get_reservations`의 비어있지 않은 행 스키마가 srtgo 문서와
다를 경우 (마스카드 청구가 아니라) **프리뷰 단계에서부터 예외로 실패한다** (risk, medium)

**앱 근거**: 없음. `get_reservations`(`/atc/selectListAtc14016_n.do`)의 비어있지 않은 응답 행
스키마는 앱/APK 어디에도 없고(`docs/VERIFICATION.md:200-204`, `models.py:617-627`이 이미 이
사실을 명시), 오직 srtgo의 라이브 실행 결과로만 알려져 있다. 2026-07-26 실서버 라운드트립은
이 계정에 예약이 전혀 없는 **빈 배열** 응답만 검증했다(`trainListMap: []`/`payListMap: []`).
카드결제(Ata09036) 자체의 2026-07-26 성공 라운드트립은 실재하지만, 그 실행에서
`SrtReservationSummary`가 실제로 `get_reservations`의 응답을 파싱해 만들어졌는지, 아니면
호출자가 직접 구성한 값이었는지는 이 저장소의 문서로는 확인할 수 없다 — 최소한 "비어있지 않은
`trainListMap`/`payListMap` 행이 문서대로 `rcvdAmt`/`dptTm`/`arvTm`/`tkSpecNum`이라는 이름으로
온다"는 가정 자체는 한 번도 실측되지 않았다는 점은 저자 스스로도 반복해서 명시하고 있다.

**라이브러리 근거**: `payloads.py:2081-2091`(`_required_digits(reservation.departure_time,
"departure_time", length=6)`, `_required_digits(reservation.arrival_time, ...)`,
`_payment_amount(reservation.received_amount, ...)`)와 `models.py:634-651`
(`SrtReservationSummary`의 `received_amount`/`departure_time`/`arrival_time`/
`ticket_special_number`가 전부 `str | None = None`)、그리고 `parsers.py:2107-2124`
(`_reservation_list_optional_string`이 서버 응답에 해당 이름의 필드가 없으면 조용히 `None`을
반환).

**detail**: `card_payment_payload`가 요구하는 5개 필드(`pnr_no`, `received_amount`,
`ticket_special_number`, `departure_time`, `arrival_time`) 중 `pnr_no`를 제외한 4개는 실제
서버 응답의 `trainListMap[i]`/`payListMap[i]`가 문서화된 이름(`rcvdAmt`, `tkSpecNum`, `dptTm`,
`arvTm`)과 문서화된 컨테이너(어느 쪽에 있는지)로 오지 않으면 파서가 조용히 `None`을 만들어 낸다.
`card_payment_payload`는 이 `None`을 받으면 `_required_digits`/`_payment_amount`에서 즉시
`ValueError`를 던진다(`payloads.py:1966-1974`, `2081-2085`) — 이는 `pay_with_card`가 네트워크
전송 이전, **`consent.dry_run=True`인 프리뷰 단계에서도** 발생하는 예외다
(`client.py:1689-1703`에서 폼 빌드가 dry-run 분기보다 먼저 실행됨).

즉 만약 실제 계정의 `get_reservations` 응답 행이 srtgo가 기록한 이름/컨테이너와 다르게 온다면
(예: 필드가 다른 컨테이너에 있거나, 이름이 다르거나, 서버가 이 이름 자체를 보내지 않는다면),
결과는 "잘못된 금액으로 카드가 청구되는 것"이 아니라 "결제 자체를 시도할 수 없는 것"이다 —
즉 **실패 방향이 안전한 쪽(fail-closed)** 이다. 이 점이 심각도를 `high`가 아니라 `medium`으로
매기는 근거다: 결제가 실서버에서 실패할 수 있는 실질적 리스크이긴 하지만(작업지시서의 high 기준
"해당 기능이 실서버에서 실패"에 해당할 수 있음), 돈이 잘못 나가거나 안전게이트가 뚫리는 것은
전혀 아니며 저자 스스로 이미 이 미검증 상태를 반복적으로 경고하고 있다는 점도 감안했다.

**suggested_fix**: 결함 수정이 아니라 검증 갭이다. 실제 예약이 있는 계정으로 `get_reservations`를
한 번 라이브 캡처해 `trainListMap`/`payListMap`의 실제 행 스키마(필드명·컨테이너 배치)를 확인하는
것이 유일한 해소 방법이며, 이는 이미 `docs/VERIFICATION.md`/`models.py`가 스스로 요청하고 있는
작업이다. 코드 차원에서는 현재의 fail-closed 동작(예외로 실패)이 올바른 선택이므로 변경을
권고하지 않는다.
