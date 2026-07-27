# SRT 3차 검증 — verifier-4 (16건)

읽기 전용 수행. 저장소 파일 수정·생성 없음, git 상태 변경 없음.
모든 file:line 은 직접 열어 확인했고, 인용이 틀린 곳은 실제 위치를 적었다.

집계: CONFIRMED 6 / PARTIAL 5 / REFUTED 5 / UNVERIFIABLE 0

| id | 제기된 심각도 | 판정 | 정정 심각도 |
|---|---|---|---|
| S2-01 | missing/low | REFUTED | info |
| S2-05 | partial/info | REFUTED | info |
| S4-01 | doc-drift/medium | REFUTED | info |
| S5-02 | doc-drift/medium | CONFIRMED | low |
| S6-03 | doc-drift/info | PARTIAL | info |
| S7-03 | unverifiable/low | PARTIAL | info |
| P2MIS-01 | missing/medium | PARTIAL | info |
| P2MIS-05 | doc-drift/low | PARTIAL | info |
| P2INC-01 | risk/critical | CONFIRMED | high |
| P2CRO-10 | doc-drift/high | CONFIRMED | high |
| P2INC-10 | doc-drift/medium | CONFIRMED | low |
| P2INC-08 | risk/low | PARTIAL | low |
| P2SAF-03 | risk/medium | REFUTED | info |
| P2SAF-07 | partial/low | CONFIRMED | low |
| P2CRO-02 | doc-drift/low | CONFIRMED | low |
| P2CRO-05 | doc-drift/info | CONFIRMED | info |

---

## S2-01 — exceptStation 인접역 제외 테이블 미구현 → **REFUTED** (info)

**앱 근거(직접 확인)**
`analysis/apktool/assets/offline/js/exceptStation.js:18` `var excpStationList = [`,
`:41` `function getStationFlag(cd1, cd2) {` — 인용 정확.
호출부는 apktool/jadx/raw 세 트리 전체에서 자기 정의(각 `:41`)와 본문(`:43-45`)뿐, **0건**.

**결정적: 테이블 데이터가 앱 자신의 역코드표와 모순된다.**
- `exceptStation.js:30` `{cd1:"0509" 울산, cd2:"0020" 부산}` vs `:31` `{cd1:"0297" 오송, cd2:"0020" 공주}`
  — 같은 코드 `0020` 에 두 개의 역명. `src/srt_mobile_api/stations.py:33` `"0020": "부산"`.
- `:34` 는 `0033` 을 "정읍", `:35`/`:36` 은 같은 `0033` 을 "광주송정" 이라 부른다.
  `stations.py:46` `"0033": "정읍"`.

**라이브러리 근거(직접 확인)** `src/srt_mobile_api/stations.py:13` `STATION_NAMES_BY_CODE`,
`:361` `station_name_by_code` 두 개뿐. `src/srt_mobile_api/models.py:216-224`
`TrainSearchQuery.__post_init__` 은 코드공백 / YYYYMMDD / HHMMSS / train_group_code 멤버십만 검사.

**판정** 호출부 0건 + 데이터 자체 모순 = 유지되지 않는 죽은 자산. 서버가 강제하는 프로토콜 제약의
근거가 될 수 없다. 주장자 본인도 "확인 불가에 가깝다"고 자인했다. 결함 아님.

---

## S2-05 — `*RsvPsbImg/Color` 가 타입 필드로 승격되지 않음 → **REFUTED** (info)

**앱 근거** `ara/ara1001l.js:26-36` 상수 (이미지 7 + 색상 4) — 인용 정확.

**핵심: spec 문서가 이 4개를 "타입 필드"로 약속한 적이 없다.**
`docs/analysis/srt-app-api-library-spec-2026-07-09.md:212` `### \`TrainRow\`` 이하 `:214-237` 은
`| Field | Notes |` 헤더의 **와이어 필드표**다. `:229-230` 에 Color/Img 가 있는 것은 맞다.
그러나 바로 다음 산문 `:239-242` 가 타입 모델이 무엇을 보존하는지 따로 열거한다:

