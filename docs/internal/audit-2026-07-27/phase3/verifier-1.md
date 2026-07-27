# SRT 감사 3차 검증 (verifier-1, 반증 담당) — 17건 판정

대상: srt-mobile-api (읽기 전용 접근만)
방법: 인용된 file:line 을 전부 직접 열어 대조. 동작 주장은 실제 실행으로 재현.
재현 스크립트는 저장소 밖 스크래치패드에만 작성 (`repro1.py`, `repro2.py`, `repro3.py`),
`PYTHONDONTWRITEBYTECODE=1` 로 실행해 저장소에 `.pyc` 를 남기지 않았다.

판정 요약: CONFIRMED 9 · PARTIAL 4 · REFUTED 1 · (UNVERIFIABLE 0) — 나머지 3건은 CONFIRMED 중 심각도 하향.

---

## S1-01 — CONFIRMED (low → info)

- `docs/analysis/full-api-analysis-2026-07-20.md:429` = `### 4.5 \`UserInfo\` (\`application.gds_userInfo\`)`,
  `:431` = `` `MB_CRD_NO` (회원카드번호; empty = not logged in), `USER_DV` ("2"=비회원), `` — 출처 `ara0101v.js:52-62`.
  즉 로그인 응답의 `userMap` 이 아니라 **`application.gds_userInfo` 전역객체**를 설명하는 절이 맞다.
- `src/srt_mobile_api/models.py:40-47` docstring 이 "read from the login response's ``userMap``… ``MB_CRD_NO`` is one of its keys
  (``…full-api-analysis-2026-07-20.md:431``…)" 라고 그 줄을 지목 → 인용 대상 객체 불일치. 주장 성립.
- 기능 판단은 옳다: `src/srt_mobile_api/session.py:70` 이 `response.get("userMap")` 을 세션에 보관하고,
  `srtgo/srtgo/srt.py:723-724` 가
  `json.loads(r.text)["userMap"]` → `user_info["MB_CRD_NO"]` 를 가드 없이 읽는다.
  (주장이 적은 `srt.py:721` 은 실제로 `:724`. 부수 인용 오차 — 실질에는 영향 없음.)
- `tests/fixtures/login_success.json` = `{"userMap":{"RTNCD","MSG","CUST_NM"}}` — MB_CRD_NO 없음. 혼동 소지 지적도 사실.
- 앱 쪽 별개 경로 확인: `analysis/apktool/assets/offline/sub/main.html:539-540`
  `return application.gds_userInfo[sColNm];` (= `lfn_getSValue`).
- 동작 무영향, 순수 주석 인용 오류 → rubric 상 "문서 불일치" = **info**.

## S2-02 — PARTIAL (low → info)

**라이브러리 측은 전부 사실:**
- `src/srt_mobile_api/payloads.py:554` `"grpDv": "0",` 고정. `search_page_payload` 시그니처(`:535-539`)에 group 인자 없음.
- `src/srt_mobile_api/client.py:525-538` `_hydrate_search` 는 group 여부와 무관, `:547` 에서 group/개인 공통 호출.
- `src/srt_mobile_api/payloads.py:676` 계열이 POST 본문에서만 `grpDv="1"` 로 덮는다.

**앱 근거는 부분 반증:**
- `ara0101v.js:522` `lfn_setRsv({"grpDv": $(this).is(":checked") ? "1" : "0"});` 는 확인된다. 다만 이건 hydration 요청이 아니라
  DOM 폼필드 갱신이다 — `main.html:549-553` `function lfn_setRsv(obj){ for (var key in obj) $("#"+key).val(obj[key]); }`.
- `ara0101v.js:548` `case "btn_inquiry"` → `:635` `Sr.ara0101v.fn_moveSearchPage()` → `:650-656` → `:658-664`
  `$("#btn_go_ara1001l").simulateClick('click')`. **그 버튼/폼의 action 은 서버렌더링이라 번들에 없다**
  (`btn_go_ara1001l` 는 번들 전체 1-hit = 이 호출부뿐).
