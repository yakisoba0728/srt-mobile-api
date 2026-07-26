# SRT 2차 감사 — 오구현 렌즈 (Phase 2 / incorrect-implementation lens)

대상: `/Users/yakisoba/Documents/GitHub/srt-mobile-api`
렌즈: **라이브러리에 있긴 한데 틀린 것** — 필드명, 값 타입(문자열/숫자), 상수값,
분기 조건, 기본값, 응답 파싱 키, 인코딩, 헤더.
방법: 1차 8건 보고서를 읽되 결론을 상속하지 않고, 앱 자산(`assets/offline/js`, `sub/main.html`)·
smali·jadx·`docs/analysis`·`tests/fixtures`·참조구현(`srtgo`)을 직접 재추적했다.
가능한 항목은 **실행으로 재현**했다(각 항목의 재현 블록은 실제로 돌린 결과다).

집계 기준: "추출한 앱 기능/엔드포인트"는 이 패스에서 **직접 재검증한 표면**만 센다
(엔드포인트 33 + 페이로드 빌더 22 + 파서 진입점 18 + 안전게이트/상수표 12 = 85).
"구현된 개수"는 그중 앱/참조구현 근거와 **일치함을 확인한** 것(75)이다.
1차의 총계(632/579)를 다시 세지 않았다 — 이 패스는 결함 렌즈다.

---

## A. 1차가 놓친 것 (NEW — 이번 패스에서 처음 제기)

### P2INC-01 [critical / risk] 문서화된 불변식이 거짓이다 — 최소 consent 로 실카드가 승인된다

**깨진 불변식 (이것이 이 항목의 핵심이며 반박 불가능한 부분이다)**
- `src/srt_mobile_api/consent.py:69-76`
  > "A real charge therefore needs both halves stated deliberately —
  > `fake_card_only=False` (this is not a test card) and
  > `real_card_acknowledged=True` (yes, charge it)."
- `src/srt_mobile_api/client.py:1673`
  > "That claim is checked here and again at the send gate, and it is now
  > **the last thing between a real PAN and the wire**."

**재현 (실행함, `httpx.MockTransport` 로 송신 바이트 가로챔)**
```
consent = MutationConsent(allow_payment=True, dry_run=False)   # 카드 플래그는 손대지 않음
fake_card_only: True   real_card_acknowledged: False           # 두 halves 모두 미선언
RESULT: SrtPaymentResult(status='SUCC', message_code='IRT000000')
PATH:   /ata/selectListAta09036_n.do
PAN ON WIRE: True        # 4111111111111111 이 평문으로 실렸다
```
**두 halves 를 하나도 선언하지 않았는데 실제 PAN 이 와이어에 실렸다.** 위 두 문장은 거짓이다.

**라이브러리 근거**
- `consent.py:87,91,95` — `allow_payment=False`(뒤집어야 함), `fake_card_only=True`,
  `real_card_acknowledged=False`.
- `consent.py:170` `require_card_kind_claim` 은 "정확히 하나"만 요구한다. 기본 조합
  (`True`/`False`)은 **정확히 하나**이므로 통과한다. "neither → 거부" 분기는 호출자가
  `fake_card_only=False` 를 **명시적으로 써야만** 도달한다 — 즉 조심하는 호출자만 게이트를 만난다.
- 카드가 실제로 테스트 카드인지 확인하는 코드는 저장소에 없다
  (`grep -rn fake_card_only` → 플래그 읽기·문서·테스트뿐, 검증 0건).
- `tests/test_payment_mutation.py:741` 이 `MutationConsent(allow_payment=True, dry_run=False,
  fake_card_only=True)` 의 전송을 **의도된 동작으로 pin** 한다 — 회귀가 아니라 현재 계약이다.

**앱 근거**: 해당 없음(라이브러리 자체 안전모델). 다만 이 라우트는 앱이 쓰지 않는 평문 결제
경로(`/ata/selectListAta09036_n.do`, 번들 0-hit, `client.py:1631`)이고 **2026-07-26 실제 카드
승인이 성공한 살아있는 경로**다(`client.py:1611-1618`). 즉 돈이 실제로 움직인다.

