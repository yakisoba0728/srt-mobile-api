# SRT 2차 감사 — 누락 렌즈 (P2MIS)

**감사자:** 2차 검토자 (독립 재확인)
**대상:** `srt-mobile-api`
**렌즈:** 앱에는 있는데 라이브러리에 **아예 없는** 기능 / 엔드포인트 / 파라미터
**날짜:** 2026-07-27

---

## 0. 방법 — 1차와 다르게 훑은 방식

1차는 8개 영역으로 분할했다. 나는 분할하지 않고 **엔드포인트 경로 하나의 집합**으로
전수 나열한 뒤, 각각에 대해 `src/srt_mobile_api/` 대응물이 있는지 확인했다.

- 경로 추출: `analysis/apktool/assets/offline/**` (bundle), `analysis/jadx/sources/**`,
  `analysis/apktool/smali*/**`, `docs/analysis/*.md`, `tests/fixtures/**`,
  그리고 참조 구현 두 벌(`srtgo/srtgo/srt.py`,
  `srtgo_plus/srtgo/srt.py`)을 docs 인용을 거치지 않고
  **직접** 열람.
- 라이브러리 대조: `safety.py`의 `READ_ONLY_ROUTES` / `SRT_MUTATION_ROUTES`를 권위로 삼고,
  `client.py` 메서드 목록·`payloads.py` 빌더·`parsers.py` 파서를 개별 확인.
- 파라미터 계열(좌석속성·승객유형·여정·결제)은 앱 원본 JS의 **호출부(call site)** 존재
  여부로 판정. "코드표에 값이 있다"만으로는 앱 기능으로 인정하지 않았다 (§4-(a) 참조).

**전수 대조한 엔드포인트/표면 44개 + 파라미터 계열 12개 = 56개.**
그중 라이브러리에 올바르게 대응물이 있는 것 43개.

---

## 1. 1차가 놓친 것 (NEW)

### P2MIS-01 — `/ard/selectListArd02019_n.do` (승차권 상세조회) 전면 부재 · missing · medium

**앱/참조 근거**
- `srtgo_plus/srtgo/srt.py:96`
  `"ticket_info": f"{SRT_MOBILE}/ard/selectListArd02019_n.do"`
  (동일 라인이 `srtgo/srtgo/srt.py:96`에도 존재 — 두 벌 일치)
- `srt.py:1102-1112` — `POST` 바디는 `{"pnrNo": <PNR>, "jrnySqno": "1"}` 단 2개,
  응답 `trainListMap` 각 행이 한 장의 승차권.
- `srt.py:274-286` (`SRTTicket.__init__`) — 행 필드는
  `scarNo`(호차), `seatNo`(좌석), `psrmClCd`(객실등급), `dcntKndCd`(할인종별),
  `rcvdAmt`(수납액), `stdrPrc`(기준운임), `dcntPrc`(할인액).
- `srt.py:286` — `self.is_waiting = self.seat == ""` : **좌석번호가 빈 문자열인 것이
  예약대기 승차권의 정의적 신호**다.
- `srt.py:1105-1109` — `get_reservations()`가 모든 예약행에 대해 이 호출을 하고
  `SRTReservation(train, pay, self.ticket_info(...))`로 조립한다. 즉 참조 구현에서
  "예약목록 읽기"는 2-엔드포인트 연산이다.

**라이브러리 근거:** **없음.**
`grep -rn "Ard02019\|02019" src/ tests/` → 0 hit (docs에만 언급:
`docs/analysis/ref-srtgo_plus.md:103` "NEW — not in our routes").
`safety.py:280-359`(`READ_ONLY_ROUTES`)에 없고, `client.py`에 메서드 없고,
`payloads.py`/`parsers.py`에 빌더·파서 없음.

**정직하게 짚어둘 점 (반론 선점).**
`models.py:625`는 라이브 승차권확인 페이지가 `gotoDetailARD02018(...)` /
`gotoDetailARD0201V(...)`로 상세를 연다고 기록한다 — **`Ard02019`가 아니다.**
따라서 "앱이 Ard02019를 호출한다"고 쓰면 안 된다. 실제 구도는 이 저장소가 결제에 대해
이미 문서화한 것과 **동일한 2중 표면**이다: 우리 앱은 WebView 페이지(`ard02017/18`)로,
srtgo 계열은 모바일 JSON(`ata09036`)으로 결제한다(`safety.py:420-424`,
`docs/analysis/ref-srtgo_plus.md:110-116`). 승차권 상세도 마찬가지로 앱=WebView,
srtgo=JSON `Ard02019`이며, **라이브러리는 둘 다 없다.**

