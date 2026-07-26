# SRT 3차 검증자 (verifier-3) — 16건 판정

대상: `/Users/yakisoba/Documents/GitHub/srt-mobile-api`
검증일: 2026-07-27
방법: 인용된 file:line 을 **전부 직접 열어** 확인. 앱 근거는 APK 에 그대로 실린
`analysis/apktool/assets/offline/**`(디컴파일 산출물이 아니라 원본 JS 에셋이므로 authoritative),
jadx Java 근거 1건은 smali 로 교차확인. 저장소 파일은 하나도 수정하지 않았고 git 상태도
바꾸지 않았다(`log`/`show`/`blame` 읽기 전용만 사용).

## 판정 규약
- **CONFIRMED** — 실재하는 결함/드리프트이며 조치 대상.
- **REFUTED** — 조치 대상이 아님. *사실관계가 틀렸다는 뜻만은 아니다.* 여기서는
  "사실은 검증됐으나 결함이 아니다(의도된 설계 · 도달 불가 표면 · 존재하지 않는 기능)"를 포함하며
  해당 항목 첫 줄에 명시했다.
- **PARTIAL** — 사실관계는 맞으나 심각도 또는 결론(무엇이 옳은가 / 왜 문제인가)이 틀림.
- **UNVERIFIABLE** — 근거 확인 불가. **이번에 해당 항목 없음**(16건 모두 양쪽 근거를 직접 확인).

## 중복 쌍 — 부모 에이전트는 이중 계상하지 말 것
- **S7-02 ≡ P2CRO-07** (예약목록 populated row 모순) → 독립 재발견 2건, 결함 1건. 판정·심각도 동일.
- **P2SAF-10 ≡ P2CRO-08** (`EXCLUDED_API_DOMAINS` 드리프트) → 독립 재발견 2건, 결함 1건. 판정·심각도 동일.

## 요약표

| ID | 판정 | 원 심각도 | 보정 심각도 |
|---|---|---|---|
| S1-03 | REFUTED | info | info |
| S2-04 | CONFIRMED | low | low |
| S3-02 | PARTIAL | low | low |
| S5-01 | PARTIAL | medium | low |
| S6-02 | CONFIRMED | low | low |
| S7-02 | PARTIAL | medium | low |
| S8-02 | REFUTED | info | info |
| P2MIS-03 | CONFIRMED | low | low |
| P2MIS-08 | REFUTED | info | info |
| P2INC-03 | PARTIAL | medium | low |
| P2INC-07 | PARTIAL | low | low |
| P2SAF-02 | PARTIAL | high | low |
| P2SAF-06 | CONFIRMED | low | low |
| P2SAF-10 | CONFIRMED | info | low |
| P2CRO-07 | PARTIAL | medium | low |
| P2CRO-08 | CONFIRMED | low | low |

**16건 중 critical/high 는 하나도 남지 않았다.** 유일한 high 신고(P2SAF-02)는 안전게이트
관통이 아니라 문서 과장으로 확인됐다.

---

## S1-03 — 로그아웃 서버 미호출 → **REFUTED / info**

사실관계는 검증됨, 결함 아님, 조치 불요.

- `analysis/apktool/assets/offline/sub/main.html:455` =
  `<form id="form1" action="/srail-app/login/loginOut.do" method="POST" data-ajax="false">` — 인용 정확.
- `src/srt_mobile_api/client.py:161-162` = `def logout(self) -> None:` / `self.clear_session()` —
  인용 정확, 서버 요청 없음.
- 주장이 든 "경로 불일치"는 결함이 아니라 서블릿 컨텍스트 접두사 차이다.
  `docs/analysis/ref-srtgo_plus.md:99` 이 srtgo `srt.py:92,745` 를 `/login/loginOut.do` 로 기록하고
  "NOT in our routes" 로 이미 분류해 뒀다. 라이브러리는 `config.py` 의 `APP_ORIGIN` 기준으로
  접두사 없는 경로를 쓴다(`client.py:174` `/main/main.do`).
