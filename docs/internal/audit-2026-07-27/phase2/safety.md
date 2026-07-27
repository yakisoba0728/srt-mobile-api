# SRT 2차 검토 — 안전·일관성 렌즈

- 대상: `srt-mobile-api`
- 렌즈: 상태변경 경로의 consent 게이트 우회 가능성 / kill switch 와 실제 라우트의 정합 /
  카드·자격증명 마스킹 탈출 경로 / allowlist 라우트의 실제 성격 / 공개 API 표면 일관성
- 방법: `safety.py`·`http.py`·`consent.py`·`redaction.py`·`client.py` 전문 정독 →
  `httpx.MockTransport` 로 **6건의 실행 프로브**로 게이트를 직접 두드림 →
  APK 디컴파일(`analysis/apktool/assets/offline/js/**`, `analysis/jadx/sources/**`)로 앱측 대조 →
  1차 8건 보고서와 대조.
- 저장소는 **읽기 전용**으로만 다뤘다. `git` 상태 변경 없음, 저장소 파일 생성·수정 없음.
  프로브 스크립트는 전부 scratchpad 안에서 실행했다.

## 실행 프로브 결과 (근거의 뼈대)

`/private/tmp/.../scratchpad/probe1.py`, `probe2.py` — `httpx.MockTransport` 로 실제 전송을 가로채
"무엇이 실제로 와이어에 나가는가"를 측정했다. 라이브 서버는 건드리지 않았다.

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | `MutationConsent(allow_payment=True, dry_run=False)` (그 외 전부 기본값) + 실카드 형태 PAN | **전송됨.** `POST /ata/selectListAta09036_n.do`, 본문에 `stlCrCrdNo1=4111111111111111` |
| 2 | `http._send_mutation_request(path, category="payment", data=<카드폼>, headers={})` — consent 객체 **없음** | **전송됨.** 동일 라우트, PAN 그대로 |
| 3 | `post_form("/ara/selectListAra10007_n.do", {"tkRetPwd":…, "dscp_no":…, "dscp_pwd":…, "hmpgPwdCphd":…})` | **전송됨.** 읽기 라우트에 반환비밀번호·쿠폰자격증명·로그인비번이 그대로 실림 |
| 4 | 같은 읽기 라우트에 `stlCrCrdNo1` | **거부됨** (`SrtProtocolError`) — 카드 필드만 데이터 기반 가드가 걸림 |
| 5 | `register_discount_coupon(..., dry_run=False)` | **거부됨** (`SrtMutationNotAllowedError`) — coupon kill switch 정상 |
| 6 | `reserve_transfer(itinerary, consent=MutationConsent(allow_reserve=True, dry_run=False))` | **전송됨.** `jrnyCnt=2`, `jrnyTpCd=14`, `stlbTrnClsfCd2`/`dptStnRunOrdr2`… 추론 필드 5개 포함 |

프로브 4·5 는 **게이트가 설계대로 작동함을 확인**한 것이고, 1·2·3·6 이 아래 결함의 근거다.

---

# A. 1차가 놓친 것

## P2SAF-01 — [high / risk] 환승 예약 홀드를 해제할 방법이 `cancel()`·`recover_hold.py` 어디에도 없다

> ※ 이 항목은 1차 04-transfer 가 **"문서화된 캐치, 버그 아님"으로 명시 기각**한 것이다.
> "B. 1차가 틀리게 본 것"에 다시 적지 않고 여기 한 번만 쓴다. 기각 근거를 무너뜨리는 사실이
> 네 가지 있다.

- **앱 근거**: `analysis/apktool/assets/offline/js/ara/ara0101v.js:92`
  (`"jrnyCnt":"1"` — 직통 기본값) 대 `ara0101v.js:302-311`
  (`sJrnyTp="14"; nJrnyCnt="2";` → `oData = {"jrnyTpCd": sJrnyTp, "jrnyCnt": nJrnyCnt}`).
  번들 전체에서 `"jrnyCnt"` write 는 이 두 곳뿐이며, **앱은 여정건수를 예약 형상별 값으로 다룬다.**