> The **typed row** also retains evidenced run/consist orders, normalized current delay,
> expected-delay string, general/special/wait/standing availability, received amount/fare,
> composition codes, and discount rate **without interpreting their display vocabularies**.

색상/이미지는 여기서 의도적으로 빠져 있고, 같은 문서가 `:206-210` 에서도 와이어 vs
`TrainSearchMetadata` 를 구분해 서술한다. 덧붙여 `TrainRow` 는 라이브러리 타입이 아니다
(`grep -rn "TrainRow" src/` → 0건). 즉 이 절 자체가 와이어 형태 기술이다.

**라이브러리 근거** `parsers.py:2430 _parse_search_train_rows`, 승격되는 가용성 필드는
`:2522 gnrmRsvPsbStr` / `:2526 sprmRsvPsbStr` 뿐. 원본 보존은 `parsers.py:2579 raw=row`.
의도된 설계임은 `payloads.py:1123 def _standby_row_image`, `:1126`
"gnrmRsvPsbImg is a UI asset name and **was never worth promoting to a field**",
`:1130 image = raw.get("gnrmRsvPsbImg")`.

**판정** spec–코드 괴리가 존재하지 않는다. 문서가 두 층을 일관되게 구분해 왔다.

---

## S4-01 — 환승 좌석지정 근거가 '환승 특이적'이 아님 → **REFUTED** (info)

**앱 근거(직접 확인)** `ara/ara0101v.js:866` `} else if (reqCode == POP_REQ_SEATSELECT_DPT_ONEWAY) {`,
`:876` `oSeatData1["scarGridcnt2"] = 0;`, `:878` `oSeatData1["scarNo2"] = "";` — jrnyTpCd/jrnyCnt 미참조. 맞다.
`ara/ara1001l.js:1427` `var item = this.ds_list[this.fv_nSelRow];`, `:1470-1487` 은 `rtnDv` 만 분기. 맞다.

**그러나 라이브러리 문장을 오독했다.** 실제 문장은 `src/srt_mobile_api/payloads.py:1655-1659`:

> **No seat selection.** 좌석지정 fills `scarNo1`/`seatNo1_*` and explicitly BLANKS the slot-2
> equivalents — `scarGridcnt2 = 0`, `scarNo2 = ""` (`ara0101v.js:875-879`) — **and no path in the
> bundle ever fills them**. That is the transfer-specific reason: 좌석지정 (jobId 1103) IS
> implemented … but it designates seats on one journey slot, and the bundle shows no path that
> designates them on a transfer's second leg.

"transfer-specific reason" 이 가리키는 것은 "이 콜백이 환승에서만 실행된다"가 아니라
"slot-2 좌석필드를 채우는 경로가 번들에 없다"이다. 편도에서는 slot 2 가 무의미하므로 이 사실은
환승(2-slot 여정)에서만 의미를 갖는다 — 정확히 환승 특이적이다.
`docs/VERIFICATION.md:1659` 는 표의 좌석지정 행이며 "explicitly BLANKS slot 2 … and nothing ever
fills them" 으로만 적혀 있어 오해 소지가 더 적다.

**판정** 인용은 적절하고 결론도 옳다. 주장이 제시한 fn_moveRsv 논거는 보완 논거일 뿐이다.

---

## S5-02 — mblPhone 생략 근거가 standby 에 대해 거짓 → **CONFIRMED** (medium → **low**)

**srtgo 원본 직접 확인** (`srtgo_plus/srtgo/srt.py`)
- `:726` `self.phone_number = user_info["MBL_PHONE"]` — 로그인 userMap 에서 가드 없이 읽음.
- `:867-869` `reservation = self.reserve_standby(train, passengers, option=option,
  mblPhone=self.phone_number)` — 대기 경로에서 실전화번호를 명시적으로 전달.
- `:986` `"mblPhone": mblPhone,` — 그 값이 그대로 reserve 바디에 실린다.