- 따라서 "실제 단체검색의 hydration GET 은 `/ara/selectListAra10007_n.do` 이고 grpDv=1 을 포함한다" 는 문장은 **확인 불가**.
  저장소 자신도 그렇게 기록한다: `docs/analysis/impl-audit-reverify5-2026-07-22.md:70`
  ("the app's initial navigation into the ara1001l page is a server-rendered link/form not present in the APK"),
  `docs/VERIFICATION.md:1029-1031`.
- 기능 영향 없음(주장 스스로 인정) + `tests/fixtures/group_search_success.json` 존재.
- 라이브러리 사실은 맞고 앱 근거의 라우트 지목이 틀림 → **PARTIAL, info**.

## S3-03 — CONFIRMED (medium 유지)

- 앱: `analysis/apktool/assets/offline/js/ara/ara1001l.js:1427-1436` `fn_moveRsv` 가 한 함수 안에서
  `sPsrmClCd`(`:1430-1432`, 행의 `gnrmRsvPsbImg`/`sprmRsvPsbImg` 로 결정)와
  `sJobId`(`:1433-1436`, `ARC0201C` → `"1103"` 시트맵예약)를 **동시에** 정한다.
  앱에는 "캐빈 A 로 시트맵을 열고 캐빈 B 로 예약" 조합 자체가 존재하지 않는다.
- 라이브러리:
  - `client.py:985-989` `get_seat_grid(..., cabin_class: str = "1", ...)`; `payloads.py:832-833` 은 `{"1","2"}` 여부만 검증하고 보존하지 않는다.
  - `models.py:1026-1037` `SeatGrid` = `car_number` + `seats`(+ HtmlPage), `models.py:968-999` `SeatDesignation` = `car_number` + `seats`,
    `models.py:924-` `SeatGridSeat` — **어디에도 캐빈 필드 없음**(grep 확인).
  - `payloads.py:1411` `special_seat = _resolve_special_seat(train, seat_type)` — `designated_seats` 를 전혀 참조하지 않는다
    (`_resolve_special_seat` 는 `payloads.py:1085-1093`).
  - `payloads.py:1114` `"psrmClCd1": "2" if special_seat else "1"`; `:1207`/`:1213` 이 `seatNo1_*`/`scarNo1` 을 designation 에서 채운다.
- 결론: `get_seat_grid(cabin_class="2")` → `SeatGrid.choose(...)` → `reserve(designated_seats=…, seat_type=GENERAL_FIRST)` 는
  일반실이 예약가능한 한 `psrmClCd1="1"` + 특실 차량/좌석 바디를 만든다. 호출자가 사후 검증할 필드도 없다. **medium 유지.**

## S4-02 — CONFIRMED (low 유지)

- 앱: `ara1001l.js:1438-1441` `"trnGpCd1": item.trnGpCd //열차그룹` — 검색행 값 사용. 직접 확인.
- 라이브러리: `payloads.py:1444` `"trnGpCd1": "300",`, `payloads.py:1580` `"trnGpCd2": "300",` — 상수.
  `TrainSummary.train_group_code`(`models.py:273`)는 예약 빌더에서 미참조(grep).
- 실해 없음 확인: `payloads.py:1342-1344` 가 `train.service_class_code != "17"` 이면 `ValueError`.
  fixture 4건(`search_success.json`, `search_personal_shape_success.json`, `search_group_shape_success.json`,
  `group_search_success.json`) 전부 `stlbTrnClsfCd=="17"` ↔ `trnGpCd=="300"`(프로그램 확인).
- 비일관성 보강근거(주장에 없던 것): 같은 필드를 `payloads.py:724-725` / `:830-831` 은
  `train.train_group_code != "300"` 으로 **강제 검증**한다. 좌석조회에서는 모델 필드를 신뢰하고 예약에서는 무시한다. **low 유지.**

## S5-03 — CONFIRMED (low → info)