**정확히 무엇이 문제인가**: `require_card_kind_claim` 이 *우회*되는 것이 아니다 — *충족*된다.
`dry_run`(기본 True→뒤집어야 함)과 `allow_payment`(기본 False→뒤집어야 함)는 진짜 게이트다.
카드종류 게이트만 **안전한 쪽이 아니라 통과하는 쪽이 기본값**이라 실질적으로 게이트가 아니다.

**수정 방향**: `fake_card_only` 기본값을 `False` 로 바꿔 "둘 다 미설정 → 거부"가 실제 기본
동작이 되게 하거나(문서가 이미 그렇게 서술함), `fake_card_only=True` 일 때 카드번호가 알려진
테스트 PAN 인지 검증할 것.

---

### P2INC-02 [high / incorrect] 좌석등급 기본 결정이 "필드 없음"을 "일반실 매진"으로 접어 **특실**로 예약한다 — 라이브 응답의 `null` 로 실제 도달한다

**앱 근거 (앱은 절대 2로 떨어지지 않는다)**
- `analysis/apktool/assets/offline/js/ara/ara1001l.js:1430-1432`
  ```js
  var sPsrmClCd = "";                                       // 기본값은 빈 문자열
  if (item.gnrmRsvPsbImg == this.S_IMG_PSBL_S || … ) sPsrmClCd = 1;   // 일반실
  else if (item.sprmRsvPsbImg == this.S_IMG_PSBL_S || …) sPsrmClCd = 2; // 특실
  ```
  동일 로직이 `:1276-1278` 과 `:809-811`(주석)에 반복된다. **둘 다 아니면 `""`.**
- 참조구현 `srtgo/srtgo/srt.py:447-448` 은 `data["gnrmRsvPsbStr"]` 를 **가드 없이** 읽으므로
  이 상태 자체가 존재할 수 없다(KeyError). 라이브러리가 옵셔널로 완화하면서 srtgo 의
  hard failure 가 **조용한 상위등급 예약**으로 바뀌었다.

**라이브러리 근거**
- `src/srt_mobile_api/payloads.py:1073-1075` `"예약가능" in (train.general_seat_availability or "")`
- `src/srt_mobile_api/payloads.py:1091` `SeatType.GENERAL_FIRST: not _general_seat_available(train)`
- `src/srt_mobile_api/parsers.py:2520-2523` `general_seat_availability=_optional_row_string(row, "gnrmRsvPsbStr")` — **옵셔널**
- `src/srt_mobile_api/parsers.py:2214-2235` `_row_field_is_absent` — **JSON `null` 을 "없음"으로
  센다.** 그 docstring 자신이: *"null 은 이 API 가 '이 행에는 그 값이 없다'를 쓰는 평범한 방식…
  우리가 옵셔널로 읽는 필드들도 같은 행, 같은 서버에 있고, 언젠가 그중 하나가 null 로 온다"*
- 기본 인자: `payloads.py:1222`, `payloads.py:1594`, `client.py:1156`, `client.py:1322`
  모두 `seat_type=SeatType.GENERAL_FIRST`

**재현 (실행함)** — 저장소 자신의 라이브형 픽스처
`tests/fixtures/search_personal_shape_success.json` 의 행에서 `gnrmRsvPsbStr`/`sprmRsvPsbStr`
를 `null` 로 바꾼 것 외에는 손대지 않았다:
```
parse_train_search_response → gnrm: None  sprm: None
personal_reservation_payload(...)["psrmClCd1"] = '2'      # 특실
```
손으로 만든 모델이 아니라 **`search_trains()` → `reserve()` 공개 경로만으로** 도달한다.
`reserve` 는 라이브 전송 가능 카테고리다(`safety.py:SRT_LIVE_MUTATION_CATEGORIES`).
`reserve_transfer` 는 두 레그가 슬롯1의 결정을 공유하므로(`payloads.py:1705`)
`psrmClCd1`/`psrmClCd2` 가 **둘 다 2** 가 된다.

**무엇이 왜 틀렸나**: `None` → `""` → `"예약가능" in ""` = False → `not False` = **True(특실)**.
"필드가 없다"와 "일반실이 매진이다"가 같은 값으로 접힌다. 앱은 같은 상황에서 `""` 를 보내고
srtgo 는 애초에 그 상태에 도달하지 못한다 — 두 소스 모두와 갈린다. 결과는 조용히 비싼 좌석을
잡는 것이고, 이 저장소의 모든 라이브 예약 검증은 `gnrmRsvPsbStr` 가 채워진 행으로만 이뤄졌다.