- **라이브러리 근거**:
  - `scripts/recover_hold.py:81` — `result = client.cancel(pnr, consent=build_cancel_consent())`.
    `journey_count` 인자 없음. `main()` 의 argparse(`:155-179`)에도 해당 플래그 없음.
  - `src/srt_mobile_api/models.py:600-603` — `SrtReservationHold` 는 `pnr_no`,
    `journey_list_key`, `total_seat_count`, `raw` 뿐. **여정건수 필드가 없다.**
  - `src/srt_mobile_api/payloads.py:1841-1842` — 기본값 `"1"` 의 정당화:
    “Defaulting to `"1"` is also what every hold this library can create actually is:
    `personal_reservation_payload` only ever sends `jrnyCnt="1"`.”
  - `src/srt_mobile_api/client.py:1399-1401` — “its default is wrong for this shape,
    and getting it wrong is how a hold survives a cancel that looked like it worked.”
  - `src/srt_mobile_api/payloads.py:1730-1769` `_cancel_journey_count` — 절대 raise 하지 않음.
- **내용**:
  1. `payloads.py:1841-1842` 의 정당화가 **낡았다**. `reserve_transfer` /
     `transfer_reservation_payload` 가 생긴 뒤로 이 라이브러리는 `jrnyCnt="2"` 홀드를 만들 수
     있다 — 프로브 6 이 실제 와이어에서 `jrnyCnt=2` 를 확인했다. "이 라이브러리가 만들 수 있는
     모든 홀드는 1건"이라는 전제가 참이 아니다.
  2. `reserve_transfer` 가 돌려주는 `SrtReservationHold` 에는 여정건수가 없으므로
     `cancel(hold)` 가 **유도할 수도 없다**. 호출자가 직접 기억해야 한다.
  3. **복구 안전망이 구조적으로 이 값을 표현할 수 없다.** `recover_hold.py` 는 이 프로젝트가
     "PNR 만으로 홀드를 해제하는 최후 수단"이라 문서화한 도구인데(`recover_hold.py:4-9`),
     `journey_count` 를 넘기지도, CLI 로 받지도 않는다. 즉 환승 홀드가 표류하면 이 도구로는
     항상 `jrnyCnt="1"` 만 보낸다.
  4. `_cancel_journey_count` 가 "절대 거부하지 않는" 설계라, 잘못된 값은 조용히 `"1"` 로
     떨어진다. 3번과 합쳐지면 **틀린 취소가 조용히 성공처럼 보일 수 있는** 구성이다.
  - `safety.py:459-469` 는 reserve/cancel 을 **함께** 연 이유를 "회수가능성(recoverability)"
    이라고 명시한다: “Enabling reserve without cancel would mean a mistake or a crash mid-flow
    strands a real reservation … with no programmatic way out.” 환승 예약에 대해서는 그
    보장이 성립하지 않는다.
- **정직성 제약**: 환승 홀드를 실제로 취소해 본 적은 **한 번도 없다**. 그러므로 "서버가 실패한다"
  고 단정하지 않는다. 결함의 실체는 **"라이브러리 자신이 필요하다고 서술한 값을 복구 경로가
  표현할 수 없다"** 이다.
  또한 취소 폼의 `jrnyCnt` 가 행별 파라미터라는 앱측 증거(`cncConfirm(v_pnrNo, v_rsvChgTno,
  v_jrnyCnt)`)는 `payloads.py:1806-1814` 와 `tests/test_live_response_shapes.py:591-611` 의
  **인용문으로만** 존재하고 저장소에 원본 캡처가 없다 — 이는 1차 07-refund S7-03 의 지적과
  일치하며, 나도 그 지적을 교차확인한다.
- **수정 방향**: `SrtReservationHold` 에 `journey_count` 를 실어 `reserve_transfer` 가 `"2"` 로
  채우고 `cancel()` 이 hold 에서 유도하게 하거나, 최소한 `recover_hold.py` 에
  `--journey-count` 를 추가.

## P2SAF-02 — [high / risk] `fake_card_only` 기본값은 "테스트카드만"을 강제하지 않는데, 세 곳의 문서가 강제한다고 서술한다