- `parsers.py:1234-1249` `_reservation_attempt_string(..., allow_empty: bool = False)` — 빈 문자열도 `SrtProtocolError`. 확인.
  (주장의 `parsers.py:1277-1249` 는 역순 범위로 잘못됨; `parse_reservation_attempt_response` 는 `:1276` 부터 시작.)
- `parsers.py:1496-1535` `parse_reservation_hold_response` 가 `SrtProtocolError` 만 잡아 `_minimal_hold_from_raw` 로 폴백,
  docstring `:1508` 이 정확히 "a missing ``trainListMap`` seat number, say" 를 예시로 든다. 확인.
- `client.py:1203-1204` "Multi-passenger, multi-leg and standby (``jobId=1102``) reservations were not exercised." 확인.
- 앱 `ara1001l.js:1447-1448` `sJobId = "1102"; //예약대기`; srtgo `srt.py:286` `self.is_waiting = self.seat == ""`. 확인.
- 내용은 전부 사실이지만 **라이브러리가 스스로 문서화한 스코프 한계 + 이미 설계된 방어**이지 결함이 아니다 → **info**.

## S6-04 — PARTIAL (medium → info)

**메커니즘은 확인:**
- `payloads.py:2081-2086` `_required_digits(reservation.departure_time,…,length=6)` / `_required_digits(reservation.arrival_time,…)`,
  `:2091` `_payment_amount(reservation.received_amount, "received_amount (rcvdAmt)")`.
  `_required_digits` 는 `payloads.py:704-709` 에서 `not isinstance(value, str)` → `ValueError`. `tkSpecNum` 은
  `_payment_passenger_count` 를 거쳐 `totPrnb`(`:2112`)로.
- `models.py:634-651` 네 필드 모두 `str | None = None`; `parsers.py:2107-2140` `_reservation_list_optional_string` 은 조용히 None.
- `client.py:1689-1703` 이 `card_payment_payload(...)` 를 만들고 `:1706` 에서야 `if consent.dry_run:` 분기 → 프리뷰도 예외.

**그러나 이는 명시된 의도이고 fail-closed 다:**
- `client.py:1687-1689` "Built before the dry-run branch so a preview validates exactly what a live send would transmit, matching cancel."
- `docs/VERIFICATION.md:299-301` "…so ``rcvdAmt``, ``tkSpecNum``, ``dptTm`` and ``arvTm`` inherit that uncertainty."
- `models.py:626-633` "Treat a ``None`` here as 'the server did not send this field under this name'…"
- `payloads.py:2044-2053` 이 같은 불확실성을 다시 경고("only its EMPTY response is live-verified").
- 저자가 반복 경고한 미검증 스코프 + 안전 방향 실패 → 결함이 아니라 기록된 한계. **PARTIAL, info.**

## S7-05 — CONFIRMED (low 유지)

- `models.py:649` `settlement_flag: str | None = None  # stlFlg` — 의미 설명 0. `is_paid` 류 파생속성 없음(grep 확인).
- `stlFlg` 앱 번들 0-hit 확인: 전체 grep 히트는 `src/`(models.py:622,649 / parsers.py:1952,2138),
  `docs/`(IMPLEMENTATION_PROGRESS.md:791, VERIFICATION.md:204), `tests/`(test_reservation_list.py:241) 뿐. `analysis/` 0건.
- `analysis/apktool/assets/offline/js/commCode.js:1397` 부터 `tkSttCd`(승차권상태코드) 테이블 시작 확인 — 결제여부 개념 없음.
- `get_reservations` 는 `client.py:284`/`:315` 의 `/atc/selectListAtc14016_n.do`, `models.py:608` 이 그 행을
  **"예약/발권 목록"** 이라고 명시 = 미결제 예약과 발권 티켓이 한 리스트에 섞인다.
- `cancel`(`client.py:1417`) 과 `refund`(`client.py:1788`, 선행 `get_refund_ticket_info` `:1727`) 은 별개 consent 카테고리.
- 한 행이 어느 쪽인지 라이브러리 API 만으로 판별 불가 = 사실. **low 유지.**