- 안전모델 구멍 아님: 로그아웃은 `safety.py:520-522`
  `SRT_LIVE_MUTATION_CATEGORIES = {"reserve","cancel","payment","refund"}` 밖이다.
- 주장 자신이 "새 결함이 아니며 정보성으로만 기록"이라 적었다.

---

## S2-04 — 개인검색 10명 이상 상한 미검증 → **CONFIRMED / low**

- 앱: 인용은 `ara0101v.js:559-563` 이나 실제 위치는 **:562-567**(3줄 드리프트, 내용 존재).
  ```
  562:  } else { // 단체 선택 하지 않은 경우
  563:      if (lfn_getRsv("totPrnb") > 9)  //10명 이상인 경우
  565:          srtAlertBoxDivShow("알림", "10매 이상은 단체예약입니다. \n단체여부를 확인하여 주십시오.", null, null);
  566:          return;
  ```
  단체 하한은 `:549-555` 로 확인(`totPrnb < 10` 이면 차단).
- 라이브러리: `payloads.py:670-674` 는 하한만 강제. 개인검색 경로에는 상한이 없다
  (`payloads.py:577-578` 은 `totPrnb`/`totPrnbNm` 을 그대로 직렬화만 하고,
  `models.py:164` `PassengerCounts.total` 에도 상한 없음).
- **결정적 근거 — 라이브러리가 규칙을 알고도 한쪽만 구현했다.** `payloads.py:210-215`:
  > "The minimum party size the app enforces for a 단체 (group) search, **and the maximum it
  > allows without one**. ara0101v.js:549-566 … So 10 is a real, client-enforced boundary
  > **in both directions, not a UI hint**."

  이어 `:217` "The one consumer is group_search_ajax_payload." — 즉 상한은 문서화만 되고
  소비자가 없다. 의도적 배제라는 서술은 어디에도 없다.
- 서버 거부 여부는 미확인이고 영향은 조회 1건에 한정 → low 유지.

---

## S3-02 — 왕복예약 국회의원 후급(mbCrdNo "11") 배제 미재현 → **PARTIAL / low**

사실관계는 전부 정확하나, "결함"으로서의 강도가 과대평가됐다.

- 앱: `ara0101v.js:317-326` 축자 일치.
  `case "chk_rtrp"`(317) → `mbCrdNo.substr(0,2) == "11"`(321) → `callbackChkRtrp()`(322, 체크 해제)
  → 안내문(323) → `return`(325).
- 라이브러리: `models.py:38-61` 인용 정확 — `membership_number` 프로퍼티가 `:51-52` 에서
  `ara0101v.js:319,321` 과 `"11"` prefix 국회의원 후급을 그대로 인용한다.
  `payloads.py:1218-1497` `personal_reservation_payload` 에는 상호검증이 없다
  (`grep -n mbCrdNo payloads.py` → 1913/2022/2061/2077/2094, **전부 카드결제 문맥**).
  `:1226` `round_trip: bool = False`, `:1453` `"rtnDv": "1" if round_trip else "0"` 로 그대로 전송된다.
- **왜 PARTIAL 인가**
  1. 앱 문구가 와이어 규칙이 아니라 **할인 자격 안내**다: "왕복승차권은 국회의원 후급 적용으로
     이용하실 수 없습니다 … 가는 열차와 오는 열차를 각각 편도로 예매 후 발권하여 주시기 바랍니다."
     서버가 왕복 자체를 거부한다는 근거는 저장소에 없다.
  2. 가드 위치가 **조회 화면 체크박스**(ara0101v = 조회 페이지)이지 예약 전송 지점이 아니다.
  3. `personal_reservation_payload` 시그니처에 membership_number 인자가 아예 없다.
     같은 파일 `:1326-1337` 은 `designated_seats+standby`, `designated_seats+round_trip` 처럼
     **증거가 있는 조합**만 거부하는 방침을 명시한다.
- 실재하는 비대칭이지만 영향 계정은 `mbCrdNo` 가 `"11"` 로 시작하는 후급회원에 한정 → low.

---

## S5-01 — 예약대기 SMS/좌석등급변경 동의(Ata01135) 미구현 → **PARTIAL / low (medium 과대)**