**무엇이 문제인가**
1. 예약 후 **실제 배정된 호차·좌석을 확인할 방법이 없다.**
   `get_reservations()`가 돌려주는 `SrtReservationSummary`에는 `seat_number`(seatNum)
   한 개뿐이고(`models.py:638`), 그것도 라이브에서 비어있는 행만 관측됐다고
   docstring이 명시한다(`models.py:617-627`).
2. **1차 05-standby S5-05가 "확인불가"로 남긴 질문의 답이 여기에 있다.**
   S5-05는 "예약대기 티켓의 목록 상태 필드"를 확인불가로 닫았는데,
   `Ard02019` 행의 `seatNo == ""`이 참조 구현이 쓰는 명시적 판별자다(`srt.py:286`).
   1차 05-standby는 본문에서 `Ard02019`를 "미검증 2개 중 하나"로 **이름만 언급**하고
   자기 영역이 아니라는 이유로 결함으로 올리지 않았다. 06-pay/07-refund는 목록
   (atc14016/atc14017)까지만 담당했다. **전형적인 영역 경계 누락.**
3. 승객별 운임/할인 분해(`stdrPrc`/`dcntPrc`/`dcntKndCd`)가 전혀 없다.
   1차 07-refund S7-04가 "위약금·부분환불 필드는 어떤 아티팩트에도 없다"고 결론냈는데,
   **운임 분해 자체는 이 엔드포인트에 있다**(위약금은 여전히 없음 — S7-04 결론은 유효).
   *(보강 근거일 뿐 호출부 아님: `commCode.js`의 `dcntKndCd` 그룹 171개 항목이 이 필드의
   해독표지만, 그 표는 코레일+SRT 공용이라 §4-(a) 규칙상 앱 기능의 증거로 세지 않는다.)*

**심각도 근거:** READ 하나가 없는 것이고, 기존 기능이 실패하지는 않는다 → medium.

**수정 방향:** `Ard02019`를 `READ_ONLY_ROUTES`에 POST로 등록하고
`{pnrNo, jrnySqno}` 정확 폼 계약을 `_assert_exact_form_contract`로 고정,
`SrtTicketDetail` 모델과 `get_ticket_detail(pnr_no)` 추가. 라이브 1회 캡처로 실존 확정 필요.

---

### P2MIS-02 — `rqSeatAttCd1/2`가 `"015"`로 고정 — 휠체어석 예약 불가 + 검색 옵션 조용한 무시 · missing · medium

**앱 근거 (1차 근거, srtgo 파생 아님)**
- `analysis/apktool/assets/offline/js/ara/ara0101v.js:758-775` — 좌석옵션 팝업
  (`POP_REQ_SEAT`) 콜백이 `rqSeatAttCd1` **와** `rqSeatAttCd2`를
  `obj.seatOption`으로 덮어쓴다:
  ```
  var arrCode = [obj.seatOption, obj.seatPosition, "009"];
  "rqSeatAttCd1": arrCode[0], "locSeatAttCd1": arrCode[1], ...
  "rqSeatAttCd2": arrCode[0], "locSeatAttCd2": arrCode[1], ...
  ```
- `ara0101v.js:611-628` — 앱이 `rqSeatAttCd1 == "021"`(휠체어) 와 `"028"`(전동휠체어)
  각각에 대해 **전용 이용동의문 다이얼로그**를 띄운다. 즉 이 두 값은 죽은 상수가 아니라
  사용자가 실제로 도달하는 값이다.
- `ara1001l.js:105` — 검색의 `seatAttCd`는 `lfn_getRsv("rqSeatAttCd1")` 그대로다.
- `ara1001l.js:1670` (`var sRqSeatAttCd1 = lfn_getRsv("rqSeatAttCd1");`) 와
  `ara1001l.js:1694` (`, {val:sRqSeatAttCd1, title:"요구좌석속성코드1"}`) —
  `rqSeatAttCd1`은 `#rsvForm`의 `fn_validChk` **필수 검증 필드 21개 중 하나**다.
  즉 예약 본문에 실려 나간다
  (`docs/analysis/full-api-analysis-2026-07-20.md:257`의 21필드 목록에도 포함).