## P2MIS-02 — CONFIRMED (medium 유지) — 이번 배치에서 가장 실체 있는 결함

- 앱:
  - `ara0101v.js:759-778` 좌석옵션 팝업 콜백이 `"rqSeatAttCd1": arrCode[0]` 와 `"rqSeatAttCd2": arrCode[0]` 를 함께 쓴다
    (주장의 758-775 ≈ 실제 759-778, 오차 무해).
  - `ara0101v.js:611-628` 휠체어(`"021"`)·전동휠체어(`"028"`) 전용 이용동의문 다이얼로그 — 문구까지 직접 확인.
    `srtAlertBoxDivConfirmShow(...,"Sr.ara0101v.fn_moveSearchPage()")` 로 정상 검색 흐름에 이어진다 = **사용자 도달 가능한 정식 기능**.
  - `ara1001l.js:105` `var sSeatAttCd = lfn_getRsv("rqSeatAttCd1");`
  - `ara1001l.js:1670` `var sRqSeatAttCd1 = lfn_getRsv("rqSeatAttCd1");`,
    `:1694` `{val:sRqSeatAttCd1, title:"요구좌석속성코드1"}` — `fn_validChk` 필수 21항목 중 하나. 줄번호까지 정확.
- 라이브러리:
  - `payloads.py:1110` `"rqSeatAttCd1": "015",` / `payloads.py:1583` `"rqSeatAttCd2": "015",` 하드코딩.
  - `client.py:1150-1162` `reserve(...)`, `client.py:1316-1330` `reserve_transfer(...)` 시그니처에 좌석속성 인자 없음.
  - 반면 `models.py:212` `seat_attr_code: str = "015"` 는 **검색**에 반영: `payloads.py:583`, `:586`, `:639`, `:2424`;
    **좌석조회**에도 반영: `payloads.py:722`,`:765`,`:802`,`:857` / `client.py:958`,`:993`.
- 실행 확인: `personal_reservation_payload` 출력이 항상 `rqSeatAttCd1 = 015` (repro2).
- (a) 휠체어/전동휠체어 예약이 어떤 공개 경로로도 도달 불가, (b) 검색에서는 존중한 값을 예약에서 경고 없이 버림 =
  **라이브러리 내부 일관성 위반**. 의도적 제외 목록(단체예약)에 해당하지 않음. **medium 유지.**

## P2MIS-06 — CONFIRMED (info 유지)

- `ls -l` 직접 확인: `tests/fixtures/public_discount_search_page.html` = **7,666 B**,
  `tests/fixtures/discount_coupons_empty.html` = **6,102 B** (fixture 중 최대 2개).
- `docs/VERIFICATION.md:977` "206,268 bytes, all eight flags empty"; `docs/VERIFICATION.md:869` "77,056 bytes". 둘 다 확인.
- `docs/VERIFICATION.md:862-868` 이 `pageMove('/apa/selectListApa03020_n.do')` 를 서버렌더링 MY SRT 메뉴에서 발견했다고 기록.
  ("SRT server-renders its MY SRT menu into every authenticated page") 확인.
- 22개 html fixture 전수 grep 결과 `.do` 참조 **10종**:
  `/apa/selectListApa03020_n.do`, `/ara/selectListAra10131_n.do`, `/ara/selectListAra12009_n.do`,
  `/ara/selectListAra13010_n.do`, `/arb/selectListArb02A01_n.do`, `/arc/selectListArc02011_n.do`,
  `/arc/selectListArc02012_n.do`, `/atc/selectListAtc14017_n.do`, `/common/ARA/ARA0301V/view.do`, `/login/login.do`.
  주장이 적은 11종 중 `main.do` 만 내 grep 에서 안 잡혔다 — 나머지는 일치하고, **미등록 신규 라우트 0건**이라는 결론은 동일.
- "신규 라우트가 없다는 증명이 아니라 저장소 아티팩트만으로는 더 못 캔다" 는 결론 = 사실. **info 유지.**

