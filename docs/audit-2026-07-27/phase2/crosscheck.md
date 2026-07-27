# SRT 2차 감사 — 교차검증 렌즈 (Phase 2)

**대상:** `srt-mobile-api`
**렌즈:** 문서(docs/, README, CHANGELOG) · 테스트가 주장하는 것 **vs** 코드가 실제로 하는 것
**vs** 앱(디컴파일/오프라인번들)이 실제로 하는 것 — 셋의 대조.
**작성일:** 2026-07-27
**모든 명령은 읽기 전용으로 실행했다.** 저장소 파일을 수정하지 않았고, git 상태를 바꾸지 않았다.
테스트는 `PYTHONDONTWRITEBYTECODE=1 ... -p no:cacheprovider` 로 실행해 `.pytest_cache/` 를 건드리지 않았다.

---

## 0. 집계 기준 (counting basis)

1차 8명의 추출 수치(22+464+34+23+19+19+5+47 = 633)는 **슬라이스 간 중복이 심해 합산하면 이중계상**된다.
본 보고서는 다른 기준을 쓴다: **내가 이번 세션에서 직접 확인한, 서로 구별되는 프로토콜 표면 단위**
(= 라우트 + 그 라우트가 요구하는 요청 계약(폼 필드 집합) + 응답 파서 + 정적 코드테이블)만 센다.

| 항목 | 수 | 확인 방법 |
|---|---:|---|
| 읽기 전용 라우트 (`READ_ONLY_ROUTES`) | 26 | 런타임 열거 (아래 §5) |
| 뮤테이션 라우트 (`SRT_MUTATION_ROUTES`) | 5 | 런타임 열거 |
| 공개 클라이언트 메서드 | 35 | `inspect.getmembers` |
| 정적 코드테이블 (역명, 할인종류코드) | 2 | 앱 원본과 전수 diff |
| **합계 (추출)** | **68** | |
| 그중 앱/문서 근거와 일치 확인 | **64** | |
| 결함·드리프트로 분류 | **4** (뮤테이션 파서 1, 취소 계약 1, 결제 consent 문서 1, 인용 계열 1) | §1 |

> `implemented_count = 64` 는 "라이브러리가 만든 요청/파서가 앱 또는 실측 근거와 일치함을 내가 직접
> 재확인한 단위 수"이고, 나머지 4는 §1의 P2CRO-06(뮤테이션 응답 파서) / P2CRO-01(취소 폼 계약) /
> P2CRO-10(결제 consent) / P2CRO-02·03·04·05(코드주석 인용 계열, 한 단위로 계상)이 걸린 단위다.
> **1차 수치(633)와 직접 비교하면 안 된다 — 슬라이스 중복 때문에 합산 자체가 이중계상이다.**

---

## 1. 1차가 **놓친 것** (신규)

### P2CRO-01 — `cancel()` 의 `jrnyCnt` 기본값 정당화가 사실이 아니다 (risk / medium)

**라이브러리 근거 (주장):** `src/srt_mobile_api/payloads.py:1833-1843`

```
``jrnyCnt`` DEFAULTS to ``"1"`` rather than being derived from the hold,
because the hold has no journey count to derive from. ...
Defaulting to ``"1"`` is also what every hold this library can create actually is:
``personal_reservation_payload`` only ever sends ``jrnyCnt="1"``.
```

**라이브러리 근거 (반례):** `src/srt_mobile_api/payloads.py:1696-1697`

```python
payload["jrnyTpCd"] = JOURNEY_TYPE_TRANSFER   # "14"
payload["jrnyCnt"]  = JOURNEY_COUNT_TRANSFER  # "2"
```

`transfer_reservation_payload` 은 `jrnyCnt="2"` 를 보내고,
`SrtClient.reserve_transfer` (`client.py:1404-1415`) 는 이 페이로드로
`_submit_reservation` 을 호출해 **`SrtReservationHold` 를 돌려준다.**
즉 **이 라이브러리는 2여정 hold 를 만들 수 있다.** 인용된 정당화 문장은 `personal_reservation_payload`
하나만 근거로 삼아 "이 라이브러리가 만들 수 있는 모든 hold"로 일반화했고, 그 일반화는 거짓이다.

**앱 근거:** `analysis/apktool/assets/offline/js/ara/ara0101v.js:302-303`
(`sJrnyTp="14"; nJrnyCnt="2";` — 번들 전체에서 `jrnyCnt="2"` 를 쓰는 유일한 지점) +
취소 폼 자체가 `jrnyCnt` 를 **런타임 인자로 받는다**:
`payloads.py:1806-1810` 이 인용한 라이브 티켓목록 페이지의 인라인 스크립트
`function cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt)` — 고정값이 아니라 예약별 값이라는 뜻이다.

