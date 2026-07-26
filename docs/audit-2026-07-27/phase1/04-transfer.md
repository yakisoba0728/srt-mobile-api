# SRT 감사 — 04. 환승예약 · 좌석지정

담당 범위: 환승(환승) 2구간 예약, 좌석지정(호차/좌석번호 선택), trnNo 5자리 제로패딩,
환승 구간에서의 좌석지정 가능 여부, 좌석 배치도(좌석배치도) 조회.

## 결론 요약

이 영역은 저장소 안에서 가장 꼼꼼하게 문서화된 부분이었다. `payloads.py`,
`client.py`, `models.py`, `parsers.py`, `docs/VERIFICATION.md` 모두 file:line 단위로
근거 등급(web bundle / native / hydrated / inferred)을 명시하고, 미검증 사실을
"NOT LIVE-VERIFIED"로 명확히 표시하고 있다. 앱 번들(`ara0101v.js`, `ara1001l.js`,
`const.js`, `messages.js`)과 네이티브 오프라인 티켓 파서(`b.java`)를 직접 대조한 결과
필드명·타입·제로패딩·상호배제 규칙 등 핵심 로직은 앱 근거와 정확히 일치했다.

**환승 구간에서 좌석지정이 가능한가 — 두 부분으로 나뉜 답.** (1) 좌석 배치도
**조회**는 다리(leg)별로 아무 제약 없이 가능하다: `get_seat_page`/`get_seat_grid`는
평범한 `TrainSummary`만 받고 `jrnyTpCd`/`chtnDvCd`를 전혀 참조하지 않으므로
(`payloads.py:717-793`), `itinerary.second_leg`를 그대로 넘기면 두 번째 다리의
좌석배치도도 정상적으로 읽힌다. (2) 그러나 **좌석을 지정해서 예약**하는 것은
환승에서 불가능하다 — `reserve_transfer`에는 `designated_seats` 파라미터 자체가
없다. 그 이유는 앱의 `fn_moveRsv`(`ara1001l.js:1427-1493`)가 좌석지정 클릭 시
`jrnyTpCd`/`jrnyCnt`를 전혀 검사하지 않고 `rtnDv`(왕복 여부)만 보며, 클릭된
**한 행(한 다리)**의 슬롯-1 필드만 기록하기 때문이다 — 환승 검색결과 행에서
좌석지정을 눌러도 앱 자체에 `jrnyTpCd="14"`/`jrnyCnt="2"`로 전환해 두 다리를
한 번에 좌석지정하는 코드 경로가 없다(F-01 참조).

발견한 문제는 크게 세 갈래다:
1. **doc-drift (medium)** — `reserve_transfer`가 좌석지정을 지원하지 않는 이유로
   드는 근거 인용이 실제로는 "환승 특이적" 증거가 아니라 편도(직통) 경로에서도
   동일하게 나타나는 범용 증거다. 결론(좌석지정 미지원)은 맞지만 그 결론을
   뒷받침하는 인용이 부정확하다.
2. **risk (low)** — `trnGpCd1`/`trnGpCd2`를 행(row) 데이터가 아니라 상수 `"300"`으로
   하드코딩한다. 앱의 `fn_moveRsv`는 `item.trnGpCd`를 읽어서 쓰는데, 라이브러리는
   그 필드를 무시한다. 실측 fixture 4건 모두 `stlbTrnClsfCd=="17"` ⇒ `trnGpCd=="300"`
   상관관계를 보여 실질적 위험은 낮지만, 코드 상으로는 행 값이 아닌 가정이다.
3. **unverifiable (info)** — `reserve_transfer` 자체가 한 번도 라이브 전송된 적이 없고,
   slot-2 키 23개 중 5개(`stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`,
   `dptStnRunOrdr2`, `arvStnRunOrdr2`)는 번들 어디에도 등장하지 않는 순수 추론이다.
   이것은 라이브러리가 이미 큰 소리로 문서화한 사실이지만, 감사 관점에서
   "확인불가"로 명시적으로 재확인해 둔다.