## P2INC-02 — CONFIRMED (high → medium)

**실행으로 재현했다** (`scratchpad/repro2.py`):
`tests/fixtures/search_personal_shape_success.json` 행에서 `gnrmRsvPsbStr`/`sprmRsvPsbStr` 만 `null` 로 바꿔
`parse_train_search_response` → `general_seat_availability is None`,
`personal_reservation_payload(t, PassengerCounts(adult=1), netfunnel_key="K")` → **`psrmClCd1 = '2'`** (특실).
같은 fixture 원본(문자열 존재)에서도 `'synthetic-general-availability'` 에 "예약가능" 이 없어 `'2'` 가 나온다.

- 경로 확인:
  `parsers.py:2520-2527` `_optional_row_string(row,"gnrmRsvPsbStr")` /
  `parsers.py:2212-2234` `_row_field_is_absent` 가 JSON null 을 "없음"으로 세고 docstring 이
  "**The server really does send nulls here, and it is not an anomaly.**" 라고 단언 /
  `payloads.py:1073-1075` `"예약가능" in (train.general_seat_availability or "")` /
  `payloads.py:1088-1093` `SeatType.GENERAL_FIRST: not _general_seat_available(train)` → None → `""` → False → `not False` = 특실.
- 환승 전파 확인: `payloads.py:1705-1710` `special_seat=payload["psrmClCd1"] == "2"` → 두 레그 모두 특실.
- 앱 대조 확인(직접 열람): `ara1001l.js:1430-1432`
  `var sPsrmClCd = ""; if (item.gnrmRsvPsbImg == …) sPsrmClCd = 1; else if (item.sprmRsvPsbImg == …) sPsrmClCd = 2;`
  — 둘 다 아니면 **빈 문자열**, 절대 2 가 아니다.
- srtgo 대조 확인: `srtgo/srtgo/srt.py:448`
  `self.general_seat_state = data["gnrmRsvPsbStr"]` — 가드 없음(주장의 447-448 정확).
- 공개 경로만으로 도달: `search_trains()` → `reserve()`. `reserve` 는 라이브 전송 가능 카테고리(`safety.py:520-522`).

**단 심각도는 high → medium.** 제목의 "라이브 null 로 실제 도달" 은 과장이다:
- `parsers.py:2214-2222` 의 라이브 null 증거는 `fresRsvPsbCdNm` / `fllwPgExt2` 에 한정. `gnrmRsvPsbStr` 이 null·부재로 온 관측은 없다.
- srtgo 가 이 키를 가드 없이 읽고도 실사용된다는 사실 자체가 "정상 응답에는 항상 존재" 쪽 증거다.
- `tests/fixtures/search_success.json` 에 이 키가 없지만 그건 서버가 아니라 **저장소가 트리밍한 fixture** 다
  (실제 키 13개만 남아 있고 `personal_reservation_payload` 는 `departure_consist_order` 에서 먼저 죽는다 — repro3 확인).
→ 트리거가 미관측 서버조건에 한정되므로 rubric 상 **medium**. 결함 자체(부재 ≠ 매진)는 진짜다.

## P2INC-04 — PARTIAL (low → info)

- 코드 사실 확인: `payloads.py:502-504`
  `hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")` /
  `fields[f"psgTpCd{index}"] = hydrated_code or type_code` / `fields[f"psgInfoPerPrnb{index}"] = str(count)`.
- `parsers.py:837` 이 모든 named input 을 필터 없이 수집, `parsers.py:840-846` `parse_search_page_state` 가 그대로 `hidden_fields` 로.
- 테스트 pin 확인: `tests/test_netfunnel_payloads_parsers.py:562-568`
  `hydrated_fields={"psgTpCd1": "hydrated-senior"}` → `assert payload["psgTpCd1"] == "hydrated-senior"` + `psgInfoPerPrnb1 == "2"`.
- 앱 근거 확인: `ara0101v.js:793-804` 가 `psgTpCd{i}`/`psgInfoPerPrnb{i}` 를 쌍으로 세팅.

