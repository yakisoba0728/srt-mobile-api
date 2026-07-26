# SRT 예약(일반·왕복) 감사 — Phase 1 / 03-reserve

대상 저장소: `/Users/yakisoba/Documents/GitHub/srt-mobile-api`
담당 범위: 일반예약(jobId 1101), 예약대기(1102), 시트맵예약(1103), 왕복예약(rtnDv),
승객 유형 구성(psgTpCd 1~6, 유아 fold), 예약 요청 필드/타입, `consent.py` 뮤테이션 게이트.
범위 밖(다른 슬라이스가 담당할 것으로 판단하여 표에서 제외): 환승예약
(`transfer_reservation_payload`/`TransferItinerary`, jrnyTpCd=14 계열), 취소/환불/결제/쿠폰
(`unpaid_reservation_cancel_payload`, `card_payment_payload`, `refund_payload`,
`coupon_registration_payload`), 단체예약(그룹, 사용자가 명시적으로 제외).

## 방법

- 라이브러리: `src/srt_mobile_api/payloads.py`(예약 관련 함수 전체), `models.py`
  (`PassengerCounts`, `TrainSummary`, `SeatDesignation`, `SrtReservationHold` 등),
  `consent.py`, `client.py`의 `reserve`/`_submit_reservation`.
- 앱 근거: `analysis/apktool/assets/offline/js/ara/ara0101v.js`,
  `analysis/apktool/assets/offline/js/ara/ara1001l.js`,
  `analysis/apktool/assets/offline/js/commCode.js`,
  `analysis/apktool/assets/offline/js/stationInfo.js`,
  `analysis/apktool/assets/offline/sub/main.html`.
- 교차검증 문서: `docs/analysis/ref-srtgo_plus.md`(§4, srtgo_plus의 `_reserve` 전체
  POST 바디 표), `docs/analysis/cross-validation-2026-07-21.md`, `docs/VERIFICATION.md`.
- 테스트 픽스처: `tests/fixtures/search_success.json`,
  `search_personal_shape_success.json`, `search_group_shape_success.json`.

라이브러리 소스 자체가 이미 대부분의 필드에 `file:line` 근거를 주석으로 달아두고
"live-verified / bundle-evidenced / inferred" 3단계로 신뢰도를 명시하는 이례적으로
자기검증적인 코드베이스다. 본 감사는 그 주석의 인용을 실제 디컴파일 파일에서
재확인하고(대부분 정확했음), 주석이 다루지 않은 두 개의 경계 조건(카빈-좌석 불일치,
왕복의 역-기반 제외 규칙)을 새로 찾아냈다.

## 1. 추출한 앱 기능 전체 목록