**노출 범위(추가)**: 할인 승차권 결과 페이지는 `gnrmRsvPsbCd`/`sprmRsvPsbCd`(코드)를 읽지
`…Str` 를 읽지 않는다(`tests/fixtures/public_discount_search_page.html:133-143`). Ara10131 행이
`…Str` 를 싣는지는 미검증이며, 안 실으면 그 검색 결과 전부가 이 경로에 걸린다.

**수정 방향**: `general_seat_availability` 가 `None` 이면 `GENERAL_FIRST` 를 특실로 승격하지 말고
거부하거나 일반실(`"1"`)로 둘 것 — 앱의 `""` 기본값에 대응.

---

### P2INC-03 [medium / risk] 예약목록의 숫자→문자 정규화가 zero-padding 을 잃어, 오전 출발 열차의 결제가 만들어지지 않는다

**라이브러리 근거**
- `src/srt_mobile_api/parsers.py:1967-1975` `_reservation_list_optional_string`
  ```python
  if isinstance(value, int) and not isinstance(value, bool):
      return str(value)          # 07:00:00 → 70000 → "70000" (5자리)
  ```
- `src/srt_mobile_api/parsers.py:2123,2127` — `departure_time`/`arrival_time` 는 `payListMap`
  행에서 이 헬퍼로 읽는다.
- `src/srt_mobile_api/payloads.py:2087-2091` —
  `_required_digits(reservation.departure_time, "departure_time", length=6)` — **정확히 6자리 요구**

**앱/실측 근거**
- 커밋 `9306e4c`(2026-07-26)가 이 정규화를 도입하며 기록한 실측 `trainListMap` 행:
  `{"pnrNo":"3202607…","rcvdAmt":7500,"jrnyCnt":1,"tkSpecNum":1,"stlFlg":"N","rsvChgTno":0}`
  — 6개 중 4개가 JSON 숫자. 커밋 메시지 자신의 결론: *"This is the sixth string-versus-number
  mismatch this codebase has hit. Both apps are inconsistent about it."*
- **`payListMap` 의 populated 행 타입은 저장소 어디에도 기록이 없다** — 이것이 이 항목을
  `incorrect` 가 아니라 `risk` 로 두는 이유다(§D 참조).

**재현 (실행함)**
```
payListMap 행에 dptTm=63000, arvTm=65600 (JSON 숫자)
→ parse: departure_time='63000'  arrival_time='65600'
→ card_payment_payload(...) RAISED ValueError: departure_time must contain exactly 6 digits
```

**무엇이 왜 틀렸나**: `rcvdAmt`(선행 0이 무의미)에 맞는 변환이 `dptTm`/`arvTm`/`iseLmtTm`/
`dptRsStnCd` 같은 **zero-padded 식별자**에는 손실 변환이다. 10시 이전 출발 편 전부가 걸린다.
실패는 fail-closed(네트워크 이전 `ValueError`)라 결제가 잘못 나가지는 않지만, 미결제 홀드를
결제 기한까지 풀 수 없게 만든다. 2026-07-26 결제 1건이 성공했다는 사실은 그 편이 10시 이후였거나
그 필드가 문자열로 왔다는 뜻일 뿐이며 어느 쪽인지 기록이 없다.

**수정 방향**: 필드별 기대 길이로 zero-fill 하거나(시각 `zfill(6)`, 역코드 `zfill(4)`),
최소한 `card_payment_payload` 가 6자리 미만 시각을 좌측 0 패딩할 것.

---

### P2INC-04 [low / risk] 검색 페이로드가 서버가 준 `psgTpCd` 와 호출자가 준 인원수를 **같은 슬롯에 섞는다**

**라이브러리 근거**
- `src/srt_mobile_api/payloads.py:503-504`
  ```python
  hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")
  fields[f"psgTpCd{index}"] = hydrated_code or type_code   # 타입은 서버 것 우선
  fields[f"psgInfoPerPrnb{index}"] = str(count)            # 수량은 항상 우리 것
  ```
- `src/srt_mobile_api/parsers.py:840-846` `parse_search_page_state` — 페이지의 **모든** named
  input 을 필터 없이 `hidden_fields` 로 담으므로 `psgTpCd1..5` 가 그대로 들어온다.
