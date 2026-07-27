# SRT 예약대기 (Standby/Waitlist) 감사 보고서

담당 영역: 예약대기 신청·조회·취소, 대기 대상 열차 판별 조건, 대기 전환 처리, 예약대기와 일반예약의 요청 필드 차이.

날짜: 2026-07-27 (세션 기준) / 라이브러리 v2.0.41 대응 분석

## 조사 방법

- `analysis/apktool/assets/offline/js/ara/ara1001l.js`, `ara0101v.js` 를 라인 단위로 직접 읽어
  `fn_moveRsv`, `div_work_grd_list_oncellclick`, 이미지 상수(`S_IMG_WAIT`, `S_IMG_WAIT_S` 등)의
  실제 분기 로직을 추적함(jadx가 아닌 apktool 원본 JS — 이 앱은 WebView 오프라인 번들이 그대로
  평문 JS라서 jadx/apktool 차이가 거의 없었음).
- `docs/analysis/*.md`(cross-validation, ref-srtgo_plus, VERIFICATION.md, IMPLEMENTATION_PROGRESS.md,
  RELEASE_GAP_PLAN.md) 전체에서 standby/예약대기/waitlist 관련 언급을 확인.
- `srtgo_plus/srtgo/srt.py` 원본을 직접 읽어 `RESERVE_JOBID`,
  `reserve()`, `reserve_standby()`, `_reserve()`, `reserve_standby_option_settings()` 전체를 대조.
- `src/srt_mobile_api/{payloads,client,models,parsers,errors,safety}.py` 를 읽고,
  `tests/test_reserve_variants.py` 의 standby 관련 테스트 전부를 확인.
- `parse_reservation_attempt_response` / `parse_reservation_hold_response`(parsers.py) 를 라인
  단위로 읽어 standby 응답처럼 `trainListMap.seatNo`(좌석 미배정)가 비었을 때 실제로 무엇이
  일어나는지 추적.
- `tests/fixtures/search_personal_shape_success.json` / `search_group_shape_success.json` 을
  파싱해 `gnrmRsvPsbImg`/`rsvWaitPsbCd` 필드의 실제 존재 여부(개인 검색엔 둘 다 있고, 단체 검색엔
  `rsvWaitPsbCd`만 없음)를 직접 검증함 — 라이브러리 주석의 주장과 정확히 일치.

## 앱 기능 전체 목록

