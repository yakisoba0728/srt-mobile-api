# SRT 전수 감사 — 최종 종합

**대상:** `srt-mobile-api` (라이브러리 v2.0.41 대응)
**절차:** 1차 Sonnet 8명(영역 분할) → 2차 Opus 4명(전체 렌즈 재확인) → 3차 Opus 4명(반증 시도 검증)
**본 문서:** 3차 검증을 통과한 항목만 종합. 3차에서 기각된 8건은 부록 A에 사유와 함께 남겨 재발을 막는다.

> **이 앱의 성격.** SRT 앱은 WebView 껍데기다. 오프라인 번들은 JS 28개뿐이고 화면·API 호출
> 대부분이 서버 렌더링 페이지에 있다. 따라서 이 감사에서 "번들 0-hit"은 **부재의 증거가 아니다**.
> 근거는 (a) `analysis/apktool/assets/offline/` 번들, (b) `analysis/jadx|apktool` 디컴파일,
> (c) `docs/analysis/`의 실서버 페이지 인라인 JS 복원 기록, (d) `tests/fixtures/` 실응답 캡처 39건,
> (e) 참조구현 `srtgo`/`srtgo_plus` 소스를 함께 봐야 성립한다. 아래 모든 항목은 이 원칙으로 판정했다.

---

## 1. 한눈에

### 1.1 기능 커버리지

1차 8개 영역이 각자 추출·대조한 수치는 다음과 같다. **열을 단순 합산하면 안 된다** — 슬라이스
경계가 겹쳐(예: 승객유형 compaction은 검색·예약·운임 세 슬라이스에 모두 등장) 이중계상된다.
2차 교차검증 렌즈가 중복을 걷어낸 유효 표면은 68개이며 그중 64개가 정확히 구현되어 있다.

| 영역 | 추출 | 구현 | 비율 | 1차 보고서 |
|---|---:|---:|---:|---|
| 01 인증·세션 (로그인/기기키/쿠키/자동로그인/로그아웃/회원정보) | 22 | 16 | 89%¹ | `phase1/01-auth.md` |
| 02 열차조회·역·운임 | 464 | 438 | 94% | `phase1/02-search.md` |
| 03 예약 (일반·왕복) | 34 | 31 | 91% | `phase1/03-reserve.md` |
| 04 환승예약·좌석지정 | 23 | 22 | 96% | `phase1/04-transfer.md` |
| 05 예약대기 | 19 | 16 | 84% | `phase1/05-standby.md` |
| 06 결제 | 19 | 13 | 68%² | `phase1/06-pay.md` |
| 07 환불·취소 | 5 | 5 | 100% | `phase1/07-refund.md` |
| 08 할인·복지·쿠폰·NetFunnel·브릿지·헤더·에러코드·안전계층 | 47 | 38 | 81%³ | `phase1/08-misc.md` |
| **1차 합계(중복 포함)** | **633** | **579** | **91.5%** | |
| **2차 교차검증(중복 제거)** | **68** | **64** | **94%** | `phase2/crosscheck.md` |