- **앱 근거**: `analysis/apktool/assets/offline/js/ara/ara1001l.js:1599`
  (`frm.action = contextPath + "/ard/selectListArd02018_n.do";` 단체)와 `:1608`
  (`frm.action = contextPath + "/ard/selectListArd02017_n.do";` 개인) — **앱은 예약 성공 후
  결제 진입 WebView 페이지로 폼을 넘긴다.** 평문 PAN 을 `/ata/selectListAta09036_n.do` 로
  POST 하는 코드는 APK 어디에도 없다: `stlCrCrdNo1`/`vanPwd1`/`Ata09036` 전부
  `analysis/apktool/**` + `analysis/jadx/**` 0-hit(직접 grep 확인). 카드 입력은 보안 키패드
  (`analysis/jadx/sources/com/softsecurity/transkey/TransKeyActivity.java`)를 거친다.
  즉 이 경로는 앱이 아니라 srtgo 계열 단일 출처이고, 그만큼 라이브러리측 게이트에 의존한다.
- **라이브러리 근거**:
  - `src/srt_mobile_api/consent.py:13-18` — “`fake_card_only` defaults to `True` … so a payment
    preview can only ever carry a non-chargeable test card. **A real, chargeable card requires
    the caller to invert BOTH flags explicitly**”
  - `src/srt_mobile_api/consent.py:80-83` — “since payment was live-enabled … it is the last
    gate before a real PAN goes out”
  - `src/srt_mobile_api/consent.py:188-201` `require_card_kind_claim` — 실제 규칙은 XOR 뿐:
    (True,False) 통과 / (False,True) 통과 / (T,T)·(F,F) 거부. **기본 consent 가 그대로 통과한다.**
  - `src/srt_mobile_api/payloads.py:2018-2124` `card_payment_payload` — `fake_card_only` 를
    읽지 않는다. `models.py:777-782` 는 PAN 을 Luhn 검사하지 않는다고 **의도적으로** 명시.
  - `tests/test_payment_mutation.py:605-670` — `(fake_card_only=True, real=False)` 케이스가
    "31개 필드가 그대로 와이어에 나간다"를 **테스트로 고정**하고 있다.
- **내용**: 프로브 1 이 확인한 대로, `MutationConsent(allow_payment=True, dry_run=False)` 만으로
  실카드가 라이브 결제 라우트에 나간다. `fake_card_only` 는 라이브러리가 **검증할 수 없는
  호출자의 주장**이고 그 자체는 설계 선택으로 정당하다(카드 진위 판정은 이 라이브러리의 일이
  아니다). 문제는 문서가 이를 **강제되는 제약**으로 서술한다는 것이다. `consent.py` 세 문단을
  읽고 "기본값이면 실카드는 못 나간다"고 믿은 운영자가, 환경변수에서 읽은 실카드를 그대로
  넘기면 그대로 결제된다. 게이트가 뚫린 것이 아니라 **게이트가 광고된 적이 없는 일을 한다고
  광고되어 있다.**
- **수정 방향**: `require_card_kind_claim` 을 "기본값이면 거부"로 바꾸거나(즉 두 플래그 모두
  명시 필요), 아니면 `consent.py:13-18`/`:80-83` 문구를 "검증 불가능한 선언"으로 정정.

## P2SAF-03 — [medium / risk] `post_mutation_form` 이 "유일한 전송 경로"라는 주장이 사실이 아니고, 진짜 전송 경계는 5개 게이트 중 3개만 재확인한다

- **앱 근거**: 해당 없음 — 라이브러리 내부 방어 계층의 자체 일관성 문제이며 앱 대조 대상이 아니다.
- **라이브러리 근거**:
  - `src/srt_mobile_api/http.py:316` — “This is the only method that can transmit to a mutation
    route.”
  - `src/srt_mobile_api/http.py:235-304` `_send_mutation_request` — 실제로 `self._client.send`
    를 호출하는 함수. 재확인하는 것: 라이브 카테고리 멤버십(`:268`), `assert_mutation_route`
    (`:274`), `assert_mutation_route_category`(`:275`), 비-payment 카드시크릿(`:285-286`).
    **재확인하지 않는 것**: `require_mutation_consent`, `consent.dry_run`,
    `require_card_kind_claim`. consent 인자 자체가 시그니처에 없다.
  - `src/srt_mobile_api/http.py:246-248` — 이 누락을 **스스로 인정**한다:
    “The consent and dry-run gating happens in post_mutation_form before we reach here.”