- 유효값: `commCode.js`의 `rqSeatAttCd` 그룹 중 SRT 호출부가 확인되는
  `015 일반 / 021 휠체어 / 028 전동휠체어` 3개만 인정 (§4-(a) 참조).

**라이브러리 근거**
- `src/srt_mobile_api/payloads.py:1110` — `_reservation_passenger_fields()` 안에서
  `"rqSeatAttCd1": "015",` **하드코딩**.
- `src/srt_mobile_api/payloads.py:1583` — 환승 2구간도
  `"rqSeatAttCd2": "015",` **하드코딩**.
- `src/srt_mobile_api/payloads.py:1218-1228` (`personal_reservation_payload`) 및
  `src/srt_mobile_api/client.py:1150-1162` (`SrtClient.reserve`) 시그니처에
  좌석속성 파라미터가 **아예 없다**. `client.py:1316`(`reserve_transfer`) /
  `payloads.py:1589-1596`(`transfer_reservation_payload`)도 동일.
- 반면 `src/srt_mobile_api/models.py:212` — `TrainSearchQuery.seat_attr_code`는
  **공개 필드**이고 기본값 `"015"`이며,
  `payloads.py:583, :586, :639`에서 검색 요청의 `rqSeatAttCd1`/`seatAttCd`로 흘러간다.
  `client.py:374`(`get_seat_option_selector`)는 좌석옵션 팝업까지 읽을 수 있다.

**무엇이 문제인가 (두 반쪽, 하나의 결함)**
- (a) **휠체어(021)/전동휠체어(028) 예약이 라이브러리로는 도달 불가능**하다.
  앱에는 전용 동의문까지 있는 정식 기능인데 대응물이 전혀 없다.
  `reserve`, `reserve_transfer` 두 경로 모두 해당.
- (b) 더 나쁜 쪽: `TrainSearchQuery(seat_attr_code="021")`로 **휠체어 재고를 검색한 뒤**
  그 결과 행으로 `reserve()`를 호출하면, 예약 본문은 조용히 `rqSeatAttCd1="015"`로
  나간다. **경고도 예외도 없다.** 검색과 예약 사이에서 사용자가 지정한 좌석속성이
  말없이 증발한다. 라이브러리 내부 일관성 위반이기도 하다 — 같은 값을 검색에서는
  존중하고 예약에서는 버린다.

**심각도 근거:** 라이브 증거로 "실서버에서 실패한다"를 입증하지 못했고, 트리거가
"호출자가 명시적으로 `seat_attr_code`를 바꾼 경우"로 한정된다 → medium.
(다만 (b)의 조용함 때문에 medium 중에서는 상단으로 본다.)

**수정 방향:** `reserve` / `reserve_transfer` / `personal_reservation_payload` /
`transfer_reservation_payload`에 `seat_attr_code`(기본 `"015"`, 허용집합
`{015,021,028}`)를 추가해 두 슬롯에 전달. 최소한, `TrainSummary`를 만든 검색 쿼리의
`seat_attr_code`가 `"015"`가 아닐 때 예약이 **거부**되게 하여 조용한 강등만은 막을 것.

---

### P2MIS-05 — `mblPhone`/`telNo`의 출처가 이미 확보돼 있는데 "가져올 데가 없다"고 기록됨 · doc-drift · low — *1차 S5-02 보강*

**앱 근거**
- `analysis/apktool/assets/offline/sub/main.html:465-482` — 앱이 인증된 페이지마다
  서버 렌더링하는 `application.gds_userInfo` 블록. `main.html:477`에 `MBL_PHONE: ""`가
  실재한다 (같은 블록에 `CUST_MG_NO`, `MB_CRD_NO`, `CUST_NM`, `CUST_SRT_CD`,
  `CUST_CL_CD`, `BTDT`, `SEX_DV_CD`, `ABRD_RS_STN_CD`, `GOFF_RS_STN_CD`, `DSCP_YN`,
  `USER_DV`, `USER_KEY`, `KR_JSESSIONID`, `SR_JSESSIONID`).
- `srtgo/srtgo/srt.py:726` 및
  `srtgo_plus/srtgo/srt.py:726` (두 벌 동일) —
  **로그인 응답의 `userMap`에서** `user_info["MBL_PHONE"]`를 가드 없이 읽는다.
  즉 전화번호는 부킹페이지를 파싱하지 않아도 **로그인 응답만으로 이미 손에 있다.**