사실관계 확인:
- `grep -rn "Ata01135" analysis/` → **0건**(직접 재실행). `src/` 는 `client.py:1224` 주석 1건뿐, 메서드 없음.
- `client.py:1224-1227` 원문 확인: "srtgo additionally POSTs `/ata/selectListAta01135_n.do`
  afterwards to set SMS/seat-change options (srt.py:1014-1051); that route is 0-hit in our
  v2.0.41 bundle and has no equivalent in it, so it is **NOT implemented** and a standby entry
  made here simply carries the server's defaults."
- `docs/analysis/cross-validation-2026-07-21.md:370` 인용 정확 — 6개 중 4개(cancel 07-25,
  payment/reserve-info/refund 07-26)가 라이브로 닫혔고 `Ata01135`/`Ard02019` 만 남았다.

**심각도 근거가 무너지는 지점 — 참조 구현을 직접 열어 확인:**
`/Users/yakisoba/Documents/GitHub/srtgo_plus/srtgo/srt.py:1014-1051`
`reserve_standby_option_settings()` 는 **독립 public 메서드**이고, 예약 경로(`srt.py:999-1012`)는
reserve POST 직후 `get_reservations()` 로 티켓을 찾아 반환하고 끝난다 — 이 메서드를 호출하지 않는다.
독스트링 예시(`:1032-1035`)도 사용자가 `reserve_standby()` **후에 따로** 호출하는 형태다.