- **내용**: **private 메서드 호출이 필요하다는 점을 먼저 밝힌다.** 그러므로 "임의 호출자가
  consent 를 우회한다"는 급의 결함이 아니다. 보고 가치는 두 가지다.
  (a) `http.py:316` 의 문장이 문자 그대로 거짓이고, 이 문장은 안전 리뷰어가 가장 먼저 읽는 곳이다.
  (b) 같은 모듈이 `:249-267` 에서 "진짜 send 경계이므로 라우트 불변식 **전체**를 스스로 다시
  주장한다"는 defense-in-depth 패턴을 선언해 놓고, 그 패턴을 5개 게이트 중 3개에만 적용했다.
  프로브 2 는 그 결과를 실측했다: consent 객체가 존재하지 않는 상태에서 PAN 이 결제 라우트로
  나갔다. `post_mutation_form` 을 우회하는 새 호출자가 생기면 그때 실제 구멍이 된다.
- **수정 방향**: `_send_mutation_request` 에 `consent: MutationConsent` 를 필수 인자로 추가하고
  `require_mutation_consent` + `dry_run` + payment 시 `require_card_kind_claim` 을 재확인하거나,
  `http.py:316` 문장을 정정.

## P2SAF-04 — [medium / risk] kill switch 는 카테고리 단위인데, `reserve` 카테고리 안에 라이브 미검증 형상 3개가 그대로 올라타 있다

- **앱 근거**: 예약대기 — `analysis/apktool/assets/offline/js/ara/ara0101v.js:90`
  (`"jobId":"1101" //조정구분코드(1101:개인예약, 1102:예약대기, 1103:시트맵예약)`),
  `ara1001l.js:1448` (`sJobId = "1102"; //예약대기`).
  환승 — `ara0101v.js:302-303` (`sJrnyTp="14"; nJrnyCnt="2";`).
  앱 자신은 이 셋을 **서로 다른 jobId/jrnyCnt 형상**으로 구분한다.
- **라이브러리 근거**:
  - `src/srt_mobile_api/safety.py:520-522` — `SRT_LIVE_MUTATION_CATEGORIES` 는 카테고리
    4개짜리 집합. 라우트나 형상 단위가 아니다.
  - `src/srt_mobile_api/client.py:1300-1314`(`reserve`)와 `:1404-1415`(`reserve_transfer`)가
    **동일 라우트·동일 `category="reserve"`** 로 `_submit_reservation` 을 탄다
    (`client.py:1122-1132`).
  - `src/srt_mobile_api/client.py:1379-1394` — 환승은 라이브러리 자신이
    “**NOT LIVE-VERIFIED — read this before sending one**”, slot-2 키 5개는 slot-1 에서 추론,
    `reserveType="11"` 도 미확인이라고 적는다.
  - `src/srt_mobile_api/safety.py:487-492` — 라이브 검증이 커버한 범위:
    “exactly one single-journey, one-adult, general-seat ticket … Multi-leg, group, standby,
    corporate cards and instalments were not exercised.”
- **내용**: 프로브 6 이 실측한 대로, `allow_reserve=True, dry_run=False` 만으로 추론 필드
  5개(`stlbTrnClsfCd2`/`dptStnConsOrdr2`/`arvStnConsOrdr2`/`dptStnRunOrdr2`/`arvStnRunOrdr2`)를
  포함한 환승 예약 본문이 실서버로 나간다. `standby=True`(jobId=1102)와
  `designated_seats`(시트맵예약)도 같은 카테고리를 탄다. 즉 **증거의 입도(형상별)와 게이트의
  입도(카테고리별)가 어긋나 있다.** 문서 경고는 있으나 게이트는 없다 —
  이 프로젝트가 `coupon` 에 대해 "구현·미리보기는 되되 전송은 막는다"로 세운 원칙이
  형상 수준에는 적용되지 않았다.