**라이브러리 근거**
- `src/srt_mobile_api/payloads.py:1235-1237` —
  "`mblPhone` is omitted -- srtgo passes `None` ... and the string has ZERO hits
  across the whole v2.0.41 bundle, **so there is nothing to add it back from.**"
- `src/srt_mobile_api/models.py:38-61` — `SrtSession`은 로그인 `user_map` **전체**를
  보관하지만 노출하는 파생 속성은 `membership_number`(`MB_CRD_NO`) 하나뿐이다.

**무엇이 문제인가:** 마지막 절("가져올 데가 없다")이 **사실이 아니다.**
값은 이미 `SrtSession.user_map["MBL_PHONE"]`에 있다. 1차 S5-02는 앞 절
("srtgo도 None을 보낸다")이 standby 경로에서 부정확함까지는 잡았지만,
**뒤 절이 통째로 틀렸다는 점과 그 값이 이미 저장소 안에 있다는 점은 짚지 않았다.**
이것이 P2MIS-04(Ata01135)의 `telNo` 공급원이기도 하므로 두 항목이 같은 뿌리를 공유한다.

**수정 방향:** `payloads.py:1235`의 마지막 절 삭제/정정하고, `SrtSession`에
`phone_number`(`MBL_PHONE`) 파생 속성을 추가(마스킹 대상으로 `redaction.py`에도 등록).

---

## 2. 1차가 틀리게 본 것 / 문서가 틀린 것

### P2MIS-03 — `docs/analysis/full-api-analysis-2026-07-20.md`의 `psgTpCd` 해독표가 틀렸다 · doc-drift · low

**앱 근거 (권위)**
`analysis/apktool/assets/offline/js/commCode.js:54-88` — `psgTpCd` 코드그룹:

| cd_val | cd_nm | rmk |
|---|---|---|
| 1 | 어른 | 어른 |
| 2 | 장애 1~3급 | 장13 |
| 3 | 장애 4~6급 | 장46 |
| 4 | 만 65세이상 | 경로 |
| 5 | 만4~12세 | 어린이 |

**문서 근거 (틀린 쪽)**
- `docs/analysis/full-api-analysis-2026-07-20.md:378`
  「`psgTpCd1..5` | 승객유형: **1=어른,2=어린이,3=경로,4=중증장애,5=경증장애** |
  `ara0101v.js:113-121`」
- 같은 문서 `:453` (§4.8 요약표)에도 동일한 잘못된 표가 반복된다.
- **인용된 근거 자체가 그 주장을 뒷받침하지 않는다.** `ara0101v.js:113-121`을 직접
  열어보면 `"psgTpCd1":"1"` ~ `"psgTpCd5":""` 초기값과 한국어 주석
  「승객유형코드1~5」뿐, **이름 매핑이 한 글자도 없다.** 표는 문서 작성 시점의 추정이다.
- 오류의 성격: 2↔5, 3↔4가 서로 뒤바뀐 형태(어린이↔장애1~3급, 경로↔장애4~6급).

**라이브러리 근거 (옳은 쪽)**
- `src/srt_mobile_api/payloads.py:269-276` — `PASSENGER_TYPE_CODES`
  `("adult","1"), ("disability_1_to_3","2"), ("disability_4_to_6","3"),
   ("senior","4"), ("child_slot_count","5")` — **commCode.js와 일치.**
- 참조 구현 `srtgo_plus/srtgo/srt.py:241-247`
  (`SRTTicket.PASSENGER_TYPE`) 도 commCode.js와 일치.

**무엇이 문제인가:** 이 저장소는 `docs/analysis/`를 사실상의 프로토콜 명세로 취급하고,
1차 감사 8명 전원이 이 문서를 근거로 지목받았다. **코드는 맞고 문서가 틀렸다.**
현재 동작에는 지장이 없으므로 low. 다만 이 표를 믿고 "코드를 문서 쪽으로 맞추는"
역방향 수정이 일어나면 어린이 요금으로 장애인석을, 경로 요금으로 장애할인을 신청하는
실운임 오류가 된다 — low로 두되 우선 정정해야 하는 이유가 이것이다.
1차 8개 보고서 중 어느 것도 이 불일치를 지적하지 않았다(02-search는 `commCode.js`의
`stlbTrnClsfCd`/`trnGpCd` 표만 대조했고 `psgTpCd`는 대조 대상에 넣지 않았다).