**영향:** `hold = client.reserve_transfer(...)` 뒤에 `client.cancel(hold, consent=...)` 를 부르면
2여정 예약에 `jrnyCnt="1"` 이 나간다. 서버가 한 다리만 취소하든 거부하든, **실서버에 실제 예약이
남는다.** README(`README.md:143-144`)는 호출자에게 `journey_count="2"` 를 넘기라고 경고하지만,
(a) `payloads.py` 의 주석은 정반대를 사실로 못박고 있고, (b) `client.cancel` docstring
(`client.py:1450-1454`)은 "if live capture **ever** shows a multi-leg PNR needing `jrnyCnt="2"`"
라고 써서 다여정 hold 를 **가정적 미래**로 서술한다 — `reserve_transfer` 가 지금 그것을 만드는데도.
(c) `SrtReservationHold` (`models.py:590-604`)는 `total_seat_count` 만 갖고 여정수를 기록하지 않아
라이브러리가 스스로 알 수 있는 사실을 버린다.

**1차 대비:** 04-transfer 는 이 기본값을 표 13행에 "있음(문서화된 캐치, 버그 아님)"으로,
그리고 §확인했으나 문제없음 목록(`04-transfer.md:223-227`)에서 명시적으로 **findings에서 제외**했다.
제외 사유는 "파라미터가 존재하고 문서에 경고가 있다"였다. 놓친 것은 **근거문 자체가 거짓이라는 점**과
**hold 가 자기 여정수를 알 수 있는데도 기록하지 않는다는 점**이다.

**수정 방향:** `SrtReservationHold` 에 `journey_count` 를 싣고(=`transfer_reservation_payload` 가
보낸 값), `unpaid_reservation_cancel_payload` 이 hold 에서 그것을 읽게 한다. 최소한
`payloads.py:1841-1842` 의 거짓 일반화를 삭제하고 `reserve_transfer` docstring 에 취소 경고를 단다.

---

### P2CRO-10 — `MutationConsent` 가 "실카드 청구에는 두 플래그를 다 뒤집어야 한다"고 말하지만, **기본 consent 만으로 실카드가 청구된다** (doc-drift / high)

**라이브러리 근거 (주장):** `src/srt_mobile_api/consent.py:13-18` (모듈 docstring)

```
* ``fake_card_only`` defaults to ``True`` and ``real_card_acknowledged``
  defaults to ``False``, so a payment preview can only ever carry a
  non-chargeable test card. A real, chargeable card requires the caller to
  invert BOTH flags explicitly (``fake_card_only=False,
  real_card_acknowledged=True``); ...
```