- **수정 방향**: 형상 단위 스위치(예: `SRT_LIVE_RESERVATION_SHAPES = {"personal-single"}`)를 두고
  `_submit_reservation` 에서 transfer/standby/seat-designation 을 별도 확인하거나, 최소한
  `reserve_transfer`/`standby` 에 명시적 opt-in 플래그를 요구.

## P2SAF-05 — [medium / risk] 데이터 기반 가드가 카드 4필드에만 걸려, 라이브러리 스스로 "PAN 과 동급 베어러 자격증명"이라 선언한 값들은 임의의 읽기 라우트로 나간다

- **앱 근거**: 해당 없음 — 라이브러리 자체 가드의 적용 범위 문제.
  (참고로 쿠폰 자격증명의 존재 자체는 앱측 문자열로 확인된다:
  `analysis/apktool/assets/offline/js/common/messages.js:111-113`
  `mysrt006 "할인쿠폰번호를 입력하여 주십시오." / mysrt007 "할인쿠폰 비밀번호를 …" / mysrt008 …`)
- **라이브러리 근거**:
  - `src/srt_mobile_api/safety.py:797-804` `CARD_SECRET_FIELDS` = `{stlCrCrdNo1, vanPwd1,
    crdVlidTrm1, athnVal1}` — 4개뿐.
  - `src/srt_mobile_api/safety.py:774-796` — 이 가드의 존재 이유: “stated on the DATA rather
    than on the route: a PAN, a card PIN, a card expiry or a cardholder birthdate may travel
    only as a `payment`.”
  - `src/srt_mobile_api/safety.py:27-32` — 라이브러리 자신이 **반환비밀번호도 같은 위험**으로
    인식한다: “without a body check, `post_form` would happily send a PAN **or a ticket return
    password** to this path.” 그런데 실제 강제는 `REFUND_TICKET_INFO_PATH` **한 경로의 빈 본문**
    (`_assert_empty_body_request`, `safety.py:834-857`)뿐이다.
  - `src/srt_mobile_api/redaction.py:91-99` — 쿠폰번호/비밀번호에 대해:
    “**A COUPON NUMBER IS A BEARER CREDENTIAL** … masked on the same footing as a PAN, not on
    the footing of a PNR.” 그러나 `SENSITIVE_KEYS` 는 **로그·프리뷰 마스킹**일 뿐, 전송 가드가
    아니다.
- **내용**: 프로브 3 이 확인한 대로 `post_form("/ara/selectListAra10007_n.do", {"tkRetPwd":…,
  "dscp_no":…, "dscp_pwd":…, "hmpgPwdCphd":…})` 는 그대로 전송된다. 프로브 4 에서 같은 라우트에
  `stlCrCrdNo1` 을 넣으면 거부된다. 즉 **동일한 위험 등급이라고 라이브러리가 직접 선언한 값들
  사이에 가드 적용이 비대칭**이다. 실제 악용 경로는 "호출자 실수 / 미래 리팩터가 잘못된
  라우트에 폼을 붙임"이며, 이는 `CARD_SECRET_FIELDS` 가 막으려고 만들어진 바로 그 시나리오다.
- **수정 방향**: `CREDENTIAL_SECRET_FIELDS`(=`tkRetPwd`/`retPwd`/`ogtkRetPwd`/`dscp_no`/`dscp_pwd`/
  `hmpgPwdCphd`)를 만들어, 각 값이 자기 라우트(refund step2 / coupon 등록 / login)에서만
  허용되도록 `assert_read_only_request` 와 `_send_mutation_request` 양쪽에 적용.

## P2SAF-06 — [low / doc-drift] `assert_mutation_route` docstring 이 "네 개"라고 하는데 집합은 다섯 개다