| # | 기능 | 엔드포인트 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|---|---|---|---|---|
| 1 | 예약대기 판별 신호(대기 대상 열차) | (검색 응답의 `gnrmRsvPsbImg` 컬럼) | `ara1001l.js:1447`(트리거), `:32-33`(이미지 상수), `:1045,:1058`(탭 시 `_S` 재작성) | `payloads.py:1123-1157` | 있음 — 정확 |
| 2 | 예약대기 신청(jobId=1102) | `POST /arc/selectListArc05013_n.do` | `ara1001l.js:1445-1448` | `client.py:1150`, `payloads.py:1218` | 있음 — 정확 |
| 3 | 예약대기 시 일반실 강제(특실대기 없음) | 동일 endpoint, `psrmClCd1` | `ara1001l.js:1431-1432`; 특실 이미지는 `_S`로 재작성되는 경로가 코드상 전혀 없음(직접 추적, 아래 §상세1 참조) | `payloads.py:1413-1419` | 있음 — 정확, 코드추적 재검증 완료 |
| 4 | `reserveType` 필드 예약대기 시 생략 | 동일 endpoint | 앱 자체엔 0-hit; srtgo만 근거(`srt.py:990-991`) | `payloads.py:1473-1481` | 있음 — srtgo 근거를 정확히 따름 |
| 5 | `stndFlg`(입석여부) 예약대기와 무관, 항상 "N" | 동일 endpoint | `ara0101v.js:96`, `ara1001l.js:1656` | `payloads.py:1443` | 있음 — 정확 |
| 6 | 판별 기준을 이미지(`gnrmRsvPsbImg`)로, srtgo의 `rsvWaitPsbCd` 대신 사용 | 검색 응답 row | 앱은 `rsvWaitPsbCd`를 어디서도 읽지 않음(0-hit, 재확인) | `payloads.py:191-202` | 있음 — 의도적 이탈, 근거 충분, 정확 |
| 7 | 이미지 컬럼 부재를 "부적격 아님"으로 처리 | — | 방어적 설계(항상 실제 데이터인 실앱엔 해당 없음) | `payloads.py:1144-1150` | 있음 — 합리적 설계 |
| 8 | `reservation_wait_availability`/`_name` 타입 필드 노출 | 검색 응답 `rsvWaitPsbCd`/`Nm` | 서버가 실제로 내려보냄(`search_personal_shape_success.json` 실측, 단체엔 없음) | `models.py:296-314`, `parsers.py:2528-2553` | 있음 — 정확, string 유지(숫자 변환 안 함) |
| 9 | 예약대기 옵트인(자동 추론 안 함) | — | `fn_moveRsv`는 선택된 행 기준으로만 결정 | `standby=False` 기본값 + 테스트 고정 | 있음 — 정확 |
| 10 | 예약대기 + 왕복 조합 | 동일 endpoint, `rtnDv` | `ara1001l.js:1454-1470`(다리별 재사용) — **이 조합 자체는 캡처가 아니라 추론**: srtgo `_reserve`는 `rtnDv`를 항상 `"0"`으로 고정해 대기+왕복을 한 번도 내보내지 않음 | `payloads.py` — `standby`/`round_trip` 동시 허용 | 있음 — 구성 논리는 정확하나 **미캡처(추론)** |
| 11 | 예약대기 + 시트맵예약(1103) 조합 거부 | — | `ara1001l.js:1435-1449` — 서로 다른 분기 | `payloads.py:1326-1331` `ValueError` | 있음 — 정확 |
| 12 | 예약대기 + 환승 조합 없음 | — | 환승은 한 행에서 jobId 결정 불가(행 2개), 앱에 규칙 없음 | 환승 빌더에 `standby` 파라미터 없음 | 의도된 제외 — 앱과 일치 |
| 13 | 예약대기 취소 | `POST /ard/selectListArd02045_n.do` | **서버 렌더 티켓목록의 인라인 JS `cncConfirm()`** — 버튼 라벨이 "예약대기 취소" | `client.py:1417`, `payloads.py:1789` | 있음 — 정확, 2026-07-25 라이브 라운드트립으로 일반예약 취소는 실제 검증(대기 취소 자체 미검증) |
| 14 | NetFunnel 게이트(act_10) 재사용 | 동일 | `srt.py:987` | `client.py:1187-1192` | 있음 — 정확 |
| 15 | mutation consent "reserve" 카테고리 재사용(전용 우회 없음) | — | 설계 | `safety.py:412-530` | 있음 — 게이트 우회 없음 |
| 16 | 예약대기 SMS/좌석등급변경 동의(`Ata01135`) | `POST /ata/selectListAta01135_n.do` | 번들 0-hit; srtgo만 근거(`srt.py:1014-1051`); 같은 그룹 6개 중 4개(cancel/payment/refund/reserve-info)는 이미 라이브로 실존 확인됨 | **없음** | **없음(누락)** — §S5-01 |
| 17 | 예약대기 reserve POST의 `mblPhone` 필드 | 동일 arc05013 | 앱 JS는 `mblPhone`을 아예 쓰지 않음(개인·대기 공통); srtgo는 **대기에서만** 실제 전화번호를 채움 | `payloads.py:1235` — 대기·개인 모두 생략, 근거 설명이 두 케이스를 혼동 | **구현은 되어있으나 근거 문서가 부정확(doc-drift)** — §S5-02 |
| 18 | 예약대기 전용 오류 사유 분류("접수마감"/"한도초과") | — | 앱은 msgCd만 분기, 문자열매칭 없음; srtgo는 문자열매칭 | `errors.py:297-304` — 의도적 미구현, 문서화됨 | 의도된 제외 — 앱과 일치 |
| 19 | 예약대기 reserve 응답 파싱(좌석 미배정 대응) | 동일 arc05013 응답 | 대기 응답은 `trainListMap.seatNo`가 비어있을 개연성이 큼(srtgo `SRTTicket.is_waiting = seat==""`) — 앱 자체는 `reservListMap[0].pnrNo`만 읽고 진행(`ara1001l.js:1577/:1609`) | `parsers.py:1496 parse_reservation_hold_response`의 PNR-salvage 경로가 정확히 이 케이스(trainListMap 결손)를 상정하고 설계됨 | **설계상 방어됨, 그러나 jobId=1102 응답으로 실제 검증된 적은 없음** — §S5-03 |