¹ 네이티브 전용 4건(FIDO/SNS로그인/푸시등록/TransKey)은 HTTP 클라이언트 구현 대상이 아니므로
비교대상 18건 기준. ² 미구현 4건은 전부 포인트/전자지갑/복합결제/자주쓰는카드로,
서버 렌더링 페이지에만 존재해 wire 필드명 확인 불가. ³ 네이티브 브릿지 8종(#19–26)을
"의도된 제외"로 분모에 포함시킨 수치.

2차 렌즈별 표면: 누락 56/43, 오구현 85/75, 안전·일관성 39/33, 교차검증 68/64.

### 1.2 확정 결함 57건 — 3차 보정심각도 분포

| critical | high | medium | low | info |
|---:|---:|---:|---:|---:|
| **0** | **2** | **4** | **32** | **19** |

**critical 0건이 이 감사의 헤드라인이다.** 3차 검증자들은 2차가 critical로 올린 유일한 항목
(P2INC-01)을 high로 내렸다 — 실카드가 나가려면 여전히 `allow_payment=True`와 `dry_run=False`라는
명시적 opt-in 두 개가 필요하기 때문이다. 돈/예약을 잘못 움직이거나 안전게이트가 뚫리거나
카드정보가 새는 경로는 **발견되지 않았다.** 2차 안전렌즈와 교차검증렌즈가 각각 독립적으로
프로브를 실행해 `assert_mutation_route` / `assert_mutation_route_category` /
`assert_no_card_secrets` / `_assert_empty_body_request` / `_assert_exact_form_contract` /
`SRT_LIVE_MUTATION_CATEGORIES` 전 게이트의 우회 경로를 탐색했고 **구멍은 없었다.**

### 1.3 57건 → 약 43개 수정단위

같은 뿌리에서 나온 것을 묶으면 실제 손댈 곳은 약 43군데다(클러스터 기준).
9개 클러스터가 24건을 흡수한다:

| 클러스터 | 뿌리 | 흡수한 findings |
|---|---|---|
| **C1** | `parsers.py:1113-1117` `normalize_result_row` | S7-01, P2CRO-06, P2INC-09, P2INC-08 |
| **C2** | `consent.py` 카드종류 산문 vs XOR 구현 | P2INC-01, P2CRO-10, P2SAF-02 |
| **C6** | populated 예약행 "검증됨/미검증" 모순 | S7-02, P2INC-10, P2CRO-07 |
| **C7** | `jrnyCnt` — 환승 홀드 해제 경로 | P2SAF-01, P2CRO-01 |
| **C8** | `get_reservations` populated row → 결제 커플링 | S6-04, P2INC-03, P2SAF-08 |
| **C9** | `Ata01135` 예약대기 옵션 | S5-01, P2MIS-04 |
| **C10** | `mblPhone`/`telNo` provenance | S5-02, P2MIS-05 |
| **C11** | `EXCLUDED_API_DOMAINS` | S8-01, P2SAF-10, P2CRO-08 |
| **C12** | 그룹검색 하이드레이션 `grpDv` — 결함 아님으로 종결(§D-15) | S2-02, P2CRO-09 |

**high 2건은 같은 한 가지 사실이다** (C2). 즉 high는 **1개 수정**으로 닫힌다.

> **"약 43개"인 이유.** §4가 35개 항목, §6이 10개 항목을 싣지만 **C8은 의도적으로 세 갈래로
> 나뉘어 추적된다** — 코드 수정(L-2 zero-fill), 문서(D-11 `reserve()` docstring),
> 라이브 캡처(U-1 populated 행). 세 갈래가 U-1 하나로 함께 닫히므로 "수정단위"를 어떻게 세느냐에
> 따라 41~44 사이에서 흔들린다. 정확한 정수보다 **클러스터 구조**가 유용한 신호다.

### 1.4 결함 성격 분포

57건 중 실제 코드 동작이 틀린 것은 소수다:

- **동작 결함(코드 수정 필요):** C1, C2, P2INC-02, P2MIS-02, S3-03, C7 — **6개**
- **문서/인용 드리프트(doc-drift):** 19건 — 코드는 맞고 주석·문서·인용이 틀림
- **미구현 기능 공백:** 8건
- **확인불가(라이브 캡처 대기):** 7건
- **일관성·견고성 지적:** 나머지

이 저장소는 코드 옆에 `file:line` 근거와 "live-verified / bundle-evidenced / inferred" 3단계
신뢰도를 명시하는 이례적으로 자기검증적인 코드베이스다. 결함이 doc-drift 쪽에 몰린 것은
그 자기문서화가 코드보다 빨리 낡았기 때문이다.

---

## 2. 있는 것 — 앱에 있고 라이브러리에도 올바르게 구현된 기능

각 행은 1차/2차 감사자가 인용된 앱 근거 파일을 **직접 열어 재확인**한 것만 실었다.
apktool 경로는 `analysis/apktool/assets/offline/` 상대.

### 2.1 인증·세션 (16/18)

| 기능 | 엔드포인트 | 앱 근거 | 라이브러리 |
|---|---|---|---|
| 로그인 페이지 취득(쿠키) | `GET /login/login.do` | `sub/main.html:721` | `session.py:46` |
| 로그인 제출 (6 hidden field) | `POST /apb/selectListApb01080_n.do` | `sub/main.html:721-728` | `session.py:47-69` |
| ID 타입 자동판별 (이메일2/휴대폰3/회원번호1) | `srchDvCd` | srtgo `srt.py:691-698` | `session.py:20-29` — 대시 없는 `01X`도 인식(srtgo 대비 개선) |
| deviceKey 상수 `"-"` | 로그인폼 전용 | 번들 0-hit; `ref-srtgo_plus.md:130,138-140` | `session.py:66` |
| 성공 판정 `userMap.RTNCD=="Y"` | — | `srt-app-api-library-spec-2026-07-09.md:620` | `session.py:71` |
| 실패 메시지 top-level `MSG` 우선 | — | srtgo `srt.py:713-716` | `session.py:79-82` |
| IP 차단 → `SrtIpBlockedError(⊂SrtAuthError)` | 비-JSON 평문 | srtgo `srt.py:719-720` | `http.py:98-115`, `errors.py:70` |
| 메인페이지 검증 `?deviceId=<ANDROID_ID>` | `GET /main/main.do` | `SRWebActivity.java:1582-1592` | `session.py:83-87`, `config.py:19` |
| 세션 만료 3중 감지 (로그인폼 / 리다이렉트 알럿 / HTTP 3xx) | — | `main.html` 로그인폼; 2026-07-26 라이브(`Sr.msgs.login020`) | `parsers.py:150-177`, `:180-240`, `http.py:36-50` |
| 회원번호 `userMap.MB_CRD_NO` | — | srtgo `srt.py:723-724` (무가드 접근) | `models.py:38-61` |
| 회원정보 상호검증 | `POST /ara/selectListAra10130_n.do` | `full-api-analysis-2026-07-20.md:195` | `client.py:404-415`, `parsers.py:1120-1160` |
| 자격증명 로그 마스킹 | — | 설계 | `redaction.py:13-14` |

### 2.2 열차조회·역·운임 (438/464)

| 기능 | 앱 근거 | 라이브러리 | 검증 |
|---|---|---|---|
| 역코드→역명 표 344건 | `js/stationInfo.js:29-433` | `stations.py` `STATION_NAMES_BY_CODE` | **344/344 프로그램 전수 diff, 불일치 0** |
| 검색 요청 `oData` 11필드 | `js/ara/ara1001l.js:98-165` | `payloads.search_ajax_payload` | 일치 |
| 직통/환승 `chtnDvCd = jrnyTpCd=="11" ? 1 : 2` | `ara1001l.js:98` | `payloads.py:98-104` | 일치 |
| 검색 URL을 `grpDv`만으로 선택 (Ara10007/Ara10082) | `ara1001l.js:174-181` | `client._prepare_search:552` | 일치 |
| 열차그룹 코드표 300/900/109 | `commCode.js:186-274` | `payloads.TRAIN_GROUP_OPTIONS` | commCode.js 직접 재대조 |
| 승객 compaction (0명 슬롯 제거, 유아 fold, 청소년 psgTpCd6) | `ara0101v.js:824-836`, `commCode.js:54-88` | `payloads._compact_passenger_slots` 등 | 2026-07-26 라이브 에코 |
| `psgGridcnt` = 채워진 유형 수(인원수 아님) | `ara0101v.js:826-836` | `payloads._distinct_passenger_type_count` | 일치 |
| 단체검색 최소 10명 가드 | `ara0101v.js:549-555` | `payloads.py:670-674` `ValueError` | 일치 |
| `dsOutput0` 메타 5필드 | `ara1001l.js:190-210` | `parsers._parse_search_metadata` | 일치 |
| `dsOutput1` 행 35컬럼 타입화 + `raw` 보존 | `ara1001l.js` 소비부 | `parsers._parse_search_train_rows` → `TrainSummary` | 라이브 40행 |
| 시각표 (Ara12009), `trnNo` 5자리 zfill | `ara1001l.js:1176-1185`, `main.html:642-661` | `payloads.timetable_payload` | 2026-07-26 라이브 교정 |
| 운임 (Ara13010) psgTpCd/psgInfoPerPrnb | `ara1001l.js:1203-1234` | `payloads.fare_payload` | 2026-07-26 라이브 교정 |
| 운임 페이지 파싱 — 첫 표만 읽어 환승 placeholder(0원 행) 회피 | 2026-07-26 라이브 | `parsers.parse_fare_page:1035-1101` | 직접 확인 |
| 시각표 역명 — HTML에 없고 인라인 `getStationNameByCode('CODE')`로만 옴 | 2026-07-26 라이브 | `parsers.parse_timetable_page` | 직접 확인 |
| 환승 검색 = 다리당 1행, `trnOrdrNo`로 페어링 | `ara1001l.js:98,159` | `parsers.pair_transfer_itineraries` | 2026-07-26 동대구→광주송정 |
| 페이징 (`fllwPgExt`, 커서 `dptTm[:5]+"1"`) | `ara1001l.js:65-95` | `client.iter_train_search_pages` | 일치 |
| 선택자 4종 (역/역지도/좌석옵션/열차그룹) | `ara0101v.js:150-260` | `client.get_*_selector` | 일치 |

### 2.3 예약 (31/34)

| 기능 | 앱 근거 | 라이브러리 |
|---|---|---|
| jobId 1101 개인예약 `POST /arc/selectListArc05013_n.do` | `ara1001l.js:1445` | `personal_reservation_payload` |
| jobId 1102 예약대기 | `ara1001l.js:1447-1448` | `standby=True` |
| jobId 1103 좌석지정 | `ara1001l.js:1435-1436`, 필드 `ara0101v.js:866-882` | `designated_seats=` |
| 예약폼 필수 21필드 (`fn_validChk`) 1:1 대응 | `ara1001l.js:1649-1701`, 값 `:1453-1468` | `personal_reservation_payload` |
| `runDt1` ≠ `dptDt1` 구분 | `ara1001l.js:1460,:1462` | run_date fallback |
| `trnNo1` 5자리 zero-pad | `ara1001l.js:1461`, `main.html:642-661` | `.zfill(5)` |
| 왕복 `rtnDv=1`, 2회 순차 POST | `ara1001l.js:1476-1492,:1580-1596` | `round_trip=True` + 2-콜 워크플로 |
| 왕복 시 `jrnyCnt="1"` 유지 (2는 환승 전용) | `ara0101v.js:92,:302-303` | 고정 |
| 왕복×환승 / 왕복×단체 / 좌석지정×대기 / 좌석지정×왕복 상호배제 | `ara0101v.js:296-299,:331-334,:348-352`; `ara1001l.js:1435-1449` | 파라미터 부재 또는 `ValueError` |
| 예약대기 자격 판별을 `gnrmRsvPsbImg`로 (srtgo의 `rsvWaitPsbCd` 대신) | `ara1001l.js:1447`, `:1045,:1058` | `payloads.py:191-202`, `_refuse_ineligible_standby` |
| 예약대기 시 특실 불가 → `psrmClCd1="1"` 강제 | `ara1001l.js:1431-1432` (특실 `_S` 재작성 경로가 코드상 **존재하지 않음** — 도달불가 죽은코드) | `payloads.py:1413-1419` |
| `reserveType="11"` 개인예약에만 부착, 대기에서 DROP | srtgo `srt.py:990-991` | `payloads.py:1474-1481`, 회귀고정 `test_reserve_variants.py:264-276` |
| SRT 전용 가드 `stlbTrnClsfCd=="17"` | srtgo `train_name != "SRT"` 거부 대응 | `payloads.py:1341-1345` |
| 전 필드 문자열 전송 (앱은 `$("#rsvForm").serialize()`) | `ara1001l.js:1550` | `str(...)` — **타입 불일치 0건** |
| MutationConsent "reserve" 게이트 — 우회 경로 없음 | 설계 | `reserve`/`reserve_transfer` 모두 `_submit_reservation` 경유 |

### 2.4 환승예약·좌석지정 (22/23)

| 기능 | 앱 근거 | 라이브러리 |
|---|---|---|
| 환승 예약 1요청 2슬롯 (`jrnyTpCd=14`, `jrnyCnt=2`) | `ara0101v.js:302-303,310-311` | `payloads.py:1590` `transfer_reservation_payload` |
| slot-2 23필드 (근거등급 명시) | `payloads.py:152-189` `TRANSFER_SLOT2_FIELD_EVIDENCE` | `payloads.py:1500` |
| 환승×왕복 상호배제 (`rtnDv="0"` 고정) | `ara0101v.js:296-299,:331-334` | `payloads.py:1701`, `round_trip` 파라미터 부재 |
| 승객수는 다리별이 아니라 유형별 1회 | `ara0101v.js:117-127,:824-836` | `payloads.py:1661-1666` |
| 좌석옵션은 두 다리에 동일 적용 | `ara0101v.js:769-778` | `_second_journey_slot_fields` |
| 좌석선택 페이지 (호차 목록) | `POST /arc/selectListArc02012_n.do`; `ara1001l.js:1495-1520` | `client.py:951`, `parsers.py:360` |
| 좌석 배치도 (호차별 그리드, 74셀) | `POST /arc/selectListArc02011_n.do`; 2026-07-26 라이브 | `client.py:985`, `parsers.py:474` |
| 좌석 셀 식별자 2종 (내부번호 vs 출력라벨) | `choiceSeatNo(내부,라벨,Y/N)`; `tests/fixtures/seat_grid_car_seats.html` | `models.py:924`, `parsers.py:425` 정규식 — fixture 재대조 일치 |
| **`trnNo` 5자리 제로패딩 = 좌석 라우트 필수 게이트** | `main.html:650-661`; 패딩 없으면 147바이트 알림 셸(라이브 재확인) | `payloads.py:793` `SEAT_TRAIN_NUMBER_LENGTH` |
| 좌석지정 slot-2 명시적 blank (`scarGridcnt2="0"`, `scarNo2=""`) | `ara0101v.js:876-879` | `_seat_designation_fields` |
| 환승 페어링 — 역 연결 기준 순서, 모호하면 `unpaired` 보존 | 2026-07-26 라이브 | `models.py:339`, `parsers.py:2745,2789` |
| 환승 다리별 좌석배치도 **조회**는 가능 (제약 없음) | — | `payloads.py:717-793`이 `jrnyTpCd` 미참조 |

### 2.5 예약대기 (16/19)

`gnrmRsvPsbImg` 기반 판별, jobId 스위치, 일반실 강제, `stndFlg="N"` 무관 처리,
`reserveType` 조건부 생략, NetFunnel/consent 게이트 재사용 — 전부 앱 코드 라인 단위 재추적으로
정확함을 확인. 특히 응답 파서가 **좌석 미배정(대기표 전형) 응답을 겨냥해 설계**되어 있다:
`parsers.py:1496-1535` `parse_reservation_hold_response`가 strict-parse 실패를 잡아
`reservListMap[0].pnrNo`만으로 `_minimal_hold_from_raw` 폴백하며, docstring `:1508`이
예시로 정확히 "a missing trainListMap seat number"를 든다.

### 2.6 결제·환불·취소 (18/24)

| 기능 | 엔드포인트 | 라이브 검증 |
|---|---|---|
| 카드결제 31필드 | `POST /ata/selectListAta09036_n.do` | **2026-07-26 실카드 승인** `SUCC`/`IRT000000` |
| 미결제 취소 | `POST /ard/selectListArd02045_n.do` | **2026-07-25 실취소** `SUCC`/`IRG000000` |
| 환불 1단계 원승차권 조회 (무본문, Referer로 PNR) | `POST /atc/getListAtc14087.do` | 2026-07-26 `WRT300005` + 실티켓 identity |
| 환불 2단계 실행 | `POST /atc/selectListAtc02063_n.do` | **2026-07-26 실환불** `SUCC`/`IRT200277` |
| 예약/발권 목록 | `POST /atc/selectListAtc14016_n.do` | 2026-07-26 — **빈 응답만** (§5 참조) |
| 승차권 확인 HTML 원문 | `GET /atc/selectListAtc14017_n.do` | 2026-07-26 |
| 할인쿠폰 등록 | `POST /arb/selectListArb02A01_n.do` | 프리뷰만 — 전송은 의도적 비활성 |
| 할인쿠폰 목록 / 공공할인 보유현황 / 공공할인 검색 | `GET /apa/selectListApa03020_n.do`, `GET /common/ARA/ARA0301V/view.do`, `POST /ara/selectListAra10131_n.do` | 2026-07-26 |

카드결제 본문 31키를 `srtgo_plus/srt.py:1184-1216`과 **키 단위 전수 대조**한 결과
`stlDmnDt … pageUrl` 31개가 이름·순서·상수값 모두 일치, 누락 0.

**카드정보 마스킹은 실행 검증됨.** `SrtPaymentCard`(PAN 4111…, PIN, 생년월일, 유효기한)로
`card_payment_payload`를 실제로 빌드해 `redact_payload()`/`redact_value()`/`repr()`을 실행한 결과
`stlCrCrdNo1`/`vanPwd1`/`crdVlidTrm1`/`athnVal1`/`athnDvCd1`/`ismtMnthNum1`/`mbCrdNo`/`pnrNo`
전부 `[REDACTED]`. 우회 경로 미발견.

**위약금·부분환불은 "확인된 부재"다.** `messages.js:10,13,211,221`과 `ara1001l.js:1319,1397`의
위약금 문구는 전부 **예매 전** 조기예매 할인 안내이고, `commCode.js:1675-1683`의 `tkKndCd` 43/44는
영수증 분류 코드이며, `tkSttCd`(`commCode.js:1397-1471`)는 상태 코드다. 환불 요청/응답 어디에도
수수료 금액이나 승객별 부분선택 필드가 없다. srtgo도 동일. 결함 아님.

### 2.7 할인·NetFunnel·에러코드·안전계층 (38/47)

| 기능 | 검증 방식 |
|---|---|
| 할인종류코드 `dcntKndCd` 173건 | `commCode.js:8474-24610`과 **173/173 바이트 단위 일치**, `rmk:"V"` 25건도 일치 |
| 공공할인 01–06 명칭 + 07/08 코드만 인정 | 2026-07-26 라이브 |
| 공공할인 최소인원 가드 (01/06 → 3명) | `discounts.py:247`, 시행 `payloads.py:2399-2403` — I/O 이전 `ValueError` |
| 청소년 `psgTpCd6` / 유아 fold + `infantCnt` | 2026-07-26 라이브 에코 |
| NetFunnel 5101/5002/5004 URL 빌더 | `netfunnel.js` 원문과 **쿼리순서·타임스탬프 위치까지 완전 일치** |
| NetFunnel 상태코드 200/300/201·202/301·302/502, ttl 클램프 1..5 | `netfunnel.js:18,84` 원문 대조 |
| 슬롯 해제 best-effort — 키 pop이 `try` 이전이라 무한누적 없음 | `client.py:510-523` 코드 추적 |
| User-Agent 접미사 (공백 없이 이어붙임) | `SRWebActivity.java:2642-2649` — 오타 아님, 정확 재현 |
| 에러코드 매핑 S111 / NET000001 / WRG000000·WRT300005 / WRD000061 / WRP011002·WRR000100 / error001 | fixtures 39건의 `msgCd` 전수 — 미분류로 떨어지는 코드 0건 |
| Read-only 라우트 allowlist 26개 | 26/26 모두 최소 3개 테스트 파일에서 참조됨 (UNPINNED=[]) |
| Mutation 라우트/카테고리 바인딩 5개, live-enable 4개 | `safety.py:412-534`, `:440-522` |
| 카드비밀 필드 데이터 게이트 / 환불1단계 빈본문 강제 / 좌석·공공할인 폼 정확계약 / NetFunnel 쿼리 정확계약 | `safety.py:797-832`, `:834-857`, `:591-658`, `:661-768` |

---

## 3. 없는 것 — 앱(또는 프로토콜)에 있는데 라이브러리에 없는 기능

| # | 기능 | 왜 필요한가 | 난이도 | 심각도 |
|---|---|---|---|---|
| 3.1 | 휠체어/전동휠체어 좌석속성 예약 (`rqSeatAttCd 021/028`) | 앱에 전용 이용동의문까지 있는 정식 기능. 게다가 검색으로 지정한 값이 예약에서 **조용히 015로 강등**된다 | **낮음** — 파라미터 1개를 두 빌더에 배선 | **medium** |
| 3.2 | 예약대기 SMS/좌석등급변경 동의 `POST /ata/selectListAta01135_n.do` | srtgo `reserve()`는 전화번호가 있으면 대기예약 직후 이 호출을 함. 없으면 서버 기본값이 그대로 남음 | 낮음 — 4필드 POST, `telNo`는 이미 `user_map["MBL_PHONE"]`에 있음 | low |
| 3.3 | 출발역=도착역 사전검증 | 앱은 전송 자체를 차단(`ara0101v.js:570-574`). 라이브러리는 그대로 보냄 — 서버 거동 미확인 | 매우 낮음 | low |
| 3.4 | 개인검색 10명 이상 상한 | 단체검색 하한(10명 미만 거부)은 이미 구현. 상한만 비대칭으로 빠짐. **구현됨 2026-07-27**: 공유 빌더가 두 흐름을 구분 못 한다는 이유로 "구조적 불가"로 읽혔으나, `SrtClient._prepare_search` 는 이미 `group: bool` 을 받고 모든 진입점이 그곳을 지난다 | 매우 낮음 | low |
| 3.5 | 왕복×코레일역 배제 (`lfn_isKorailStn`) | 앱은 왕복 체크 즉시 차단. 다만 `stlbTrnClsfCd=="17"` 가드에 사실상 포섭되어 트리거 여지 희박 | 낮음 | low |
| 3.6 | 왕복×국회의원 후급(`mbCrdNo` prefix `"11"`) 배제 | 앱 문구는 서버 거부가 아니라 할인자격 안내("각각 편도로 예매하라")로 읽힘 | 낮음 | low |
| 3.7 | OK캐쉬백 포인트 / 전자지갑 / 복합결제 | `messages.js:28-40`의 pay010–pay019가 실재를 증언. 단 wire 필드명은 서버렌더링이라 **확인불가** | 높음 — 라이브 캡처 선행 필요 | info |
| 3.8 | 자주쓰는 카드(저장카드) 등록/사용 | `messages.js:44` pay019. 순수 편의기능 | 높음 (동일 사유) | info |
| 3.9 | 승차권 상세조회 `POST /ard/selectListArd02019_n.do` | srtgo 단독출처(`srtgo_plus/srt.py:96,1102-1112`). 앱 자신은 WebView(`gotoDetailARD02018/ARD0201V`)로 열고 이 JSON 라우트를 쓰지 않음 | 낮음 — 다만 **의도된 범위결정** | info |
| 3.10 | 승차권 변경(여행변경) `tkDptDt/tkDptTm/tkTrnNo/tkTripChgFlg` | 검색폼의 4필드가 통로. 참조구현에도 없고 캡처 차단 상태 | 착수 불가 | info |
| 3.11 | 부킹페이지 `application.gds_userInfo` 파싱 | `MB_CRD_NO`는 이미 `userMap`으로 확보되고 나머지(`USER_DV`/승하차역)는 UI 편의필드 | 낮음 | info |

> **3.9에 관한 정정.** 2차는 "예약 후 실제 배정 호차·좌석을 확인할 방법이 없다"고 썼으나
> 3차가 이를 반증했다 — `parsers.py:1413-1427`이 예약 응답 `trainListMap`에서 `seatNo`/`scarNo`를
> 읽어 `models.py:570-573` `ReservationTrain`을 만들고, `models.py:638`에도 `seat_number`가 있다.
> 또 이 라이브러리는 srtgo 단독출처 라우트를 **라이브 검증 후에만** 편입한다는 방침을 갖고 있고
> (`safety.py:415-428`), 이 gap은 `ref-srtgo_plus.md:103`,
> `cross-validation-2026-07-21.md:74,370`, `RELEASE_GAP_PLAN.md:1054-1055`에 이미 추적 중이다.
> 따라서 "결함"이 아니라 **추적 중인 범위결정**으로 기록한다.

---

## 4. 수정이 필요한 것 — 심각도 순

각 항목: 앱근거 · 라이브러리근거 (`file:line`) → 무엇이 틀렸는가 → 어떻게 고치는가.
3차 검증자가 줄번호를 교정한 경우 **교정된 값**을 실었다.

---

### 4.1 HIGH

#### H-1 [C2] `MutationConsent` 문서가 "실카드엔 두 플래그를 다 뒤집어야 한다"고 하지만, 기본 consent + `dry_run=False`만으로 PAN이 실서버로 나간다
> 흡수: **P2INC-01** (원 critical → 보정 high), **P2CRO-10** (high), **P2SAF-02** (원 high → 보정 low)

- **앱근거:** 해당 없음 — 라이브러리 자체 안전모델 문서와 구현의 불일치.
  (참고: 앱은 이 평문 결제 라우트를 쓰지 않는다. `stlCrCrdNo1`/`vanPwd1`/`Ata09036` 모두
  `analysis/apktool/**`+`analysis/jadx/**` 0-hit이고, 카드입력은 보안 키패드
  `analysis/jadx/sources/com/softsecurity/transkey/TransKeyActivity.java` 경유
  → `POST /ard/selectListArd02017_n.do`(개인)/`Ard02018`(단체) WebView.
  이 라우트는 srtgo 계열의 JSON 표면이며 2026-07-26 실승인으로 실존이 확정됨.)
- **라이브러리근거(드리프트 산문):**
  - `consent.py:15-18` — "A real, chargeable card requires the caller to invert **BOTH** flags explicitly"
  - `consent.py:62-63` — "`fake_card_only` (default True) **keeps any payment path restricted to a non-chargeable test card**"
  - `consent.py:70-72` — "A real charge therefore needs both halves stated deliberately"
- **라이브러리근거(실제 구현):** `consent.py:91` `fake_card_only=True` / `consent.py:95`
  `real_card_acknowledged=False` 기본값 → `consent.py:188-201` `require_card_kind_claim`은
  **"정확히 하나"(XOR)만 요구**하므로 기본값 조합이 그대로 통과한다.
  `fake_card_only`를 읽는 곳은 `consent.py:188,195` 두 줄뿐이고, 카드가 실제 테스트카드인지
  검증하는 코드는 저장소 전체에 없다 — `models.py:777-780`이 "this library must never be the
  thing that tells a caller whether a card number is real"로 명시적으로 그렇게 설계했다.
- **무엇이 틀렸나:** `httpx.MockTransport` 프로브로 4조합 실행 확인 —
  `(True,False)` 기본값 → **전송됨**(PAN `4111111111111111`이 `/ata/selectListAta09036_n.do` 본문에 평문),
  `(False,True)` → 전송됨, `(True,True)` → 거부, `(False,False)` → 거부.
  즉 실카드 청구에 실제 필요한 것은 `allow_payment=True` + `dry_run=False`뿐이고
  `real_card_acknowledged`는 **불필요하다**. 게이트가 뚫린 것이 아니라 **게이트가 하지 않는 일을
  한다고 광고**되어 있다. `help(MutationConsent)`를 읽고 "기본 consent로는 돈이 안 움직인다"고
  믿은 운영자가 환경변수의 실카드를 넘기면서 `dry_run`만 끄면 그대로 결제된다.
- **정확히 서술된 대조군(수정 불필요):** `safety.py:495-496`과 `client.py:1668-1672`는
  이 게이트를 "모호성 방지(exactly one of …; neither and both are refused)"로 **정확히** 기술한다.
  테스트도 정직하다 — `tests/test_payment_mutation.py:605-611`이 `(True,False)`와 `(False,True)`
  둘 다 와이어에 실린다고 단언하고 `:615-618`이 과거 불변식이 라이브 검증으로 뒤집혔다고 기록한다.
  **드리프트는 `consent.py` 산문 3블록에만 있다.**
- **왜 critical이 아닌가:** `allow_payment=True`(`consent.py:87`, `:163-167`)와
  `dry_run=False`(`http.py:367-371`)라는 명시적 opt-in 두 개가 여전히 필요하다.
- **수정 — 세 선택지, 권고는 (b1):**
  - **(a) 문서만 정정.** `consent.py:15-18/:62-63/:70-72`를 실동작("card-kind 플래그는
    **주장을 명확히 할 뿐** 카드를 제약하지 않는다")에 맞게 재작성. 최소 변경이지만
    기본값이 여전히 "카드종류 미선언"을 통과시킨다.
  - **(b1) `fake_card_only` 기본값을 `False`로.** ← **권고.** "둘 다 미설정 → 거부"가 실제
    기본 동작이 되어 문서가 자동으로 참이 되고, `models.py:777-780`의 PAN 불투명 원칙을
    건드리지 않는다. **주의:** 이 변경은 `tests/test_payment_mutation.py:605-611`이 현재
    핀하고 있는 사실(기본 조합이 와이어에 도달함)을 뒤집으므로 그 테스트와 `:615-618`의
    주석도 함께 갱신해야 한다 — 그러지 않으면 **D-1과 똑같은 병리**(테스트가 코드와
    반대되는 사실을 단언)를 새로 만든다.
  - **(b2) `fake_card_only=True`일 때 알려진 테스트 PAN인지 검증.** 문서를 참으로 만들지만
    `models.py:777-780`("this library must never be the thing that tells a caller whether a
    card number is real")이 **의도적으로 세운 원칙과 충돌**한다. 그 원칙을 개정하겠다는
    별도 결정 없이는 권고하지 않는다.

---

### 4.2 MEDIUM

#### M-1 [C1] `normalize_result_row`의 컨테이너 우선순위가 환불/취소/결제 결과를 뒤바꾼다 — **실행으로 2회 독립 재현**
> 흡수: **S7-01**(low), **P2CRO-06**(medium), **P2INC-09**(low), **P2INC-08**(low)

- **앱근거:** `Atc02063`/`Ard02045`/`Ata09036`은 v2.0.41 번들 전체 0-hit이라 앱으로는 컨테이너
  조합을 검증할 수 없다. 그러나 같은 `/atc/` 패밀리의 예약목록 실응답
  (`tests/fixtures/reservation_list_empty.json`, 2026-07-26 실측)은 **한 응답 안에
  `resultMap`(SUCC/IRZ000005)과 `rsMap`(FAIL/WRT300005)이라는 서로 모순되는 두 컨테이너를 동시에**
  싣는다. "곁다리 컨테이너를 얹어 보낸다"는 패턴이 이 백엔드에 실재한다.
  앱 자신은 `ara1001l.js:1562`에서 `resultMap.strResult`만 본다.
- **라이브러리근거:** `parsers.py:1113-1117`
  ```python
  def normalize_result_row(data):
      out = data.get("outDataSets") or {}
      if isinstance(out, dict) and "dsOutput0" in out:   # ← 키 '존재'만 검사
          return _first_row(out.get("dsOutput0"))
      return _first_row(data.get("resultMap"))
  ```
  소비처 3곳: `parsers.py:1619` cancel, `:1739` payment, `:1902` refund.
- **무엇이 틀렸나 — 두 분기 모두 실행으로 재현됨:**
  1. **빈 `dsOutput0`가 진짜 결과를 가린다.**
     `{"outDataSets":{"dsOutput0":[]}, "resultMap":[{"strResult":"FAIL","msgCd":"WRT999999","msgTxt":"환불 불가"}]}`
     → `parse_refund_response` / `parse_unpaid_cancel_response` / `parse_card_payment_response`
     **셋 다 `SrtProtocolError`**. 실제 FAIL 사유가 전혀 읽히지 않는다. `dsOutput0=None`도 동일.
     호출자는 "돈이 움직였는지 모르는 예외"를 받는다.
  2. **곁다리 `dsOutput0`가 실패를 성공으로 덮는다.**
     `{"outDataSets":{"dsOutput0":[{"strResult":"SUCC"}]}, "resultMap":[{"strResult":"FAIL",...}]}`
     → 셋 다 `status='SUCC'` 반환. 환불이 실패했는데 호출자는 성공으로 읽는다.
- **왜 진짜 결함인가:** `_parse_result_envelope` 자신의 docstring(`parsers.py:1546-1553`)이
  "dsOutput0 first, **resultMap as the fallback**"이라고 선언하는데, 키 존재만 검사하므로
  폴백이 **도달 불가능**하다. 같은 파일 `parsers.py:2069` 예약목록 파서는 정반대로
  `resultMap`만 읽도록 명시 설계(`:2027-2035` 주석)되어 있어, 같은 API 패밀리에 대해
  한 파일 안에서 우선순위가 상반된다.
- **연쇄 항목(P2INC-08):** `parse_reservation_hold_response`의 docstring(`parsers.py:1517-1519`)은
  declared-FAIL 배제가 "enforced twice"라고 하지만 두 겹이 **다른 컨테이너**를 본다 —
  본 파서 `parsers.py:1288`은 `resultMap`을 직접 읽고, salvage 가드 `parsers.py:1492`
  `_declares_a_declared_failure`는 `normalize_result_row`(=dsOutput0 우선)를 쓴다.
  M-1을 고치면 이 불일치도 함께 닫힌다.
- **정직한 한계:** `outDataSets`+`resultMap` 동시 적재는 이 세 라우트에서 **관측된 적 없다**
  (관측된 선례는 `resultMap`+`rsMap`이라는 다른 쌍). 그리고 `dsOutput0`에 유효한 행이 있을 때
  우선하는 것은 문서화된 의도다. 결함의 확정적 부분은 **빈/None `dsOutput0`가 폴백을 막는 것**이다.
- **수정:** `dsOutput0`가 **비어있지 않은 유효한 행**을 담을 때만 우선하고 아니면 `resultMap`으로
  폴백. 두 컨테이너가 모두 status를 말하면 라우트별 우선순위를 명시. 그리고
  **"두 컨테이너 동시 존재, 서로 다른 status" 테스트를 추가해 의도를 pin**할 것(현재 0건).
  `_declares_a_declared_failure`도 `resultMap` 직접 읽기로 통일.

#### M-2 좌석등급 기본 결정이 "필드 없음"을 "일반실 매진"으로 접어 **특실**로 예약한다
<!-- 제목 정정 2026-07-27: 원 제목의 "라이브 null 로 실제 도달"은 과장이라고
     같은 감사의 phase3/verifier-1.md:169 가 명시적으로 부정했다 -- 라이브 null
     관측은 fresRsvPsbCdNm / fllwPgExt2 에 한정이고 gnrmRsvPsbStr 이 null·부재로
     온 관측은 없다. 심각도만 보정되고 제목은 그대로 남아 있었다. -->
> **P2INC-02** (원 high → 보정 medium)

- **앱근거:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:1430-1432`
  ```js
  var sPsrmClCd = "";
  if (item.gnrmRsvPsbImg == …) sPsrmClCd = 1;
  else if (item.sprmRsvPsbImg == …) sPsrmClCd = 2;
  ```
  둘 다 아니면 **빈 문자열**이지 절대 `2`가 아니다(동일 로직 `:1276-1278`).
  참조구현 `srtgo/srtgo/srt.py:447-448`은 `data["gnrmRsvPsbStr"]`를 가드 없이 읽으므로
  이 상태가 애초에 존재할 수 없다. 즉 **앱·srtgo 양쪽 모두와 갈린다.**
- **라이브러리근거:** `payloads.py:1073-1075` (`"예약가능" in (x or "")`),
  `payloads.py:1088-1093` (`GENERAL_FIRST` → `not _general_seat_available` → 특실),
  `parsers.py:2520-2527`(옵셔널 읽기), `parsers.py:2212-2234`
  (`_row_field_is_absent`가 **JSON `null`을 "없음"으로 세며 docstring이 "서버가 실제로 null을
  보낸다"고 명시**), 기본 인자 `client.py:1156`, `:1322` / `payloads.py:1222`, `:1594`.
- **무엇이 틀렸나 — 실행 재현:** `tests/fixtures/search_personal_shape_success.json`의 행에서
  `gnrmRsvPsbStr`/`sprmRsvPsbStr`만 `null`로 바꾸면
  `parse_train_search_response` → `general_seat_availability=None` →
  `personal_reservation_payload(...)` → **`psrmClCd1='2'`(특실)**.
  체인: `None` → `""` → `"예약가능" in ""` = `False` → `not False` = `True` → 특실.
  손으로 만든 모델이 아니라 `search_trains()` → `reserve()` **공개 경로만으로 도달**하며
  reserve는 라이브 전송 가능 카테고리다. `reserve_transfer`는 슬롯2가 슬롯1 결정을 공유하므로
  (`payloads.py:1705-1710`) **두 레그 모두 특실**이 된다. 요금이 더 비싼 쪽으로 조용히 넘어간다.
- **수정:** `general_seat_availability`가 `None`이면 `GENERAL_FIRST`를 특실로 승격하지 말 것 —
  거부하거나 일반실(`"1"`)로 둔다. `"필드 부재"`와 `"매진"`을 구분하는 것이 핵심.

#### M-3 `rqSeatAttCd1/2`가 `"015"` 하드코딩 — 휠체어석 예약 불가 + 검색 좌석옵션이 예약에서 조용히 무시됨
> **P2MIS-02** (medium)

- **앱근거:**
  - `analysis/apktool/assets/offline/js/ara/ara0101v.js:759-778` — 좌석옵션 팝업 콜백이
    `rqSeatAttCd1` **과** `rqSeatAttCd2`를 `obj.seatOption`으로 덮어씀.
  - `ara0101v.js:611-628` — 휠체어(`021`)·전동휠체어(`028`) **전용 이용동의문 다이얼로그**.
    사용자가 실제로 도달하는 값이며 죽은 상수가 아니다.
  - `ara1001l.js:105` — 검색의 `seatAttCd = lfn_getRsv("rqSeatAttCd1")`.
  - `ara1001l.js:1670`, `:1694` — `{val:sRqSeatAttCd1, title:"요구좌석속성코드1"}`,
    `#rsvForm` `fn_validChk` **필수 21필드 중 하나** = 예약 본문에 실려 나간다.
  - 유효값은 SRT 호출부가 확인되는 `015/021/028` 3개만 인정(`commCode.js`의 나머지 좌석속성
    코드는 코레일 공용이라 제외).
- **라이브러리근거:** `payloads.py:1110` `"rqSeatAttCd1": "015",` 하드코딩;
  `payloads.py:1583` `"rqSeatAttCd2": "015",` 하드코딩;
  `client.py:1150-1162` `reserve` / `:1316-1330` `reserve_transfer` 시그니처에 좌석속성 파라미터
  **없음**. 대비: `models.py:212` `TrainSearchQuery.seat_attr_code`는 **공개 필드**이고
  `payloads.py:583,:586,:639`를 통해 **검색에는 반영된다.**
- **무엇이 틀렸나 — 두 반쪽이 하나의 결함:**
  - (a) 휠체어/전동휠체어 예약이 `reserve`·`reserve_transfer` 어느 경로로도 **도달 불가능**.
  - (b) 더 나쁜 쪽: `TrainSearchQuery(seat_attr_code="021")`로 휠체어 재고를 검색한 뒤 그 행으로
    `reserve()`를 부르면 본문은 **조용히 `rqSeatAttCd1="015"`**로 나간다. 경고도 예외도 없다.
    같은 값을 검색에서는 존중하고 예약에서는 버리는 **라이브러리 내부 일관성 위반**이다.
- **수정:** `reserve`/`reserve_transfer`/두 payload 빌더에 `seat_attr_code`(기본 `"015"`,
  허용집합 `{015,021,028}`)를 추가해 두 슬롯에 전달. 최소한 `"015"`가 아닌 검색으로 만든 행의
  예약을 **거부**해 조용한 강등만은 막을 것.

#### M-4 좌석지정 예약에서 캐빈클래스(`psrmClCd1`)와 실제 좌석그리드 캐빈이 서로 연결되어 있지 않음
> **S3-03** (medium)

- **앱근거:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:1427-1436` (`fn_moveRsv`) —
  캐빈 셀 탭이 `sPsrmClCd`(`:1430-1432`, 행의 gnrm/sprm 이미지에서 결정)와
  `sJobId="1103"`(`:1433-1436`, 시트맵 라우팅)을 **하나의 상태 전이에서 동시 결정**한다.
  앱에는 캐빈 불일치 조합 자체가 존재하지 않는다.
- **라이브러리근거:** `client.py:985-989` `get_seat_grid(cabin_class="1")` 기본값;
  `payloads.py:832-833`은 `cabin_class`를 검증만 하고 **저장하지 않음**;
  `models.py:924-1037` `SeatGridSeat`/`SeatDesignation`/`SeatGrid` 어디에도 캐빈 필드 없음;
  `payloads.py:1411` `special_seat=_resolve_special_seat(train, seat_type)`이
  `designated_seats`를 **전혀 참조하지 않음**(`payloads.py:1083-1093`).
- **무엇이 틀렸나:** `get_seat_grid(cabin_class="2")`로 특실 좌석을 골라 `SeatDesignation`을 만들고
  `reserve(designated_seats=..., seat_type=GENERAL_FIRST 기본값)`를 호출하면 —
  해당 열차의 일반실이 예약가능한 한 `psrmClCd1="1"`(일반실)이 전송되는데 함께 붙는
  `scarNo1`/`seatNo1_*`는 **특실 차량·좌석**을 가리킨다. 어느 타입도 조회에 쓰인 `cabin_class`를
  보존하지 않아 호출자가 사후에 불일치를 검증할 방법도 없다. 앱이 구조적으로 만들 수 없는
  조합이라 **서버 반응에 대한 근거가 전혀 없다.**
- **수정:** `SeatGrid`/`SeatCarOption`에 조회 시 `cabin_class`를 보존하고 `SeatDesignation`에 실어,
  `reserve()`가 `designated_seats` 존재 시 그 캐빈으로 `psrmClCd1`을 강제(또는 `seat_type`과
  불일치 시 `ValueError`)하도록 수정.

---

### 4.3 LOW — 동작 관련

#### L-1 [C7] 환승 예약 홀드를 해제할 방법이 `cancel()`·`recover_hold.py` 어디에도 없다 (`jrnyCnt` 기본값 `"1"`)
> 흡수: **P2SAF-01**(원 high → 보정 low), **P2CRO-01**(원 medium → 보정 low)

- **앱근거:** `ara0101v.js:92` `"jrnyCnt":"1"`(직통 기본값) 대 `ara0101v.js:302-303`
  `sJrnyTp="14"; nJrnyCnt="2";` → `:309-311` `oData={"jrnyTpCd":sJrnyTp,"jrnyCnt":nJrnyCnt}`.
  **번들 전체에서 `jrnyCnt` write는 이 두 곳뿐**(grep 확정) — 앱은 여정건수를 예약 형상별 값으로 다룬다.
  취소 폼도 `jrnyCnt`를 런타임 인자로 받는다: `payloads.py:1806-1814`가 인용한 라이브 티켓목록
  인라인 스크립트 `function cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt)`.
- **라이브러리근거:**
  - `payloads.py:1840-1842` — "Defaulting to `\"1\"` is also what **every hold this library can
    create** actually is: `personal_reservation_payload` only ever sends `jrnyCnt=\"1\"`"
    → 이 일반화는 **거짓**이다. `payloads.py:1697`이 `JOURNEY_COUNT_TRANSFER`(=`"2"`)를 쓰고
    `client.py:1404-1415` `reserve_transfer`가 그 페이로드로 `SrtReservationHold`를 돌려준다.
  - `models.py:594-603` `SrtReservationHold`에 여정건수 필드 없음(`pnr_no`/`journey_list_key`/
    `total_seat_count`/`raw`뿐).
  - `scripts/recover_hold.py:79-81`이 `client.cancel(pnr, consent=...)`만 호출하고
    argparse(`:155-179`)에도 `--journey-count` 플래그가 없다(`grep -n journey` → 0건).
  - `payloads.py:1730-1770` `_cancel_journey_count`는 "Never raises" — 무엇이든 조용히 `"1"`로 떨어뜨린다.
- **무엇이 틀렸나:** `reserve_transfer`는 실제로 `jrnyCnt=2` 홀드를 만드는데,
  (1) 기본값 정당화 주석이 그 사실 앞에서 거짓이고, (2) Hold 타입이 여정건수를 기록하지 않아
  `cancel(hold)`가 유도할 수 없으며, (3) 이 프로젝트가 "PNR만으로 홀드를 해제하는 최후 수단"이라
  문서화한 `recover_hold.py`가 그 값을 **표현할 수단조차 없다.**
- **상한(과대평가 방지):** `client.py:1398-1402`가 "getting it wrong is how a hold survives a cancel
  that looked like it worked"라고 **크게 경고**하고 있고 `cancel(journey_count=...)` 파라미터
  자체는 존재하므로, 호출자가 명시하면 해결된다. 환승 홀드를 실제로 취소해 본 적이 없으므로
  "서버가 실패한다"고 단정하지 않는다. 결함의 실체는 **라이브러리 자신이 필요하다고 서술한 값을
  복구 경로가 표현할 수 없다는 것**이다.
- **수정:** `SrtReservationHold`에 `journey_count`를 싣고 `reserve_transfer`가 `"2"`로 채워
  `cancel()`이 유도하게 하거나, 최소한 `recover_hold.py`에 `--journey-count`를 추가하고
  `payloads.py:1840-1842`의 거짓 일반화를 삭제할 것.

#### L-2 [C8-a] 예약목록 숫자→문자 정규화가 zero-padding을 잃어 오전 출발 편의 결제가 만들어지지 않는다
> **P2INC-03** (원 medium → 보정 low)

- **앱근거:** 커밋 `8cb8420`(2026-07-26)가 기록한 실측 `trainListMap` 행
  `{"pnrNo":"3202607…","rcvdAmt":7500,"jrnyCnt":1,"tkSpecNum":1,"stlFlg":"N","rsvChgTno":0}`
  — 6개 중 4개가 JSON **숫자**. `payListMap`의 populated 행 타입은 저장소에 기록 0건.
- **라이브러리근거:** `parsers.py:1967-1975` `_reservation_list_optional_string` → `str(value)`;
  `parsers.py:2123,2127`이 `departure_time`/`arrival_time`을 `payListMap`에서 이 헬퍼로 읽음;
  `payloads.py:2082-2085` `_required_digits(..., length=6)`(정의 `:697-714`, 길이 불일치 시 `ValueError`).
- **무엇이 틀렸나 — 실행 재현:** `payListMap`에 `dptTm=63000`, `arvTm=65600`이 오면
  파싱 결과가 `'63000'`/`'65600'`(5자리)이 되고 `card_payment_payload`가
  `ValueError: departure_time must contain exactly 6 digits`로 거부한다.
  `rcvdAmt`(선행 0 무의미)에 맞는 변환이 `dptTm`/`arvTm`/`iseLmtTm`/`dptRsStnCd` 같은
  zero-padded **식별자**에는 손실 변환이다. 10시 이전 출발 편 전부가 걸린다.
  실패는 fail-closed지만 미결제 홀드를 결제 기한까지 풀 수 없게 만든다.
- **왜 medium이 아닌가:** 트리거 전제(시각 필드가 숫자로 옴)가 **관측 0건**이고 증거는 반대 방향이다 —
  `tests/fixtures/search_success.json`의 `dsOutput1[0]`은 `dptTm='060000'`, `arvTm='083000'`으로
  **같은 서버가 시각을 zero-padded 문자열로 보낸다**. `8cb8420`가 숫자로 관측한 것은
  `rcvdAmt`/`jrnyCnt`/`tkSpecNum`/`rsvChgTno` 같은 **수량**뿐이다.
- **수정:** 필드별 기대 길이로 zero-fill(시각 `zfill(6)`, 역코드 `zfill(4)`)하거나
  `card_payment_payload`가 6자리 미만 시각을 좌측 0 패딩.

#### L-3 출발역=도착역 동일 검증이 없음
- **앱근거:** `ara0101v.js:570-574` — `:572` `srtAlertBoxDivShow("알림","출발역과 도착역이 같습니다.",null,null)`,
  이후 `return`으로 전송 차단.
- **라이브러리근거:** `models.py:216-224` `TrainSearchQuery.__post_init__` — 코드 공백 여부,
  날짜 8자리/시간 6자리, `train_group_code` 멤버십만 검사. 두 역코드 비교 없음.
- **무엇이 틀렸나:** `TrainSearchQuery(departure_station_code="0001", arrival_station_code="0001", …)`이
  예외 없이 생성·전송된다. 서버 거동은 미확인이므로 "오답"으로 단정하지 않는다.
- **수정:** `__post_init__`에 동일 코드 시 `ValueError`.

#### L-4 개인검색 10명 이상 상한 검증이 없음 (단체 하한과 비대칭)
- **앱근거:** `ara0101v.js:562-567` — 단체 미체크 + `totPrnb>9` → alert 후 `return`.
  대응하는 단체 하한은 `:549-555`.
- **라이브러리근거:** `payloads.py:670-674` `group_search_ajax_payload`는 10명 미만이면 `ValueError`(하한 O).
  개인검색 경로(`payloads.py:577-578`, `models.py:164`)에 상한 **없음**.
- **결정적 정황:** `payloads.py:210-215`가 "the maximum it allows without one … a real,
  client-enforced boundary **in both directions**, not a UI hint"라고 스스로 적어놓고
  `:217`에서 "The one consumer is `group_search_ajax_payload`"라고 한다 — **알고도 한쪽만 구현**했고
  의도적 배제 서술은 없다.
- **수정:** non-group 요청의 총인원 상한(9명)을 검사하거나 최소한 `GROUP_MIN_PARTY_SIZE` 옆에
  이 비대칭을 문서화.

#### L-5 왕복예약이 앱의 "코레일역이면 왕복 금지" 게이트를 재현하지 않음
- **앱근거:** `ara0101v.js:337-341` (`chk_rtrp` 핸들러, `lfn_isKorailStn(sDptStn)||lfn_isKorailStn(sArvStn)`이면
  되돌리고 "코레일 열차는 왕복 열차 예약을 이용하실 수 없습니다"); 함수 `sub/main.html:568-577`;
  데이터 `js/stationInfo.js:29-45` (`gubun=="SRT"` 17개역: 수서·동탄·지제·천안아산·오송·대전·
  김천구미·동대구·신경주·울산·부산·공주·익산·정읍·광주송정·나주·목포).
- **라이브러리근거:** `payloads.py:1341-1345`는 `service_class_code!="17"`만 거부. 역 화이트리스트
  검사 없음. `stations.py`는 코드→이름 표뿐이고 `gubun` 정보 자체가 없다.
- **왜 low인가:** 앱 게이트는 검색폼에서 열차 존재 이전에 발동하고 라이브러리 `round_trip`은
  이미 찾은 `TrainSummary`에 붙는 플래그로 **생애주기가 다르다.** 또 클래스 17 열차의 역은
  앱 자신의 `stationInfo.js` 정의상 SRT 17개역 집합에 속하므로 기존 `"17"` 가드에 사실상 포섭된다.
- **수정:** 라이브 세션으로 현재 `stationList`를 재확인해 SRT-gubun 집합을 확정하고,
  포섭이 확인되면 "문제없음"으로 재분류. 아니면 `round_trip=True`에서 집합 밖 역을 거부.

#### L-6 왕복예약이 국회의원 후급(`mbCrdNo` prefix `"11"`) 배제를 재현하지 않음
- **앱근거:** `ara0101v.js:317-326` — `mbCrdNo.substr(0,2)=="11"`이면 `callbackChkRtrp()` 후
  "왕복승차권은 국회의원 후급 적용으로 이용하실 수 없습니다" 알림, `return`.
- **라이브러리근거:** `models.py:49-55`가 이미 이 규칙의 근거(`ara0101v.js:319,321`)를 **정확히 인용**하고
  있으나 `payloads.py:1226`/`:1453`에 상호검증 로직 없음(`grep mbCrdNo` → 카드결제 문맥만).
  `personal_reservation_payload` 시그니처에 `membership_number` 인자 자체가 없다.
- **왜 low인가:** 앱 문구는 와이어 규칙이 아니라 **할인자격 안내**("각각 편도로 예매하라")이고
  서버 거부 근거가 없다. 가드 위치도 조회화면 체크박스이지 예약 전송점이 아니다.
  같은 파일 `payloads.py:1326-1337`은 "증거 있는 조합만 거부한다"는 방침을 명시한다.
- **수정:** `reserve(round_trip=True, …)`가 `session.membership_number`를 받아 prefix `"11"`이면
  거부하거나, 최소한 호출자 책임임을 문서에 명시.

#### L-7 [C9] 예약대기 SMS/좌석등급변경 동의 `Ata01135` 미구현
> 흡수: **S5-01**(원 medium → 보정 low), **P2MIS-04**(원 medium → 보정 low)

- **앱/참조근거:** 번들 0-hit 재확인(`grep -rl '01135' analysis/` → 0건). 유일한 근거는
  `srtgo_plus/srtgo/srt.py:98` `"standby_option": …/ata/selectListAta01135_n.do`;
  `srt.py:1014-1051` 바디 `{pnrNo, psrmClChgFlg, smsSndFlg, telNo}`(`:1041-1046`) + POST(`:1049`);
  `srt.py:862-876` — `reserve()`가 `if self.phone_number:`로 대기예약 직후 이 옵션 호출을 수행;
  `srt.py:726` `self.phone_number = user_info["MBL_PHONE"]`(무가드).
  같은 6-endpoint 그룹 중 4개(cancel/payment/refund/reserve-info)는 2026-07-25~26 라이브로
  실존 확정됨(`cross-validation-2026-07-21.md:370`) — **번들 0-hit을 부재 근거로 쓸 수 없다.**
- **라이브러리근거:** `grep -rn '1135' src/` → `client.py:1224` 주석 1건뿐(자기 신고
  "that route is 0-hit … so it is NOT implemented"). 메서드·빌더·라우트 전무.
- **정직한 범위 축소:** srtgo의 **저수준** 예약 경로(`srt.py:999-1012`)는 이 호출을 하지 않는다 —
  호출하는 것은 상위 `reserve()`(`:862-876`)다. 따라서 `reserve(standby=True)`의 **와이어 흐름
  자체는 참조구현과 다르지 않고**, 빠진 것은 선택적 알림설정이다. "통보를 못 받는다"는 서술은
  서버 기본값 SMS off라는 **미증명 가정**에 의존하므로 쓰지 않는다.
- **`telNo` 공급원은 이미 있다:** `SrtSession.user_map["MBL_PHONE"]`(→ L-8).
- **수정:** `Ata01135`를 standby 전용 mutation 라우트/카테고리로 추가하고 `telNo`를 `MBL_PHONE`에서
  공급, 라이브 1회 캡처로 실존 확정.

#### L-8 [C10] `mblPhone`/`telNo` 생략 근거가 standby 경로에 대해 사실과 다름
> 흡수: **S5-02**(원 medium → 보정 low), **P2MIS-05**(원 low → 보정 info)

- **앱근거:** `ara1001l.js:1453-1468` `fn_moveRsv`의 `oRsvData`에 `mblPhone` 키 없음(개인·대기 공통).
  `sub/main.html:465-482` 서버렌더 `application.gds_userInfo` 블록에 `:477 MBL_PHONE: ""` 실재.
  `srtgo/srt.py:726`이 로그인 응답 `userMap`에서 `MBL_PHONE`을 무가드로 읽음.
- **라이브러리근거:** `payloads.py:1235-1237` — "`mblPhone` is omitted -- srtgo passes `None`,
  which requests drops from the wire, and the string has ZERO hits …, **so there is nothing to
  add it back from.**"
- **무엇이 틀렸나:** 이 근거는 **personal(jobId=1101) 케이스에만** 사실이다.
  standby(1102)에서는 srtgo `reserve()`(`srt.py:867-869`)가 `mblPhone=self.phone_number`를
  **명시적으로 채우고** `:986`에서 실제로 싣는다 — `requests`가 드롭하지 않는다.
  `payloads.py:1235`가 붙은 `personal_reservation_payload`는 `:1219`/`:1240`에서 1101·1102를
  모두 만든다고 선언하므로, personal 한정 사실을 standby에도 적용해
  `cross-validation-2026-07-21.md:131`이 미해결로 열어둔 질문을 답이 난 것처럼 닫아버렸다.
- **범위 축소(P2MIS-05에 대한 3차 반증):** "뒤 절이 통째로 틀렸다"는 성립하지 않는다 —
  `the string`은 백틱으로 감싼 와이어 키 `` `mblPhone` ``(소문자)이고 그것은 실제로 번들 0-hit이다.
  `MBL_PHONE`은 별개 토큰이며 **'값의 출처'와 '필드의 근거'는 다른 문제**다.
- **수정:** `payloads.py:1235` 주석을 personal/standby로 분리해 정확히 서술.
  `SrtSession`에 `phone_number`(`MBL_PHONE`) 파생 속성을 추가하고 `redaction.py` `SENSITIVE_KEYS`에
  등록(L-7의 공급원). standby 라이브 캡처 시 `mblPhone` 유무를 최우선 확인.

#### L-9 `trnGpCd1`/`trnGpCd2`가 검색행 값이 아닌 상수 `"300"`으로 하드코딩
- **앱근거:** `ara1001l.js:1440` `"trnGpCd1": item.trnGpCd` — 검색 결과 행의 실제 값을 그대로 전송.
- **라이브러리근거:** `payloads.py:1444` `"trnGpCd1": "300"`, `payloads.py:1580` `"trnGpCd2": "300"`.
  `TrainSummary.train_group_code`(`models.py:273`)는 예약 빌더가 **한 번도 읽지 않는다**(grep).
- **관측된 실해 없음:** `payloads.py:1342-1344`가 `service_class_code != "17"`을 거부하고,
  실측 fixture 4건 모두 `stlbTrnClsfCd=="17"` ⇔ `trnGpCd=="300"`.
  **불일치 프레이밍의 보강 근거:** 같은 파일 `payloads.py:724-725`와 `:830-831`은
  좌석 라우트에서 `train.train_group_code=='300'`을 **실제로 강제**한다 — 즉 라이브러리는
  같은 값을 어떤 곳에선 검증하고 어떤 곳에선 무시한다.
- **수정:** `train.train_group_code`가 있으면 그 값을 쓰고 없을 때만 `"300"` 폴백,
  또는 최소한 하드코딩 근거(관측된 fixture 전부 일치)를 코드 주석에 명시.

#### L-10 `settlement_flag`(`stlFlg`) 의미 미문서화로 cancel/refund 라우팅을 라이브러리만으로 결정 불가
- **앱근거:** `commCode.js:1397` 이하 `tkSttCd`(승차권상태코드) 테이블에 결제여부 유사 개념 없음.
  `stlFlg` 문자열 자체가 `analysis/` 전체 0-hit(hits는 `src/`,`docs/`,`tests/`뿐).
- **라이브러리근거:** `models.py:649` `settlement_flag: str | None = None  # stlFlg` — 의미 설명 없음.
  `is_paid`류 파생 속성 전무(grep). `get_reservations`(`client.py:284`,`:315`,
  `/atc/selectListAtc14016_n.do`)는 `models.py:608`에서 "예약/발권 목록" = 미결제 홀드와 발권 티켓이
  **섞인 한 리스트**로 기술되는데, cancel(`client.py:1417`)과 refund(`client.py:1788`)는
  서로 다른 consent 카테고리로 완전히 분리되어 있다.
- **무엇이 틀렸나:** 한 행이 미결제 예약(→cancel)인지 결제완료 티켓(→refund)인지 판단할 방법이
  라이브러리 API에 없다. `stlFlg`가 그 정보를 담을 가능성이 높으나(필드명이 '정산') 의미가
  명시돼 있지 않고, 유일 관측값 `"N"`조차 L-11에서 지적한 출처 문제를 안는다.
- **수정:** 결제 전/후 두 상태의 `get_reservations()` 행을 라이브 캡처해 의미를 확정하고
  문서화하거나 `is_paid` 파생 프로퍼티 추가.

#### L-11 [C6] populated 예약행의 "라이브 검증됨/미검증"이 코드 안에서 서로 모순 — **git이 답한다**
> 흡수: **S7-02**(원 medium → 보정 low), **P2INC-10**(원 medium → 보정 low), **P2CRO-07**(원 medium → 보정 low)

- **앱근거:** 없음 — 라이브러리 내부 문서 불일치.
- **라이브러리근거(A, 검증됐다):** `parsers.py:1946-1958` — "LIVE 2026-07-26 settled what the
  non-empty row looks like" + 구체 행 `{"pnrNo":"3202607…","rcvdAmt":7500,…}`.
- **라이브러리근거(B, 미검증이다) 6곳:** `parsers.py:2043-2046`, `models.py:618-627`,
  `client.py:301-306`(및 `:1650-1655`), `tests/test_reservation_list.py:12-13`,
  `docs/VERIFICATION.md:297-299`, `docs/IMPLEMENTATION_PROGRESS.md:790`.
- **판정 — "판정 불가"가 아니다:** `git blame` 결과 `:2043`은 `2b11025`(예약목록 최초 구현),
  `:1948`은 `8cb8420`(2026-07-26 15:10:22)로 **`:1948`이 더 나중**이다.
  `git show 8cb8420` 메시지가 1차 증언이다 — "a live card payment refused to build … on a
  reservation that plainly carried 7500". 교차확증: `client.py:1611-1619`의 라이브 결제액이
  7,500 KRW. 즉 **`parsers.py:1948` 쪽이 사실이고 나머지 6곳이 stale**이다.
  (`client.py:301`은 "for an account with no reservations" 조건부라 프로브 시점엔 참이었다.
  캡처 fixture 부재는 반증이 아니다 — `safety.py:924-927` `SAFETY_STATEMENTS`가 PNR 저장을 금지한다.)
- **여전히 미해결:** `payListMap`의 populated 행 **타입**은 기록 0건이며 그것이 L-2의 근본 원인이다.
- **수정:** 6곳의 UNVERIFIED 서술을 갱신하고 `docs/VERIFICATION.md`에 그 캡처를 기록
  (특히 `payListMap` 행의 타입).

#### L-12 `_optional_row_string`은 숫자를 만나면 검색 전체를 죽인다
- **앱근거:** 커밋 `8cb8420` 메시지 — "This is the **sixth** string-versus-number mismatch this
  codebase has hit. Both apps are inconsistent about it; **new parsers** should accept either
  from the start."
- **라이브러리근거:** `parsers.py:2248-2251`(present non-string → `SrtProtocolError`,
  예외가 필드 단위로 스코프되지 않아 `search_trains` 전체가 죽음) 대 `parsers.py:2214-2237`(null만 완화)
  대 `parsers.py:1967-1975`(예약목록은 숫자를 정규화).
- **범위 축소(3차 반증):** "저장소 자신의 규칙과 반대"라는 프레이밍은 틀렸다 — `8cb8420`의 규칙은
  **신규 파서** 전향 지침이다. 더 결정적으로 두 헬퍼의 차이는 **의도적이며 코드 옆에 이유가 적혀
  있다**: `parsers.py:1960-1965` "Still deliberately more forgiving than `_optional_row_string`,
  which raises on a present non-string. Raising over one odd field would cost the caller the PNRs
  of every reservation in the list."
- **현재 위험:** 검색 행 40건이 2026-07-26 라이브로 관측됐으므로 낮다.
- **수정(선택):** 검색 행에도 숫자→문자 정규화를 적용하되 zero-padded 컬럼은 L-2의 zero-fill 규칙을
  함께 적용. 또는 현 설계를 유지하고 비대칭 이유를 `_optional_row_string` 쪽에도 명시.

---

### 4.4 LOW/INFO — 문서·인용·일관성 (동작 영향 없음)

이 절의 항목은 **코드가 옳고 문서·주석·인용이 틀린 것**이다. 한 번에 배치로 처리하는 것이 효율적이다.

| # | 항목 | 틀린 곳 | 옳은 값 / 조치 |
|---|---|---|---|
| D-1 [C11] | `EXCLUDED_API_DOMAINS`가 라이브 전송 중인 4카테고리를 "제외"로 명명 | `safety.py:911-922`(reservation/ard-payment-entry/payment/refund/cancellation) 대 `safety.py:520-522` `SRT_LIVE_MUTATION_CATEGORIES`; 테스트가 이를 pin: `tests/test_redaction_safety.py:165-168` | 이 상수를 읽는 코드는 그 테스트 1곳뿐(전수 grep) → 런타임 영향 0. 실제 게이트는 `assert_mutation_route`(`:537`)/`assert_mutation_route_category`(`:559`)이며 정확하다. `RELEASE_GAP_PLAN.md:519-524`가 이미 분리를 지시하고 `:1068`은 "retire it"까지 적음. **네 카테고리 제거 또는 `PERMANENTLY_EXCLUDED_API_DOMAINS`로 개명 + 테스트명 정정.** ※ S8-01·P2SAF-10·P2CRO-08 3중 독립 확인 |
| D-2 | `full-api-analysis`의 `psgTpCd` 해독표가 `commCode.js`와 어긋남 — **코드가 옳고 문서가 틀림** | `docs/analysis/full-api-analysis-2026-07-20.md:378`, `:453` — "1=어른,2=어린이,3=경로,4=중증장애,5=경증장애" (2↔5, 3↔4 역전). 인용한 근거 `ara0101v.js:113-121`(실제 `:114-127`)에는 이름 매핑이 **한 글자도 없다** | 권위: `commCode.js:54-88` (1=어른, 2=장애1~3급, 3=장애4~6급, 4=만65세이상, 5=만4~12세). 코드는 정상: `payloads.py:269-277`(`:261-268`에 2026-07-26 라이브 에코 검증 기록). **이 표를 믿고 코드를 문서 쪽으로 맞추는 역방향 수정이 일어나면 어린이 요금으로 장애인석을, 경로 요금으로 장애할인을 신청하는 실운임 오류가 된다** — low이지만 우선 정정할 이유가 이것. ※ `impl-audit-reverify-2026-07-22.md:221-224`가 이미 같은 지적을 했으나 여전히 미수정 |
| D-3 | `"0001 : 선행, 0002 : 후행"` 글로스 줄번호가 4곳에서 `:1607`로 오인용 | `models.py:354`, `payloads.py:93`, `:1284`, `:1621` | 실제는 `ara1001l.js:1611` `frm.jrnySqno.value = 1; // 0001 : 선행, 0002 : 후행`. `:1607`은 `frm.action = contextPath + "/ard/selectListArd02017_n.do";`로 무관. 1차 근거 `ara0101v.js:97`은 정확하므로 기능 결함 없음. 정정 시 "`:1611`의 필드는 **접미사 없는** `jrnySqno`이고 예약폼이 아니라 결제 핸드오프 폼(Ard02017)에 실린다"는 단서를 함께 달 것 |
| D-4 | 로그인 `deviceKey="-"`의 참조문헌 인용이 엉뚱한 줄을 가리킴 | `session.py:57-60` 주석이 `ref-srtgo_plus.md:112,120-121`을 지목 — `:112`는 결제 엔드포인트 대조 문단, `:120`은 빈 줄, `:121`은 "## 3. Login / auth" 제목 | 값 자체는 정확(`session.py:66` `"deviceKey": "-"`). 실제 근거는 `ref-srtgo_plus.md:130`(`deviceKey=-, # literally a hyphen`)과 `:138-140`. `deviceKey`는 `analysis/` 전체 0-hit이라 **참조문헌 인용의 정확성이 유일한 검증 수단**이다 |
| D-5 | `AndroidManifest.xml` 인용이 jadx/apktool 두 렌더링을 트리 표기 없이 섞어 씀 | `payloads.py:1882`, `:1884`(및 `VERIFICATION.md:251-252`, `IMPLEMENTATION_PROGRESS.md:548-549`)는 **jadx** 번호; `cross-validation-2026-07-21.md:323`,`:324`,`:356`은 **apktool** 번호 | apktool(170줄): `:2` package, `:53` usesCleartextTraffic, `:72` TransKeyActivity, `:140` UAFClientActivity. jadx(393줄): `:143` TransKeyActivity, `:315` UAFClientActivity. 저장소에 Manifest가 7개 있고 줄 체계가 다르다 — **`analysis/jadx/resources/AndroidManifest.xml:143`처럼 트리 접두사를 붙일 것** (이 저장소는 이미 그렇게 쓰는 곳이 있다) |
| D-6 | `SrtReservationSummary` docstring의 컨테이너 라벨이 실제 배치와 반대로 읽힘 | `models.py:610-612` — "`trainListMap[i]` (journey identity) with `payListMap[i]` (settlement state)" | 실제(`models.py:634-649` + `parsers.py:2109-2145`): `trainListMap` → `rcvdAmt`/`tkSpecNum`/`seatNum`(결제·티켓 식별), `payListMap` → `trnNo`/`dptDt`/`dptTm`/`arvTm`/역코드(여정 식별) + `iseLmtDt`/`stlFlg`(정산). **파서와 인라인 주석은 서로 일치하므로 파싱 버그 없음.** docstring만 재작성 |
| D-7 | `SrtSession.membership_number` docstring이 엉뚱한 절을 근거로 인용 | `models.py:40-47`이 `full-api-analysis-2026-07-20.md:431`을 "`userMap`이 `MB_CRD_NO`를 키로 갖는다"의 근거로 지목 — 그 줄은 `### 4.5 UserInfo (application.gds_userInfo)`(`:429`) 아래의 **부킹페이지 전역 JS 객체** 설명이다 | 기능적 판단은 옳다: `session.py:70`이 `response['userMap']`을 저장하고 srtgo `srt.py:723-724`가 `user_info['MB_CRD_NO']`를 무가드로 읽는다. 인용을 srtgo `srt.py:723-724` + `docs/VERIFICATION.md`의 2026-07-26 라이브 결제런으로 교체하고, `gds_userInfo`는 별개 객체임을 명시 |
| D-8 | `netfunnel.js:60477`은 줄번호가 아니라 **문자 오프셋** | `netfunnel.py:38`(및 `errors.py:262`) — 같은 주석 블록의 `netfunnel.py:36`은 `netfunnel.js:84`를 줄번호로 씀 | `netfunnel.js`는 86,293자 / 84줄의 미니파이 파일. 오프셋 60477은 `NetFunnel.TsClient.prototype._showResultChkEnter`의 `_`(진짜 `_showResult`는 58653). **`netfunnel.js@60477` 또는 `netfunnel.js (char 60477)`로 구분 표기**하고 저장소 전체에 규칙 통일. 자동 인용검사(268건)에서 범위 이탈로 오탐된 2건 중 하나가 이것(나머지가 D-5) |
| D-9 | `assert_mutation_route` docstring이 "the four evidenced state-changing routes"라는데 집합은 다섯 | `safety.py:537-538` 대 `safety.py:412-438`(Arc05013 `:416`, Ard02045 `:419`, Ata09036 `:424`, Atc02063 `:428`, COUPON `:436`) | 본문 `safety.py:546-556`이 `route not in SRT_MUTATION_ROUTES`만 검사하므로 실제로 5개를 허용한다(coupon은 `:520-522` 카테고리 게이트에서 막힘). 같은 파일 `safety.py:377-378`은 "the FIFTH route added on 2026-07-26"으로 **정확히** 서술 — 파일 내부 불일치. "the five registered state-changing routes (four live-enabled, one preview-only)"로 정정 |
| D-10 | `SrtCouponRegistrationRequest`가 공개 export인데 공개 메서드가 받지 않음 | `__init__.py:50`(import), `:144`(`__all__`) 대 `client.py:1499-1504` `register_discount_coupon(coupon_number: str, coupon_password: str, *, consent)`; 타입은 `client.py:1578-1582`에서 내부 생성 | 다섯 mutation 중 쿠폰만 bare `str` 두 개를 받는다(비교: `reserve` `:1150`, `reserve_transfer` `:1316`, `cancel` `:1417`, `pay_with_card` `:1600`, `refund` `:1788` 전부 타입 경로 보유). `models.py:1257-1258`의 `repr=False` 이점이 호출자에게 전달되지 않는다. **오버로드 추가 또는 `__all__`에서 제거** |
| D-11 [C8-b] | `reserve()`가 돌려주는 `SrtReservationHold`를 `pay_with_card()`가 받지 못함 (타입 단절) | `client.py:1162`(→`MutationPreview \| SrtReservationHold`) 대 `client.py:1600-1601`(`pay_with_card(reservation: SrtReservationSummary, …)`); `models.py:594-603` Hold에 `received_amount`/`ticket_special_number`/`departure_time`/`arrival_time` 없음 대 `payloads.py:2082-2085`,`:2091`,`:2108`이 그 넷을 필수 요구 | 앱은 예약 응답을 그대로 결제 폼으로 옮긴다(`ara1001l.js:1608-1618`). 라이브러리는 `get_reservations()` 재조회를 강제하는데(`payloads.py:2044-2053`) 그 읽기가 저장소에서 가장 검증이 얇다. **필드를 추측하지 않는 안전 방향이므로 코드 변경 대신 `reserve()` docstring에 "Hold로는 결제 폼을 만들 수 없다"를 명시**하고 흐름 문서에 재조회 필수 단계를 못박을 것 |
| D-12 | 숫자 PNR 정규화가 cancel 빌더가 명시적으로 금지한 변환을 대신 수행 | `payloads.py:1772-1786`(int PNR 거부: "converting a numeric PNR drops any leading zeros, which would cancel the wrong reservation") 대 `parsers.py:1970-1971`(`isinstance(value,int)` → `str(value)`), 호출 `parsers.py:2101-2103` | **실피해 없음**(JSON 정수 리터럴은 선행 0을 표현할 수 없으므로 잃을 것이 없다). 두 방어는 다른 입력을 막는다 — 쓰기 경로는 호출자의 int를, 읽기 경로는 서버의 JSON 숫자를 다루며 후자는 `parsers.py:1960-1965`가 근거를 대고 선택한 정책이다. **일관성 메모만 남길 것** |
| D-13 | 검색 페이로드가 서버 `psgTpCd`와 호출자 인원수를 같은 슬롯에 섞음 | `payloads.py:502-504`(`psgTpCd`는 hydrated, `psgInfoPerPrnb`는 호출자), `parsers.py:837,840-846`(모든 named input 무필터 수집), `tests/test_netfunnel_payloads_parsers.py:562-568`이 `psgTpCd1=='hydrated-senior'`+`psgInfoPerPrnb1=='2'`를 계약으로 pin | **위험 전제는 3차에서 반증됨** — `search_page_payload` 자신이 하이드레이션 GET을 호출자의 `psgTpCd`/`psgInfoPerPrnb` 쌍으로 시드하므로(`payloads.py:592`) 서버 에코는 같은 코드를 돌려주고 desync가 불가능하다. **조치 불필요**, 참고로만 기록 |
| D-14 | 카드 필드 검증 규칙의 provenance 서술 | `payloads.py:1869-1923`("every card field … genuinely 0-hit") 대 `messages.js:45` pay024, `:46` pay025, `:48` pay027, `:50` pay029(비밀번호 앞 2자리 / 주민번호 앞 6자리 / 할부선택) | 필드 **이름**이 0-hit인 것은 사실이고, 필드의 **형식 규칙**은 `messages.js`가 독립 증언한다(`models.py:755-758`,`:783-799`와 의미 일치). 다만 "비관적"이라는 평가는 과하다 — `payloads.py:1911-1923`이 스스로 "The blanket claim 'every field name is 0-hit' is **FALSE**"로 시작해 이름/개념을 명시 분리한다(`:1923`). **`messages.js` 인용 한 줄 추가**로 충분 |
| D-15 | 그룹검색 하이드레이션 GET의 `grpDv` | `payloads.py:554`(항상 `"0"`), `:676`(POST에서 `"1"`), `client.py:551` | **결함 아님으로 종결.** 앱의 페이지 로드 시드도 언제나 `ara0101v.js:93 "grpDv":"0"`이고 체크박스(`:522`)는 폼 입력값을 바꿀 뿐 별도 하이드레이션 요청을 만들지 않는다. 라이브러리는 "시드 0, 검색 POST에서 1" 순서를 그대로 재현하며 `tests/fixtures/group_search_success.json`이 이 흐름의 실응답을 증명한다. **`payloads.py:554`에 앱 시드도 항상 0이라는 주석 한 줄만 남겨 재발 지적을 막을 것** (1차 S2-02는 결함으로 올렸으나 2차 P2CRO-09가 기각, 3차가 이를 확인) |
| D-16 | 데이터 기반 가드가 카드 4필드에만 걸림 | `safety.py:797-804` `CARD_SECRET_FIELDS = {stlCrCrdNo1, vanPwd1, crdVlidTrm1, athnVal1}`; 취지는 `:774-796`("stated on the DATA rather than on the route"); `redaction.py:91-99`는 쿠폰번호를 "A COUPON NUMBER IS A BEARER CREDENTIAL … masked on the same footing as a PAN"이라 선언 | 프로브 재현: `post_form("/ara/selectListAra10007_n.do", {tkRetPwd, dscp_no, dscp_pwd, hmpgPwdCphd})`는 그대로 전송되고 같은 라우트에 `stlCrCrdNo1`을 넣으면 거부된다 — 비대칭 확인. **그러나 게이트에 구멍은 없다**: `CARD_SECRET_FIELDS`는 카드비밀 게이트이고 카드비밀에 대해 뚫린 곳이 없으며, 출하된 어떤 메서드도 이 값들을 엉뚱한 라우트에 싣지 않는다(`tkRetPwd`는 `payloads.py:2208`,`:2226` 환불 폼에서만). **하드닝 제안**: `CREDENTIAL_SECRET_FIELDS`를 만들어 각 값이 자기 라우트에서만 허용되게 |
| D-17 | `READ_ONLY_ROUTES`는 개수만 canary, mutation은 정확집합 | `tests/test_safety.py:166` `assert len(READ_ONLY_ROUTES) == 26` 대 `tests/test_mutation_live_paths.py:573-590` 정확집합 canary("do NOT 'fix' the test" 주석 포함) | **"라우트 하나를 빼고 하나를 넣으면 어떤 테스트도 안 깨진다"는 3차에서 반증됨** — `safety.py:887`이 `route not in READ_ONLY_ROUTES: raise`이므로 테스트가 실제 호출하는 라우트는 그 테스트가 핀이 된다. 26개 전수 스크립트 검사 결과 **모든 라우트가 최소 3개 테스트 파일에서 참조**(UNPINNED=[]). 명시 멤버십 단언도 존재(`test_reservation_list.py:353`, `test_discount_reads.py` 등). **정확집합 canary 추가는 여전히 권장(스타일 통일)** |
| D-18 | `STLB_TRAIN_CLASS_NAMES`의 16/18/19에 저장소 근거 없음 | `payloads.py:887` `"16":"KTX-이음"`, `:889` `"18":"ITX-마음"`, `:890` `"19":"KTX-청룡"`; 주석 `payloads.py:869-872`는 "lifted verbatim from the LIVE search page served on 2026-07-26"이라 주장 | `sub/main.html:622-636` `getStlbTrnClsfCdNm`는 정확히 13개(00–10,15,17)이고 나머지는 `return ""`. `commCode.js`의 `stlbTrnClsfCd` 그룹도 프로그램 추출 결과 동일 13개. 저장소 전체 grep에서 세 이름은 `payloads.py` 3줄에만 hit — `docs/`·`CHANGELOG.md`·`tests/fixtures/` 어디에도 없음. **SRT(`"17"`)에는 영향 없음.** 라이브 페이지 발췌를 fixture/docs로 남기거나 세 값을 제거 |

---

## 5. 의도된 제외 — 결함이 아님

### 5.1 사용자가 명시적으로 제외한 범위

- **단체예약(그룹예약).** `Arc06014`(예약), `Ard02018`(단체 결제진입), `Ata01033`(단체 결제 JSON).
  `docs/IMPLEMENTATION_PROGRESS.md`에 "단체 (group) booking: removed"로 기록됨.
  **단체 검색(read-only)은 구현되어 있고 정상 동작한다** — `payloads.group_search_ajax_payload`,
  `tests/fixtures/group_search_success.json`(2026-07-26 라이브 10행). 감사 중 발견된 단체 관련
  항목은 전부 이 제외에 해당하며 **결함으로 집계하지 않았다.**

### 5.2 구조적으로 HTTP 클라이언트가 재현할 수 없는 것

| 대상 | 사유 |
|---|---|
| FIDO/OnePass 생체인증 (`requestServiceRegist/Release/Auth`) | `fido.srail.co.kr` UAF 프로토콜 + 하드웨어 attestation. `com/raonsecure/**` SDK 전용 |
| SNS 로그인 (Google/Kakao) | 네이티브 SDK가 `{id,type}`만 콜백. 서버 엔드포인트가 번들·jadx 어디에도 없음 |
| 푸시 디바이스 등록 (`regDevice`/`unRegDevice`) | H2O SmartBroker **바이너리 TCP** 프로토콜(`push.srail.co.kr:3101`), HTTP/JSON 아님 |
| TransKey 보안키패드 (`showTransKey`) | 로그인 UI의 네이티브 입력 보안. 실제 와이어 필드 `hmpgPwdCphd`는 평문이므로 라이브러리에 불필요 |
| 네이티브 브릿지 8종 (`mkQRCode`/`takePicture`/`selectPicture`/`pkgVersion`/`getNetworkAddress`/`callExtApp`/`pnrDataSave`/`pnrDataLoad`) | `common/bridge.js` — WebView 전용 |
| `Ard02017`/`Ard02018` WebView 결제 진입 | 앱의 PG/TransKey/FIDO 경로. 라이브러리는 JSON `Ata09036`으로 대체 구현(`safety.py:420-424`) |
| 코레일톡 상호연동 지정열차 검색 (`gs_koYn`) | 진입점이 `getDataBridge(toKrailFlag)` 딥링크(`SRWebActivity.java:2004-2022`) — HTTP만으로는 진입 자체가 불가 |

### 5.3 앱에 존재하지 않거나 죽은 코드

| 대상 | 사유 |
|---|---|
| 마일리지(적립·조회·사용) | `analysis/**`·`docs/**`·`src/**`·`tests/fixtures/**` 전수 대소문자 무시 grep **0건**. `포인트`는 전부 OK캐쉬백 결제수단 문맥. 코레일과 달리 SRT 프로토콜에 이 기능이 없다 |
| 위약금·부분환불 필드 | §2.6 참조 — 요청·응답 어디에도 수수료 금액이나 승객별 선택 필드 없음. **확인된 부재** |
| 정기승차권 / SRT 여행상품 | `sub/main.html:426,700,701,707,708`, `sub/ticketList.html:380`에 메뉴 라벨만 있고 `href="#"`/`onclick=""`로 비활성. 엔드포인트 근거 0 |
| `eventTrainInfo.js` | 2018/03 만료 이벤트 하드코딩, `getEventTrainInfo` 소비자 0 — 죽은 코드 |
| `Ata01032`(할인상세) | 런타임 HTTP 500 |
| `Ara10h01` | 주석 처리된 죽은 Nexacro 게이트웨이(`ara1001l.js:254-278`) |
| 특실 예약대기 | `ara1001l.js:1025-1083` 전수 추적 결과 `sprmRsvPsbImg`가 `_S`로 재작성되는 경로가 **한 곳도 없음**. `:1122`,`:1127`의 방어 조건은 **도달 불가능한 죽은 코드**. 라이브러리의 일반실 강제가 srtgo보다 앱 진실에 더 가깝다 |
| `/cms/article/*.do`, `/neo/common/rest/JongURi/view.do` | 예매호스트가 아닌 `www.srail.co.kr`/dev 자산 — 범위 밖 |
| 로그아웃 서버 호출 | 3차례 선행감사(`impl-audit`, `reverify`, `reverify2`)가 "deliberate read-only design"으로 확정. `client.py:161-162`가 로컬 쿠키만 클리어 |

### 5.4 안전 모델은 설계다 (결함 아님)

`dry_run` 기본 True, `MutationConsent` 카테고리 게이트, `SRT_LIVE_MUTATION_CATEGORIES` kill switch,
쿠폰의 "빌드·프리뷰는 되되 전송은 막음", 카드정보 마스킹, `CARD_SECRET_FIELDS` 데이터 게이트,
`_assert_empty_body_request`, `_assert_exact_form_contract` — 전부 의도된 설계이며
**2차·3차 프로브가 우회 경로를 찾지 못했다.** 이번 감사가 제안하는 어떤 수정도 이 게이트를
느슨하게 하지 않는다(H-1의 권고 (b)는 오히려 조인다).

---

## 6. 판단 보류 — 근거 확인 불가로 남은 것

라이브 캡처 1회면 대부분 닫힌다. 우선순위 순.

| # | 항목 | 무엇이 미확인인가 | 닫는 방법 |
|---|---|---|---|
| U-1 | `get_reservations` **populated 행 스키마** (특히 `payListMap` 타입) | `card_payment_payload`가 요구하는 4필드(`received_amount`/`ticket_special_number`/`departure_time`/`arrival_time`)가 문서화된 이름·컨테이너로 오는지 한 번도 실측되지 않았다. 다르게 오면 파서가 조용히 `None`을 만들고(`parsers.py:2107-2140`) 빌더가 `ValueError`(`payloads.py:2082-2091`) — **`dry_run=True` 프리뷰 단계에서도** 발생(`client.py:1689-1703`이 `:1706`의 dry_run 분기보다 먼저 폼을 빌드). 방향은 **fail-closed**이며 `client.py:1687-1689`가 이를 **의도로 명시**한다. L-2의 근본 원인이기도 하다 | 실제 예약이 있는 계정으로 `get_reservations` 1회 캡처. **`payListMap` 행의 값 타입을 반드시 기록할 것** |
| U-2 | `reserve_transfer` 전체 | 한 번도 실서버에 전송된 적 없음. slot-2 23필드 중 5개(`stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`, `dptStnRunOrdr2`, `arvStnRunOrdr2`)는 `analysis/` 전체 grep **0건**의 순수 추론(`payloads.py:152-189`가 'inferred' 등급으로 이미 표시). `reserveType="11"`이 환승에도 그대로 적용되는지(`jrnyTpCd`를 따라 `"14"`여야 하는지)도 미확인. `client.py:1379-1394` docstring이 "NOT LIVE-VERIFIED"로 명시 | `docs/VERIFICATION.md`에 이미 안내된 절차대로 동대구→광주송정 등 환승 전용 구간 1회 실행 |
| U-3 | standby reserve 응답 형상 | jobId=1102로 실제 전송된 적 없음(`client.py:1203-1204`가 자인). 파서는 이 시나리오를 **겨냥해 설계**되어 있어(`parsers.py:1496-1535` salvage, docstring `:1508`이 "a missing trainListMap seat number"를 예시로 듦) 홀드가 고아가 될 위험은 설계상 낮으나 **추론된 방어이지 실측된 방어가 아니다** | standby reserve 1건 전송 후 응답 shape(특히 `trainListMap`/`reservListMap` 존재 여부, `mblPhone` 유무)을 fixture로 고정 |
| U-4 | `Ata01135`(L-7) / `Ard02019`(§3.9) 실존 | 둘 다 번들 0-hit + srtgo 단독출처. 같은 그룹 4/6이 라이브 확정된 점을 보면 부재 근거로 쓸 수 없다 | 각 1회 캡처 |
| U-5 | cancel 폼의 "앱 자신의 인라인 응답이 증명한다"는 부가 주장 | `cncConfirm`은 산문 4곳(`payloads.py:1807`, `parsers.py:1710`, `VERIFICATION.md:1288`, `tests/test_live_response_shapes.py:597`)에만 있고 `analysis/`·fixture 0-hit. 단 `tests/fixtures/ticket_list_expired_session.html:23-30`이 스스로 "REDACTED excerpt … The real body was 153161 bytes"라 선언하므로 2,308바이트 발췌본의 침묵은 **반증이 아니다**. cancel 라우트·필드·응답봉투 자체는 2026-07-25 실취소로 독립 뒷받침됨 | 인증된 `/atc/selectListAtc14017_n.do` 응답의 `cncConfirm` 발췌를 fixture로 저장 |
| U-6 | `STLB_TRAIN_CLASS_NAMES` 16/18/19 (D-18) | "verbatim" 주장이 저장소 아티팩트로 재현 불가. SRT에는 무영향 | 라이브 검색 페이지 발췌 저장 또는 세 값 제거 |
| U-7 | MY SRT 서버렌더 메뉴의 미등록 라우트 | fixture 22개 전수 스캔 결과 `.do` 참조 **10종 전부 이미 등록됨**, 미등록 0건. 그러나 fixture가 전부 트리밍돼 메뉴 마크업이 없다(`public_discount_search_page.html` 7,666B vs 라이브 원본 206,268B; `discount_coupons_empty.html` 6,102B vs 77,056B). **"신규 라우트가 없다"는 증명이 아니라 "저장소 안에서는 더 캘 수 없다"는 확정** | 인증 세션으로 아무 페이지나 1회 받아 메뉴 블록 `pageMove(...)` 전수를 fixture로 보존 |
| U-8 | 로그인→결제 종단 테스트 부재 | `tests/fixtures/login_success.json`은 `{"userMap":{"RTNCD","MSG","CUST_NM"}}`로 **`MB_CRD_NO`가 없다.** 결제 테스트는 `SrtSession(user_map={'MB_CRD_NO':…})`를 직접 주입해 `login()`을 건너뛴다(`tests/test_payment_mutation.py:133`,`:489-500`). `test_mutation_scripts.py:735-759`의 E2E 라우터에도 결제 라우트가 없다. 실서버 동작은 2026-07-26 라이브 결제런으로 간접 실증(가드 `client.py:1679-1684`가 정상 동작) — **현재 버그 가능성은 낮으나 회귀 방지망에 구멍** | `login_success.json`에 `MB_CRD_NO` 추가 + `login()`→`pay_with_card()`가 `mbCrdNo`를 채우는 종단 테스트 1개 |
| U-9 | 포인트/전자지갑/복합결제 wire 필드명 (§3.7) | `messages.js:28-40`이 기능 실재를 증언하지만 소비 페이지가 서버렌더링이라 파라미터명 확인 불가. `payloads.py:1929-1930`에 대체수단 wire 코드는 이미 기록됨(`02` 신용카드 / `11` 전자지갑 / `12` 포인트; `crdInpWayCd1` `@` vs `""`)이고 `payloads.py:2088-2091`이 단일수단 제약 이유를 명시("would invent a split this form cannot express") | 결제 페이지 라이브 캡처 |
| U-10 | 공공할인 검색의 **응답 효과** | 요청 형태(23필드 고정계약)는 검증됐으나 승인된 공공할인 계정이 없어 응답을 못 봄. 코드 docstring이 이미 명시 | 승인 계정 확보 시 1회 |

---

## 7. 권고 작업 순서

우선순위 기준: **실행으로 재현된 것 + 돈/예약 상태에 닿는 것**이 먼저.

### 1단계 — 동작 결함 (재현됨)

1. **`parsers.py:1113-1117` `normalize_result_row` 수정 + 양쪽 컨테이너 테스트 추가** (M-1)
   → 4건(S7-01/P2CRO-06/P2INC-09/P2INC-08)을 **한 줄**로 닫는다. 2회 독립 실행 재현.
   환불·취소·결제 세 파서 전부에 영향. 함께 `_declares_a_declared_failure`(`parsers.py:1492`)를
   `resultMap` 직접 읽기로 통일.
2. **`consent.py` 카드종류 게이트** (H-1) → high 2건을 한 번에 닫는다.
   권고는 **(b1) `fake_card_only` 기본값 `False`** — 문서가 자동으로 참이 되고 PAN 불투명
   원칙을 건드리지 않는다. **`tests/test_payment_mutation.py:605-611`/`:615-618`을 반드시 함께
   갱신**할 것. 테스트 PAN 검증(b2)은 `models.py:777-780`과 충돌하므로 권고하지 않는다.
3. **`payloads.py:1073-1093` — `None` 가용성이 `GENERAL_FIRST`를 특실로 승격하지 않게** (M-2)
   → 라이브 `null`로 실제 도달하며 `search_trains()`→`reserve()` 공개 경로만으로 재현된다.
   `reserve_transfer`는 두 레그 모두 영향.
4. **`rqSeatAttCd1/2` 파라미터화** (M-3) → 조용한 강등을 먼저 막고(거부), 그 다음 휠체어 값 배선.
5. **`SeatGrid` 캐빈 ↔ `psrmClCd1` 연결** (M-4) → 좌석지정 예약의 캐빈 불일치 차단.
6. **`SrtReservationHold.journey_count` + `recover_hold.py --journey-count`** (L-1)
   → 환승 홀드 복구 경로를 표현 가능하게. `payloads.py:1840-1842`의 거짓 일반화 삭제.

### 2단계 — 사전검증·일관성 (저비용)

7. `TrainSearchQuery.__post_init__`에 동일역 검사(L-3) + 개인검색 상한(L-4).
8. `parsers.py` 시각/역코드 zero-fill(L-2) — U-1 캡처 전이라도 방어적으로 넣을 가치가 있다.
9. `SrtSession.phone_number`(`MBL_PHONE`) 파생 속성 + `redaction.py` 등록(L-8) → L-7의 선행작업.
10. `trnGpCd1/2`를 행 값 우선으로(L-9), 왕복 게이트 2건(L-5, L-6) — 근거 확정 후 판단.

### 3단계 — 문서·인용 배치 정정 (동작 무관, 한 커밋)

11. **D-2 `psgTpCd` 해독표**를 먼저 (역방향 수정 위험이 가장 크다).
12. **D-1 `EXCLUDED_API_DOMAINS`** + 테스트명 (3중 독립 확인, `RELEASE_GAP_PLAN`이 이미 지시).
13. **L-11 populated 행 6곳 UNVERIFIED 서술 갱신** + `VERIFICATION.md`에 캡처 기록.
14. 인용 정정 묶음: D-3(`:1607`→`:1611` 4곳), D-4(`session.py:57-60`),
    D-5(Manifest 트리 접두사), D-7(`models.py:44`), D-8(netfunnel 문자 오프셋 표기),
    D-6(`SrtReservationSummary` 라벨), D-9(`safety.py:537-538` "four"→"five"),
    D-14(`messages.js` 인용 추가), D-15(`payloads.py:554` 주석 한 줄).
15. 공개표면: D-10(쿠폰 타입), D-11(`reserve()` docstring 경고).
16. 하드닝(선택): D-16(`CREDENTIAL_SECRET_FIELDS`), D-17(`READ_ONLY_ROUTES` 정확집합 canary),
    D-18(16/18/19 근거 확보 또는 제거).

### 4단계 — 라이브 캡처 백로그 (확인불가 해소)

우선순위: **U-1 → U-3 → U-2 → U-4 → U-8 → U-5 → U-7 → U-6/U-9/U-10**

U-1(populated 예약행, `payListMap` 타입 포함) 하나가 L-2·L-10·D-11·U-1을 동시에 닫으므로
투자 대비 회수가 가장 크다. U-8(종단 테스트)은 캡처 없이도 지금 할 수 있다.

---

## 부록 A — 3차에서 기각된 8건 (다시 살리지 말 것)

이 8건은 2차까지 findings로 올라왔으나 3차 반증에서 무너졌다. **"없는 것"이나 "수정 필요"로
재등장시키지 말 것.** 특히 A-2와 A-6은 "누락 렌즈"에서 다시 잡히기 쉽다.

| # | 기각된 주장 | 기각 사유 |
|---|---|---|
| A-1 | S1-03 로그아웃이 서버 엔드포인트를 호출하지 않음 | 이미 3차례 선행감사가 "deliberate read-only design"으로 확정 |
| A-2 | S2-01 `exceptStation.js` 인접역 제외표 미구현 | `getStationFlag` 호출부가 **번들 전체 0-hit** — 앱이 이 표를 실제로 쓴다는 증거가 없다. 게다가 표 자체에 코드↔이름 불일치가 있다(`:31` `0020`을 "공주"라 라벨하지만 `0020`은 부산) — **`stations.py`를 이 표에 맞추면 오히려 틀려진다** |
| A-3 | S2-05 `*RsvPsbImg`/`*RsvPsbColor` 타입 필드 미승격 | 데이터 손실 없음(`raw=row` 보존). `payloads._standby_row_image`가 `.raw`에서 읽는 것이 의도된 계약 |
| A-4 | S4-01 환승 좌석지정 미지원의 근거 인용이 환승 특이적이 아님 | 결론(미지원)은 옳고, 근거 인용 문제는 doc-drift로도 유지할 만큼의 실체가 없다고 3차가 판단 |
| A-5 | S8-02 마일리지 미구현 | SRT 앱/프로토콜에 기능 자체가 없음(전수 grep 0건) |
| A-6 | P2MIS-08 코레일톡 상호연동 지정열차 검색(`gs_koYn`) | 진입점이 딥링크(`getDataBridge`)라 HTTP 클라이언트로 진입 불가 |
| A-7 | P2SAF-03 `post_mutation_form`이 "유일한 전송 경로"라는 주장이 거짓 | 3차 검증에서 무너짐 |
| A-8 | P2SAF-04 kill switch가 카테고리 단위라 라이브 미검증 형상 3개가 reserve를 타고 나감 | 3차 검증에서 무너짐 |

---

## 부록 B — 이 감사가 확인한 "결함 없음" (재조사 방지)

같은 지점을 다시 파지 않도록, 의심했으나 **재검증 결과 정상이었던** 항목을 남긴다.

- **문자열/숫자 타입 불일치** — 이 코드베이스에서 6번 재발한 결함류라 2차가 전수 재검했고
  **이번엔 0건**. 앱은 `$("#rsvForm").serialize()`(`ara1001l.js:1550`)로 전 필드를 문자열화하고
  라이브러리도 전 필드를 `str(...)`로 보낸다.
- **정적 코드테이블 전수 diff** — 역 344/344, 할인종류 173/173 완전 일치.
- **코드 인용 268건 줄범위 기계검사** — 범위 이탈 2건뿐이고 둘 다 표기체계 문제(D-5, D-8).
- **수치 핀** — 과거 "72 public methods" 류의 stale canary 재발 없음.
- **안전게이트 우회** — 2차 안전렌즈·교차검증렌즈가 각각 프로브를 실행해 전수 확인, 구멍 0건.
- **카드정보 마스킹** — 실제 페이로드 빌드 + `redact_*` 실행으로 확인, 우회 경로 0건.
  (`CARD_RE`가 구분자 없는 21자리 연속 숫자를 놓치는 것은 `redaction.py` 자체 주석이 이미 명시한
  한계이며 필드명 기반 마스킹이 1차 방어이므로 실질 우회로 보지 않음.)
- **`PassengerCounts.total`의 유아 포함** — 앱의 `totPrnb`가 어린이 슬롯 fold **이후** 계산되는 것과
  일치. 2026-07-26 라이브 에코(`adult=1,infant=1` → `totalPessnger=2`)로 실측 확인.
- **`_release_netfunnel_slots` 키 누적** — `pop()`이 `try` 이전이라 실패해도 누적되지 않음.
- **`reserveType="11"`** — 개인예약에만 정확히 부착, 대기에서 DROP. 회귀 테스트 고정됨.
- **카드결제 31키** — `srtgo_plus/srt.py:1184-1216`과 이름·순서·상수값 전수 일치, 누락 0.
- **`rsvWaitPsbCd` vs `gnrmRsvPsbImg`** — 의도적 이탈이며 `payloads.py:197-202`가 이유를 설명하고
  `parsers.py:2530`이 원값을 raw로 보존. 앱은 `rsvWaitPsbCd`를 어디서도 읽지 않는다(0-hit).
- **User-Agent 공백 없는 접미사** — 오타 아니라 `SRWebActivity.java:2642-2649` 정확 재현.