**수정 방향:** `full-api-analysis-2026-07-20.md:378, :453`의 표를 `commCode.js:54-88`
값으로 교체하고, 근거를 `ara0101v.js:113-121`에서 `commCode.js:54-88`로 바꿀 것.
"라이브러리가 옳다"는 문장을 함께 남겨 역방향 수정을 막을 것.

---

## 3. 1차와 겹치는 항목 (교차확인)

### P2MIS-04 — `/ata/selectListAta01135_n.do` (예약대기 SMS/좌석등급변경 동의) 미구현 · missing · medium — *1차 S5-01 교차확인 + 보강*

**앱/참조 근거**
- `srtgo_plus/srtgo/srt.py:98`
  `"standby_option": f"{SRT_MOBILE}/ata/selectListAta01135_n.do"`
- `srt.py:1014-1051` — 바디는 정확히 4개:
  `{pnrNo, psrmClChgFlg: Y|N, smsSndFlg: Y|N, telNo: <phone> or ""}`.
- `srt.py:862-876` — **예약대기 예약은 이 호출과 한 쌍이다.** 전화번호가 있으면
  `reserve_standby(...)` 직후 `reserve_standby_option_settings(res, isAgreeSMS=True,
  isAgreeClassChange=..., telNo=self.phone_number)`를 즉시 호출한다.
- v2.0.41 번들 0-hit(1차 확인과 동일). 단 같은 6개 그룹 중 4개
  (cancel/payment/reserve-info/refund)가 2026-07-25~26 라이브로 실존 확정됐으므로
  "번들에 없으니 없다"는 판단은 금지된다.

**라이브러리 근거:** **없음.** `grep -rn "1135" src/` → `client.py:1224`의 주석 1건뿐
(자기 신고: "that route is 0-hit ... so it is NOT implemented"). 메서드·빌더·라우트 없음.

**1차 대비 보강 2점**
1. `telNo`의 공급원이 이미 있다 — `SrtSession.user_map["MBL_PHONE"]`
   (P2MIS-05 근거). 1차 S5-01은 "필드: pnrNo/psrmClChgFlg/smsSndFlg/telNo"까지만
   적고 `telNo`를 어디서 얻는지는 열어뒀다.
2. 참조 구현에서 이 호출은 **선택 기능이 아니라 standby 예약의 두 번째 절반**이다
   (`srt.py:862-876`). 즉 `reserve(standby=True)`만 구현한 현재 상태는
   "기능 일부 누락"이 아니라 "2단계 흐름의 1단계만 구현"에 가깝다.

**심각도:** `reserve(standby=True)` 자체는 실패하지 않으므로 medium (1차와 동일).

---

## 4. 오탐으로 판단해 **결함으로 올리지 않은** 것 — 그리고 그 이유

이 절은 "누락 렌즈"가 빠지기 쉬운 오탐을 명시적으로 배제한 기록이다.

**(a) `commCode.js` 코드표 마이닝은 하지 않았다.**
`commCode.js`는 **코레일+SRT 공용 표**다. `stlbTrnClsfCd`에 새마을호/무궁화호/통근열차,
`trnGpCd`에 O-train/V-train/DMZ train/정선아리랑, `cmtrUtlTrmCd`/`cmtrUtlAgeCd`에
정기승차권 기간·연령 코드가 들어 있다 — 전부 SRT가 아니다. 따라서
`psrmClCd 4(입석/자유석)`, `rqSeatAttCd 018/019/031/032`, `locSeatAttCd 011(1인석)`,
`tkKndCd`(81개), `tkSttCd`(16개), `schdTrvlDvCd`, `dcntKndCd`(171개) 등은
**SRT 쪽 호출부가 없으므로 결함으로 올리지 않았다.**
P2MIS-02가 `015/021/028`만 다루는 것은 이 세 값만 `ara0101v.js:611-628, :758-775`에
실제 호출부가 있기 때문이다.

**(b) 정기승차권(定期乘車券).** `sub/main.html:426, :700, :707`,
`sub/ticketList.html:380`에 메뉴 레이블은 있으나 `href="#"` / `onclick=""` 로
비활성이고 엔드포인트 근거가 0이다 → 확인불가, 결함 아님.
(`sub/main.html:701, :708`의 "SRT 여행상품"도 같은 상태.)

**(c) `eventTrainInfo.js`** — 2018/03 기간의 만료된 할인이벤트 하드코딩,
`getEventTrainInfo` 소비자 없음 → 죽은 코드.