| # | 기능 | 엔드포인트/필드 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|---|---|---|---|---|
| 1 | jobId 1101 개인예약 | `POST /arc/selectListArc05013_n.do` | `ara0101v.js:90`(주석), `ara1001l.js:1445` | `RESERVE_PERSONAL_JOBID`, `personal_reservation_payload` | 있음 |
| 2 | jobId 1102 예약대기 | 동일 endpoint | `ara1001l.js:1447-1448` (`item.gnrmRsvPsbImg == S_IMG_WAIT_S`) | `RESERVE_STANDBY_JOBID`, `standby=True` | 있음 |
| 3 | jobId 1103 시트맵예약 | 동일 endpoint(추론) | `ara1001l.js:1435-1436`, 필드는 `ara0101v.js:866-882` | `RESERVE_SEATMAP_JOBID`, `designated_seats=` | 있음 (엔드포인트는 앱 스스로도 inferred로 명시) |
| 4 | 예약 폼 정적 필드 15종(jrnyCnt,jrnyTpCd,jrnySqno1,stndFlg,trnGpCd1,grpDv,rtnDv,stlbTrnClsfCd1,dptRsStnCd1/Nm1,arvRsStnCd1/Nm1,dptDt1,dptTm1,arvDt1,arvTm1,trnNo1,runDt1,dptStnConsOrdr1,arvStnConsOrdr1,dptStnRunOrdr1,arvStnRunOrdr1,netfunnelKey) | `fn_validChk` 필수목록 | `ara1001l.js:1649-1701`, 값은 `ara1001l.js:1453-1468` | `personal_reservation_payload` | 있음 — 전 필드 1:1 대응 확인 |
| 5 | runDt1(운행일자) ≠ dptDt1(출발일자) 구분 | 동일 | `ara1001l.js:1460`,`:1462` (같은 블록 안 서로 다른 두 row 필드) | `run_date` fallback 로직 | 있음 |
| 6 | arvDt1 빈값 허용 | 동일 | seed `ara0101v.js` `arvDt1=""` , 서버가 트림된 바디 수용(2026-07-25 라이브) | `arrival_date` "" fallback | 있음 |
| 7 | trnNo1 5자리 zero-pad | 동일 | `ara1001l.js:1461` `lfn_getTrNoData(item.trnNo)`, `main.html:642-661` | `.zfill(5)` | 있음 |
| 8 | 왕복예약 rtnDv=1, 2회 순차 POST(가는→오는, 검색 재실행) | 동일 endpoint, 2회 호출 | `ara1001l.js:1476-1492`, `:1580-1596` | `round_trip=True` + `reserve()`/`TrainSearchQuery.for_return_leg` 문서화된 2-콜 워크플로 | 있음 |
| 9 | 왕복시 jrnyCnt는 "1" 유지(=2는 환승 전용) | 동일 | `jrnyCnt="2"` 는 전 번들 유일하게 `ara0101v.js:302-303` 환승 토글에서만 write | `jrnyCnt: "1"` 고정 | 있음 |
| 10 | 왕복 x 환승 상호배제 | 클라 alert, 양방향 | `ara0101v.js:296-299`, `:331-334` | `transfer_reservation_payload`가 `round_trip` 인자 자체를 안 받음(구조적 배제) | 있음 |
| 11 | 왕복 x 단체 상호배제 | 클라 alert | `ara0101v.js:348-352` | 해당없음 — `personal_reservation_payload`는 `grpDv` 항상 "0" | 있음(단체 자체 미구현이므로 자동 충족) |
| 12 | **왕복 x 코레일역 상호배제 (`lfn_isKorailStn`)** | 클라 alert, `chk_rtrp` 클릭시 | `ara0101v.js:337-341` | 없음 | **없음 — Finding S3-01** |
| 13 | **왕복 x 국회의원 후급(mbCrdNo prefix "11") 배제** | 클라 alert | `ara0101v.js:317-326` | 없음(`SrtSession.membership_number`로 값은 노출되나 `round_trip` 경로에서 검사 안함) | **부분 — Finding S3-02** |
| 14 | psgTpCd 1~5 (어른/장애1-3/장애4-6/경로/어린이) | `commCode.js:55-88` | 동일 | `PASSENGER_TYPE_CODES` | 있음 |
| 15 | psgTpCd 6 (청소년, 공공할인04 전용, 번들 0-hit·라이브 확인) | 라이브 캡처 2026-07-26 | `docs/VERIFICATION.md:1173-1204` | `PassengerCounts.youth`, `PASSENGER_TYPE_CODES` | 있음(검색 경로만 라이브검증, 예약 경로는 미검증으로 스스로 명시) |
| 16 | 유아(infantCnt) fold: 어린이 슬롯 카운트에 합산 + `infantCnt` 별도 선언 | `goRevFn`(라이브, 번들 0-hit) | 동일 | `PassengerCounts.child_slot_count`, `_infant_count_field` | 있음 |
| 17 | psgGridcnt = 채워진 승객유형 슬롯 개수(0명 제외 compaction) | `ara0101v.js:824-836` | 동일 | `_compact_passenger_slots`/`_distinct_passenger_type_count` | 있음 |
| 18 | 예약 폼 승객필드는 5-슬롯 패딩이 아니라 compaction만(패딩은 검색폼 전용) | `srt.py:179-204` 대조(ref-srtgo_plus.md:202-216) | — | `_reservation_passenger_fields` | 있음 |
| 19 | 좌석유형 결정(GENERAL_ONLY/SPECIAL_ONLY/GENERAL_FIRST/SPECIAL_FIRST) | `ara1001l.js:1430-1432` + srtgo `is_special_seat` | `ref-srtgo_plus.md:222-224` | `_resolve_special_seat` | 있음 |
| 20 | 창측/복도측 선호(locSeatAttCd1) | srtgo `WINDOW_SEAT` (`ref-srtgo_plus.md:209`) | — | `_WINDOW_SEAT_CODES` | 있음 |
| 21 | 예약대기 자격 확인(행의 gnrmRsvPsbImg 검사) | `ara1001l.js:1447` | 동일 | `_refuse_ineligible_standby`, `_STANDBY_ROW_IMAGES` | 있음(입력 경로 `TrainSummary.raw` 실제로 서버 원본 row 보존 확인, `parsers.py:2579`) |
| 22 | 예약대기시 특실 불가(psrmClCd1 강제 "1") | `ara1001l.js:1431` (S_IMG_WAIT_S는 sPsrmClCd=1 분기에만 존재, 특실 분기는 없음) | 동일 | `standby=True` → `special_seat=False` 강제 | 있음 |
| 23 | 예약대기시 reserveType 생략 | srtgo만 근거(`srt.py:990-991`), 번들 0-hit | — | `if not standby: payload["reserveType"]="11"` | 있음(출처 한정적이라고 스스로 명시) |
| 24 | 좌석지정 필드군(seatNo1_1..N=printed label, scarGridcnt1/2, scarNo1/2) | `ara0101v.js:866-882` | 동일 | `_seat_designation_fields` | 있음 |
| 25 | 좌석지정 매수=인원수 일치 강제 | `choiceSeatCount=totPrnb`(`ara1001l.js:1511`) | 동일 | `SeatDesignation`/`_seat_designation_fields`의 개수 검증 | 있음 |
| 26 | 좌석지정 x 예약대기 상호배제 | 서로 다른 jobId 분기(`ara1001l.js:1435-1449`) | 동일 | `ValueError` (raise) | 있음 |
| 27 | 좌석지정 x 왕복 상호배제 | 왕복 좌석콜백이 좌석필드를 전혀 안 씀(`ara0101v.js:884-892`) | 동일 | `ValueError` (raise) | 있음 |
| 28 | **좌석지정시 psrmClCd1(캐빈)과 실제 좌석그리드 캐빈 불일치 가능** | `ara1001l.js:1430-1436`(같은 탭이 캐빈과 jobId 라우팅을 동시결정) | — | `_resolve_special_seat`/`get_seat_grid(cabin_class=)` 상호 무관 | **위험 — Finding S3-03** |
| 29 | SRT 전용 가드(stlbTrnClsfCd=="17") | srtgo `train_name != "SRT"` 거부 대응 | `ref-srtgo_plus.md:184` | `_SRT_TRAIN_CLASS_CODE` 체크(개인예약 라우트) | 있음 |
| 30 | trnGpCd1 하드코딩 "300" | `item.trnGpCd`(row 자체 필드), 실측 fixture 전부 stlbTrnClsfCd=="17"일때 trnGpCd=="300" | `search_success.json`,`search_personal_shape_success.json` | `"trnGpCd1": "300"` 하드코딩(`train.train_group_code` 미사용) | 있음(결과적으로 일치, `TrainSummary.train_group_code`를 안 쓰는 점은 info) |
| 31 | trnGpCd(접미없음) "109" 부가 필드 | srtgo 잔재, 앱 자체 예약폼에는 없음(이미 `cross-validation-2026-07-21.md:138`에 "서버가 무시하는 srtgo 잔재"로 기결) | — | 동일하게 포함 | 있음(기결 사항, 재확인만) |
| 32 | mblPhone 필드 생략 | srtgo `None`(드롭), 번들 0-hit | — | 미전송 | 있음 |
| 33 | MutationConsent 게이트("reserve" 카테고리), dry_run 기본 True | 앱 자체엔 대응 개념 없음(설계) | — | `require_mutation_consent(consent,"reserve")`, `_submit_reservation` | 있음 — 우회 경로 없음 확인(`reserve`/`reserve_transfer` 모두 동일 `_submit_reservation` 경유) |
| 34 | 예약 문자열-숫자 wire 타입 | `$("#rsvForm").serialize()`가 DOM 값을 문자열화(`ara1001l.js:1550`) | 동일 | 전 필드 `str(...)` 로 전송 | 있음(타입 불일치 없음, 아래 "확인한 항목" 참조) |