같은 취지가 `consent.py:62-63` ("``fake_card_only`` (default ``True``) **keeps any payment path
restricted to a non-chargeable test card**") 와 `consent.py:70-72`
("A real charge therefore **needs both halves stated deliberately** — ``fake_card_only=False`` …
and ``real_card_acknowledged=True``") 에 반복된다.

**라이브러리 근거 (실제 동작):** `consent.py:188-201` `require_card_kind_claim` 은
**둘 다 참** 또는 **둘 다 거짓**만 거부한다. 기본값은 `fake_card_only=True,
real_card_acknowledged=False` = "정확히 하나" = **통과**한다.
그리고 `fake_card_only=True` 가 **카드가 실제로 테스트카드인지 검증하는 코드는 어디에도 없다**
(전수 grep: 이 플래그를 읽는 곳은 `require_card_kind_claim` 하나뿐).

**실행으로 확인했다** (httpx `MockTransport` 로 트랜스포트만 갈아끼우고 `pay_with_card` 호출,
네 조합 전부):

| consent | 결과 |
|---|---|
| `MutationConsent(allow_payment=True, dry_run=False)` — **기본 카드종류값** | **전송됨.** `POST https://app.srail.or.kr/ata/selectListAta09036_n.do`, 본문에 PAN 평문 포함 |
| `fake_card_only=False, real_card_acknowledged=True` | 전송됨 (같음) |
| 둘 다 True | 거부 `SrtMutationNotAllowedError` |
| 둘 다 False | 거부 `SrtMutationNotAllowedError` |

즉 **실서버에 실카드를 청구하는 데 실제로 필요한 것은 `allow_payment=True` + `dry_run=False` 둘뿐**이고,
`real_card_acknowledged` 는 **필요 없다.** `fake_card_only` 는 검증되지 않는 **호출자의 주장**인데
문서는 그것을 **제약**("restricted to a non-chargeable test card")으로 서술한다.

**앱 근거:** 해당 없음 — 이것은 라이브러리 자체의 안전모델 문서와 구현 사이의 불일치다.
(참고: 실제 게이트가 하는 일은 `safety.py:494-497` 과 `client.py:1670-1673` 에 정확히 쓰여 있다:
"the consent must state, unambiguously, WHICH kind of card it is" — **모호성 방지**이지 실카드 차단이 아니다.)

**테스트는 정직하다 — 여기가 중요하다.** `tests/test_payment_mutation.py:605-614` 는
`(fake_card_only=True, real_card_acknowledged=False)` 를 포함한 두 조합 모두에 대해
`test_a_fully_valid_payment_consent_puts_the_documented_form_on_the_wire` 로 **전송됨**을 단언하고,
`tests/test_mutation_consent.py:309-313` 도 기본값 통과를 단언한다. 즉 이건 "보호하는 척하는 핀"이
아니라 **문서만 코드보다 강하게 주장하는** 경우다. 드리프트는 `consent.py` 산문에 국한된다.
`README.md:219-223` 의 "exactly one of …" 서술은 정확하다(다만 `:220` 의
"`fake_card_only=True` (a non-chargeable test card, the default)" 는 주장을 사실처럼 읽히게 한다).

**영향:** `help(MutationConsent)` 를 읽고 "기본 consent 로는 돈이 움직일 수 없다"고 믿은 호출자가
`dry_run=False` 만 켜면 실제로 결제된다. 이 저장소의 심각도 사다리에서 "실행하면 돈이 잘못 나간다"에
가장 가까운 항목이다. **다만 게이트 자체에 구멍은 없다**(코드가 말하는 대로 동작하고 우회 경로가 없다)
— 그래서 critical 이 아니라 high 다.

**수정 방향:** `consent.py:13-18`, `:62-63`, `:70-72` 를 실제 동작에 맞춘다 —
"a real charge needs `allow_payment=True` and `dry_run=False`; the card-kind flags disambiguate the
claim and do not restrict the card." 더 강한 대안: `fake_card_only=True` 인데 PAN 이 알려진
테스트 PAN 이 아니면 거부하도록 실제 제약을 구현한다(그러면 문서가 이미 참이 된다).

---

### P2CRO-02 — `AndroidManifest.xml` 인용이 두 개의 서로 다른 렌더링을 섞어 쓴다 (doc-drift / low)

**라이브러리 근거:** `src/srt_mobile_api/payloads.py:1882-1884`

```
# keypad (com.softsecurity.transkey, AndroidManifest.xml:143;
#  bridge.js:2,31,66-68) and RaonSecure FIDO (com.raon.fido.*,
#  AndroidManifest.xml:315).
```

**앱 근거:** 저장소에는 `AndroidManifest.xml` 이 7개 있고 줄번호 체계가 서로 다르다.

| 파일 | 줄수 | `com.softsecurity.transkey` | `com.raon.fido.*` |
|---|---:|---:|---:|
| `analysis/apktool/AndroidManifest.xml` | 170 | **:72** | :140-141 |
| `analysis/jadx/resources/AndroidManifest.xml` | 393 | **:143** | **:315** |

즉 `:143` / `:315` 는 **jadx 렌더링** 기준으로는 정확하다(확인함:
`analysis/jadx/resources/AndroidManifest.xml:143` = `android:name="com.softsecurity.transkey.TransKeyActivity"`,
`:315` = `android:name="com.raon.fido.client.process.UAFClientActivity"`).
문제는 **같은 저장소의 다른 인용들이 apktool 렌더링 기준**이라는 것이다:
`docs/analysis/cross-validation-2026-07-21.md:323` 의 `AndroidManifest.xml:2`
(`package="kr.co.srail.newapp"`) 와 `:324,:356` 의 `AndroidManifest.xml:53`
(`android:usesCleartextTraffic="true"`) 는 **apktool 파일에서만** 맞는다
(jadx:53 은 `android:required="false"/>` 다).

**영향:** 파일명이 수식 없이 쓰여 있어, apktool 트리를 먼저 여는 독자에게 `:315` 는 **범위 밖**(170줄)이고
`:143` 은 TransKey 가 아니라 RaonSecure OnePass 액티비티라서 **다른 주장을 확인해주는 것처럼** 읽힌다.
이 저장소는 "jadx 가 이상하면 smali/apktool 로 확인하라"를 규칙으로 삼고 있으므로, 어느 트리 기준인지
표시하지 않은 인용은 그 규칙을 실행할 수 없게 만든다. `docs/VERIFICATION.md:251-252`,
`docs/IMPLEMENTATION_PROGRESS.md:548` 이 같은 인용을 복제하고 있어 3곳이 함께 흔들린다.

**수정 방향:** `analysis/jadx/resources/AndroidManifest.xml:143` 처럼 트리 접두사를 붙인다
(이 저장소는 `analysis/raw/base/assets/offline/js/commCode.js` 처럼 이미 그렇게 쓰는 곳이 있다).

---

### P2CRO-03 — `0001 : 선행, 0002 : 후행` 글로스의 줄번호가 4곳에서 틀렸다 (doc-drift / low)

**라이브러리 근거:** `models.py:354`, `payloads.py:93`, `payloads.py:1284`, `payloads.py:1621`
— 넷 다 `ara1001l.js:1607` 로 인용.

**앱 근거:** 실제 글로스는
`analysis/apktool/assets/offline/js/ara/ara1001l.js:1611`
`frm.jrnySqno.value = 1; // 0001 : 선행, 0002 : 후행`
이다. 인용된 `:1607` 은 `frm.action = contextPath + "/ard/selectListArd02017_n.do";`
— 개인 **결제** 페이지로 폼을 돌리는 줄이고 여정순번과 무관하다.

**추가 관찰(더 중요):** 1611행의 필드명은 접미사 없는 `jrnySqno` 이고, 그것도 예약 폼이 아니라
**결제 핸드오프 폼**(Ard02017)에 실린다. 반면 라이브러리가 실제로 보내는 것은
`jrnySqno1="001"` / `jrnySqno2="002"` 이고, 그 근거는 `ara0101v.js:97`
(`"jrnySqno1" : "001", //여정일련번호1(001:선행, 002:후행)` — 직접 확인, 정확)이다.
즉 **1차 근거는 멀쩡하고 보조 인용만 틀렸다.** 기능적 결함은 아니다.

**수정 방향:** 네 곳 모두 `ara1001l.js:1611` 로 정정하고, 그 줄이 결제 핸드오프 폼의 무접미사
`jrnySqno` 라는 점을 한 줄 덧붙인다.

---

### P2CRO-04 — 로그인 `deviceKey="-"` 의 참조문헌 인용이 엉뚱한 줄을 가리킨다 (doc-drift / low)

**라이브러리 근거:** `src/srt_mobile_api/session.py:56-61`

```
# The login deviceKey is the server-rendered constant "-", not an
# ANDROID_ID. Both wire refs agree: srtgo srt.py:704 (data["deviceKey"]
# = "-") and ref-srtgo_plus.md:112,120-121.
```

**문서 근거:** `docs/analysis/ref-srtgo_plus.md`
- `:112` = `**Key reconciliation vs our APK analysis.**` (결제 엔드포인트 대조 문단)
- `:120-121` = `## 3. Login / auth (srt.py:673-731)` / `- **Endpoint:** POST /apb/selectListApb01080_n.do.`
- **실제 `deviceKey` 근거는 `:130`** (`deviceKey=-,  # literally a hyphen — no real device key needed`)
  **와 `:138-140`** (`deviceKey는 상수 "-" (srt.py:705)`).

**영향:** 값 자체는 옳다(직접 확인). 다만 `deviceKey` 는 오프라인 번들 전체에 0-hit 이라
**참조구현이 유일한 근거**인데, 그 유일한 근거를 가리키는 포인터가 틀려 있다. 1차 01-auth 는
`models.py:44` 의 유사 오인용은 잡았지만 이건 놓쳤다(같은 파일 표 2d행에서 근거를
`srtgo/srt.py:704` 로만 인용하고 `session.py` 주석의 인용은 대조하지 않았다).

---

### P2CRO-05 — `netfunnel.js:60477` 은 줄번호가 아니라 문자 오프셋이다 (doc-drift / info)

**라이브러리 근거:** `src/srt_mobile_api/netfunnel.py:36-38`
— 같은 파일을 `netfunnel.js:84`(코드명 목록)와 `netfunnel.js:60477`(`_showResult` 디스패처)로 인용한다.

**앱 근거:** `analysis/apktool/assets/offline/js/common/netfunnel.js` 는 **83줄 / 86,293자**의
미니파이 파일이다. 60,477 은 줄이 아니라 **문자 오프셋**이고, 그 위치는 실제로
`NetFunnel.TsClient.prototype._showResultChkEnter=function(b){...` 이다(직접 확인 —
오프셋 60450~60560 구간을 덤프해 대조). 즉 **사실은 맞고 표기 체계만 섞여 있다.**

**영향:** 같은 `파일:숫자` 표기가 한 주석 안에서 줄과 문자 오프셋 두 가지를 뜻한다.
자동화된 인용 검사(내가 이번에 돌린 것과 같은)나 사람 모두 `:60477` 을 "범위 밖 인용"으로 오판한다.
`errors.py:262` 도 같은 파일을 인용하므로 표기 규칙을 한 번 정하는 편이 낫다.

**수정 방향:** `netfunnel.js@60477` 또는 `netfunnel.js (char 60477)` 처럼 구분 표기.

---

## 2. 1차가 **틀리게 본 것**

### P2CRO-09 — 02-search S2-02 "그룹검색 하이드레이션 GET이 항상 `grpDv="0"`" 는 결함이 아니다 (info)

1차 02-search 는 이것을 finding 으로 올렸다. 앱을 직접 읽으면 **라이브러리가 앱과 정확히 같다.**

**앱 근거 (직접 확인):**
- `ara0101v.js:93` — 예약 스토어의 **시드**: `"grpDv" : "0",  //단체구분(0:개인, 1: 단체)`.
  즉 페이지가 로드될 때 grpDv 는 언제나 `"0"` 이다.
- `ara0101v.js:522` — 단체 체크박스: `lfn_setRsv({"grpDv": $(this).is(":checked") ? "1" : "0"});`
  — **로컬 스토어만** 바꾼다. 새 하이드레이션 요청을 보내지 않는다.
- `ara1001l.js:174-181` — 검색 시점에 `lfn_getRsv("grpDv") == "1"` 로 **URL을 고른다**
  (단체 → `/ara/selectListAra10082_n.do`, 개인 → `/ara/selectListAra10007_n.do`),
  그리고 `$("#seatSearchForm").serialize()` 로 그 시점의 grpDv 를 함께 보낸다.

**라이브러리 근거:** `client.py:540-559` `_prepare_search` — 하이드레이션 GET 은
`search_page_payload`(항상 `grpDv:"0"`, `payloads.py:554`) 로 보내고, 그 다음 POST 에서
`group_search_ajax_payload`(`payloads.py:676`)가 `payload["grpDv"] = "1"` 로 덮어쓰며 URL 도
`Ara10082` 로 바꾼다(`client.py:551`).

**결론:** 앱의 "시드는 항상 0, 검색 POST 에서 1" 순서를 그대로 재현한다. 결함 아님.
(실측 뒷받침: `tests/fixtures/group_search_success.json` 이 존재한다 = 이 흐름으로 실응답을 받은 적이 있다.)

### 그 밖에 재확인은 했으나 심각도를 올리지 않은 1차 항목

- **04-transfer F-02** (`trnGpCd1/2` 상수 `"300"`): 앱도 `TRAIN_GROUP_OPTIONS` 로 상수를 쓰고
  `ara0101v.js:845` 이후 `obj.trainOption == "300"` 분기가 SRT 를 뜻하므로 위험 낮음. 유지.
- **05-standby S5-04** (예약대기 시 `seat_type` 무시): **의도된 설계이고 옳다.** 앱
  `ara1001l.js:1431` 은 예약대기 이미지(`S_IMG_WAIT_S`)를 일반실(`psrmClCd=1`)로만 매핑하고
  특실 분기(`:1432`)는 예약가능 이미지 두 개만 검사한다. 라이브러리가 강제하지 않았다면
  기본 `SeatType.GENERAL_FIRST` 가 `not _general_seat_available()` → **특실**로 해석되어
  조용히 1등석을 주문했을 것이다(`payloads.py:1083-1094`). 강제는 버그가 아니라 버그 방지다.
- **03-reserve S3-03** (좌석지정 캐빈클래스 미연결): 재현했다. 다만
  `_seat_designation_fields` 는 좌석 라벨만 다루고 `psrmClCd1` 은 `seat_type` 에서 오므로
  호출자가 특실 그리드를 읽고 `seat_type` 을 안 바꾸면 불일치가 난다. 1차 판단(medium) 타당.

---

## 3. 1차와 **교차확인된 것** (재현 성공)

### P2CRO-06 — `normalize_result_row` 컨테이너 우선순위 (risk / high) — 07-refund S7-01 재현

`src/srt_mobile_api/parsers.py:1113-1117`:

```python
def normalize_result_row(data):
    out = data.get("outDataSets") or {}
    if isinstance(out, dict) and "dsOutput0" in out:   # 키 존재만 검사
        return _first_row(out.get("dsOutput0"))        # []/None 이어도 여기서 끝
    return _first_row(data.get("resultMap"))
```

**직접 실행으로 재현했다:**

```
data = {"outDataSets": {"dsOutput0": []},
        "resultMap": [{"strResult":"SUCC","msgCd":"IRT200277","msgTxt":"ok"}]}
  normalize_result_row(data)      -> {}
  parse_refund_response(data)     -> SrtProtocolError: must contain a resultMap result row
  parse_unpaid_cancel_response(d) -> SrtProtocolError: must contain a resultMap result row
  parse_card_payment_response(d)  -> SrtProtocolError: must contain a outDataSets.dsOutput0 (or resultMap) result row
```

즉 **성공을 `resultMap` 에 정확히 담아 보낸 응답이라도, 옆에 빈 `outDataSets.dsOutput0` 이
하나 붙어 있으면 세 뮤테이션 파서 모두 예외를 던진다.** 환불·취소·**결제** 세 경로 모두 해당이며
(1차는 refund/cancel 중심으로 썼지만 결제도 같은 헬퍼를 쓴다), 결제/환불에서는 "돈이 움직였는지
모르는 예외"가 된다.

**개연성 근거(앱/실측):** 같은 `/atc/` 패밀리의 예약목록 실응답이 이미
`resultMap`(SUCC/IRZ000005) 과 `rsMap`(FAIL/WRT300005) 을 **한 응답에 동시에** 담아 보낸다 —
`tests/fixtures/reservation_list_empty.json` 에서 직접 확인. 즉 "관련 없는 컨테이너를 곁들여 보낸다"는
패턴이 이 백엔드에 실재한다. 다만 `Atc02063`/`Ard02045`/`Ata09036` 이 그 조합을 보낸다는 실측은 없다
(세 라우트 모두 번들 0-hit). **확인불가하지만 방어 비용이 거의 0인 케이스.**

**수정 방향:** `dsOutput0` 이 **유효한 행을 담고 있을 때만** 우선하고 아니면 `resultMap` 폴백.
"두 컨테이너 동시 존재" 테스트를 추가해 의도를 pin.

### P2CRO-07 — 예약목록 populated row 의 라이브검증 여부, 코드 내부 모순 (doc-drift / medium) — S7-02 재확인

- `parsers.py:1948-1952` : "**LIVE 2026-07-26 settled** what the non-empty row looks like",
  구체 값까지 (`{"pnrNo":"3202607...","rcvdAmt":7500,"jrnyCnt":1,"tkSpecNum":1,"stlFlg":"N","rsvChgTno":0}`)
- `parsers.py:2043` : "The NON-EMPTY shape remains **UNVERIFIED** by this repository."
- 같은 취지가 `models.py:618-627`, `client.py:301-307`, `tests/test_reservation_list.py:12-13`,
  `docs/IMPLEMENTATION_PROGRESS.md:783-789` 에 반복된다.

두 서술이 동시에 참일 수 없다. 이 필드들이 `pay_with_card` 의 **결제금액**(`rcvdAmt` → `_payment_amount`)
과 **승차인원**(`tkSpecNum` → `_payment_passenger_count`)의 출처이므로, 신뢰도 오판의 대가가 크다.
`tests/fixtures/` 에 이 캡처를 뒷받침하는 파일은 없다(`reservation_list_empty.json` 하나뿐).
`docs/VERIFICATION.md` 에도 이 캡처 기록이 없다 — 그런데 같은 문서 `:297-299` 는
"`get_reservations` 의 populated-row shape 은 srtgo-attested (only the EMPTY response is
live-verified)" 라고 **UNVERIFIED 쪽에 선다.** 즉 다수결로는 `parsers.py:1948` 이 이상값이다.

### P2CRO-08 — `EXCLUDED_API_DOMAINS` 와 그것을 pin 하는 테스트 (doc-drift / low) — S8-01 재확인

`safety.py:911-922` 가 `reservation`/`payment`/`refund`/`cancellation` 을 "제외 도메인"으로
계속 명명하고, `tests/test_redaction_safety.py:165-168`
`test_safety_excludes_dangerous_domains_without_stub_apis` 가 **그 거짓을 적극적으로 단언**한다.
이 상수를 읽는 코드는 그 테스트 하나뿐이므로(전수 grep 확인) 런타임 안전성 영향은 없다.
다만 **테스트가 현재 상태와 반대되는 사실을 pin 하고 있다**는 점에서 "72 public methods" 계열의
재발 형태다: 테스트가 통과한다는 사실이 안전을 증명하지 않는다.

---

## 4. 안전게이트 — 우회 경로 전수 확인 (구멍 없음)

지시문이 "게이트에 **구멍**이 있으면 최우선"이라 했으므로 이것부터 봤다. **결과: 구멍 없음.**

`src/` 전체에서 실제로 네트워크에 나가는 지점은 **정확히 2곳**이다
(grep: `build_request|\.send\(|httpx.Client|\.post\(|urlopen|requests\.`):

| 지점 | 게이트 |
|---|---|
| `http.py:146-149` `_request` | `assert_read_only_request` (26개 라우트 allowlist + `assert_no_card_secrets` + 정규 origin + 퍼센트인코딩 금지 + 4개 POST-read 의 정확한 폼 계약) |
| `http.py:276-288` `_send_mutation_request` | 카테고리 live-enable + `assert_mutation_route` + `assert_mutation_route_category` + `assert_no_card_secrets`(payment 제외). **호출자를 신뢰하지 않고 스스로 재검증한다.** |

`post_form` / `post_html_form` 은 둘 다 `_post_form_response` → `_request` 를 타므로 read allowlist 아래.
`post_mutation_form` 은 그 위에 consent · dry_run · live-enable · 카드종류 주장 · origin · 라우트/카테고리 바인딩을 얹는다.
`scripts/` 중 `dry_run=False` 를 쓰는 것은 `recover_hold.py:66`, `verify_reserve_cancel_roundtrip.py:93,109`
뿐이고 둘 다 공개 클라이언트 메서드를 경유한다.

부수 확인:
- **로깅이 전혀 없다** (`import logging|logger|print(` 0-hit) → 로그 유출 경로 없음.
- 예외 메시지는 `request.url.path` 만 담고 본문을 담지 않는다(`http.py:151-160, 289-300`), `from None` 으로 컨텍스트도 끊는다.
- `models.py` 의 secret-shaped 필드는 전부 `repr=False` (52곳 확인) + `redaction.SENSITIVE_KEYS` 에 이름 등록(이중 방어).
- `MutationPreview.__post_init__` 이 생성 시점에 `redact_payload` 를 강제한다(`consent.py:141-142`).

**카드정보 유출 경로 — 검증된 부재(negative).** 예외 메시지로 카드/PNR/비밀번호가 새는지 AST 로 전수
확인했다: `src/srt_mobile_api/*.py` 의 모든 `raise` 문에서 f-string 으로 보간되는 표현식을 뽑아보면
`payloads.py` 21건 / `parsers.py` 31건 / `http.py` 15건 / `models.py` 12건 / `client.py`·`session.py` 0건이고,
**보간되는 것은 전부 필드 *이름*·상수·길이·컨텍스트 문자열이다.** 값이 들어가는 것은
`payloads.py:1154`(`gnrmRsvPsbImg` 이미지명), `:1202`(좌석수/인원수), `:1691`(열차종별코드),
`:2402`(할인코드/인원수), `models.py:407,416,435`(역코드·열차번호·일시) 뿐 — 어느 것도 자격증명이 아니다.
특히 `_required_digits`(`payloads.py:697-714`)는 `{name}`/`{length}`/`{max_length}` 만 보간하고
**값은 절대 보간하지 않으므로**, 형식이 틀린 PAN 이 예외 문자열로 새지 않는다.
`safety.assert_no_card_secrets`(`safety.py:821-833`)도 **필드명만** 나열한다.

**설계상 남는 성질(→ P2CRO-10 으로 승격했다):** `fake_card_only=True` 는 검증되지 않는 호출자의 주장이고,
기본 consent + `dry_run=False` 만으로 실카드가 청구된다. 게이트 코드는 자기가 하는 일을 정확히 하지만
`consent.py` 의 산문이 그보다 강하게 주장한다. 자세한 내용과 4조합 실행결과는 §1 P2CRO-10.

---

## 5. 문서·테스트 주장 대 실제 — 기계적 대조 결과

### 5.1 수치 핀은 모두 살아 있다 (과거 "72 public methods" 재발 없음)

| 주장 위치 | 주장 | 실측 | 판정 |
|---|---|---|---|
| `README.md:228` / `test_release_readiness.py:876` | "26 routes" | `len(READ_ONLY_ROUTES) == 26` | ✅ |
| `README.md:53` / 같은 테스트 | `1607 passed, 1 deselected` | `-m "not live"` 미적용 실행에서 `1607 passed, 1 skipped` (그 1건이 `test_live_service.py:11` live 마커) | ✅ |
| `test_public_contract.py:9-100` | 공개 메서드 집합 | 실제 35개와 **정확히 일치** (`inspect` 로 확인) | ✅ |
| `README.md:129-130` | "six `get_*_selector(...)`" | station/station_map/date/passenger/seat_option/train_group = 6 | ✅ |
| `README.md:193-199` | kill switch 표 4 yes / coupon no | `SRT_LIVE_MUTATION_CATEGORIES == {"reserve","cancel","payment","refund"}` | ✅ |

**전체 스위트: 1607 passed, 1 skipped.** 무의미하게 조용히 스킵되는 테스트는 없다(스킵 1건은
`SRT_MOBILE_API_LIVE` opt-in 이 목적인 live 스모크). 즉 "핀이 있는 척하지만 아무것도 검사하지 않는"
패턴은 이번에 발견되지 않았다 — §3의 P2CRO-08(거짓을 pin 하는 테스트)만 예외.

### 5.2 정적 코드테이블 전수 diff — 둘 다 완벽 일치

**역명 테이블** `src/srt_mobile_api/stations.py`
vs `analysis/apktool/assets/offline/js/stationInfo.js` (`stationList` 배열 358행 파싱):
고유 코드 344개, **누락 0 / 여분 0 / 이름 불일치 0.**

**할인종류코드** `src/srt_mobile_api/discounts.py` vs
`analysis/raw/base/assets/offline/js/commCode.js` (JSON 파싱, 361 엔트리):
- `code_group_cd == "dcntKndCd"` 인 행 = **171개**, 라이브러리 표 = **173개**
- 차이 2개 = `133 기본 특별할인(기준)`, `191 정차역 할인` — 둘 다 `code_group_cd` 키가 **없는** 행이고,
  파일에서 `132`(dcntKndCd)와 `192`(dcntKndCd) **사이**(`commCode.js:487-494`)에 있다.
  docstring 이 주장한 그대로다(인용 `:487-495` 도 정확).
- `rmk == "V"` 행 = **25개** — docstring 주장과 일치.
- 이름 불일치 0.

**즉 `discounts.py` docstring 의 세 가지 주장(173 vs 171, 어느 두 행인지, V 25개)이 전부 실측으로 참이다.**

### 5.3 코드 인용 268건 줄범위 검사

`src/srt_mobile_api/*.py` + `tests/*.py` 의 `파일.js/java/html:숫자` 인용 중, 저장소 안에서
파일명이 해석되는 것 **268건**을 뽑아 대상 파일 줄수와 대조:
**범위 이탈 2건뿐** — 둘 다 위에서 다뤘다(P2CRO-02 `AndroidManifest.xml:315`,
P2CRO-05 `netfunnel.js:60477`). 나머지 266건은 줄범위 안이다.

내용까지 표본 검증한 것(전부 정확):
- `messages.js:217` = `rsv023 : "선택하신 열차는 선행 및 후행 열차를 모두 선택하셔야 예약이 가능합니다."`
  → `TRANSFER_BOTH_LEGS_MESSAGE` 와 글자 단위 일치
- `ara0101v.js:302-303` = `sJrnyTp="14"; nJrnyCnt="2";` → 환승 토글, 번들 유일
- `ara0101v.js:866-882` = 좌석지정 필드 일가(`seatNo1_N`, `scarGridcnt1/2`, `scarNo1/2`) → 그대로
- `ara1001l.js:1435-1448` = jobId `1103`/`1101`/`1102` 분기 → 그대로
- `ara1001l.js:1511` = `choiceSeatCount: lfn_getRsv("totPrnb")` → 그대로
- `ara1001l.js:1580-1596` = 왕복 2단계(가는열차 결과 임시저장 후 재검색) → 그대로
- `ara0101v.js:808-836` = 승객 슬롯 압축 루프 `i=1..5`, `psgGridcnt = idx-1` → 그대로
- `main.html:650-661` `lfn_getTrNoData` = 3/4자리만 패딩, 5자리 통과 → `zfill(5)` 와 정합
  (라이브러리가 1~2자리도 패딩하는 것은 앱보다 관대할 뿐 어긋나지 않음)
- `commCode.js:487-495` = 무그룹 2행 위치 → 그대로

### 5.4 문자열/숫자 타입 불일치 — 이번엔 0건

AST 로 `payloads.py` 의 모든 문자열키 dict 리터럴을 훑어 **비문자열 상수값 0건**.
런타임으로도 8개 빌더를 실제 호출해 반환 dict 의 모든 값이 `str` 임을 확인했다
(search_page 68필드, search_ajax 32, fare 25, timetable 4, personal_reserve 36,
cancel 3, reservation_list 1, passenger_selector 8 — 전부 non-str 0).
금액·인원수는 `_payment_amount` / `_payment_passenger_count` 가 `lstrip("0")` 후 빈 문자열이면
**거부**하도록 되어 있어(`payloads.py:1972-1974, 2013-2015`) "0000 → ''" 함정도 막혀 있다.

---

## 6. 확인불가로 남기는 것

- `Ata09036` / `Atc02063` / `Atc14087` / `Ard02045` 네 라우트의 **정적** 근거는 여전히 0-hit 이고
  참조구현 1개(srtgo=ryanking13 벤더링=srtgo_plus, 셋이 사실상 하나)뿐이다. 2026-07-26 라이브런은
  단일여정·1인·일반실·개인카드·일시불 한 건만 답했다. 이 사실 자체가 코드/문서에 정직하게 적혀 있다
  (`safety.py:483-492`, `client.py:1626-1648`) — 결함이 아니라 명시된 한계다.
- `reserve_transfer` 의 slot-2 키 5개(`hydrated`/`inferred` 티어)와 좌석지정(`jobId=1103`)의
  **제출 대상 URL** 은 여전히 추론이다. `payloads.py:118-146` 의 티어 데이터와
  `client.py:1281-1291` 의 "fetch `/ara/ara0101v.do` and read its inline `fn_submit` before trusting this"
  경고가 이미 이것을 정확히 서술한다.
- P2CRO-06 이 실서버에서 실제로 발화하는지는 미검증(해당 라우트의 실응답 컨테이너 조합 미관측).

---

## 7. 우선순위 요약

| id | 심각도 | 한 줄 |
|---|---|---|
| P2CRO-10 | high | `MutationConsent` 문서는 "실카드 청구엔 두 플래그를 다 뒤집어야 한다"지만, 기본 consent + `dry_run=False` 만으로 PAN 이 실서버로 나간다(4조합 실행 확인) |
| P2CRO-06 | high | `normalize_result_row` 가 빈 `dsOutput0` 하나에 막혀 `resultMap` 의 진짜 결과를 못 읽는다(환불·취소·**결제** 공통) |
| P2CRO-01 | medium | `cancel()` jrnyCnt 기본값의 근거문이 거짓 — `reserve_transfer` 가 만든 2여정 hold 를 흘릴 수 있다 |
| P2CRO-07 | medium | 예약목록 populated row 의 라이브검증 여부를 코드가 스스로 모순되게 말한다(결제금액 출처) |
| P2CRO-02 | low | `AndroidManifest.xml:143/:315` 는 jadx 기준, 같은 저장소의 `:2/:53` 은 apktool 기준 — 트리 미표기 |
| P2CRO-03 | low | `선행/후행` 글로스는 `ara1001l.js:1611`, 4곳이 `:1607` 로 인용 |
| P2CRO-04 | low | `deviceKey="-"` 근거는 `ref-srtgo_plus.md:130,138-140`, 인용은 `:112,120-121` |
| P2CRO-08 | low | `EXCLUDED_API_DOMAINS` 와 그것을 단언하는 테스트가 현재와 반대 사실을 pin |
| P2CRO-05 | info | `netfunnel.js:60477` 은 줄이 아니라 문자 오프셋 |
| P2CRO-09 | info | 1차 S2-02(그룹 하이드레이션 grpDv="0")는 앱과 동일한 동작 — 결함 아님 |