- `tests/test_netfunnel_payloads_parsers.py:563-568` 이 이 동작을 pin 한다:
  `psgTpCd1 == "hydrated-senior"` — **`psgTpCd` 로서 유효하지 않은 임의 문자열** — 이 호출자의
  경로 인원수(`psgInfoPerPrnb1 == "2"`)와 짝지어 전송되는 것이 현재 계약이다.

**앱 근거**
- `analysis/apktool/assets/offline/js/ara/ara0101v.js:795-804` — 앱은 승차인원 팝업 콜백에서
  `psgTpCd{i}` 와 `psgInfoPerPrnb{i}` 를 **항상 쌍으로 함께** 쓴다. 라이브러리는 그 콜백을
  수행하지 않으므로 하이드레이션 값의 타입만 신뢰할 근거가 없다.

**무엇이 왜 틀렸나 / 어디까지가 관측된 사실인가**
`psgTpCd{i}` 와 `psgInfoPerPrnb{i}` 는 한 쌍이어야 의미가 있는데, 빌더가 한쪽만 서버 값으로
바꾼다. 서버가 비어 있지 않은 **다른** 코드를 렌더하면(예: 정적 씨앗 `"1"`=어른)
경로/어린이 일행이 어른 인원수로 조회되어 잔여석·운임이 달라진다.
**다만 그 전제는 관측되지 않았다.** 이 서버의 하이드레이션 페이지에 대한 유일한 실측
(`docs/VERIFICATION.md:1037`, 할인 승차권 GET)은 슬롯이 **빈 문자열**로 온다고 말하고, 빈
문자열이면 `or` 가 계산값을 쓰므로 아무 문제도 없다. `tests/fixtures/search_page.html` 은
448바이트 합성 픽스처(`serverNonce: nonce-1`, `unknownField: keep-me`)라 서버 동작의 증거가
아니고, `ara0101v.js:118` 의 `psgTpCd1:"1"` 씨앗은 **부킹 페이지**(`/ara/ara0101v.do`)의
`gds_rsv` 씨앗이지 우리가 파싱하는 Ara10007 페이지의 `#seatSearchForm` 이 아니다.
따라서 이 항목은 "관측된 오작동"이 아니라 **계약이 허용하는 위험**으로 제출한다.

**수정 방향**: `psgTpCd`/`psgInfoPerPrnb` 패밀리는 하이드레이션 override 대상에서 제외하고
항상 `_compact_passenger_slots` 계산값을 쓸 것(다른 hidden input 보존은 그대로 유지).

---

### P2INC-05 [low / doc-drift] 숫자 PNR 정규화가 cancel 빌더가 **명시적으로 금지한** 변환을 대신 수행한다

- **라이브러리 근거 A**: `src/srt_mobile_api/payloads.py:1772-1786` `_foreign_reservation_message`
  > "cancel requires the PNR as a string, not an int: converting a numeric PNR **drops any
  > leading zeros, which would cancel the wrong reservation or none at all**"
- **라이브러리 근거 B**: `src/srt_mobile_api/parsers.py:1971-1972` — `pnrNo` 가 숫자면 `str(value)`
  로 변환한다(정확히 위에서 금지한 변환). 결과가 `str` 이라 cancel 빌더의 검사를 통과한다.
  호출 지점 `parsers.py:2101-2103`.
- **재현 (실행함)**
  ```
  trainListMap {"pnrNo": 20260700001} → pnr_no='20260700001'
  unpaid_reservation_cancel_payload('20260700001') → 통과
  unpaid_reservation_cancel_payload(20260700001)   → 거부
  ```
- **정직한 한계**: JSON 은 선행 0 이 붙은 정수 리터럴을 표현할 수 없으므로, 숫자로 도착한
  `pnrNo` 에는 **애초에 잃을 선행 0 이 없다.** 즉 문서가 든 실제 피해("엉뚱한 예약을 취소")는
  이 경로로 발생하지 않는다. 남는 것은 같은 위험에 대해 한 모듈은 예외를 던지고 다른 모듈은
  조용히 수행하는 **정책 불일치**이며, 읽기 경로가 쓰기 경로의 방어를 세탁한다는 사실이다.
- **수정 방향**: 두 곳의 정책을 하나로 맞출 것 — `pnrNo` 숫자를 정규화할 거면 cancel 빌더의
  int 거부 사유 주석을 정정하고, 유지할 거면 정규화 시 표식을 남겨 빌더가 다시 거부하게 할 것.