**위험 전제는 구조적으로 상쇄된다:**
- `search_page_payload` 자신이 `payloads.py:592` `payload.update(_passenger_fields(query.passengers))` 로
  **호출자 기준 psgTpCd/psgInfoPerPrnb 쌍을 hydration GET 에 실어 보낸다.** 서버가 그 폼을 되돌려주면
  `hydrated_code == type_code` 이므로 쌍이 깨질 수 없다.
- 주장이 인용한 `docs/VERIFICATION.md:1035-1037` 의 "슬롯이 빈 문자열" 실측은 실은 **Ara10131(할인 승차권) GET** 에 대한 것이고
  Ara10007 이 아니다 — 주장 자신의 반박근거도 대상이 다르다. 어느 쪽이든 실측된 불일치는 0건.
- `tests/fixtures/search_page.html` 448 B 가 합성 픽스처인 것도 직접 확인(7개 input, `unknownField="keep-me"` 포함).
- **코드 사실은 맞고 위험은 미실현 → PARTIAL, info.**

## P2INC-06 — CONFIRMED (low → info)

- `analysis/apktool/assets/offline/sub/main.html:622-636` `getStlbTrnClsfCdNm` =
  00,01,02,03,04,05,06,07,08,09,10,15,17 의 **13개**, 나머지는 `else return "";`. 직접 확인.
- `commCode.js` 의 `code_group_cd == "stlbTrnClsfCd"` 블록도 프로그램 추출 결과 **정확히 13개**.
- 저장소 전체 grep(`--exclude-dir=.git`) 결과 `KTX-이음`/`ITX-마음`/`KTX-청룡` 은
  `src/srt_mobile_api/payloads.py:887`, `:889`, `:890` **세 줄뿐**. `docs/`·`CHANGELOG.md`·`tests/fixtures/` 0-hit.
- `payloads.py:869-872` 주석의 "lifted verbatim from the LIVE search page served on 2026-07-26" 은 저장소 아티팩트로 재현 불가.
  (세 값 자체는 실재하는 열차명이므로 "틀렸다"고는 하지 않는다 — **저장소 내 근거 부재**만이 확인 사항.)
- SRT 는 `"17"` 이라 동작 무영향 → **info**.

## P2SAF-04 — REFUTED (medium → info)

- **게이트에 구멍이 없다.** `http.py:306-351` `post_mutation_form` 이 유일한 송신 경로이며 5개 게이트를 명시:
  (1) `require_mutation_consent(consent, category)`, (2) `consent.dry_run` 이 False, (3) `category ∈ SRT_LIVE_MUTATION_CATEGORIES`,
  (4) payment 는 카드종류 주장, (5) 정규 origin + `assert_mutation_route`/`assert_mutation_route_category`.
  docstring `:347-351` 이 `_send_mutation_request` 가 게이트 3·5 를 송신 경계에서 **독립 재확인**한다고 적시.
- `reserve`/`reserve_transfer`/standby/좌석지정 모두 `client.py:1122-1132` `_submit_reservation` →
  `post_mutation_form(..., category="reserve")` 하나만 통과한다. 우회 경로 없음(`client.py:1300-1314`, `:1404-1415` 확인).
- 주장의 "프로브 6 실측: allow_reserve=True, dry_run=False 만으로 전송됐다" 는 **게이트가 설계대로 동작한 것**이다.
  운영자가 명시적으로 카테고리 동의를 켜고 dry_run 을 껐다.
- 카테고리 입도는 의도된 설계이고 근거가 코드에 있다: `safety.py:500-518`
  "adding the category was a MODELLING decision … while adding it HERE would be an evidence decision of the same weight",
  `test_mutation_live_paths` 카나리가 집합을 정확히 4개로 고정. `safety.py:520-522` 확인.
- 형상 경고도 코드에 존재: `client.py:1379-1394` "**NOT LIVE-VERIFIED — read this before sending one.**" +
  slot-2 5개 키 추론 명시 + `reserveType` 불확실성 + "cancel(hold, journey_count='2')" 안내.