→ `reserve(standby=True)` 의 와이어 흐름은 참조 구현과 **다르지 않다.** 빠진 것은 인접한
**선택적** 알림설정이고, 그마저 번들 0-hit·라이브 미검증이며(`docs/VERIFICATION.md:1317`,
`:1657` — 예약대기 표면 자체가 미검증), 커밋 `d7698d8`("SRT never offered 예약대기 across ten
searches")가 시사하듯 SRT 는 예약대기를 거의 제공하지 않는다.
또 "통보를 못 받아 전환 기회를 놓친다"는 **서버 기본값이 SMS off** 라는 미증명 가정에 의존한다.
공개 기록 위치: `client.py:1224-1227`, `docs/VERIFICATION.md:1335`,
`docs/IMPLEMENTATION_PROGRESS.md:264,1047`, `docs/RELEASE_GAP_PLAN.md:63,234,1001,1055`,
`docs/analysis/ref-srtgo_plus.md:105`.

→ 공백 존재 CONFIRMED, "예약대기 흐름이 앱/참조와 어긋난다"는 함의 REFUTED → PARTIAL, low.

---

## S6-02 — `SrtReservationSummary` docstring 컨테이너 라벨 역전 → **CONFIRMED / low**

- `models.py:610-612` 원문: "Built by zipping two parallel containers by index —
  ``trainListMap[i]`` (**journey identity**) with ``payListMap[i]`` (**settlement state**)".
- 실제 배치(`models.py:634-649` 인라인 주석 + `parsers.py:2109-2145` 파서, 둘은 서로 일치):
  - `trainListMap` → `rcvdAmt`(2109-2111), `tkSpecNum`(2112-2114), `seatNum`(2115-2117)
    = 금액·매수·좌석
  - `payListMap` → `stlbTrnClsfCd`(2118), `trnNo`(2121), `dptDt`(2122), `dptTm`(2123),
    `dptRsStnCd`(2124), `arvTm`(2127), `arvRsStnCd`(2128) = **여정 식별자**
    + `iseLmtDt`(2131), `iseLmtTm`, `stlFlg` = 정산 상태
- 즉 "journey identity" 는 payListMap 쪽이고 라벨이 뒤집혀 읽힌다. 주장 정확.
- 파싱 버그 없음, `card_payment_payload` 도 올바른 컨테이너에서 읽는다 → 순수 문서 드리프트 low.

---

## S7-02 — 예약목록 populated row 라이브검증 여부 내부 모순 → **PARTIAL / low (medium 과대)**

**모순 자체는 축자 확인됨:**
- `parsers.py:1946-1958`: "LIVE 2026-07-26 settled what the non-empty row looks like … 
  `{"pnrNo": "3202607...", "rcvdAmt": 7500, "jrnyCnt": 1, "tkSpecNum": 1, "stlFlg": "N", "rsvChgTno": 0}`"
- `parsers.py:2043-2046`: "The NON-EMPTY shape remains **UNVERIFIED** by this repository …
  the containers exist in the verified response, the row fields do not."
- 같은 취지 반복: `models.py:618-627`, `client.py:1650-1655`, `payloads.py:2049-2053`,
  `tests/test_reservation_list.py`, `docs/IMPLEMENTATION_PROGRESS.md`, `docs/VERIFICATION.md:297-299`.

**그러나 "어느 쪽이 맞는지 저장소 아티팩트만으로는 판정 불가"는 틀렸다 — 결정 가능하다.**
1. `git blame`: `parsers.py:2043` = 커밋 `5db3567`(로그 #39, 예약목록 최초 구현),
   `parsers.py:1948` = 커밋 `9306e4c`(로그 #29, **2026-07-26 15:10:22 +0900**).
   → 1948 이 **더 나중** 서술이고 2043 은 갱신되지 않은 잔존물이다. 다수결은 신선도를 측정하지 못한다.
2. `git show 9306e4c` 커밋 메시지가 1차 증언이다:
   "LIVE 2026-07-26. The reservation list's populated row had never been observed … and the real
   one sends numbers … **a live card payment refused to build, reporting that the reservation
   carried no amount, on a reservation that plainly carried 7500.**"
   실패한 라이브 결제가 이 코드 변경을 강제했다 — 관측 없이는 나올 수 없는 서술이다.
3. 교차 확증: `client.py:1611-1619` 가 기록한 2026-07-26 라이브 결제 금액이 **7,500 KRW** 로
   `rcvdAmt: 7500` 과 일치한다.
4. `docs/VERIFICATION.md:297-299` 는 `713c591`(로그 #3, 9306e4c 보다 **뒤**)에서 작성됐지만
   새 관측이 아니라 오래된 문장을 옮겨 적은 것이다(같은 파일에 populated row 캡처 없음).
5. `tests/fixtures/` 에 캡처가 없다는 점은 "관측하지 않았다"의 증거가 아니다.
   `safety.py:924-927` SAFETY_STATEMENTS 가 "Do not store credentials, cookies, NetFunnel keys,
   raw response bodies, **PNRs**, or card-shaped values in the repository" 라고 금지한다.

→ 모순 지적 CONFIRMED, "1948이 이상값/판정 불가" 결론 REFUTED. 런타임 영향 0 → low.

---

## S8-02 — 마일리지 기능 전체 0-hit → **REFUTED / info**

사실관계는 검증됨, 결함 아님.
- `grep -rniE "마일리지|mileage|적립" analysis/ docs/ src/ tests/` → **0건**(직접 실행).
- 주장 자신이 "라이브러리 누락으로 분류하지 않는다"고 적었다. 결함 주장으로 성립하지 않음.

---

## P2MIS-03 — `psgTpCd` 해독표 문서 오류 → **CONFIRMED / low**

- 앱(권위): `analysis/apktool/assets/offline/js/commCode.js:54-88` 줄 단위 확인 —
  `1=어른(rmk 어른)`, `2=장애 1~3급(장13)`, `3=장애 4~6급(장46)`, `4=만 65세이상(경로)`,
  `5=만4~12세(어린이)`.
- 문서(틀림): `docs/analysis/full-api-analysis-2026-07-20.md:378` 및 `:453` 둘 다
  "1=어른,2=어린이,3=경로,4=중증장애,5=경증장애" — **2↔5, 3↔4 역전**.
- 문서가 댄 근거 `ara0101v.js:113-121` 을 직접 열었다: `:114-127` 은
  `"psgTpCd1" : "1",   //승객유형코드1` … `"psgTpCd5" : "",   //승객유형코드5` 뿐,
  **이름 매핑이 한 글자도 없다.** 근거가 주장을 뒷받침하지 않는 진짜 인용 실패다.
- 라이브러리(정상): `payloads.py:269-277` `PASSENGER_TYPE_CODES` =
  adult 1 / disability_1_to_3 2 / disability_4_to_6 3 / senior 4 / child_slot_count 5 / youth 6
  — commCode.js 와 일치. `:261-268` 에 2026-07-26 라이브 에코 검증 기록까지 있다.
- **주장의 부수 서술 1건은 반증된다**: "1차 8개 보고서 중 아무도 지적하지 않았다"는 새로움 주장.
  저장소 자신이 이미 2026-07-22 에 같은 줄을 같은 근거로 지적해 두었다 —
  `docs/analysis/impl-audit-reverify-2026-07-22.md:221-224`:
  > "`full-api-analysis-2026-07-20.md:378` states `psgTpCd` \"2=어린이, 3=경로, 4=중증장애,
  > 5=경증장애\", which is **wrong** per the decompiled `commCode.js` (2=장애1~3, 3=장애4~6,
  > 4=경로, 5=어린이). Our source uses the correct mapping."

  즉 신규 발견이 아니라 **알려진, 그러나 여전히 미수정인** 문서 드리프트다.
- 결함 자체(명세 취급 문서가 오늘도 틀린 표를 싣고 있음)는 실재하고 조치 대상이므로 CONFIRMED.
  코드는 정상이라 현재 운임 오류는 없다 → low.

---

## P2MIS-08 — `gs_koYn` 코레일톡 상호연동 지정열차 검색 → **REFUTED / info**

사실관계는 검증됨, 결함 아님, 조치 불요.
- `ara1001l.js:150-156` 인용 정확:
  `if (application.gs_koYn == "Y")`(150) → 페이징이면 `sTrnNo = ""`(152), 아니면
  `sTrnNo = lfn_getRsv("trnNo1")`(154). `:169 "trnNo": sTrnNo`. (`:819` 에 같은 분기가 주석 처리.)
- 진입점: `analysis/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:2004-2022`
  `G0(Bundle)` 가 인텐트 extra `"PARAM"` 을 읽어 `jSONObject.put("toKrailFlag", "1")`(2016) 후
  `javascript:getDataBridge(...)`(2017) 주입 — 안드로이드 네이티브 딥링크가 맞다.
- `payloads.py:637` `"trnNo": ""` 고정 — 인용 정확.
- `gs_koYn` 은 서버 렌더링 전역값이고 진입 수단이 네이티브 인텐트이므로 순수 HTTP 클라이언트가
  들어갈 수 있는 모드가 아니다. 주장 자신이 "도달 불가 표면이며 info로만 기록"이라 적었다.

---

## P2INC-03 — 예약목록 숫자→문자 정규화의 zero-padding 손실 → **PARTIAL / low (medium 과대)**

**메커니즘은 완전히 정확하다.** 3단계 전부 직접 확인:
1. `parsers.py:1967-1975` — `str(value)` 정규화, zero-padding 복원 없음:
   `1968: if isinstance(value, str): return value` /
   `1971: if isinstance(value, int) and not isinstance(value, bool): return str(value)`
2. `parsers.py:2123` `departure_time=_reservation_list_optional_string(pay_row, "dptTm")`,
   `:2127` `arrival_time=…(pay_row, "arvTm")` — 인용 정확.
3. `payloads.py:2082-2085`(인용 2087-2091 은 5줄 드리프트, 실체 동일):
   `_required_digits(reservation.departure_time, "departure_time", length=6)`.
   `_required_digits` 정의 `payloads.py:697-714` 는 `len(value) != length` 에서
   `ValueError: departure_time must contain exactly 6 digits`.
   → `dptTm=63000` 이 오면 `'63000'`(5자리) → 결제 빌드 거부. 재현 논리 성립, fail-closed 도 맞음.

**왜 low 로 내리는가**
- 트리거 전제(payListMap 시각 필드가 JSON 숫자)는 저장소에 관측 기록 0건이며,
  **현재 증거는 반대 방향**이다: 같은 서버의 검색 응답이 같은 필드명을 zero-padded 문자열로 보낸다 —
  `tests/fixtures/search_success.json` `dsOutput1[0]`: `dptTm='060000'`, `arvTm='083000'`
  (오전 6시 편도 열차인데 문자열, 앞자리 0 유지).
- 커밋 `9306e4c` 가 실제로 숫자로 관측한 것은 `rcvdAmt`/`jrnyCnt`/`tkSpecNum`/`rsvChgTno` 같은
  **수량**뿐이고 수량에는 padding 이 무의미하다.
- 2026-07-26 라이브 결제(`client.py:1611-1619`)는 실제 `payListMap` 행으로 31필드를 구성해
  성공했으므로 최소 1건은 6자리를 통과했다.
- 주장 중 **과장 1건**: `iseLmtTm`/`dptRsStnCd` 는 결제 본문에 들어가지 않는다.
  `card_payment_payload`(`payloads.py:2092-2124`)의 31필드는 `stlDmnDt, mbCrdNo, stlMnsSqno1,
  ststlGridcnt, totNewStlAmt, athnDvCd1, vanPwd1, crdVlidTrm1, stlMnsCd1, rsvChgTno, chgMcs,
  ismtMnthNum1, ctlDvCd, cgPsId, pnrNo, totPrnb, mnsStlAmt1, crdInpWayCd1, athnVal1, stlCrCrdNo1,
  jrnyCnt, strJobId, inrecmnsGridcnt, dptTm, arvTm, dptStnConsOrdr2, arvStnConsOrdr2, trnGpCd,
  pageNo, rowCnt, pageUrl` 로, reservation 에서 읽는 것은 `pnrNo/rcvdAmt/tkSpecNum/dptTm/arvTm` 뿐이다.

→ 실재하는 잠재 결함(수정도 자명: zfill 또는 문자열 보존)이지만 발현 조건 미증명 + fail-closed → low.

---

## P2INC-07 — `_optional_row_string` 이 숫자에 죽는다 → **PARTIAL / low**

**기계적 사실은 정확하다:**
- `parsers.py:2248-2251` 축자 일치 — present non-string → `raise SrtProtocolError("SRT search
  train row {key} must be a string")`. 예외가 필드 단위로 스코프되지 않아 `search_trains` 전체가
  죽는 것도 사실(`_optional_row_string_tuple` 2277-2280 도 동일).
- `parsers.py:2214-2237` `_row_field_is_absent` 는 `null` 만 완화. 인용 정확.
- `parsers.py:1967-1975` 는 같은 파일에서 숫자를 정규화 — 처리 차이 실재.
- 시간순도 주장에 유리: null 완화 커밋 `3ef1e5b`(2026-07-26 03:01:25) → "여섯 번째
  string/number 불일치" 커밋 `9306e4c`(2026-07-26 15:10:22). 규칙이 세워진 뒤 검색 파서는 재방문되지 않았다.

**그러나 "저장소 자신의 사후조치 규칙과 반대"라는 프레이밍은 틀렸다:**
- 그 규칙 문장은 "**new** parsers should accept either from the start" 로 **신규** 파서를 겨냥한
  전향적 지침이지 기존 파서 소급 지시가 아니다.
- 두 헬퍼의 차이는 **명시적·의도적이며 코드 옆에 이유가 적혀 있다.** `parsers.py:1960-1965`:
  > "Still **deliberately** more forgiving than :func:`_optional_row_string`, which raises on a
  > present non-string. Raising over one odd field would cost the caller the PNRs of every
  > reservation in the list, which is the outcome this read exists to prevent."

  그리고 `parsers.py:2233-2235`: "A present non-string that is NOT null still raises. A number or
  an object where a string belongs is a genuine protocol surprise."
  즉 "동일 위험을 반대로 처리"가 아니라 "두 read 의 실패 비용이 달라 의도적으로 다르게 둔다"이다.
- 검색 행 40건이 2026-07-26 라이브 관측(전부 문자열)됐다는 점은 주장 자신도 인정.

→ 잔존 견고성 리스크(한 컬럼이 숫자가 되면 검색 전체 사망, 예외 비스코프)는 실재하므로 low 유지.

---

## P2SAF-02 — `fake_card_only` 기본값이 "테스트카드만"을 강제하지 않음 → **PARTIAL / low (high 과대)**

**메커니즘은 확인됨 — 게이트가 하지 않는 일을 한다는 지적의 핵심은 옳다.**
- `consent.py:188-201` `require_card_kind_claim` 은 XOR 검사뿐:
  `188: if consent.fake_card_only and consent.real_card_acknowledged: raise` /
  `195: if not consent.fake_card_only and not consent.real_card_acknowledged: raise`.
  기본값 `(fake_card_only=True, real_card_acknowledged=False)` 는 두 분기 모두 통과한다.
- `payloads.py:2018-2124` `card_payment_payload` 는 `fake_card_only` 를 읽지 않는다
  (`grep -n fake_card_only payloads.py` → **0건**).
- `models.py:777-782` 는 Luhn 을 의도적으로 검사하지 않고 12~19자리 숫자면 통과
  (`4111111111111111` 통과). 사유가 명시돼 있다: "this library must never be the thing that
  tells a caller whether a card number is real."
- 경로: `client.py:1704`(dry_run 분기) → `1714 require_card_kind_claim` → `1719 post_mutation_form`
  → `http.py:403-404`. `MutationConsent(allow_payment=True, dry_run=False)` 만으로 실카드 형태 PAN 이
  전송된다. `fake_card_only` 가 검증 불가한 호출자 주장이라는 지적은 옳다.

**그러나 "세 곳의 문서가 강제한다고 서술한다"는 과장 — 실제 과장 서술은 1곳뿐이다.**
- 과장 O — `consent.py:13-18`: "so a payment preview **can only ever carry** a non-chargeable
  test card. A real, chargeable card **requires** the caller to invert BOTH flags explicitly."
  → 강제되지 않는 보장을 선언한다. **이 한 문단이 유일한 진짜 드리프트다.**
- 과장 X — `consent.py:78-82`: "The card-kind claim is a **requirement to send**, never a
  permission to" — 정확.
- 과장 X — `consent.py:170-186`(require_card_kind_claim 독스트링): "the consent must **STATE**,
  … two mutually exclusive **claims**" — 정확(검증이 아니라 진술 요구임을 명시).
- 과장 X — `http.py:329-333`: "requires an unambiguous card-kind **claim**" — 정확.
- 과장 X — `http.py:389-396`: "refuses to transmit one unless the consent **states**,
  unambiguously, WHICH kind of card it is" — 정확.
- 과장 X — `safety.py:494-498`: "keeps a separate card-kind gate (exactly one of …)" — 정확.

**심각도.** 게이트는 뚫리지 않았고(주장 자신도 인정) 동작은 설계대로다.
반대 방향 경고도 강하다: `client.py:1623` "a ``dry_run=False`` call **moves real money**".
이 감사 기준의 critical(게이트 관통/카드정보 유출)도 high(실서버 실패/오결과)도 아니며
"동작에는 지장 없는 문서 일관성 문제" → **low**.

---

## P2SAF-06 — `assert_mutation_route` docstring "four" vs 집합 5개 → **CONFIRMED / low**

- `safety.py:537-538` 축자: `"""Allow only the four evidenced state-changing routes (host "app", POST).`
- `safety.py:412-438` `SRT_MUTATION_ROUTES` 는 **5개**: `Arc05013`(:416), `Ard02045`(:419),
  `Ata09036`(:424), `Atc02063`(:428), `COUPON_REGISTRATION_PATH`(:436).
- `safety.py:546-556` 함수 본문은 `if route not in SRT_MUTATION_ROUTES: raise` 뿐이므로
  **실제로 5개를 허용한다.** "only the four" 는 개수로도 틀렸다.
  (coupon 은 여기가 아니라 `SRT_LIVE_MUTATION_CATEGORIES`(:520-522) 카테고리 게이트에서 막힌다.)
- 같은 파일 `safety.py:377-378` 은 "the **FIFTH** route added on 2026-07-26" 로 정확히 서술 —
  파일 내부 불일치.
- 동작 영향 없음(집합이 진실이고 함수는 집합을 본다) → low.

---

## P2SAF-10 — `EXCLUDED_API_DOMAINS` 재확인 → **CONFIRMED / low**

- `safety.py:911-922` 축자 확인: `{reservation, ard-payment-entry, payment, refund, cancellation,
  ata-detail, native-bridge, external-seatmap}`. 이 중 reservation/payment/refund/cancellation 은
  현재 구현·라이브 활성(`safety.py:520-522`)이므로 "제외"라는 명명이 사실과 반대다.
- 독립 grep(`src tests docs scripts`) 결과 **이 상수를 읽는 코드는 테스트 1곳뿐**:
  `tests/test_redaction_safety.py:16`(import), `:165-168`(assert). → 런타임 영향 0.
- 실제 전송 게이트는 `SRT_LIVE_MUTATION_CATEGORIES` / `assert_mutation_route`(:537) /
  `assert_mutation_route_category`(:559) 이며 그쪽은 정확하다 — 1차 결론 재확인.
- `docs/RELEASE_GAP_PLAN.md:1068` 이 이미 "retire it" 지시. 부수 확인: 문서들이 인용하는 행번호
  (`safety.py:180-192`, `:183`)는 이미 어긋났고, 그 시절 원소 `netfunnel-act-19` 는 현재 집합에 없다.
- 상수와 테스트가 현재와 반대되는 사실을 고정하고 있으므로 조치 대상 → low
  (원 신고 info 에서 상향, P2CRO-08 과 동일 심각도로 통일).

---

## P2CRO-07 — 예약목록 populated row 모순 (결제금액 출처) → **PARTIAL / low**

S7-02 과 **동일 사실**. 판정·심각도 동일하게 부여(위 S7-02 절의 근거 전부 적용).
추가 확인: `grep -rn "3202607" .` → 저장소 전체 0건, `tests/fixtures/` 에는
`reservation_list_empty.json` 하나뿐 — 주장의 이 부분은 맞다. 그러나 캡처 파일 부재는
관측 부재의 증거가 아니다(`safety.py:924-927` 이 PNR 저장을 금지한다).
→ 모순 지적 CONFIRMED, "판정 불가" 결론 REFUTED, 런타임 영향 0 → low.

---

## P2CRO-08 — `EXCLUDED_API_DOMAINS` 와 그것을 핀하는 테스트 → **CONFIRMED / low**

P2SAF-10 과 **동일 사실**. 판정·심각도 동일.
`tests/test_redaction_safety.py:165-168` `test_safety_excludes_dangerous_domains_without_stub_apis`
가 `"reservation"`/`"ard-payment-entry"`/`"payment"` 의 "제외"를 단언하는데,
`safety.py:520-522` 상 그중 둘은 라이브 전송 가능 카테고리다.
"테스트가 통과한다"가 "그 카테고리는 전송되지 않는다"를 증명하지 않는다는 지적은 정확하다.
`docs/RELEASE_GAP_PLAN.md:519` 의 의미 분리 지시가 미반영된 것도 확인. 런타임 영향 없음 → low.

---

## 확인불가(UNVERIFIABLE) 항목
없음. 16건 모두 앱 근거·라이브러리 근거 양쪽을 직접 열어 확인했다.
앱 근거가 "없음"으로 신고된 항목(S6-02, S7-02, P2SAF-06, P2SAF-10, P2CRO-07, P2CRO-08)은
라이브러리 내부 문서 불일치이므로 앱 근거 부재가 정상이다.

## 인용 드리프트 기록 (내용은 존재, 줄번호만 어긋남)
- S2-04: `ara0101v.js:559-563` → 실제 **:562-567**
- P2INC-03: `payloads.py:2087-2091` → 실제 **:2082-2085**
- S6-02: `parsers.py:2107-2124` → 실제 **:2109-2145**(필드 전체 범위)

## 인용 실패 기록 (근거가 주장을 뒷받침하지 않음)
- P2MIS-03 이 지적한 대로, `full-api-analysis-2026-07-20.md:378` 이 근거로 댄
  `ara0101v.js:113-121` 에는 psgTpCd 이름 매핑이 **존재하지 않는다**(:114-127 은 초기값+번호 주석뿐).