**app_functions_extracted = 19** (위 표 전체 행), **implemented_count = 16**
(#1–15, #18 — 정확히 구현되었거나 앱과 일치하는 의도된 제외).
문제로 보고하는 것은 #16(missing), #17(doc-drift), #19(risk) 세 가지이며, 이 표에 포함되지 않은
"예약대기 순번조회"·"대기 티켓 상태필드"는 각각 "앱 자체에 없는 기능"과 "확인불가"로 별도 기록한다
(아래 §확인불가 항목 참조 — 결함 집계에서 제외).

---

## 상세 조사1 — 대기 판별 조건의 정확성 재검증(코드추적)

라이브러리 주석은 "특실(특실) 예약대기는 앱에 표현 자체가 없다"고 주장한다(`payloads.py:1247-1254`).
jadx 요약이 아니라 apktool 원본 JS의 전체 상태 전이 로직을 직접 추적해 검증했다:

1. `div_work_grd_list_oncellclick`(`ara1001l.js:979-1150`)의 이미지 재작성 블록(`:1025-1083`)을
   전부 읽으면, **일반실(`gnrmRsvPsbImg`)이 `S_IMG_WAIT`에서 `S_IMG_WAIT_S`로 재작성되는 경로는
   두 곳**(`:1045`, `:1058`) 있지만, **특실(`sprmRsvPsbImg`)에 대해서는 그런 재작성 경로가 단
   한 곳도 없다** — `:1028-1039`, `:1066-1083`의 특실 분기는 `S_IMG_PSBL`/`S_IMG_PSBLK`만 검사하고
   `S_IMG_WAIT`는 아예 검사하지 않는다.
2. 반면 예약하기 버튼 활성화 조건(`:1122`, `:1127`)은 `sImgSp == S_IMG_WAIT_S`도 검사한다 —
   코드상으로는 "특실이 대기 선택 상태"인 케이스에 대한 방어적 조건이 존재하지만, (1)에 의해
   `sprmRsvPsbImg`가 `_S`로 재작성되는 경로가 전혀 없으므로 **이 조건은 실행 시점에 항상 거짓이며
   도달 불가능한 죽은 코드**다.
3. 따라서 `fn_moveRsv`(`:1447`)의 `jobId=1102` 결정은 항상 일반실 대기(`gnrmRsvPsbImg==WAIT_S`)만
   근거로 하며, 특실 대기는 앱의 상태 기계 어디에도 실제로 도달할 수 없다.

**결론: 라이브러리의 "특실 대기 없음, 강제로 일반실" 주장은 정확하다.** 코드리뷰 결함 아님 —
오히려 라이브러리가 srtgo보다 앱 진실에 더 가깝다(srtgo는 `SeatType.SPECIAL_FIRST`를 대기에
넘기면 실제로 `psrmClCd1="2"`를 보내는데, 이는 앱이 만들어낼 수 없는 바디다).

---

## 문제 항목 상세

### S5-01: 예약대기 SMS/좌석등급변경 동의(Ata01135) 미구현

**분류:** missing
**심각도:** medium

**앱 근거:**
- 앱 자체 번들에는 `Ata01135` 관련 문자열이 전혀 없음(apktool+jadx 전체 21,673 파일 0-hit,
  `grep -rn "1135|ata01135" analysis/` 로 재확인 — 0건).
- "번들에 없다≠앱에 없다" 원칙이 적용되는 사례: 같은 6개 endpoint 그룹(payment/cancel/refund/
  standby-option/reserve-info/ticket-info) 중 **4개(cancel, payment, reserve-info, refund)는
  2026-07-25~26 라이브 라운드트립으로 이미 실제로 존재함이 검증됐다**
  (`docs/analysis/cross-validation-2026-07-21.md:370`). 남은 2개(`Ata01135`, `Ard02019`)만
  여전히 미검증이며, 존재하지 않는다고 볼 근거는 없다.
- 앱 자신의 `fn_moveRsv`(`ara1001l.js:1453-1468`)가 만드는 `oRsvData`에는 `mblPhone` 등 알림
  관련 키가 전혀 없다 — 즉 SMS 동의 설정은 최초 `arc05013` POST와는 별도의 요청으로 이뤄진다는
  srtgo의 흐름과 정합적이다.

**라이브러리 근거:**
- `src/srt_mobile_api/client.py:1224-1227`(reserve 독스트링): "srtgo additionally POSTs
  `/ata/selectListAta01135_n.do` afterwards to set SMS/seat-change options ...; that route is
  0-hit in our v2.0.41 bundle and has no equivalent in it, so it is NOT implemented" — 라이브러리
  자신의 정직한 자기 신고.
- `grep -rn "1135" src/srt_mobile_api/` → `client.py:1224` 단 1건(문서 주석)뿐, 실제 메서드 없음.

**무엇이 왜 문제인가:** 예약대기의 실질적 목적은 좌석이 나면 SMS로 통보받는(+선택적으로 좌석등급
자동변경에 동의하는) 것이다. 이 endpoint가 빠지면 `reserve(standby=True)`로 만든 대기 항목은
서버 기본값을 그대로 갖게 되어, 대기 전환("예약대기 전환 처리") 통보를 못 받을 개연성이 있다.
다만 (a) `reserve(standby=True)` 자체는 정상적으로 대기표를 생성하며 실패하지 않고, (b) 이 gap은
이미 5곳의 문서(VERIFICATION.md:1335, IMPLEMENTATION_PROGRESS.md:263, RELEASE_GAP_PLAN.md,
cross-validation, client.py 독스트링)에 정직하게 기록되어 있으므로 — "숨겨진 결함"이 아니라 "알려진
채 방치된 기능 공백"이다. 따라서 심각도는 high가 아니라 **medium**으로 매긴다(감사 기준의 high는
"기능이 실서버에서 실패하거나 잘못된 결과를 낸다"인데, 여기서 reserve 자체는 실패하지 않는다).