**요약**: 표 34행 중 31행이 앱 동작과 일치(있음), 1행은 결과적으로 일치하지만
근거 필드를 안 쓰는 설계상 특이점(info, finding에 넣지 않음), 2행이 실제 결함/위험으로
분류되어 findings에 포함(S3-01, S3-03), 1행이 부분 구현(S3-02).

`app_functions_extracted = 34`, `implemented_count = 31` (있음으로 표시된 행;
#30은 "있음"으로 카운트, #12/#28은 결함행, #13은 부분행이므로 제외).

## 2. 확인했으나 문제없음으로 닫은 항목 (참고)

- **문자열/숫자 타입 불일치** — 이 저장소에서 반복된 결함 유형이라 별도로 확인함.
  앱은 JS 내부적으로 `sPsrmClCd=1`, `scarGridcnt1=scarSeatArr.length`,
  `scarNo1=obj.scarNo` 등 숫자를 쓰지만(`ara1001l.js:1431`, `ara0101v.js:876-878`),
  실제 전송은 `$("#rsvForm").serialize()`(`ara1001l.js:1550`)이므로 DOM 값이 전부
  문자열로 직렬화된다. 라이브러리는 애초에 전 필드를 `str(...)`로 보내므로 wire 상
  차이 없음. 문제없음으로 닫음.
- **`_refuse_ineligible_standby`의 입력 데이터 존재 여부** — `TrainSummary.raw`가
  검색 응답 row 전체를 보존하는지(`parsers.py:2579` `raw=row`) 확인했고,
  `gnrmRsvPsbImg`가 클라이언트 파생값이 아니라 서버가 실제로 내려주는 필드임을
  `ara1001l.js:1000`(`item.gnrmRsvPsbImg`)과 테스트 픽스처
  (`search_personal_shape_success.json`, `search_group_shape_success.json`)로
  확인함. 가드가 실제로 작동할 데이터가 있음 — 문제없음.
- **`_STANDBY_ROW_IMAGES`가 선택 전/후(`_S` 유무) 두 스펠링을 모두 인정하는 설계** —
  `fn_moveRsv`는 `S_IMG_WAIT_S`(선택된 스펠링)만 검사하지만(`ara1001l.js:1447`),
  이는 앱이 탭 시점에 `S_IMG_WAIT`→`S_IMG_WAIT_S`로 다시 쓰기 때문이고
  (`ara1001l.js:1045`,`:1058`), 라이브러리는 UI 탭을 거치지 않는 원시 검색 응답을
  받으므로 두 스펠링 모두 받아들이는 것이 맞다. 문제없음.
- **`personal_reservation_payload`의 `standby`+`round_trip` 동시 사용 허용** —
  앱 코드상 jobId 1101/1102 결정 로직(`ara1001l.js:1437-1449`)은 rtnDv 분기
  이전에 공통으로 실행되므로 앱도 이 조합을 막지 않는다. 라이브러리도 막지 않음 —
  일치.

## 3. Findings 상세

### S3-01 (missing, medium) — 왕복예약이 앱의 "코레일역 배제" 게이트를 재현하지 않음

앱은 왕복 체크박스(`chk_rtrp`)를 누르는 순간 출발역/도착역 중 하나라도
`stationList`에서 `gubun=="SRT"`가 아니면(=코레일 전용역이면) 즉시 되돌리고
경고를 띄운다:

```js
// ara0101v.js:328-341
var sDptStn = lfn_getRsv("dptRsStnCd1");
var sArvStn = lfn_getRsv("arvRsStnCd1");
...
if (lfn_isKorailStn(sDptStn) || lfn_isKorailStn(sArvStn)) {
    callbackChkRtrp();
    srtAlertBoxDivShow("알림", "코레일 열차는 왕복 열차 예약을 이용하실 수 없습니다.", null, null);
    return;
}
```

`lfn_isKorailStn`(`analysis/apktool/assets/offline/sub/main.html:568-578`)은
`stationList`(`analysis/apktool/assets/offline/js/stationInfo.js:28-...`)에서
`gubun=="SRT"`이고 `stn_cd`가 일치하는 항목이 있을 때만 `false`(코레일 아님)를
반환한다. 이 정적 목록에는 **17개 역**(수서·동탄·지제·천안아산·오송·대전·김천구미·
동대구·신경주·울산·부산·공주·익산·정읍·광주송정·나주·목포)만 `SRT`로 표시되어
있고, 나머지(밀양·구포·경산·서대구·순천·남원·곡성·구례구 등)는 전부
`gubun:"korail"`로 표시되어 있다(`stationInfo.js:61,68,81,83,106,159,213` 등).

`personal_reservation_payload`는 열차 자체의 `service_class_code=="17"`
(SRT 운영 열차)만 검사할 뿐(`payloads.py:1342-1345`), **출발/도착 역이
`lfn_isKorailStn` 화이트리스트에 속하는지는 전혀 검사하지 않는다.** `round_trip=True`
경로에도 이 검사가 없다.

**단, 이 오프라인 번들의 `stationList`가 SRT의 현재(2026-07) 실제 운행 역
전체를 반영하는지는 이 저장소의 정적 분석만으로는 확정할 수 없다** — 번들은
특정 시점의 앱 버전 스냅샷이고, SRT가 이후 노선을 확장했다면(예: 경부선/전라선
추가 정차역) 라이브 앱의 `stationList`가 이 번들과 다를 수 있다. 확실한 것은
"이런 게이트가 앱에 존재하고 라이브러리에는 없다"는 사실이고, 불확실한 것은
"어떤 구체적인 역 코드 조합이 실제로 이 차이를 유발하는가"이다. `stlbTrnClsfCd=="17"`
필터를 통과하는 모든 실제 SRT 열차의 출발/도착역이 이 17개 역 안에만 있다면
이 gap은 실질적으로 트리거되지 않는다.

- **app_evidence**: `analysis/apktool/assets/offline/js/ara/ara0101v.js:328-341`
  (`chk_rtrp` 핸들러, `lfn_isKorailStn` 호출); 함수 정의
  `analysis/apktool/assets/offline/sub/main.html:568-578`; 데이터
  `analysis/apktool/assets/offline/js/stationInfo.js:28-44`(SRT 17개 역 전체 나열)
- **library_evidence**: `src/srt_mobile_api/payloads.py:1218-1345`
  (`personal_reservation_payload`, SRT-only 가드만 있고 station 화이트리스트 검사 없음)
- **suggested_fix**: 라이브 세션으로 현재 앱이 실제로 내려주는 `stationList`(또는
  동등한 라이브 station 마스터)를 다시 캡처해 SRT-gubun 역 코드 집합을 확정하고,
  `round_trip=True` 시 출발/도착역이 그 집합 밖이면 `ValueError`로 거부하거나,
  집합이 이미 `stlbTrnClsfCd=="17"` 필터와 겹친다는 것이 확인되면 이 항목을
  "문제없음"으로 재분류.

### S3-02 (partial, low) — 왕복예약이 국회의원 후급(mbCrdNo prefix "11") 배제를 재현하지 않음

```js
// ara0101v.js:317-326
case "chk_rtrp" :
    if(mbCrdNo == "" || mbCrdNo == null){
    } else if(mbCrdNo.substr(0,2) == "11"){
        callbackChkRtrp();
        var msg = "왕복승차권은 국회의원 후급 적용으로<br/>이용하실 수 없습니다...";
        srtAlertBoxDivShow("알림", msg, null);
        return;
    }
```

`SrtSession.membership_number`(`models.py:38-61`)가 이미 `MB_CRD_NO`를
노출하고, 그 필드가 `mbCrdNo`이며 `"11"` prefix가 국회의원 후급을 뜻한다는
사실 자체는 `models.py:51`의 주석이 정확히 인용하고 있다(`ara0101v.js:319,321`
근거). 그러나 이 규칙이 실제로 `reserve(round_trip=True, ...)` 호출 경로에
연결되어 있지는 않다 — 어떤 회원번호를 쓰든 왕복예약 페이로드가 그대로 만들어진다.

이미 라이브러리가 근거를 정확히 알고 문서화까지 해둔 상태에서 규칙만 적용하지
않은 것이므로 "결함"이 아니라 "부분 구현"으로 분류한다. 실제 영향은 국회의원
회원 계정으로 왕복예약을 시도할 때만 발생하므로 낮은 심각도.

- **app_evidence**: `analysis/apktool/assets/offline/js/ara/ara0101v.js:317-326`
- **library_evidence**: `src/srt_mobile_api/models.py:38-61`(`SrtSession.membership_number`,
  규칙 근거는 알고 있음); `src/srt_mobile_api/payloads.py:1218-1497`
  (`personal_reservation_payload`에 mbCrdNo/round_trip 상호검증 없음)
- **suggested_fix**: `reserve(round_trip=True, ...)`가 `session.membership_number`를
  받아 prefix `"11"`이면 (앱과 동일하게) 거부하거나, 최소한 문서에 "호출자가
  직접 확인해야 함"이라고 명시.

### S3-03 (risk, medium) — 좌석지정(시트맵예약) 시 캐빈클래스(psrmClCd1)와 실제 좌석그리드 캐빈이 서로 연결되어 있지 않음

앱에서는 "어느 캐빈(일반실/특실) 셀을 탭했는가"가 `psrmClCd1`과 "좌석선택
페이지로 이동해 시트맵예약(jobId 1103)을 시작하는가"를 **동시에** 결정하는
하나의 상태 전이다:

```js
// ara1001l.js:1430-1436 (fn_moveRsv)
var sPsrmClCd = "";
if (item.gnrmRsvPsbImg == this.S_IMG_PSBL_S || ... || item.gnrmRsvPsbImg == this.S_IMG_WAIT_S) sPsrmClCd = 1;
else if (item.sprmRsvPsbImg == this.S_IMG_PSBL_S || ...) sPsrmClCd = 2;

var sJobId = "";
if (oGoPageData.id == "ARC0201C") {
    sJobId = "1103"; //시트맵예약
} ...
```

즉 사용자가 특실 셀을 탭해 좌석선택(ARC0201C, jobId 1103)으로 진입하면
`sPsrmClCd`는 자동으로 2가 되고, 그 좌석그리드는 특실 차량만 보여준다. 앱에는
"특실 그리드에서 좌석을 고르고 일반실로 예약을 넣는" 경로 자체가 없다.

라이브러리에서는 이 두 값이 완전히 독립된 파라미터다:

- `get_seat_grid(train, car_number, cabin_class="1", ...)`
  (`client.py:985-994`) — 기본값 `"1"`(일반실).
- `reserve(train, ..., seat_type=SeatType.GENERAL_FIRST, designated_seats=...)`
  — `personal_reservation_payload` 내부에서 `_resolve_special_seat`
  (`payloads.py:1083-1093`)가 `seat_type`과 열차의 실시간 잔여석 문자열만으로
  `psrmClCd1`을 계산하며, `designated_seats`가 어느 캐빈에서 왔는지는 전혀
  참조하지 않는다.
- `SeatGrid`/`SeatCarOption`/`SeatGridSeat`/`SeatDesignation`
  (`models.py:900-1022`) 어디에도 캐빈 코드(`psrmClCd`)를 보존하는 필드가 없어서,
  호출자가 나중에 두 값이 일치하는지 스스로 검증할 방법도 없다.

**구체적 실패 시나리오**: 호출자가 `get_seat_page`/`get_seat_grid`를
`cabin_class="2"`(특실)로 호출해 특실 좌석을 고르고 `SeatDesignation`을
만든 뒤, `reserve(train, designated_seats=..., consent=...)`를 `seat_type`
기본값(`GENERAL_FIRST`)인 채로 호출하면 — 해당 열차의 일반실이 예약가능한
한 `_resolve_special_seat`는 `False`를 반환해 `psrmClCd1="1"`(일반실)이
전송되는데, 여기 붙는 `scarNo1`/`seatNo1_*`는 특실 차량·좌석이다. 앱은 구조상
이런 조합을 만들 수 없으므로 서버가 이 조합에 어떻게 반응하는지(거부/오배정)
에 대한 근거가 전혀 없다 — 실서버에서 실패하거나 잘못된 결과를 낼 위험.

- **app_evidence**: `analysis/apktool/assets/offline/js/ara/ara1001l.js:1430-1436`
  (`fn_moveRsv`, 캐빈 탭과 jobId 라우팅이 하나의 상태에서 동시 결정됨)
- **library_evidence**: `src/srt_mobile_api/payloads.py:1083-1093`
  (`_resolve_special_seat`, `designated_seats`/캐빈 미참조),
  `:1412-1419`(`personal_reservation_payload`에서 `special_seat` 계산 후
  `seat_fields`와 독립적으로 합쳐짐), `src/srt_mobile_api/client.py:985-994`
  (`get_seat_grid` 기본 `cabin_class="1"`), `src/srt_mobile_api/models.py:900-1022`
  (`SeatGrid`/`SeatDesignation`에 캐빈 필드 없음)
- **suggested_fix**: `SeatGrid`(또는 `SeatCarOption`)에 조회 시 사용한
  `cabin_class`를 보존하고, `SeatDesignation`에 그 값을 실어 `reserve()`가
  `designated_seats`가 있을 때는 `seat_type` 대신(또는 그것과 일치하는지 검증한
  뒤) `designated_seats`의 캐빈으로 `psrmClCd1`을 강제하도록 수정.

## 4. 범위 밖으로 판단해 표에서 제외한 것

- **환승예약**(`transfer_reservation_payload`, `TransferItinerary`,
  `_second_journey_slot_fields`, `TRANSFER_SLOT2_FIELD_EVIDENCE`) — jrnyTpCd=14
  계열은 "일반·왕복"과 다른 축(여정 슬롯 2개)이며 별도 슬라이스로 판단해 상세
  검증에서 제외함. 코드 자체는 슬롯2 필드명 5개가 "inferred" 등급임을 스스로
  명시하는 등 이미 신뢰도 라벨링이 되어 있음을 확인만 했음.
- **취소/환불/결제/쿠폰**(`unpaid_reservation_cancel_payload`, `card_payment_payload`,
  `refund_payload`, `coupon_registration_payload`) — 별도 담당 영역으로 판단해
  제외.
- **단체(그룹) 예약** — 사용자가 명시적으로 제외한 범위. `group_search_ajax_payload`
  (검색)만 남아 있고 그룹 예약 자체는 제거되어 있음(`docs/IMPLEMENTATION_PROGRESS.md`
  "단체 (group) booking: removed") — 결함 아님, 의도된 설계.