**(d) `exceptStation.js`** — 1차 02-search S2-01이 이미 다뤘고, 번들 내 소비자가 없다
(`getStationFlag` 호출부 0-hit). 재보고 생략.

**(e) 명시적 제외 범위 재확인 (결함 아님):**
단체예약(`Arc06014`, `Ard02018`) — 사용자가 명시 제외.
`Ard02017/02018` WebView 결제 진입 — 앱의 PG/TransKey 경로, 라이브러리는 JSON
`Ata09036`으로 대체 구현(`safety.py:420-424`).
`Ata01032`(할인상세, 런타임 HTTP 500), `Ara10h01`(주석 처리된 죽은 Nexacro 게이트웨이,
`ara1001l.js:254-278`), `srbridge` 30 액션 / FIDO(`fido.srail.co.kr`) / H2O 푸시
(`push.srail.co.kr:3101`) / SNS 로그인 / TransKey 보안키패드 — 전부 HTTP API가 아니거나
하드웨어 의존 → 의도된 제외. `/cms/article/*.do`(SR 소식)·`/neo/common/rest/JongURi/view.do`
는 예매호스트가 아닌 `www.srail.co.kr`/dev 자산 → 범위 밖.
`/login/loginOut.do` — 1차 S1-03이 info로 처리, 3차례 선행감사에서 "deliberate
read-only design" 확정. 재보고 생략.

**(f) `rsvWaitPsbCd` vs `gnrmRsvPsbImg`** — srtgo는 `rsvWaitPsbCd >= 0`으로 대기
가능 여부를 판정하고 라이브러리는 `gnrmRsvPsbImg`를 쓴다. 그러나 `payloads.py:197-202`가
이 차이를 명시적으로 인지·설명하고 있고 `parsers.py:2530`가 `rsvWaitPsbCd`를 raw로
보존한다 → 결함 아님.

**(g) 결함일 줄 알았으나 확인해보니 **정상 구현**된 것 (필드 단위 대조 결과)**
- `reserveType="11"` — 참조 구현이 개인예약(`jobId=1101`)에만 붙이는 필드
  (`srtgo_plus/srt.py:990-991`). `cross-validation-2026-07-21.md:132`가
  "absent from OUR code"라 적었지만 그건 **디컴파일** 기준이고, 라이브러리는
  `payloads.py:1474-1481`에서 개인예약에만 정확히 붙인다
  (`payloads.py:1255` 대기 경로에서는 DROP, `tests/test_reserve_variants.py:264-276`가
  회귀 고정). **누락 아님.**
- 카드결제 본문 31키 — `payloads.py:2092-2124`를 `srtgo_plus/srt.py:1184-1216`과
  키 단위 전수 대조: `stlDmnDt … pageUrl` 31개가 **이름·순서·상수값 모두 일치**,
  누락 0. 1차 06-pay는 결제수단 관점으로 접근해 이 대조를 하지 않았으므로
  여기서 채운다.

---

## 5. info로만 기록한 항목

### P2MIS-06 — MY SRT 서버렌더링 메뉴 재탐색: 저장 아티팩트로는 신규 라우트 도출 불가 · unverifiable · info

이 저장소의 마지막 두 라우트 발견(`COUPON_LIST_PATH`, `PUBLIC_DISCOUNT_PAGE_PATH`)은
모두 **인증된 모든 페이지에 서버 렌더링되는 MY SRT 메뉴**에서 나왔다
(`docs/VERIFICATION.md:863-867`). 같은 기법을 한 번 더 돌려 미등록 라우트가 남았는지
확인했다.

- `tests/fixtures/*.html` 22개 전수에서 `.do`/`.jsp` 참조를 뽑은 결과:
  `/login/login.do`, `/ara/selectListAra10131_n.do`, `/arc/selectListArc02012_n.do`,
  `/arc/selectListArc02011_n.do`, `/apa/selectListApa03020_n.do`, `/main/main.do`,
  `/common/ARA/ARA0301V/view.do`, `/atc/selectListAtc14017_n.do`,
  `/arb/selectListArb02A01_n.do`, `/ara/selectListAra13010_n.do`,
  `/ara/selectListAra12009_n.do` — **전부 이미 등록된 라우트**. 미등록 0건.