**제안 수정 방향:** `Ata01135`에 대한 메서드를 추가 구현(필드: `pnrNo`, `psrmClChgFlg`,
`smsSndFlg`, `telNo` — srtgo `srt.py:1014-1051` 기준)하고, 최소 라이브 캡처 1회로 실존을 확정할 것.

---

### S5-02: `mblPhone` 생략의 근거 문서가 standby 케이스에 대해서는 부정확함

**분류:** doc-drift
**심각도:** medium

**앱 근거:** `ara1001l.js:1453-1468`(fn_moveRsv가 만드는 `oRsvData`)에 `mblPhone` 키가 없음 —
개인·대기 공통으로 앱 JS 자체는 이 필드를 쓰지 않는다(0-hit, 전체 번들).

**라이브러리 근거 / 문제:**
- `payloads.py:1235`: "`mblPhone` is omitted -- srtgo passes `None`, which requests drops from
  the wire, and the string has ZERO hits across the whole v2.0.41 bundle, so there is nothing to
  add it back from."
- 이 근거는 **personal(jobId=1101) 케이스에만 정확**하다: srtgo `reserve()`가 personal 경로로
  갈 때는 `mblPhone` 인자를 아예 넘기지 않아 `_reserve`의 기본값 `None`이 쓰이고, `requests`가
  `None` 값을 가진 키를 인코딩에서 자동으로 드롭한다(`_encode_params`의 `if v is not None`).
- 그러나 **standby(jobId=1102) 케이스는 다르다.** srtgo `reserve()`(`srt.py:862-864`)는 대기로
  갈 때 `mblPhone=self.phone_number`를 명시적으로 채우며, `self.phone_number`는 로그인 응답의
  `user_info["MBL_PHONE"]`에서 채워진 **실제 전화번호 문자열**이다(`srt.py:726`). 즉 srtgo의
  실제 와이어에서는 대기 reserve POST에 사용자의 실전화번호가 실려 나간다 — `None`이 아니므로
  `requests`가 드롭하지 않는다.