트랜스퍼-특이적 위험(게이트 우회 등)은 발견하지 못했다. `reserve_transfer`는
`reserve`와 동일한 `MutationConsent`/`dry_run`/NetFunnel 게이트를 그대로 상속하며,
좌석지정과 조합되지 않도록 타입 단계(파라미터 자체가 없음)에서 막혀 있다.

## 앱 기능 전체 목록

| # | 기능 | 엔드포인트 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|------|-----------|---------|-----------------|------|
| 1 | 환승 검색 토글 (`chtnDvCd` 1→2, `jrnyTpCd` 11→14) | `POST /ara/selectListAra10007_n.do` (직통과 동일) | `ara1001l.js:98,159,174-181`; `ara0101v.js:288-311` | `client.py:745` `search_transfer_trains`; `payloads.py` (search_page_payload transfer 인자) | 있음 |
| 2 | 환승 응답 = 다리(leg)당 1행, `trnOrdrNo`로 묶임 | 응답 파싱 | 2026-07-26 라이브 캡처 (`docs/VERIFICATION.md:1524-1546`); 동대구→광주송정 실측 | `parsers.py:2725` `_itinerary_key`, `parsers.py:2789` `pair_transfer_itineraries` | 있음 |
| 3 | 다리 순서(선행/후행) 판정 — 역 연결 기준, 위치 기준 아님 | 파싱 로직 | `ara0101v.js:97`("001:선행,002:후행"); `ara1001l.js:1258-1272`(왕복 2편 시간검증 로직을 유추 근거로 재사용) | `models.py:339` `TransferItinerary.__post_init__`; `parsers.py:2745` `_order_transfer_legs` | 있음 |
| 4 | 모호한/불일치 페어링은 버리지 않고 `unpaired`로 보존 | — | 설계 결정 (앱에 대응 UI 없음, 서버 렌더 화면) | `models.py:461` `UnpairedTransferGroup` | 있음 |
| 5 | 환승 예약 제출 — 1개 요청에 2개 여정 슬롯 | `POST /arc/selectListArc05013_n.do` (개인예약과 동일) | `ara0101v.js:302-303,310-311` (`jrnyCnt="2"` 유일한 write) | `client.py:1316` `reserve_transfer`; `payloads.py:1590` `transfer_reservation_payload` | 있음(미검증, bundle-evidenced) |
| 6 | slot-2 필드 23종 (`jrnySqno2`~`etcSeatAttCd2`) | 위와 동일 | `TRANSFER_SLOT2_FIELD_EVIDENCE` (`payloads.py:152-189`)에 근거등급 명시 | `payloads.py:1500` `_second_journey_slot_fields` | 있음(5개 키는 확인불가 — 아래 F-04) |
| 7 | 환승+왕복 상호배제 (`rtnDv` 항상 `"0"`) | 클라이언트 검증 | `ara0101v.js:296-299`,`:331-334` (알림 "환승은 왕복예약이 불가능") | `payloads.py:1701` (`payload["rtnDv"]="0"`); `reserve_transfer`엔 `round_trip` 파라미터 자체가 없음 | 있음 |
| 8 | 승객수는 다리별이 아니라 유형별로 1회만 전송 | — | `ara0101v.js:117-127`,`:824-836` | `payloads.py:1661-1666` 설명, `personal_reservation_payload`가 1회만 생성 | 있음 |
| 9 | 좌석옵션(`seat_type`,`window_seat`)은 두 다리에 동일하게 적용 | — | `ara0101v.js:769-778` (팝업 콜백이 slot1/slot2에 동일 값 기록) | `_second_journey_slot_fields(special_seat=payload["psrmClCd1"]=="2", window_seat=window_seat)` | 있음 |
| 10 | 환승 예약대기(`jobId=1102`) 미지원 | — | `ara1001l.js:1445-1448` (행 1개 기준 판정, 환승은 행 2개) | `reserve_transfer`에 `standby` 파라미터 없음 | 의도된 제외(정확) |
| 11 | 환승 단체(단체환승) 미지원 | — | `eventTrainInfo.js:12,19`; `commCode.js:1591-1596`(tkKndCd 27) — 앱은 금지하지 않으나 라이브러리가 단체예약 자체를 안 함 | `reserve_transfer`에 `group` 파라미터 없음 | 의도된 제외(정확) |
| 12 | 환승 좌석지정(2번째 다리) 미지원 | — | 아래 **F-01** 참조 — 근거 인용이 부정확 | `reserve_transfer`에 `designated_seats` 파라미터 없음 | 있음(결론 정확, **근거 doc-drift**, F-01) |
| 13 | 환승 취소 시 `jrnyCnt="2"` 필요 (기본값은 `"1"`) | `POST /ard/selectListArd02045_n.do` | srtgo 대조, `docs/VERIFICATION.md:1674-1678` | `client.py:1417` `cancel(..., journey_count=...)`; `payloads.py:1730` `_cancel_journey_count` | 있음(문서화된 캐치, 버그 아님) |
| 14 | 환승 운임조회 2번째 다리 placeholder — 항상 빈 문자열 전송 | `POST /ara/selectListAra13010_n.do` | `ara1001l.js:1209-1216` | `payloads.py:998` `fare_payload` — 의도적으로 미확장 | 의도된 제외(문서화됨) |
| 15 | 좌석선택 페이지 조회 (호차 목록) | `POST /arc/selectListArc02012_n.do` | `ara1001l.js:1495-1520`; 2026-07-26 라이브 확인 | `client.py:951` `get_seat_page`; `parsers.py:360` `parse_seat_selection_page` | 있음 |
| 16 | 좌석 배치도(호차별 좌석 그리드) 조회 | `POST /arc/selectListArc02011_n.do` | 서버 렌더(번들 0-hit); 2026-07-26 라이브 확인, 74셀 | `client.py:985` `get_seat_grid`; `parsers.py:474` `parse_seat_grid_response` | 있음 |
| 17 | **trnNo 5자리 제로패딩** — 좌석 라우트의 필수 게이트 | `lfn_getTrNoData` | `main.html:650-661` (3/4자리→5자리 패딩); 2026-07-26 라이브로 재확인(패딩 없으면 147바이트 알림 셸) | `payloads.py:793` `SEAT_TRAIN_NUMBER_LENGTH`; `_required_digits(...).zfill(5)` (seat_page_payload, seat_grid_payload, personal/transfer 예약폼) | 있음, 정확 |
| 18 | 좌석 셀 식별자 2종 (internal vs printed label) | onclick `choiceSeatNo(내부번호, 출력라벨, Y/N)` | 2026-07-26 라이브 캡처, `tests/fixtures/seat_grid_car_seats.html` | `models.py:924` `SeatGridSeat`; `parsers.py:425` 정규식 | 있음, fixture로 재검증(정규식 일치 확인) |
| 19 | 좌석지정 예약 (`jobId=1103`, `seatNo1_N`/`scarNo1`/`scarGridcnt1`) | `POST /arc/selectListArc05013_n.do` | `ara0101v.js:866-882` (`POP_REQ_SEATSELECT_DPT_ONEWAY`) | `payloads.py:1160` `_seat_designation_fields`; `client.py:1150` `reserve(designated_seats=...)` | 있음, 엔드포인트는 추론(문서화됨) |
| 20 | 좌석지정 시 slot-2 명시적 blank (`scarGridcnt2="0"`, `scarNo2=""`) | 위와 동일 | `ara0101v.js:876-879` | `_seat_designation_fields` 마지막 2줄 | 있음 |
| 21 | 좌석지정 ↔ 예약대기/왕복 상호배제 | — | `ara1001l.js:1435-1449` (jobId 분기 상이); `ara0101v.js:884-892` (왕복 콜백은 좌석 필드 자체를 안 씀) | `personal_reservation_payload`의 `ValueError` 가드 2곳 | 있음 |
| 22 | 좌석옵션 팝업(선택자) 읽기 | `POST /common/ARA/ARA0701P/view.do` | `ara0101v.js:252-270` | `client.py:374` `get_seat_option_selector` | 있음(읽기전용, 예약과 무관) |
| 23 | 환승 구간에서 좌석 배치도 "조회"는 가능 | Arc02012/Arc02011, 다리별 독립 | `get_seat_page`/`get_seat_grid`는 `TrainSummary`만 받고 `jrnyTpCd`/`chtnDvCd`를 전혀 참조하지 않음 (`payloads.py:717-793`) | `itinerary.first_leg`/`itinerary.second_leg`를 각각 넘기면 정상 동작 — 코드 경로상 제한 없음 | 있음(설계상 가능, 문서에 명시적 서술은 약함) |