**라이브러리 근거** `src/srt_mobile_api/payloads.py:1235-1237`
"``mblPhone`` is omitted -- srtgo passes ``None``, which requests drops from the wire, and the
string has ZERO hits …". 이 docstring 이 붙은 함수는 `payloads.py:1218
def personal_reservation_payload(... standby: bool = False ...)` 이고 `:1219` 가
"개인예약 / **예약대기** reservation form", `:1240` 이 "``standby=True`` switches ``jobId`` to
``1102``" 라고 두 경우를 함께 다룬다고 선언한다.
따라서 "srtgo 도 None 을 보낸다"는 1101 에만 참, 1102 에는 거짓이다.

**저장소가 이미 열어둔 질문을 닫았다** `docs/analysis/cross-validation-2026-07-21.md:131` —
"populated only for standby, dropped for personal … Either a server-rendered JSP hidden input we
cannot see, or an srtgo-empirical field."

**low 로 조정** `docs/VERIFICATION.md:1299` "## Reservation variants: standby, round trip
(bundle-evidenced, **NOT live-verified**)" 이므로 mblPhone 누락이 무해하다는 것도 아무도 확인하지
않았다 — 그러나 **실패가 관측된 것도 아니다**. 확인된 결함은 어디까지나 "personal 한정 사실을
standby 에 일반화한 주석"이며, 감사 기준의 medium("특정 조건에서만 실패한다")을 뒷받침할 실패
증거가 없다. low("일관성 문제, 동작에는 지장 없음")가 확인된 내용에 정확히 대응한다.

---

## S6-03 — 카드 형식규칙이 messages.js 로 뒷받침됨 → **PARTIAL** (info)

**앱근거 인용이 틀렸다.** 실제 위치 (`common/messages.js`):
`:45` pay024, `:46` pay025, `:48` pay027, `:50` pay029.
주장이 쓴 `:49-52` 는 pay028/029/030/031 이므로 4개 인용 중 pay029 하나만 범위 안이다.

**"비관적" 프레이밍은 코드가 스스로 부정한다.** `payloads.py:1911-1923`:
"WHAT THE BUNDLE DOES AND DOES NOT CORROBORATE. **The blanket claim 'every field name is 0-hit'
is FALSE**, and the precise version is more useful." 이어서 `mbCrdNo`(ara0101v.js:319,321),
`totPrnb`, `jrnyCnt` 3개 히트를 열거하고 `:1923` "the three that hit tell us the app uses those
NAMES for those CONCEPTS; they say nothing about this form" 로 이름/개념을 명시 분리한다.
"전부 srtgo 단독출처"라는 인상을 주는 서술이 아니다.

**남는 유효한 부분** `models.py:755-758` (개념 서술) 과 `:783-799` (실제 검증: PIN 앞 2자리,
J=YYMMDD 6자리 / S=사업자번호 10자리) 어디에도 messages.js 인용이 없다
(`grep -rn "messages.js" src/` 결과 카드필드 관련 인용 0건). 개념이 앱 UI 메시지로 독립 증언된다는
관찰은 타당하고 인용해 둘 값어치가 있다. 결함은 아니다.

---

## S7-03 — cancel 폼의 '서명아웃 인라인' 근거가 재현 불가 → **PARTIAL** (info)

**확인한 것** `cncConfirm` 은 저장소에서 **산문에만** 존재한다 —
`src/srt_mobile_api/payloads.py:1807`, `src/srt_mobile_api/parsers.py:1710`,
`docs/VERIFICATION.md:1288`, `tests/test_live_response_shapes.py:597`.
`analysis/` 전체 0-hit. `tests/fixtures/ticket_list_expired_session.html` (전문 56줄) 에도 0-hit,
`:53` `<ul data-role="listview" id="ticketList"></ul>` 는 비어 있다. 여기까지 주장대로다.

**그러나 fixture 의 침묵은 반증도 결함도 아니다.** 같은 파일 자기 주석 `:23-30`:
> "REDACTED excerpt of a REAL response, captured 2026-07-26 from GET
> /atc/selectListAtc14017_n.do **issued with no session cookie**. The real body was **153161
> bytes**: the ORDINARY ticket-list page shell … the bulk that is omitted is **boilerplate
> menu/footer markup**."

2,308바이트 발췌본에 인라인 스크립트가 없는 것은 발췌 정책의 결과다. 또 이 저장소는 라이브 관측을
원칙적으로 산문으로 기록한다(2026-07-25 실취소 SUCC/IRG000000, 2026-07-26 SUCC/IRT000000 등 전부 동일).
"재현 가능한 verbatim 캡처가 없다"까지는 유효한 지적이나, 이 항목 고유의 결함이 아니다.

---

## P2MIS-01 — `/ard/selectListArd02019_n.do` 전면 부재 → **PARTIAL** (info)

**부재는 사실** `grep -rn "Ard02019\|02019" src/ tests/` → **0건**.
`src/srt_mobile_api/safety.py:415-430` 의 라우트 목록에도, 클라이언트 메서드에도 없다.

**그러나 명시된 결과가 사실이 아니다.** "예약 후 실제 배정된 호차/좌석을 확인할 방법이 없다" 는 틀렸다:
- `src/srt_mobile_api/parsers.py:1413-1427` 이 예약 응답의 `trainListMap` 에서
  `seatNo` / `scarNo` 를 읽어 `ReservationTrain` 을 만든다.
- `src/srt_mobile_api/models.py:570-573` `ReservationTrain(seat_number, car_number, raw)`,
  `:582` `ReservationAttemptResult.train`.
- 예약목록 쪽에도 `models.py:638` `seat_number: str | None`(seatNum) 이 있고, `:623-625` 는 그 이름이
  실서버 승차권확인 페이지 인라인 JS(`gotoDetailARD02018`, `gotoDetailARD0201V`)로 앱 측
  뒷받침을 받는다고 기록한다.

**의도된 범위 결정이며 이미 추적 중이다**
- `docs/analysis/cross-validation-2026-07-21.md:74` "Ard02019 does not appear anywhere … server-only
  and unverifiable from our offline decompile"
- `:370` — 6개 미검증 라우트 중 4개는 라이브런으로 닫혔고 "Standby `Ata01135` and ticket-info
  `Ard02019` are untouched, and **the gap stands for those two**"
- `docs/RELEASE_GAP_PLAN.md:1054-1055` — ABSENT(runtime-only) 목록
- `docs/analysis/ref-srtgo_plus.md:103` "NEW — not in our routes"

이 라이브러리는 srtgo 단독출처 라우트를 **라이브 검증 후에만** 편입해 왔다
(`safety.py:415-428` 의 각 라우트 주석이 검증일자를 달고 있다). Ard02019 는 미검증이므로 미구현이
일관된 정책이다. 주장자도 "앱이 Ard02019 를 호출한다고 단정하면 안 된다"고 인정한다.

**남는 유효한 부분** 승객별 운임 분해(`stdrPrc`/`dcntPrc`/`dcntKndCd`)는 실제로 어디에도 없다.

---

## P2MIS-05 — "가져올 데가 없다"가 사실이 아님 → **PARTIAL** (info)

**앱근거 인용은 매우 정확하다.** `analysis/apktool/assets/offline/sub/main.html`
`:465` `gds_userInfo: {`, `:477` `MBL_PHONE: ""`, `:482` 블록 종료 직후 — 주장한 465-482/:477 과 정확 일치.
srtgo `:726` 도 위 S5-02 에서 확인.
`src/srt_mobile_api/models.py:33-61` `SrtSession` 이 `user_map` 전체를 보관하면서 파생 노출은
`:38 membership_number`(MB_CRD_NO) 하나뿐인 것도 사실.

**그러나 문장의 지시대상을 잘못 읽었다.** `payloads.py:1236-1237` 은
"**the string** has ZERO hits across the whole v2.0.41 bundle, so there is nothing to add it back
from" 이고, 여기서 "the string" 은 백틱으로 감싼 **와이어 키 `mblPhone`**(소문자)이다.
그 문자열은 실제로 번들 0-hit 이다. `MBL_PHONE`(userMap 키)은 별개 토큰이고, 그것이 존재한다고 해서
`mblPhone` 이라는 **필드를 reserve 폼에 되살릴 근거**가 생기는 것은 아니다 — "값의 출처"와
"필드의 근거"는 다른 문제다.

**남는 유효한 부분** 문장이 느슨해 "값을 구할 데가 없다"로 읽힐 여지가 있고, 값이 이미
`SrtSession.user_map["MBL_PHONE"]` 에 있다는 관찰 자체는 사실이며 S5-02 와 함께 보면 유용하다.
다만 "뒤 절이 통째로 틀렸다"는 과장이고 동작 영향은 없다.

---

## P2INC-01 — 최소 consent 로 실카드가 승인된다 → **CONFIRMED** (critical → **high**)

**사실관계 전부 확인**
- `consent.py:86-95` 기본값: `allow_payment=False`, `dry_run=True`, `fake_card_only=True`,
  `real_card_acknowledged=False`.
- `consent.py:170 def require_card_kind_claim`, `:188-194` 둘 다 True(모순) 거부,
  `:195-201` 둘 다 False(미선언) 거부. 기본값 `(True, False)` 는 "정확히 하나"이므로 **통과한다**.
- 게이트가 걸린 두 지점 모두 같은 규칙: `client.py:1673` 계열 서술 + 실제 호출,
  `http.py:404` `require_card_kind_claim(consent)`.
- `fake_card_only=True` 일 때 카드가 실제 테스트카드인지 검증하는 코드는 **없다**.
  `grep -rn "fake_card_only\|4111\|TEST_CARD" src/` 결과 `fake_card_only` 를 **읽는** 곳은
  `consent.py:188`, `:195` 두 줄뿐. 오히려 `models.py:777-780` 이 그 성격을 명시한다 —
  "checked for shape rather than by a Luhn digit … **this library must never be the thing that
  tells a caller whether a card number is real**."
- 문서화된 불변식 `consent.py:15-18`("requires the caller to invert **BOTH** flags explicitly")과
  `:70-72`("A real charge therefore needs both halves stated deliberately") 는 구현과 불일치.
- `tests/test_payment_mutation.py:741-742` 가 `MutationConsent(allow_payment=True, dry_run=False,
  fake_card_only=True)` 를 유효한 결제 consent 로 사용한다.

**critical 이 아니라 high 인 이유** 감사 기준의 critical 은 "안전게이트가 뚫리거나"인데
뚫리는 게이트가 없다. 실카드 청구에는 여전히 `allow_payment=True`(`consent.py:87`,
`require_mutation_consent` `:163-167`)와 `dry_run=False`(`http.py:367-371`) 두 개의 명시적
opt-in 이 필요하고, 둘 다 안전한 쪽이 기본값이다. 카드종류 주장은 검증 불가능한 자기신고이며
`safety.py:495-496` 과 `client.py:1668-1672` 는 그 성격을 정확히 서술한다(모호성 방지).
결함은 **`consent.py` 산문이 존재하지 않는 추가 방어막을 약속한다**는 것이다.
P2CRO-10 과 동일 사실이므로 같은 심각도(high)로 맞춘다.

---

## P2CRO-10 — MutationConsent 문서 vs 구현 불일치 → **CONFIRMED** (high 유지)

P2INC-01 과 동일 사실이며, 이쪽의 진단과 심각도 판단이 옳다.

드리프트 문장(직접 확인):
- `consent.py:15-18` "A real, chargeable card requires the caller to invert **BOTH** flags explicitly"
- `consent.py:62-63` "``fake_card_only`` (default ``True``) **keeps any payment path restricted to a
  non-chargeable test card**" ← 강제하는 코드가 존재하지 않으므로 거짓
- `consent.py:70-72` "A real charge therefore needs both halves stated deliberately"

정확히 서술된 대조군:
- `safety.py:495-496` "post_mutation_form keeps a separate card-kind gate (exactly one of
  ``fake_card_only`` / ``real_card_acknowledged``)"
- `client.py:1668-1672` "exactly one of … neither and both are refused"

테스트는 정직하다: `tests/test_payment_mutation.py:605-611` 의 `@pytest.mark.parametrize` 가
`(True, False)  # a consent claiming a non-chargeable test card` 와 `(False, True)` **둘 다**
와이어에 실린다고 단언하고(`:612` 함수명 …`puts_the_documented_form_on_the_wire`),
`:615-618` 이 "WAS 'a fully permissive payment consent still cannot transmit', which was this
file's central invariant **until the live verification refuted it**" 라고 기록한다.
드리프트는 `consent.py` 산문에만 있다. high 타당.

---

## P2INC-10 — populated 예약행 "검증됨/미검증" 모순 → **CONFIRMED** (medium → **low**)

**모순 확인 (인용 7곳 전부 직접 확인, 전부 정확)**
- 커밋 `8cb8420` "fix(parsers): read a reservation's amount when it arrives as a number" —
  "LIVE 2026-07-26. The reservation list's populated row had never been observed … the real one
  sends numbers … `{"pnrNo":"3202607…","rcvdAmt":7500,"jrnyCnt":1,"tkSpecNum":1,"stlFlg":"N",
  "rsvChgTno":0}` … a live card payment refused to build, reporting that the reservation carried
  no amount, on a reservation that plainly carried 7500."
- `parsers.py:1948-1958` 가 같은 실측 행을 코드 주석에 박아 놓았다.
- 반대 서술: `parsers.py:2043` "The NON-EMPTY shape remains UNVERIFIED by this repository",
  `models.py:618-620`, `client.py:301-306`, `tests/test_reservation_list.py:12-13`,
  `docs/VERIFICATION.md:201`, `docs/IMPLEMENTATION_PROGRESS.md:790` (인용 783-789 는 같은 문단,
  한두 줄 어긋남).

**주장이 놓친 부분적 화해** `client.py:301` 은 "Live-verified … **for an account with no
reservations**" 라고 조건을 달고 있어 프로브 시점에는 문자 그대로 참이었다. 거짓이 된 것은 같은 날
결제 런에서 홀드를 만든 뒤다. 따라서 "6곳 전부 stale" 중 일부는 시점 한정 서술이다.
payListMap populated 행이 여전히 미기록이라는 지적은 사실(`models.py:637-646` 컨테이너 분배 주석).

**low 로 조정** 파서는 정상 동작하고 오차 방향이 "실제보다 덜 검증됐다"는 보수적 쪽이다.
감사 기준의 low("일관성 문제, 동작에는 지장 없음")에 해당하되, 6곳이 검증상태를 잘못 진술하는 것은
이 저장소가 load-bearing 으로 삼는 provenance 원장에 실질 손해이므로 info 로는 내리지 않는다.

---

## P2INC-08 — salvage 가드가 다른 컨테이너를 본다 → **PARTIAL** (low)

**인용은 한 줄도 틀리지 않았다**
`ara1001l.js:1562` `if (resultMap.strResult == "FAIL")`;
`parsers.py:1288` `result_row = _reservation_attempt_row(data, "resultMap")`;
`parsers.py:1492` `row = normalize_result_row(data)`;
`parsers.py:1113-1117` 이 `outDataSets.dsOutput0` 우선 → 없으면 `resultMap` 폴백;
docstring "enforced twice" 는 `parsers.py:1517-1519`.

**그러나 "2겹이 1겹이 된다"는 미입증이다**
1. 실제 reserve 응답은 `resultMap`/`reservListMap` 형태이므로(`ara1001l.js:1560-1562`)
   `normalize_result_row` 는 `:1117` 폴백으로 **같은 컨테이너**를 읽는다 → 두 겹이 성립한다.
2. 두 겹은 중복이 아니라 상보적이다. 층1 은 declared FAIL 을 `SrtAppError` 로 올리는데
   salvage 의 `except` 는 `SrtProtocolError` 만 잡는다(`parsers.py:1523-1530`).
   즉 층1 이 FAIL 을 잡으면 salvage 경로에 아예 들어가지 않는다.
3. 발산 조건은 "reserve 응답이 `outDataSets.dsOutput0` 를 함께 싣는다"인데, 이 라우트에서 그런
   형태는 관측된 적이 없다(dsOutput0 는 상호검증/환불 봉투다).

**판정** 컨테이너 불일치라는 관찰과 문구의 부정확성은 사실이나, 결론은 극히 좁은 미관측 조건에서만
성립한다. low 유지.

---

## P2SAF-03 — post_mutation_form 이 "유일한 전송 경로" → **REFUTED** (info)

**확인한 것** `http.py:316` "This is the only method that can transmit to a mutation route." 실재.
`_send_mutation_request`(정의 `:235`)가 실제 `self._client.send` 호출부(`:290`)이고
재확인 항목은 `:268`(라이브 카테고리), `:274` `assert_mutation_route`,
`:275` `assert_mutation_route_category`, `:285-286` 비-payment 카드시크릿. `consent` 는 시그니처에 없다.

**(b) "5개 게이트 중 3개만 재확인" 은 성립하지 않는다 — 문서가 정확히 그렇게 말하고 있다.**
- `http.py:245-246` "The consent and dry-run gating happens in **post_mutation_form** before we
  reach here."
- `http.py:249-252` "it re-asserts **the WHOLE route invariant** itself rather than trusting its
  caller — not just the category half. **Three checks**, and all three must hold" — 5개 게이트가
  아니라 라우트 불변식을 다시 주장한다고 명시.
- `http.py:347-352` docstring "``_send_mutation_request``, **the function that actually calls
  ``send``**, independently re-asserts **all of gate 3 and gate 5** — membership,
  ``assert_mutation_route`` and ``assert_mutation_route_category``" (여기서 membership 은 회원번호가
  아니라 `SRT_LIVE_MUTATION_CATEGORIES` **집합 소속**), 이어 `assert_no_card_secrets` 를 따로 서술.