- `docs/analysis/cross-validation-2026-07-21.md:131`도 이 정확한 지점을 **미해결로 남겨둔다**:
  "`mblPhone` sent by srtgo ... populated only for standby, dropped for personal ... Either a
  server-rendered JSP hidden input we cannot see, or an srtgo-empirical field." — 이 열린 질문이
  `payloads.py:1235`의 주석에서는 "0-hit이니 추가할 근거 없음"으로, personal/standby 구분 없이
  뭉개져 있다.

**결론:** 필드를 생략하는 **행동 자체**가 틀렸다고 단정할 근거는 없다(앱 JS 자신도 안 쓰므로,
어쩌면 진짜로 서버 렌더 hidden input일 뿐 arc05013 POST 본문엔 필요 없을 수 있다). 그러나 **생략의
근거로 제시된 설명("srtgo도 드롭한다")은 standby 경로에서는 사실이 아니며**, cross-validation
문서가 이미 열어둔 질문을 코드 주석이 답이 난 것처럼 닫아버린 것이 문제다. doc-drift로 분류한다.

**제안 수정 방향:** `payloads.py:1235`의 주석을 personal/standby로 분리해서 정확히 서술하고,
standby 라이브 캡처 시 `mblPhone` 필드 유무를 최우선으로 확인할 것.

---

### S5-03: 예약대기 reserve 응답 파싱 — 설계상 방어되어 있으나 jobId=1102로 실제 검증된 적 없음

**분류:** risk
**심각도:** low

**분석:** standby 응답은 좌석이 아직 배정되지 않았을 가능성이 크다(srtgo 자신의 모델도
`SRTTicket.is_waiting = self.seat == ""`, `srt.py:286` — 좌석 미배정을 "대기중"의 정의로 삼음).
`parse_reservation_attempt_response`(`parsers.py:1277`)는 `trainListMap[0].seatNo`/`scarNo`를
**비어있지 않은 문자열로 엄격 요구**하고(`_reservation_attempt_string(..., allow_empty=False)`),
`reservListMap[0]`의 14개 필드(`pnrNo`, `totSeatNum` 등)도 전부 엄격 요구한다 — standby 응답이
이 중 하나라도 비우면 `SrtProtocolError`가 발생한다.

**그러나** 실제 라이브 전송 경로가 쓰는 함수는 `parse_reservation_attempt_response`가 아니라
`parse_reservation_hold_response`(`parsers.py:1496`, `client.py`의 `_submit_reservation`이 호출)
이며, 이 함수는 위 `SrtProtocolError`를 명시적으로 잡아(`:1521-1529`) — 응답이 **선언된 FAIL이
아닌 한** — `_minimal_hold_from_raw`로 폴백한다. 이 폴백은 `reservListMap[0].pnrNo`(비어있지 않은
문자열)만 있으면 성공하고, `trainListMap`이나 `totSeatNum` 등 나머지 필드는 전혀 요구하지 않는다.
독스트링(`:1506-1508`)은 이 폴백의 예시로 정확히 **"a missing trainListMap seat number"**를
든다 — 즉 이 설계는 좌석 미배정 응답(대기표의 전형적 모양)을 구체적으로 염두에 두고 만들어진
것으로 보인다.

**결론:** `reserve(standby=True)`의 응답이 좌석 미배정 형태로 오더라도 PNR이 살아있는 한 hold는
salvage되어 캐치가 손실되지 않을 개연성이 높다 — 이는 검증된 부정적 사실(verified negative)로
기록할 가치가 있다. 다만 이는 **추론된 방어**이지 **실측된 방어**가 아니다: standby reserve
자체는 한 번도 라이브로 전송된 적이 없고(`client.py:1202-1204`가 스스로 인정),
`reservListMap[0].pnrNo` 자체가 비정상인 극단적 케이스나 컨테이너 구조 자체가 다른 경우까지는
방어하지 못한다. risk/low로 남긴다 — high로 격상하지 않는 이유는 실제 실패 사례를 찾지 못했고
설계가 이미 이 시나리오를 겨냥하고 있기 때문이다.

---

### S5-04 (info): 예약대기 seat_type 무시가 예외 없이 조용히 오버라이드됨

**분류:** doc-drift(참고용, 결함 아님)
**심각도:** low