- **앱 근거**: 해당 없음.
- **라이브러리 근거**: `src/srt_mobile_api/safety.py:537-538`
  “Allow only **the four** evidenced state-changing routes (host "app", POST).”
  대 `safety.py:412-438` `SRT_MUTATION_ROUTES` — reserve/cancel/payment/refund + `coupon`
  = **5개**. `safety.py:378-379` 는 같은 파일에서 “the FIFTH route added on 2026-07-26” 이라고
  정확히 쓰고 있어, 함수 docstring만 갱신 누락이다.
- **내용**: 동작에는 영향 없음(집합이 진실). 다만 이 함수 docstring 은 mutation allowlist 를
  검토할 때 첫 진입점이고, "evidenced" 라는 단어가 coupon(라이브 미검증)까지 포함하는 것으로
  읽히면 P2SAF-04 와 같은 오해를 부른다.
- **수정 방향**: “the five registered state-changing routes (four live-enabled, one preview-only)”.

## P2SAF-07 — [low / partial] `SrtCouponRegistrationRequest` 는 공개 export 인데 공개 메서드가 받지 않는다

- **앱 근거**: 해당 없음 — 공개 API 표면 일관성.
- **라이브러리 근거**: `src/srt_mobile_api/__init__.py:50,144` (`__all__` 에 포함) 대
  `src/srt_mobile_api/client.py:1499-1504` — `register_discount_coupon(self, coupon_number: str,
  coupon_password: str, *, consent)`. 타입은 `client.py:1577-1582` 에서 **내부적으로만** 생성된다.
- **내용**: 다른 네 mutation 은 전부 타입 객체를 받는다 —
  `cancel(SrtReservationHold | str)`, `pay_with_card(SrtReservationSummary, SrtPaymentCard)`,
  `refund(SrtRefundTicketInfo)`, `reserve(TrainSummary)`/`reserve_transfer(TransferItinerary)`.
  쿠폰만 bare `str` 두 개다. 결과적으로 export 된 타입이 공개 경계에서 쓸 데가 없고,
  `models.py:1257-1258` 이 `repr=False` 로 보호해 놓은 이점(자격증명을 객체로 감싸 다루기)도
  호출자에게 전달되지 않는다.
- **수정 방향**: `register_discount_coupon(request: SrtCouponRegistrationRequest, *, consent)`
  오버로드를 추가하거나, `__all__` 에서 내리기.

## P2SAF-08 — [low / partial] `reserve()` 가 돌려주는 객체를 `pay_with_card()` 가 받지 못한다 (예약→결제 흐름의 타입 단절)

- **앱 근거**: `analysis/apktool/assets/offline/js/ara/ara1001l.js:1608-1618` — 앱은 예약 응답의
  `reservListMap.pnrNo` / `arvDt` / `dptTm` / `lumpStlTgtNo` … 를 **그대로** 결제 진입 폼에
  옮겨 담는다. 즉 앱 흐름에서는 예약 결과가 곧 결제 입력이다.
- **라이브러리 근거**: `src/srt_mobile_api/client.py:1162`
  (`reserve(...) -> MutationPreview | SrtReservationHold`) 대 `client.py:1600-1608`
  (`pay_with_card(reservation: SrtReservationSummary, ...)`).
  `models.py:600-603` `SrtReservationHold` 에는 `received_amount`/`ticket_special_number`/
  `departure_time`/`arrival_time` 이 없고, `payloads.py:2091,2108,2082-2085` 는 그 넷을 필수로
  요구한다.
- **내용**: `reserve` → `pay_with_card` 라는 가장 자연스러운 흐름이 타입 수준에서 끊겨 있어,
  호출자는 반드시 `get_reservations()` 를 다시 읽어 행을 찾아야 한다. `payloads.py:2044-2047` 이
  그렇게 하라고 문서화하고는 있으나, `get_reservations` 의 **populated 행 스키마는 라이브
  미검증**(`models.py:614-628`)이다. 즉 흐름의 필수 중간 단계가 이 저장소에서 가장 검증이 얇은
  읽기에 의존한다. 안전 방향(필드를 추측하지 않음)으로 실패하므로 심각도는 low 로 둔다.