- 도출 불가 사유: fixture가 전부 **트리밍**돼 있다. 최대가
  `public_discount_search_page.html` 7,666바이트인데 라이브 원본은 206,268바이트
  (`docs/VERIFICATION.md:977`), `discount_coupons_empty.html`은 6,102바이트인데
  원본은 77,056바이트다(`docs/VERIFICATION.md:869`). 메뉴 마크업은 잘려 나갔다.

**결론:** 이 질문은 **저장소 안 아티팩트만으로는 더 진행 불가**다. 신규 라우트가 없다는
증명이 아니라, 여기서는 더 캘 수 없다는 확정이다. 추가 진전을 원하면 인증 세션으로
아무 페이지나 1회 받아 메뉴 블록의 `pageMove(...)` 전수를 뜨는 것이 유일한 경로다.
(읽기 전용 감사이므로 이번 세션에서는 실행하지 않았다.)

### P2MIS-07 — 승차권 변경(여행변경) 미구현 · info

검색 폼의 `tkDptDt`/`tkDptTm`/`tkTrnNo`/`tkTripChgFlg`가 그 통로이며 라이브러리는
4개 모두 빈 문자열 고정(`payloads.py:641-644`).
`docs/analysis/ref-srtgo_plus.md:415`가 이미 "Change(변경): NOT resolved, still
capture-blocked"로 명시 → **알려진 공백**, 새 발견 아님.

### P2MIS-08 — 코레일톡 상호연동 지정열차 검색(`gs_koYn`) 미구현 · info

`ara1001l.js:150-156` — `application.gs_koYn == "Y"`일 때만
`sTrnNo = lfn_getRsv("trnNo1")`(특정 열차 지정 검색), 페이징 시에는 다시 `""`.
라이브러리는 `payloads.py:637`에서 `"trnNo": ""` 고정.
`gs_koYn`은 서버 렌더링 값이고 진입점은 `getDataBridge(toKrailFlag)` 딥링크다
(`SRWebActivity.java:2004-2022`) → 순수 HTTP 클라이언트로는 진입 자체가 불가.

---

## 6. 요약표

| id | 분류 | 심각도 | 제목 | 1차 대비 |
|---|---|---|---|---|
| P2MIS-01 | missing | medium | `/ard/selectListArd02019_n.do` 승차권 상세조회 전면 부재 | **NEW** |
| P2MIS-02 | missing | medium | `rqSeatAttCd1/2` "015" 고정 — 휠체어 예약 불가 + 검색옵션 조용한 무시 | **NEW** |
| P2MIS-04 | missing | medium | `/ata/selectListAta01135_n.do` 예약대기 옵션 미구현 | 교차확인(S5-01)+보강 |
| P2MIS-03 | doc-drift | low | full-api-analysis의 `psgTpCd` 해독표 오류 (코드가 옳고 문서가 틀림) | **NEW** |
| P2MIS-05 | doc-drift | low | `mblPhone`/`telNo` 출처 부재 주장이 사실 아님 | 보강(S5-02) |
| P2MIS-06 | unverifiable | info | MY SRT 메뉴 재탐색 — fixture 트리밍으로 질문 종결 | **NEW** |
| P2MIS-07 | info | info | 승차권 변경(tk* 필드) 미구현 — 기지의 capture-blocked | 참고 |
| P2MIS-08 | info | info | 코레일톡 상호연동 지정열차 검색(`gs_koYn`) 미구현 | 참고 |

**집계:** 앱 표면 56개 추출 / 라이브러리에 올바른 대응물 43개.
차이 13개 중 **실제 공백은 3개**(P2MIS-01 Ard02019, P2MIS-04 Ata01135,
P2MIS-02 좌석속성 계열)이고 나머지 10개는 §4-(e)의 의도된 제외다.

**안전모델:** `dry_run` 기본값 · `MutationConsent` 카테고리 게이트 ·
`SRT_LIVE_MUTATION_CATEGORIES` kill switch · `assert_mutation_route_category`
(카테고리↔라우트 교차검증) · `assert_no_card_secrets`(바디 기준 카드비밀 차단) ·
`_assert_empty_body_request`(Atc14087 무바디 강제) · `_assert_exact_form_contract`
(좌석페이지/좌석그리드/공공할인검색 폼 고정) 를 전부 읽어 확인했고,
**우회 경로는 발견되지 않았다.** 이번에 제안한 어떤 수정도 이 게이트를 느슨하게
하지 않는다(Ard02019는 READ 등록, 좌석속성은 허용집합 검증 추가).