---

### P2INC-06 [low / unverifiable] `STLB_TRAIN_CLASS_NAMES` 의 `16`/`18`/`19` 는 저장소 어디에도 근거가 없다

- **앱 근거**: `analysis/apktool/assets/offline/sub/main.html:622-637` — `getStlbTrnClsfCdNm` 의
  전체 정의는 `00,01,02,03,04,05,06,07,08,09,10,15,17` **13개**이고 나머지는 `return ""`.
  `commCode.js` 의 `stlbTrnClsfCd` 그룹도 같은 13개(프로그램 추출로 확인). `16`/`18`/`19` 는
  번들 전체 0-hit.
- **라이브러리 근거**: `src/srt_mobile_api/payloads.py:887,889,890`
  (`"16":"KTX-이음"`, `"18":"ITX-마음"`, `"19":"KTX-청룡"`).
- **detail**: 주석(`payloads.py:869-872`)은 "lifted verbatim from the LIVE search page served on
  2026-07-26" 이라 주장하지만 이 세 값은 `docs/`, `CHANGELOG.md`, `tests/fixtures/` 어디에도 없다
  (`grep -rn "KTX-이음|ITX-마음|KTX-청룡"` → `payloads.py` 3줄뿐). SRT(`"17"`)에는 영향이 없어
  동작 위험은 없으나 "verbatim" 주장이 재현 불가다.
- **수정 방향**: 라이브 페이지 발췌를 fixture/docs 캡처로 남기거나 근거 없는 3개를 제거.

---

### P2INC-07 [low / risk] `_optional_row_string` 은 숫자를 만나면 검색 전체를 죽인다 — 이 저장소 자신의 사후조치 규칙과 반대

- **라이브러리 근거**: `src/srt_mobile_api/parsers.py:2248-2251` — 값이 있으나(그리고 null 이
  아니고) 문자열이 아니면 `SrtProtocolError`. 같은 파일 `:1967-1975`(예약목록)는 정반대로 숫자를
  정규화한다.
- **앱/실측 근거**: 커밋 `9306e4c` 메시지 — *"Both apps are inconsistent about it;
  **new parsers should accept either from the start.**"* 검색 행 파서는 그 규칙을 따르지 않았다.
  (`parsers.py:2214-2235` 가 null 만 완화했고 숫자는 그대로 폭발한다.)
- **detail**: 검색 행 40건이 라이브 관측됐으므로 현재 위험은 낮다. 다만 한 컬럼이라도 숫자로
  바뀌면 `search_trains` 전체가 죽고 예약목록은 같은 상황에서 살아남는다 — 같은 파일 안에서
  동일 위험을 반대로 처리한다.
- **수정 방향**: 검색 행에도 숫자→문자 정규화를 적용(단 zero-padded 컬럼은 P2INC-03 참조).

---

### P2INC-08 [low / risk] 예약 salvage 가드가 본 파서와 **다른 컨테이너**를 본다

- **라이브러리 근거**: `parsers.py:1288` `parse_reservation_attempt_response` 는 `resultMap` 을
  직접 읽는데, `parsers.py:1492` `_declares_a_declared_failure` 는
  `normalize_result_row`(= `outDataSets.dsOutput0` 우선, `:1113-1117`)를 쓴다.
- **detail**: `parse_reservation_hold_response` docstring(`:1515-1518`)은 declared-FAIL 배제가
  "enforced twice" 라고 하지만 두 겹이 **서로 다른 컨테이너**를 본다. 응답이 두 컨테이너를
  동시에 실으면 2겹이 1겹이 된다(도달 조건은 좁다 — 본 파서가 `SrtProtocolError` 를 던진
  경우에만). P2INC-09 와 같은 뿌리.
- **수정 방향**: `_declares_a_declared_failure` 도 `resultMap` 을 직접 읽게 통일.

---

## B. 1차가 틀리게/불완전하게 본 것

### P2INC-09 [high / risk] `normalize_result_row` 컨테이너 우선순위 — 1차(S7-01)는 절반만 봤다. **조용한 "성공" 오보고**가 더 위험하다