- **수정 방향**: `SrtReservationHold` 로부터 결제 폼을 만들 수 없다는 사실을 `reserve()`
  docstring 에 명시하고, `get_reservations` 재조회가 필수임을 흐름 문서에 못 박기.

## P2SAF-09 — [low / risk] `READ_ONLY_ROUTES` 는 **개수만** 고정되고, mutation 카테고리는 **정확집합**으로 고정된다 (엄밀성 비대칭)

- **앱 근거**: 해당 없음.
- **라이브러리 근거**: `tests/test_safety.py:166` — `assert len(READ_ONLY_ROUTES) == 26`
  (개수 canary) 대 `tests/test_mutation_live_paths.py:573-590` —
  `assert SRT_LIVE_MUTATION_CATEGORIES == frozenset({"reserve","cancel","payment","refund"})`
  (정확집합 canary, "이 테스트가 깨지면 고치지 말라"는 주석까지 포함).
- **내용**: 읽기 allowlist 에서 라우트 하나를 빼고 다른 하나를 넣으면 개수가 같아 **어떤
  테스트도 깨지지 않는다.** 읽기 allowlist 는 "이 라이브러리가 무엇을 건드릴 수 있는가"의
  절반을 차지하는데, mutation 쪽에만 적용된 엄밀성이 여기엔 없다.
- **수정 방향**: `READ_ONLY_ROUTES` 에도 정확집합 canary 추가.

## P2SAF-10 — [info] `EXCLUDED_API_DOMAINS` — 1차 S8-01 교차확인 (재검토 결과 1차 판단이 정확함)

- **앱 근거**: 해당 없음. **라이브러리 근거**: `src/srt_mobile_api/safety.py:911-922`,
  `tests/test_redaction_safety.py:166-168`.
- **내용**: 독립적으로 `grep -rn EXCLUDED_API_DOMAINS src tests docs scripts` 를 돌려 확인했다 —
  이 상수를 읽는 코드는 테스트 1곳뿐이고, 실제 전송 게이트는 `SRT_LIVE_MUTATION_CATEGORIES` /
  `assert_mutation_route` 가 담당하며 그쪽은 정확하다. **런타임 영향 없음**이라는 1차 결론에
  동의하며 심각도도 low 로 유지한다. 다만 `docs/RELEASE_GAP_PLAN.md:1068` 이 이미
  "retire it" 이라고 지시해 둔 상태라는 점만 덧붙인다.

---

# B. 1차가 틀리게 본 것

## B-1. `cancel()` 의 환승 기본값 — 04-transfer.md:62 / :223 은 "버그 아님"으로 기각했다

1차 04-transfer 는 표 13행에서 이렇게 적었다:

> | 13 | 환승 취소 시 `jrnyCnt="2"` 필요 (기본값은 `"1"`) | … | 있음(**문서화된 캐치, 버그 아님**) |

그리고 :223 에서 "이미 (문서화되어) 있음"으로 닫았다. 이 판단은 **문서화 여부만 보고 복구
경로를 보지 않았다.** P2SAF-01 이 그 근거다 —
`scripts/recover_hold.py:81` 은 `journey_count` 를 넘기지도 받지도 않고,
`SrtReservationHold` 에는 유도할 필드가 없으며,
`payloads.py:1841-1842` 의 기본값 정당화는 `reserve_transfer` 도입 이후 사실이 아니다.
"문서에 경고가 있다"는 것과 "도구가 그 값을 표현할 수 있다"는 것은 다른 문제다.

## B-2. 결제 안전 서술 — 06-pay.md 는 카드 게이트를 결함 없음으로 통과시켰다

1차 06-pay 는 findings 4건(S6-01 결제수단 미구현, S6-02/03 doc-drift, S6-04 예약목록 스키마)을
냈고 "실행 검증 (redaction)" 절에서 마스킹은 확인했으나, **`require_card_kind_claim` 이 기본
consent 로 통과한다는 사실은 다루지 않았다.** P2SAF-02 참조. `consent.py:13-18` 의 문장
("requires the caller to invert BOTH flags explicitly")은 코드가 하지 않는 일을 서술한다.

---