- 지침의 "안전 모델은 설계이지 결함이 아니다" 에 정확히 해당하며 구멍은 없다. **REFUTED, info.**

## P2SAF-08 — CONFIRMED (low → info)

- `client.py:1162` `) -> MutationPreview | SrtReservationHold:` 확인.
- `client.py:1600-1601` `def pay_with_card(self, reservation: SrtReservationSummary, card: SrtPaymentCard, …)` 확인.
- `models.py:594-603` `SrtReservationHold` = `pnr_no` / `journey_list_key` / `total_seat_count` / `raw` 뿐 —
  `received_amount`/`ticket_special_number`/`departure_time`/`arrival_time` 없음. 확인.
- `payloads.py:2044-2053` 이 명시적으로 `get_reservations` 재조회를 지시하고, 그 읽기가
  "only its EMPTY response is live-verified (2026-07-26, ``trainListMap: []`` / ``payListMap: []``)" 라고 자기 고백.
  `models.py:614-628` 도 동일.
- 앱 대조: `ara1001l.js:1608-1618` 이 예약 응답의 `reservListMap.*` 를 결제 진입 폼에 직접 옮긴다(직접 확인).
- 사실관계 전부 맞다. 다만 **필드를 지어내지 않는 방향의 의도적 설계 귀결**이고 동작 위험이 없다 → **info**.

## P2CRO-06 — CONFIRMED (high → medium)

**실행으로 재현했다** (`scratchpad/repro1.py`):
```
data = {"outDataSets": {"dsOutput0": []}, "resultMap": [{"strResult":"SUCC","msgCd":"IRT200277","msgTxt":"ok"}]}
normalize_result_row(data)          -> {}
parse_unpaid_cancel_response(data)  -> SrtProtocolError: SRT cancel response must contain a resultMap result row
parse_card_payment_response(data)   -> SrtProtocolError: … must contain a outDataSets.dsOutput0 (or resultMap) result row
parse_refund_response(data)         -> SrtProtocolError: SRT refund response must contain a resultMap result row
dsOutput0=None 도 동일하게 {} 반환
```
- 원인 확인: `parsers.py:1113-1117`
  `out = data.get("outDataSets") or {}` / `if isinstance(out, dict) and "dsOutput0" in out: return _first_row(out.get("dsOutput0"))`
  — **키 존재만 보고 값의 진위성을 보지 않는다.** `if out.get("dsOutput0"):` 였다면 `resultMap` 폴백이 살아난다.
- 소비자 확인: `parsers.py:1492`(`_declares_a_declared_failure`), `:1568`(unpaid cancel),
  결제/환불 계열이 같은 헬퍼를 경유(`:1739`, `:1902` 계열 docstring `:1716-1717`, `:1893` 이 "both container spellings" 를 명시).
- 두 컨테이너 동시 존재를 pin 하는 테스트 없음(grep) — 사실.

**단 high → medium.**
- 이 시나리오(빈 `dsOutput0` + 유의미한 `resultMap`)는 세 라우트 어디에서도 관측된 바 없다.
- 주장이 든 방증 `tests/fixtures/reservation_list_empty.json` 은 `resultMap`(SUCC/IRZ000005) + `rsMap`(FAIL/WRT300005) 조합이지
  `outDataSets` 가 아니고, 그 fixture 자체가 `"wctNo":"SYNTHETIC-WCT"`, `"uuid":"SYNTHETIC-UUID"` 로 스크럽된 합성물이다
  (직접 열어 확인). 즉 "무관한 컨테이너를 곁들인다" 는 패턴 증거가 `dsOutput0` 에까지 미치지 않는다.
→ "특정 미관측 조건에서만 실패" = rubric medium. 결함(키존재 vs 진위성) 자체는 진짜이고 한 줄로 닫힌다.

## P2CRO-03 — CONFIRMED (low → info)