- **라이브러리 근거**: `src/srt_mobile_api/parsers.py:1113-1117`; 사용처
  `parse_unpaid_cancel_response`(`:1619`), `parse_card_payment_response`(`:1739`),
  `parse_refund_response`(`:1902`).
- **실측 근거와 그 한계 (정확히 말한다)**: `outDataSets` 와 `resultMap` 이 **함께** 온 응답은
  이 저장소에서 한 번도 관측된 적이 없다 — 픽스처 전수 확인 결과 모든 응답이 둘 중 하나만
  싣는다. 관측된 선례는 **다른 컨테이너 쌍**이다: `tests/fixtures/reservation_list_empty.json`
  (2026-07-26 실측)이 한 응답 안에 `resultMap`=SUCC/IRZ000005 와 `rsMap`=FAIL/WRT300005 를
  동시에 담는다. 그래서 예약목록 파서는 `parsers.py:2069` 에서 `resultMap` **만** 읽도록
  명시 설계됐다(`parsers.py:2027-2035` 주석). 같은 파일이 mutation 파서에서는 정반대
  우선순위를 쓴다 — 이 불일치가 이 항목의 실질이다.
- **재현 (실행함)** — 1차가 든 두 사례(예외)에 더해 **1차가 놓친 세 번째**:
  ```
  {"outDataSets":{"dsOutput0":[{"strResult":"SUCC"}]},
   "resultMap":[{"strResult":"FAIL","msgCd":"W","msgTxt":"…"}]}
  → parse_refund_response        = SrtRefundResult(status='SUCC')   ← 실패를 성공으로 보고
  → parse_unpaid_cancel_response = SrtCancelResult(status='SUCC')
  → parse_card_payment_response  = SrtPaymentResult(status='SUCC')
  ```
  1차는 `dsOutput0` 가 비었을 때의 `SrtProtocolError` 만 제시했다. 실제로 더 나쁜 분기는
  곁다리 `dsOutput0` 가 SUCC 라고 말할 때 진짜 `resultMap` FAIL 을 덮는 것이다 — 환불이
  실패했는데 호출자는 성공으로 읽는다.
- **수정 방향**: `dsOutput0` 는 **유효한 행을 담고 있을 때만** 우선하고, 두 컨테이너가 모두
  status 를 말하면 `resultMap` 을 이기지 못하게 할 것. 결제만 `dsOutput0` 우선이 필요하므로
  라우트별 컨테이너를 명시하는 편이 안전하다.

### P2INC-10 [medium / doc-drift] populated 예약행 "검증됨/미검증" 모순 — 1차(S7-02)는 "저자에게 확인"에서 멈췄지만 git 이 답한다

- **라이브러리 근거**: 커밋 `9306e4c`(2026-07-26) *"LIVE 2026-07-26. The reservation list's
  populated row had never been observed … and the real one sends numbers"* — 실측 행과 그로 인한
  실제 버그(카드결제가 "금액 없음"으로 거부)를 함께 기록하고 있다. 즉 **`parsers.py:1948` 쪽이
  사실**이고 나머지가 stale: `parsers.py:2043`, `models.py:618-627`, `client.py:301-307`,
  `tests/test_reservation_list.py:12-13`, `docs/VERIFICATION.md:201`,
  `docs/IMPLEMENTATION_PROGRESS.md:783-789`.
- **detail**: 1차는 "두 서술이 동시에 참일 수 없다"에서 멈췄다. 커밋 메시지가 판정 근거다.
  다만 **`payListMap` 의 populated 행은 여전히 미기록**이며 그것이 P2INC-03 의 근본 원인이다.
- **수정 방향**: 6곳의 "UNVERIFIED" 를 갱신하고 `docs/VERIFICATION.md` 에 그 캡처(특히
  `payListMap` 행의 **타입**)를 남길 것.

---

## C. 이번 패스에서 **정확함을 재확인**한 것 (교차확인 기록)

1차 결론을 신뢰해서가 아니라 다시 돌려서 얻은 결과다.