# C. 확인했으나 결함이 아니었던 것 (기록용)

- **coupon kill switch**: 프로브 5 확인. `allow_coupon=True, dry_run=False` 로도 전송되지
  않는다(`http.py:379-388` 과 `:268-273` 이중 거부). 설계대로 작동.
- **읽기 경로에서 mutation 라우트 도달**: `assert_read_only_request`(`safety.py:886-890`)의
  allowlist 가 4+1 mutation 라우트를 전부 거부. `tests/test_payment_mutation.py:766-775` 가 고정.
- **카테고리↔라우트 교차사용**: `assert_mutation_route_category`(`safety.py:559-576`)가
  `post_mutation_form` 과 `_send_mutation_request` **양쪽**에서 재확인됨. 프로브 없이 코드로
  확인, 테스트도 존재(`test_payment_mutation.py:713-746`).
- **`repr` 유출**: `SrtPaymentCard`(`models.py:761-764`),
  `SrtRefundTicketInfo`(`models.py:856-862`), `SrtCouponRegistrationRequest`(`models.py:1257-1258`),
  `SrtReservationHold`(`models.py:600-603`) 모두 비밀 필드가 `repr=False`. 예외 메시지도
  `errors.py:8`/`:102`/`:232` 에서 `redact_url` 을 거친다. **유출 경로 없음.**
- **`SrtConfig` 오리진 고정**: `config.py:23-45` 가 생성 시점에 canonical origin 을 강제하므로
  base_url 을 바꿔 쿠키를 다른 호스트로 흘리는 경로 없음. `_request` 는 리다이렉트를 따르지
  않고 raise 한다(`http.py:154-160`).
- **저장소 내 자격증명**: `.gitignore` 가 `/analysis/`, `/srt.apk`, `/.env`,
  `/.local-live-smoke.env` 를 제외한다(`git ls-files analysis` → 0건). APK 에셋
  `analysis/apktool/assets/offline/sub/main.html:479-480` 에는 벤더 빌드 시점의 실제
  `JSESSIONID` 와 개인정보(`BTDT`, `USER_KEY`)가 들어 있으나 **추적되지 않는다**.
  `tests/fixtures/public_discount_search_page.html:6` 는 세션 ID 를 제거했다고 자기 서술하고
  실제로 값이 없다. `SAFETY_STATEMENTS`(`safety.py:924-928`) 위반 없음.
- **`Ara10130`(상호검증값 생성)의 읽기 분류**: 앱 주석은 "상호검증값 **생성**"
  (`ara1001l.js:225`)이지만, 이 값을 홈페이지로 전송하는 `fn_setLog` 본문은 번들에서
  **주석 처리**되어 있고(`ara1001l.js:253-265`), 라이브러리도 값을 읽고 쓰지 않는다.
  앱 동작과 일치하며 돈·예약에 영향 없음. **결함 아님.**
- **NetFunnel 슬롯 취득/해제**: 큐 서버 상태를 바꾸지만 앱의 `TS_AUTO_COMPLETE` 와 동일하고
  (`client.py:495-523`), 실패는 삼켜지되 키가 먼저 pop 되어 누적되지 않는다. **결함 아님.**
- **`get_refund_ticket_info` 가 consent 없이 반환비밀번호를 반환**: 읽기로 분류된 설계이며
  `safety.py:300-327` 이 그 추론의 한계까지 적어 두었다. 1차 07-refund 가 이미 다룸.

---

# D. 집계 근거

이 렌즈에서 내가 독립적으로 재열거한 "전송 가능 표면 + 안전 통제" 항목:
읽기 allowlist 라우트 26개(`safety.py:280-359`) + mutation 라우트 5개(`safety.py:412-438`) +
consent 카테고리 5개(`consent.py:44`) + NetFunnel 오퍼코드 3개(`safety.py:701-716`) = **39**.
이 중 위 결함이 직접 걸리는 것은 payment 라우트/카테고리, cancel 라우트, reserve 카테고리(3개
형상), coupon 카테고리(API 형상), 읽기 라우트 클래스(자격증명 가드) = **6** → 정상 **33**.