- `ara1001l.js:1611` = `frm.jrnySqno.value = 1; // 0001 : 선행, 0002 : 후행` — grep 으로 위치 확정
  (파일군 내 `jrnySqno` 히트는 `ara0101v.js:97`, `ara1001l.js:1611`, `ara1001l.js:1657` 셋뿐).
- `ara1001l.js:1607` = `frm.action = contextPath + "/ard/selectListArd02017_n.do";` — 개인 결제 핸드오프 폼의 action.
  여정순번과 무관. 직접 확인.
- 라이브러리 4곳 전부 `:1607` 로 인용: `models.py:354`, `payloads.py:93`, `payloads.py:1284`, `payloads.py:1621`. 확인.
- 1차 근거 `ara0101v.js:97` `"jrnySqno1" : "001", //여정일련번호1(001:선행, 002:후행)` 은 정확 → 기능 무영향.
- 보강 지적도 확인: `:1611` 의 필드명은 접미사 없는 `jrnySqno` 이고 `#rsvForm` 이 아니라 Ard02017 핸드오프 폼에 실린다
  (`:1600-1611` 문맥). 즉 그 줄은 선행/후행의 **의미**만 뒷받침하고 슬롯 이름은 뒷받침하지 않는다. **info.**

## P2CRO-09 — PARTIAL (info 유지)

메타주장("02-search S2-02 는 결함이 아니다")의 **결론은 대체로 성립**하나 앱 근거 두 개가 부정확하다.
- 맞는 것: `ara0101v.js:93` 시드 `"grpDv" : "0"`; `ara1001l.js:174-181` 이 검색시점에 grpDv 로 URL 선택 후
  `#seatSearchForm` serialize; `payloads.py:554` / `:676`; `client.py:551` 의 group 라우트 전환;
  `tests/fixtures/group_search_success.json` 존재 = 이 흐름으로 실응답을 받은 적 있음.
- **틀린 것 (1):** `ara0101v.js:522` 를 "로컬 스토어만 바꾼다" 고 했으나 `main.html:549-553` 기준
  `lfn_setRsv` 는 `$("#"+key).val(...)` — **실제 폼 input 값을 쓴다.**
- **틀린 것 (2):** "앱에는 단체용 별도 하이드레이션 요청이 없으므로 divergence 가 아니다" 는 과한 결론이다.
  별도 요청이 없을 뿐, 같은 내비게이션(`btn_inquiry :548` → `fn_moveSearchPage :650` → `netfunnel_callback :658` →
  `#btn_go_ara1001l` 클릭)이 그 폼을 실어 나른다. 증거: 결과 페이지 스크립트 `ara1001l.js:174` 이
  `lfn_getRsv("grpDv")` 를 읽는다 = 전이 후에도 grpDv 가 DOM 에 존재 = 내비게이션 요청에 실려 갔다는 뜻이다
  (`main.html` 에 `grpDv` input 은 없다 — grep 0-hit — 이므로 서버렌더링 페이지 소속).
- 정직한 서술은 "앱의 하이드레이션 내비게이션 자체가 번들에 없어 비교 자체가 불가" 다. **PARTIAL, info.**

---

## 부기 — 검증 중 확인한 사실 (판정 근거 보강용)

- `lfn_setRsv`/`lfn_getRsv` 는 `main.html:549-566` 에서 **DOM input 읽기/쓰기** 로 정의된다. 이 프로젝트의 여러 주장이
  이를 "로컬 스토어" 로 오해하고 있다.
- `analysis/jadx/resources/assets/offline/js/` 는 `analysis/apktool/assets/offline/js/` 와 동일 파일(줄번호 동일).
  이번 17건은 전부 오프라인 JS/HTML 에 근거하므로 smali 재확인이 필요한 상수 주장은 없었다.
- 라이브 캡처 원본은 저장소에 없다(모든 html fixture ≤ 7.7 KB, json fixture 도 트리밍/합성).
  "fixture 에 없다"는 서버 동작의 증거가 아니다 — P2INC-02 심각도 하향의 근거 중 하나.