합계 23개 항목 중 22개는 앱 근거와 정확히 일치하는 것으로 확인했고, 1개(#12)는
결론은 맞으나 인용 근거가 부정확한 doc-drift다. 별도로 low-risk 1건(trnGpCd 하드코딩)과
info 1건(slot-2 5개 키 미검증 재확인)을 findings에 추가했다.

## 문제 항목 상세

### F-01 (doc-drift, medium) — "환승이라서 좌석지정을 막는다"는 인용이 틀렸다

**주장 위치**: `src/srt_mobile_api/payloads.py:1653-1659` (`transfer_reservation_payload`
docstring), 동일 문구가 `docs/VERIFICATION.md:1659`에도 반복됨.

인용된 문구:
> "좌석지정 fills `scarNo1`/`seatNo1_*` and explicitly BLANKS the slot-2
> equivalents — `scarGridcnt2 = 0`, `scarNo2 = ""` (`ara0101v.js:875-879`) —
> and no path in the bundle ever fills them. **That is the transfer-specific
> reason**: 좌석지정 (jobId 1103) IS implemented ... but it designates seats
> on one journey slot, and the bundle shows no path that designates them on a
> transfer's second leg."

`ara0101v.js:866-882`을 직접 읽으면 이 블록은 `POP_REQ_SEATSELECT_DPT_ONEWAY`
(**편도** 좌석지정 콜백, `const.js:9` `"좌석지정(편도) --> 예매내역"`)이다.

```js
} else if (reqCode == POP_REQ_SEATSELECT_DPT_ONEWAY) {
    // 좌석지정(편도) --> 예매내역
    var oSeatData1 = {};
    var scarSeatArr = obj.scarSeatNm.split(",");
    for (...) oSeatData1["seatNo1_" + (i+1)] = scarSeatArr[i];
    oSeatData1["scarGridcnt1"] = scarSeatArr.length;
    oSeatData1["scarGridcnt2"] = 0;
    oSeatData1["scarNo1"] = obj.scarNo;
    oSeatData1["scarNo2"] = "";
    lfn_setRsv(oSeatData1);
    fn_submit();
```

이 콜백은 **직통(non-transfer) 편도 예약**에서도 100% 동일하게 실행된다 — `jrnyTpCd`나
`jrnyCnt`를 전혀 참조하지 않고, 그냥 slot-2를 비운다. 즉 `scarGridcnt2=0`/`scarNo2=""`는
"환승이라서" 비우는 게 아니라 "편도라서(두 번째 여정이 원래 없어서)" 비우는 것이다.
이 코드만으로는 환승 특이적인 근거가 될 수 없다.

진짜 환승 특이적인 근거는 다른 곳에 있다 — `ara1001l.js:1427-1493`
(`fn_moveRsv`)를 추적하면:

```js
fn_moveRsv : function(oGoPageData) {
    var item = this.ds_list[this.fv_nSelRow];   // 클릭된 "한" 행만
    ...
    var oRsvData = {
        "jobId" : sJobId, ...
        "trnNo1": lfn_getTrNoData(item.trnNo), ...   // 접미사 "1"만 기록
    };
    lfn_setRsv(oRsvData);
    if (lfn_getRsv("rtnDv") == "0")            // 분기는 rtnDv만 본다
        this.fn_goPage(oGoPageData, POP_REQ_SEATSELECT_DPT_ONEWAY);
```

`fn_moveRsv`는 **`jrnyTpCd`/`jrnyCnt`를 전혀 검사하지 않고 `rtnDv`(왕복 여부)만
본다.** 환승은 항상 `rtnDv=="0"`이므로(왕복과 상호배제, `ara0101v.js:296-299`),
환승 검색결과 행에서 좌석지정을 클릭해도 **직통 편도와 동일한
`POP_REQ_SEATSELECT_DPT_ONEWAY` 분기로 들어간다.** 그리고 `item`은 클릭된
**한 행(한 다리)** 뿐이므로, `jrnyTpCd="14"`/`jrnyCnt="2"`로 전환되는 코드 경로가
어디에도 없다 — 앱 자체가 환승 두 다리를 한 번에 좌석지정할 방법을 UI 상에 갖고
있지 않다는 뜻이다. 이것이 "환승 특이적"이라 부를 수 있는 진짜 이유다.

**영향**: 라이브러리의 최종 동작(=`reserve_transfer`가 `designated_seats`를
받지 않음)은 옳다. 다만 코드/문서에 박힌 인용이 "환승이라서"가 아니라 "편도라서"의
증거를 오인 배치한 것이라, 나중에 이 근거를 따라가서 "그럼 편도 예약에도 이 문제가
있는 거 아닌가?"를 검증하려는 사람이 헛다리를 짚게 된다. 심각도는 medium — 동작은
맞지만 향후 검증/유지보수 시 근거 추적을 오도한다.

**제안**: `payloads.py:1653-1659`와 `docs/VERIFICATION.md:1659`의 인용을
`ara0101v.js:875-879`(범용, 편도 전체에 적용) + `ara1001l.js:1427-1493`
(`fn_moveRsv`가 `rtnDv`만 보고 `jrnyTpCd`/`jrnyCnt`를 무시하며 한 행만 기록한다는
사실, 진짜 환승 특이적 근거)로 교체.

---

### F-02 (risk, low) — `trnGpCd1`/`trnGpCd2`가 행 데이터가 아닌 상수 `"300"`

**위치**: `src/srt_mobile_api/payloads.py:1444` (`personal_reservation_payload`
내 `"trnGpCd1": "300"`), `src/srt_mobile_api/payloads.py:1580`
(`_second_journey_slot_fields` 내 `"trnGpCd2": "300"`).

앱의 `fn_moveRsv`(`ara1001l.js:1438-1441`)는:
```js
var oRsvData = {
    "stlbTrnClsfCd1" : item.stlbTrnClsfCd, //역무열차종별코드
    "trnGpCd1": item.trnGpCd //열차그룹
};
```
즉 **검색 결과 행의 실제 `trnGpCd` 값을 그대로 전송**한다. 반면 라이브러리는
`TrainSummary.train_group_code`(파싱된 행 필드, `models.py:273`, `parsers.py:2465`)를
전혀 참조하지 않고 상수 `"300"`을 항상 쓴다.

실측 fixture 4건(`search_success.json`, `search_personal_shape_success.json`,
`search_group_shape_success.json`, `group_search_success.json`)을 확인한 결과
전부 `stlbTrnClsfCd=="17"` 행은 예외 없이 `trnGpCd=="300"`이었다 — 즉 SRT-only
가드(`service_class_code == "17"`)를 통과한 행이라면 실질적으로 하드코딩 값과
같다. 그래서 **현재까지 관측된 데이터로는 실해는 없다.**

다만 이는 "관측된 적 없음"이 아니라 "관측된 사례가 전부 일치했음"이라는
경험적 근거일 뿐 코드가 행 값을 검증/사용하는 것은 아니다. `stlbTrnClsfCd="17"`인
행이 `trnGpCd`를 다른 값으로 보내는 경우가 존재한다면(예: 전체(`109`) 검색에서
혼합 응답의 특정 서버 버전) 두 슬롯 모두 조용히 틀린 값을 보내게 된다.
전송값 자체가 서버에서 검증 실패로 이어질지, 아니면 무시되고 통과할지는 미확인.

**제안**: 가능하면 `train.train_group_code`가 존재할 때 그 값을 쓰고 없을 때만
`"300"`으로 폴백하도록 바꾸거나, 최소한 주석에 "행 필드를 무시하고 상수를 쓰는
이유는 SRT-only 가드 하에서 관측된 모든 fixture가 일치했기 때문"이라고
명시적으로 근거를 남길 것.

---

### F-03 (unverifiable, info) — `reserve_transfer`는 라이브 미검증, slot-2 키 5개는 완전 추론

**위치**: `src/srt_mobile_api/payloads.py:152-189`
(`TRANSFER_SLOT2_FIELD_EVIDENCE`), `src/srt_mobile_api/client.py:1379-1394`
(`reserve_transfer` docstring).

라이브러리 스스로 이미 "NOT LIVE-VERIFIED"로 명시하고 있으므로 이것은 새로 발견한
결함이 아니라 감사 관점에서 재확인·기록하는 항목이다. 실제로 대조해보니:

- `stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`, `dptStnRunOrdr2`,
  `arvStnRunOrdr2` — 5개 키 이름은 오프라인 번들(웹/네이티브) 어디에도 등장하지
  않는다. slot-1 키(`stlbTrnClsfCd1` 등, `ara1001l.js:1439,1467-1470`)에서
  접미사만 바꾼 순수 추론이다. 직접 실행 확인:
  `grep -rn "stlbTrnClsfCd2\|dptStnConsOrdr2\|arvStnConsOrdr2\|dptStnRunOrdr2\|
  arvStnRunOrdr2" analysis/` (21,673개 파일 전체, jadx+apktool+smali+res 포함)
  → **0건**, exit code 1. 다섯 키 모두 번들 전체에서 실제로 0-hit임을 재확인했다.
- `reserveType="11"`이 환승에도 그대로 쓰이는지(혹은 `jrnyTpCd`를 따라가
  `"14"`가 되어야 하는지)도 미확인 — `reserveType` 자체가 앱 번들에 0-hit이고
  srtgo 전용 필드.
- 서버 렌더 `#rsvForm`(`ara1001l.js:1550` `$("#rsvForm").serialize()`)은 어떤
  분석 산출물에도 존재하지 않는다 — WebView 셸 특성상 당연한 결과이며, 이
  프로젝트의 "번들에 없다≠프로토콜에 없다" 원칙에 완전히 부합한다.

**결론**: 라이브 검증 전에는 `reserve_transfer`를 실제 서버에 전송하는 순간
5개 필드명이 틀렸거나, `reserveType`이 거부 사유가 될 가능성이 있다. 이미
`client.py`/`docs/VERIFICATION.md`에 운영자용 라이브 검증 절차가 안내되어 있으므로
설계 결함이 아니라 "검증 대기" 상태로 분류한다.

## 확인했으나 문제 없음으로 판단한 항목 (참고)

- **`rqSeatAttCd2`/`dirSeatAttCd2` 하드코딩(`"015"`/`"009"`)**: slot-1도 동일하게
  하드코딩되어 있어(`_reservation_passenger_fields`, `payloads.py:1109-1111`)
  환승에 국한된 회귀가 아니다. 휠체어석(`021`/`028`, `ara0101v.js:611-628`)을
  요청하는 경로가 애초에 라이브러리에 없으므로 이 부분은 환승 범위 밖의
  별도 이슈로 보고 여기서는 findings에 넣지 않았다.
- **`cancel()` 기본값 `journey_count="1"`이 환승(2)에는 틀림**: 이미
  `client.py:1396-1402`, `docs/VERIFICATION.md:1674-1678`에 크게 경고되어 있고,
  파라미터 자체가 존재해 호출자가 명시적으로 `"2"`를 넘기면 해결된다. 게이트를
  우회하는 결함이 아니라 문서화된 기본값 함정으로 판단해 findings에서 제외했다.
- **좌석 그리드 정규식(`_SEAT_CHOICE_CALL_RE`/`_SEAT_CLASS_RE`)**:
  `tests/fixtures/seat_grid_car_seats.html`(2026-07-26 실측 재현)의 실제 마크업
  (`class="seatChoice015Y" onclick="choiceSeatNo('2', '1B', 'Y');"`)과 대조한 결과
  정확히 일치했다.
- **trnNo 5자리 제로패딩(`lfn_getTrNoData`)**: `main.html:650-661` 원본과
  `payloads.py`의 `_required_digits(...).zfill(5)` 적용처(좌석페이지, 좌석그리드,
  개인/환승 예약폼) 전부 대조 완료. 3/4자리 입력을 5자리로 패딩하는 로직 일치.
- **환승 페어링 로직**(`trnOrdrNo` 그룹핑, 역 연결 기준 순서 판정, 모호한 경우
  `unpaired` 보존, 전무 페어링 시 `SrtProtocolError`)은 `docs/VERIFICATION.md`의
  2026-07-26 실측 캡처와 코드가 정확히 일치했다.