`personal_reservation_payload(standby=True, seat_type=SeatType.SPECIAL_ONLY)` 를 호출해도 예외가
발생하지 않고 조용히 일반실로 강제 전환된다(`payloads.py:1413-1419`,
`tests/test_reserve_variants.py:591-604`로 명시적으로 고정됨). §상세 조사1에서 확인했듯 앱 자체에
특실 대기가 존재하지 않는다는 사실에 정확히 부합하는 설계다. 결함으로 보지 않으나, 특실을
명시적으로 요청한 호출자가 조용히 일반실 대기를 받게 된다는 점은 API 사용자 관점에서 유의할 만하다.

---

### S5-05 (확인불가): 예약대기 티켓의 목록 상태 필드

**분류:** unverifiable
**심각도:** info

`SrtReservationSummary`(예약/발권 목록, `/atc/selectListAtc14016_n.do`)에는 "이 항목이 대기중인지
확정되었는지"를 나타내는 전용 필드가 없다(`raw_train`/`raw_pay`만 보존). 결함이 아니라 — 라이브
검증에 쓰인 계정에 예약 내역이 전혀 없어(`trainListMap: []`) 실제 채워진 행 모양을 한 번도 관측한
적이 없기 때문이다(라이브러리 스스로 정직하게 문서화). srtgo의 `SRTReservation.is_waiting`
(`= not (paid or payment_date or payment_time)`)은 "미결제"와 "대기중"을 동일시하는 srtgo 자체의
개념적 단순화이며 앱 근거가 없어 그대로 채용하는 것도 위험하므로, findings로 올리지 않고
확인불가로만 기록한다.

---

## 정확히 구현된 것으로 확인된 주요 항목(재확인 요약)

- 예약대기 트리거를 `gnrmRsvPsbImg`(이미지)로 판별하고 srtgo의 `rsvWaitPsbCd`를 의도적으로 따르지
  않는 설계 — 코드 추적 및 fixture 실측으로 정확함을 재확인.
- `jobId` 1101/1102/1103 세 값의 의미·트리거 전부 정확.
- 예약대기 시 `psrmClCd1` 강제 일반실 — apktool 원본 JS 전체 상태전이 추적으로 "특실 대기는
  도달 불가능한 죽은 코드"임을 재확인, 라이브러리 설계가 정확함.
- `reserveType` 필드 조건부 생략 — srtgo 근거를 정확히 따름.
- `stndFlg`(입석)와 예약대기 무관 처리 — 정확.
- 예약대기 취소가 일반예약 취소와 동일 엔드포인트/필드를 쓴다는 것 — 서버 렌더 페이지의
  `cncConfirm()` 인라인 JS(실측, "예약대기 취소 버튼" 라벨)로 뒷받침되고, 일반 취소는 2026-07-25
  라이브 라운드트립으로 실제 검증됨.
- NetFunnel 게이트, mutation consent 카테고리 — standby 전용 우회 없음, 안전 모델 구멍 없음.
- **응답 파싱의 PNR-salvage 경로가 좌석 미배정(대기 전형) 응답을 구체적으로 겨냥해 설계됨**
  (§S5-03) — 결함이 아니라 오히려 강건성의 증거.
- 단체(그룹) 예약대기는 사용자가 명시적으로 제외한 범위이므로 결함 아님.
- 예약대기 순번/대기자목록 조회 API는 앱·srtgo 어디에도 없는 기능이라 "누락"이 아니라 애초에
  존재하지 않는 기능.

## 결론

예약대기의 **핵심 예약/취소 흐름**(신청 트리거 판별, `jobId` 스위치, 일반실 강제, 취소, 응답
파싱의 방어적 설계)은 앱 코드를 라인 단위로 재추적한 결과 라이브러리 구현이 정확했다. 실질적
공백은 **대기 좌석 전환 알림(Ata01135) 미구현**(medium, 이미 문서화된 알려진 gap)과, 그와 엮인
**`mblPhone` 생략 근거의 문서 부정확**(doc-drift, medium) 두 가지이며, 세 번째로 **standby 응답
자체가 한 번도 라이브 검증되지 않았다는 점**을 risk/low로 남긴다(단, 파서의 PNR-salvage 설계가
이미 이 시나리오를 겨냥하고 있어 실제 파손 가능성은 낮다고 판단).