| 항목 | 방법 | 결과 |
|---|---|---|
| 역 테이블 | `stationInfo.js` 파싱 후 `stations.STATION_NAMES_BY_CODE` 전량 비교 | 344/344 코드·명칭 **완전 일치**, 누락·추가·오탈자 0 |
| 할인종류코드 | `commCode.js` `dcntKndCd` 런 JSON 파싱 후 `discounts.py` 비교 | 171개 일치 + 문서화된 `133`/`191` 2개 추가(주석이 근거 명시), 명칭 diff 0 |
| `TRAIN_GROUP_OPTIONS` | `ara0101v.js:845-862` 콜백 | `300→17`, `900→00`, `109→05` **완전 일치** |
| User-Agent | `apktool/smali/kr/co/srail/newapp/webview/SRWebActivity.smali:14675` + `apktool.yml:11` | `<WebView UA>` + `"SRT-APP-Android V."` + `2.0.41`, **공백 없음** — `config.py:5-8` 연결 결과와 일치 |
| base_url | `SRWebActivity.smali:3974` `"https://app.srail.or.kr"` | `config.py:10` 일치 |
| NetFunnel 상수 | `netfunnel.js:18,84` | `TS_MAX_TTL=5`, 5002/5004/5101, 200/201/202/300/301/302/502 **전부 일치** |
| `reqCode` 1~9 | `common/const.js:1-11` | 선택자 6종 + 좌석페이지 `reqCode=9` **일치** |
| 좌석지정 필드군 | `ara0101v.js:866-882` | `seatNo1_N`(=`scarSeatNm`), `scarGridcnt1/2`, `scarNo1/2` **일치** |
| 좌석페이지/그리드 필드 | `ara1001l.js:1503-1512` | 13필드/11필드 **일치**, `trnNo` 5자리 패딩(`main.html:642-661`) 일치 |
| 좌석속성 코드 | `commCode.js:1-52`(`locSeatAttCd`) | `000/012/013` = 기본/창측/내측 **일치**, `rqSeatAttCd1=015`·`dirSeatAttCd1=009`(`ara0101v.js:130-132`) 일치 |
| 페이징 커서 | `ara1001l.js:1777` `sNextTm.substr(0,5)+"1"` | `payloads.py:692` `departure_time[:5]+"1"` **일치** |
| 결제/환불/취소/예약 폼 | `srtgo/srt.py:1184-1216, 1239-1246, 1138, 962-997` 전 필드 대조 | 필드명·순서·상수 **전부 일치** (`txtPrnNo` 류 오탈자 없음) |
| 엔드포인트 | `srtgo/srt.py:89-103` + `SRForegroundDialogActivity.java:31` | 9개 라우트 **일치** (`Atc14016`=목록 POST / `Atc14017`=페이지 GET 구분 정확) |
| 할인 승차권 폼 | `tests/fixtures/public_discount_search_page.html:42-69` | 23필드·8상수 **완전 일치** |
| 페이로드 필드명 전수 | `payloads.py` 의 152개 wire 키를 번들·jadx·docs·srtgo 에 전수 grep | 미확인 6개는 전부 `PUBLIC_DISCOUNT_SEARCH_CONSTANTS` 이며 픽스처로 실증됨 — **오탈자 0** |
| 안전게이트 구조 | `safety.py` 전체 + `http.py:232-300` | 읽기 allowlist / mutation 라우트·카테고리 이중검사 / `assert_no_card_secrets` / 빈바디 강제 — **우회 경로 없음** (유일한 약점은 P2INC-01, 게이트 자체가 아니라 그 기본값) |
| 한글 리터럴 인코딩 | 2026-07-26 라이브 환불이 `cnc_dmn_cont="승차권 환불로 취소"` 로 성공 + `http.py:227` `charset=UTF-8` | 문제 없음 |

## D. 확인불가로 남긴 것

- `payListMap` populated 행의 **필드 타입** — 저장소에 캡처 0건. P2INC-03 의 발현 여부가 여기 달려 있다.
- Ara10131(할인 승차권) 행이 `gnrmRsvPsbStr` 를 싣는지 — 결과 페이지는 `gnrmRsvPsbCd` 만 읽는다.
  P2INC-02 의 **노출 범위**(발현 여부가 아니라)가 여기 달려 있다.
- Ara10007 하이드레이션 GET 의 `#seatSearchForm` 이 `psgTpCd1` 을 무엇으로 렌더하는지 —
  P2INC-04 의 발현 여부가 여기 달려 있다. 같은 서버의 할인 승차권 GET 은 슬롯을 **빈 문자열**로
  준다는 실측(`VERIFICATION.md:1037`)이 유일한 간접 증거이며, 그 경우 결함은 발현하지 않는다.