**(a) 도 실질적으로 무너진다.** `:316` 문장은 같은 docstring `:347` 에서 `_send_mutation_request`
가 진짜 send 경계임을 스스로 밝히므로 독자를 오도하지 않는다. 게다가 그 메서드는 private 이고
저장소 내 호출부는 `http.py:425` 하나뿐이며 나머지는 전부 `post_mutation_form` 경유
(`client.py:1122, 1491, 1591, 1719, 1862`). 프로브가 PAN 을 내보내려면 밑줄 붙은 private 메서드를
직접 호출해야 하는데, 이는 우회 경로가 아니라 계약 밖 호출이다(저장소 자신의 테스트도 그 성격으로
쓴다 — `tests/test_coupon_mutation.py:265-269` 가 "Defense in depth: _send_mutation_request
re-asserts membership itself" 라고 명시).

**판정** 주장의 두 축이 모두 문서 본문으로 반박된다. 결함 아님.

---

## P2SAF-07 — SrtCouponRegistrationRequest 가 공개 경계에서 쓰이지 않음 → **CONFIRMED** (low)

**전부 확인** `__init__.py:50`(import), `:144`(`__all__`).
`client.py:1499-1504` `def register_discount_coupon(self, coupon_number: str, coupon_password: str,
*, consent: MutationConsent)`. 타입은 `:1578-1582` 에서 내부 생성.
`models.py:1257-1258` `coupon_number` / `coupon_password` 둘 다 `field(repr=False)`.
비교군 시그니처도 확인: `client.py:1150 reserve`, `:1316 reserve_transfer`,
`:1417 cancel(reservation: SrtReservationHold | str, …)`, `:1600 pay_with_card(reservation, card,…)`,
`:1788 refund`. 다섯 mutation 중 **타입 객체 경로가 아예 없는 것은 쿠폰뿐** — 사실이다.

**low 유지** 동작·안전 영향 없는 공개표면 일관성 문제. 다만 "쓸 데가 전혀 없다"는 다소 과하다 —
호출자가 직접 만들어 `models.py:1236-1254` 의 검증을 미리 받고 두 필드를 풀어 넘길 수는 있다.

---

## P2CRO-02 — AndroidManifest.xml 인용이 두 트리를 섞어 씀 → **CONFIRMED** (low)

**전수 확인**
- 저장소 내 AndroidManifest.xml **7개**: `analysis/apktool/`, `analysis/apktool/original/`,
  `analysis/jadx/resources/`, `analysis/raw/base/`, `raw/split_arm64_v8a/`, `raw/split_xxhdpi/`,
  `raw/split_ko/`.
- 줄 수: `analysis/apktool/AndroidManifest.xml` **170줄**, `analysis/jadx/resources/AndroidManifest.xml` **393줄**.
- apktool: `:2` `<manifest … package="kr.co.srail.newapp" …>`, `:53` `<application …
  android:usesCleartextTraffic="true">`, `:72` TransKeyActivity,
  `:140` `com.raon.fido.client.process.UAFClientActivity`, `:141` AsmListActivity.
- jadx: `:53` `android:required="false"/>` (uses-feature camera.front),
  `:143` `android:name="com.softsecurity.transkey.TransKeyActivity"`,
  `:315` `android:name="com.raon.fido.client.process.UAFClientActivity"`.

**인용처**
- jadx 번호(수식 없음): `src/srt_mobile_api/payloads.py:1882` "AndroidManifest.xml:143",
  `:1884` "AndroidManifest.xml:315"; 복제본 `docs/VERIFICATION.md:251-252`,
  `docs/IMPLEMENTATION_PROGRESS.md:548-549`.
- apktool 번호(수식 없음): `docs/analysis/cross-validation-2026-07-21.md:323` "AndroidManifest.xml:2",
  `:324` 와 `:356` "AndroidManifest.xml:53".

**오독 위험 실재** apktool 트리를 먼저 여는 독자에게 `:315` 는 범위 밖(170줄)이고,
`analysis/apktool/AndroidManifest.xml:143` 은 직접 열어보면
`android:name="com.raonsecure.touchen.onepass.sdk.OPBackgroundActivity"` — TransKey 가 아니라
**다른 보안 벤더(RaonSecure OnePass)** 라서 무심코 "확인됨"으로 읽힌다.
이 저장소의 규칙("jadx 가 이상하면 apktool/smali 로 확인하라")을 실행 불가능하게 만든다.
사실관계는 전부 맞고 표기만 문제 → low 타당.

---

## P2CRO-05 — netfunnel.js:60477 은 줄번호가 아니라 문자 오프셋 → **CONFIRMED** (info)

**정량 확인** `analysis/apktool/assets/offline/js/common/netfunnel.js`
- 87,089 바이트 / **86,293 문자**(주장의 수치와 일치) / 개행 83개.
  마지막 바이트가 `;` 라 개행이 없어 `wc -l` 이 83 을 보고하지만 실제 줄 수는 **84**.
- 문자 오프셋 **60477** 지점을 직접 덤프:
  `t[60437:60517] = '})}return};NetFunnel.TsClient.prototype._showResultChkEnter=function(b){var c=th'`
  — `_showResultChkEnter` 의 `_` 가 정확히 오프셋 60477. 주장대로다.
- 같은 파일의 다른 정의: 58653 `_showResult`, 59868 `_showResultGetTicketID`,
  64057 `_showResultAliveNotice`, 66409 `_showResultSetComplete`.

**표기 혼재 확인** `src/srt_mobile_api/netfunnel.py:36` "the codes below are **netfunnel.js:84**'s
own names"(진짜 줄번호), 두 줄 아래 `:38` "(_showResult, **netfunnel.js:60477**)"(문자 오프셋).
게다가 오프셋 60477 은 **줄 84 안**에 있어(미니파이라 본문 전체가 한 줄) 같은 주석 블록에서
`파일:숫자` 두 표기가 같은 위치를 가리키는 셈이라 혼동이 크다.

**추가로 찾은 미세 오차** `netfunnel.py:38` 은 그 위치를 "`_showResult` 디스패처"라 부르지만
60477 은 `_showResultChkEnter`(타입별 핸들러)이고 진짜 `_showResult` 는 58653 이다.
`errors.py:262-263` 은 같은 파일을 경로로만 인용하고 숫자를 붙이지 않아 이 문제와 무관하다.
info 타당.
