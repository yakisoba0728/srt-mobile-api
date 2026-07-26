# SRT 3차 검증 (verifier-2) — 16건 반증 감사

검증자 원칙: 인용된 file:line 을 직접 열어 확인. 실행 가능한 주장은 실제로 실행.
애매하면 REFUTED/하향. 저장소는 읽기 전용으로만 접근했다
(python 실행으로 생기는 `src/srt_mobile_api/__pycache__` 는 사전 존재분이라 손대지 않음).

### 검증 범위 밖 (반드시 읽을 것)
- 1·2차 산출물(`04-transfer.md:223-227`, "1차 S5-01", "1차 S7-03" 등)은 이 저장소 밖에 있어 **대조하지 못했다.**
  그 교차참조가 사실인지는 이 보고서가 보증하지 않는다.
- "프로브 3/4/6" 은 이전 세션의 실행기록이므로 원문을 볼 수 없었다. 대신 **동일 프로브를 직접 재실행**했다.

### 줄번호 드리프트 처리 원칙
- ±5줄 이내에서 **같은 구문**이 인접 줄에 실재하면 줄번호만 정정하고 주장은 유지한다.
- 인용이 **무관한 내용**에 착지하면 그 근거는 무너진 것으로 본다 (→ P2CRO-04 가 정확히 그 경우).

---

## S1-02 — 로그인→결제 종단 테스트 부재 → **CONFIRMED (low)**

- `tests/fixtures/login_success.json` 전문 = `{"userMap":{"RTNCD":"Y","MSG":"로그인 성공","CUST_NM":"TEST"}}` — `MB_CRD_NO` 없음. 직접 확인.
- `src/srt_mobile_api/client.py:1679-1684` — `membership_number = session.membership_number` / `if not membership_number: raise SrtAuthError("... userMap.MB_CRD_NO ...")`. 인용 정확.
- `tests/test_payment_mutation.py:133` `SrtSession(login_id="synthetic", user_map={"MB_CRD_NO": FAKE_MEMBERSHIP})`; `:477-500` 도 `SrtSession` 직접 주입. `client.login()` 경유 없음.
- `grep -rn login_success tests/` → `test_session.py:18,63,82,153,183,187,230` 와 `test_mutation_scripts.py:740` 뿐. 후자의 라우터(`:735-759`)는 login→search→reserve→cancel 만 다루고 결제 라우트 `/ata/selectListAta09036_n.do` 가 없다. → login() 경유 pay_with_card() 테스트 0건.
- **인용 드리프트 2건**: (a) `docs/VERIFICATION.md:303-304` 는 "`mbCrdNo` is read from the session's own `userMap.MB_CRD_NO` rather than asked of the caller." 라는 **설계 서술**이지 라이브런 기록이 아니다. 실제 라이브 결제런 기록은 `docs/VERIFICATION.md:40` (`pay_with_card | 2026-07-26 | SUCC / IRT000000`) 와 `:230`. (b) `srtgo/srt.py:721` 은 빈 줄이고 `MB_CRD_NO` 는 `:724`.
- 판정: 사실관계 전부 확인. 런타임 결함이 아니라 테스트 커버리지/픽스처 최소성 문제 → low 유지.

---

## S2-03 — 출발역=도착역 검증 부재 → **CONFIRMED (low)**, 인용줄 정정

- 앱 근거 인용줄이 4줄 틀렸다. `ara0101v.js:563-568` 은 "10매 이상은 단체예약" 안내 블록이고, 실제 동일역 가드는 **`analysis/apktool/assets/offline/js/ara/ara0101v.js:570-574`**:
  `570: if ($("#btn_dpt_stn").text() == $("#btn_arv_stn").text())` / `572: srtAlertBoxDivShow("알림","출발역과 도착역이 같습니다.",null,null);` / `573: return;`
  (grep 로 `:572` 확정). 파일·함수·내용이 맞으므로 주장은 유지, 줄번호만 정정.
- `src/srt_mobile_api/models.py:216-224` `TrainSearchQuery.__post_init__` — 역코드 공백여부 / `departure_date` 8자리 / `departure_time` 6자리 / `train_group_code ∈ {300,900,109}` 만 검사. 동일역 비교 없음. 직접 확인.
- 서버 거동은 미확인이므로 "오답을 낸다"는 단정 불가. 앱의 사전검증이 라이브러리에 없다는 사실만 확정 → low.

---

## S3-01 — 왕복 시 코레일역 금지 게이트 미재현 → **PARTIAL (low)**

- 앱 근거는 전부 정확(줄번호 포함):
  - `ara0101v.js:337-341` — `if (lfn_isKorailStn(sDptStn) || lfn_isKorailStn(sArvStn)) { callbackChkRtrp(); srtAlertBoxDivShow("알림","코레일 열차는 왕복 열차 예약을 이용하실 수 없습니다.",null,null); return; }`
  - 함수 정의 `analysis/apktool/assets/offline/sub/main.html:568-577` — `gubun == 'SRT'` 이면서 코드가 일치하면 false, 아니면 true.
  - 데이터 `analysis/apktool/assets/offline/js/stationInfo.js:29-45` — `gubun:"SRT"` 17개역(광주송정·김천구미·공주·나주·대전·동대구·동탄·목포·부산·수서·신경주·오송·울산·익산·정읍·지제·천안아산).
- 라이브러리: `src/srt_mobile_api/payloads.py:1341-1345` 는 `train.service_class_code != "17"` 만 거부. 역 화이트리스트 검사 없음. `round_trip` 은 `:1453` 에서 `rtnDv` 만 바꾼다. `src/srt_mobile_api/stations.py` 는 코드→이름 표뿐이고 `gubun` 정보를 아예 갖고 있지 않다(`:1-12` 및 grep).
- **결함으로서의 실체가 약하다.**
  1. 생애주기가 다르다. 앱 게이트는 *검색 폼*에서 열차가 존재하기 전에 선택된 역만 보고 발동한다. 라이브러리의 `round_trip` 은 *이미 찾은 `TrainSummary`* 에 붙는 플래그다.
  2. 포섭된다. 클래스 17 열차의 역은 앱 자신의 `stationInfo.js` 정의상 SRT 17개역 집합 안에 있으므로, 기존 `service_class_code=="17"` 가드가 사실상 같은 결과를 낸다. 주장 본문도 이를 자인.
- 사실(화이트리스트 부재)은 참이므로 REFUTED 아님. medium → low.

---

## S4-03 — reserve_transfer 미검증 + slot-2 5키 추론 → **CONFIRMED (info)**

- `src/srt_mobile_api/payloads.py:152-189` `TRANSFER_SLOT2_FIELD_EVIDENCE` 직접 확인. `stlbTrnClsfCd2 / dptStnConsOrdr2 / arvStnConsOrdr2 / dptStnRunOrdr2 / arvStnRunOrdr2` 5개가 `"inferred"` 이고 바로 위 주석이 "0-hit in any form. Slot 1's name with the suffix changed, and nothing more."
- `src/srt_mobile_api/client.py:1379-1394` docstring 확인: "**NOT LIVE-VERIFIED — read this before sending one.**", 5개 키 이름 나열, `reserveType` 이 `"11"` 이며 `jrnyTpCd` 를 따라간다면 `"14"` 여야 할 수 있음을 명시.
- 0-hit 재검증(직접 실행): `grep -rl "stlbTrnClsfCd2\|dptStnConsOrdr2\|arvStnConsOrdr2\|dptStnRunOrdr2\|arvStnRunOrdr2" analysis/` → 출력 0건.
- 실제 전송 지점 `payloads.py:1553-1570` `_second_journey_slot_fields` 도 확인.
- 라이브러리가 이미 전부 문서화 → 신규 결함 아님. 감사 재확인 사실로 info.

---

## S6-01 — 포인트/전자지갑/복합결제 미구현 → **PARTIAL (info)**

- 앱 근거는 참: `analysis/apktool/assets/offline/js/common/messages.js:28-40` 에 `pay010`~`pay019`.
  `:28-31` pay010 "포인트번호(휴대폰번호)와 포인트비밀번호를 입력해주세요 … OK캐쉬백 포인트 …", `:39` pay018 "복합결제 시 포인트는 100원 단위로 사용가능합니다." (주장의 `:29-40` 은 1줄 드리프트.)
- **라이브러리 근거 두 건이 사실과 다르다.**
  - 주장 "`grep -rn 포인트|point|wallet src/` → 0건" 은 **거짓**. `src/srt_mobile_api/payloads.py:1929` = `PAYMENT_MEANS_CREDIT_CARD = "02"  # 결제수단코드 (02 신용카드, 11 전자지갑, 12 포인트)`, `:1930` = `PAYMENT_CARD_INPUT_WAY = "@"  # 카드입력방식 (@ 신용카드/OK포인트, "" 전자지갑)`. 즉 대체 결제수단의 wire 코드값이 이미 코드에 기록되어 있다.
  - 주장 "왜 없는지에 대한 명시적 기록이 코드에 없다" 도 **거짓**. `payloads.py:2088-2091` — "there is exactly one payment means on this form (`ststlGridcnt` / `inrecmnsGridcnt` / `stlMnsSqno1` are all \"1\"). Computing them independently would invent a split this form cannot express."
- 참인 부분: 포인트/전자지갑/복합결제 빌더는 없고 `card_payment_payload`(`payloads.py:2092-2124`)는 `stlMnsCd1="02"`, `stlMnsSqno1`/`ststlGridcnt`/`inrecmnsGridcnt` 모두 `"1"` 고정. 정확한 wire 필드명 미확인도 참.
- 기능 부재는 사실이나 "흔적/기록 없음" 프레이밍은 반증됨. low → info.

---

## S7-01 — normalize_result_row 폴백 실패 → **CONFIRMED (low)**

- `src/srt_mobile_api/parsers.py:1113-1117` 직접 확인:
  ```python
  def normalize_result_row(data):
      out = data.get("outDataSets") or {}
      if isinstance(out, dict) and "dsOutput0" in out:
          return _first_row(out.get("dsOutput0"))
      return _first_row(data.get("resultMap"))
  ```
  `dsOutput0` **키 존재만으로** resultMap 폴백이 차단된다. 소비처 `:1619` cancel, `:1739` payment, `:1902` refund 확인.
- **직접 실행 재현**:
  입력 `{'outDataSets':{'dsOutput0':[]}, 'resultMap':[{'strResult':'FAIL','msgCd':'WRT999999','msgTxt':'환불 불가'}]}`
  → `parse_refund_response` / `parse_unpaid_cancel_response` 모두
  `SrtProtocolError: SRT {refund|cancel} response must contain a resultMap result row`. 실제 FAIL 사유는 읽히지 않는다.
- 이는 **"폴백이 폴백하지 않는" 진짜 로직 결함**이다. `_parse_result_envelope` 자신의 docstring(`parsers.py:1546-1553`)이 "accepts BOTH container spellings (`outDataSets.dsOutput0` first, `resultMap` as the fallback)" 라고 선언한 계약을 위반한다. 서버가 무엇을 보내든 무관하게 잘못된 코드다.
- **다만 이 조합은 픽스처 전수에서 관측된 적 없다.** 관측된 병렬 컨테이너 선례는 `tests/fixtures/reservation_list_empty.json` 의 `resultMap(SUCC/IRZ000005)` + `rsMap(FAIL/WRT300005)` 라는 **다른 쌍**이고, `parsers.py:2009-2037` 주석도 그렇게 기록한다.
- 실피해 미입증 → high → **low**.

---

## S8-01 — EXCLUDED_API_DOMAINS 명명 불일치 → **CONFIRMED (low)**

- `src/srt_mobile_api/safety.py:911-922` `EXCLUDED_API_DOMAINS = frozenset({"reservation","ard-payment-entry","payment","refund","cancellation","ata-detail","native-bridge","external-seatmap"})` 확인.
- `tests/test_redaction_safety.py:165-168` `test_safety_excludes_dangerous_domains_without_stub_apis` 가 `"reservation"/"ard-payment-entry"/"payment" in EXCLUDED_API_DOMAINS` 를 단언 — 확인.
- **기능적 사용처 0건**: `grep -rn EXCLUDED_API_DOMAINS src/ tests/ scripts/` → 정의 1곳 + 그 테스트 3줄뿐. 실제 전송 게이트는 `safety.py:440-470` `SRT_LIVE_MUTATION_CATEGORIES` 가 담당하며, 그 주석은 reserve/cancel(2026-07-25), payment/refund(2026-07-26)이 **전부 라이브 검증됨**을 기록한다.
- `docs/RELEASE_GAP_PLAN.md:519-524` 가 이미 "native-bridge/external-seatmap 만 영구제외로 두고 reservation/cancellation/refund(+payment)는 opt-in tier 로" 라고 지시했고 미반영. `:1068` 은 "retire it" 이라고까지 적혀 있다. (주장의 `:520-527` 은 항목 8이 `:519` 에서 시작하는 1줄 드리프트.)
- 런타임 안전성 무영향 + 유지보수 오도 → low 유지가 정확.

---

## P2MIS-04 — 예약대기 옵션 `/ata/selectListAta01135_n.do` 미구현 → **CONFIRMED (low)**

- 참조구현 직접 확인(`/Users/yakisoba/Documents/GitHub/srtgo_plus/srtgo/srt.py`):
  - `:98` `"standby_option": f"{SRT_MOBILE}/ata/selectListAta01135_n.do",`
  - `:1014-1051` `reserve_standby_option_settings(...)` — 바디 `{pnrNo, psrmClChgFlg, smsSndFlg, telNo}` 4개(`:1041-1046`), POST(`:1049`).
  - `:862-876` `reserve()` — 좌석불가+예약대기가능이면 `reserve_standby(...)` 후 `if self.phone_number:` 로 곧바로 `reserve_standby_option_settings(...)` 호출.
  - telNo 공급원 `:726` `self.phone_number = user_info["MBL_PHONE"]` — 가드 없음. 우리 쪽은 `models.py:36` 이 userMap 전체를 보관하므로 값은 이미 손에 있다.
- 라이브러리: `grep -rn "1135" src/` → `client.py:1224` 주석 1건뿐 — "that route is 0-hit in our v2.0.41 bundle and has no equivalent in it, so it is NOT implemented and a standby entry made here simply carries the server's defaults." 메서드/빌더/라우트 전무.
- 0-hit 재확인: `grep -rl "01135" analysis/` → 0건.
- **다만** 참조구현에서도 `if self.phone_number:` 조건부 후처리이고, 미구현 시 서버 기본값이 적용될 뿐 잘못된 결과가 나오지 않는다. standby 자체도 라이브 미검증. medium → **low**.

---

## P2MIS-07 — 승차권 변경 4필드 빈 값 고정 → **CONFIRMED (info)**

- `docs/analysis/srt-app-api-library-spec-2026-07-09.md:187` — "| `tkDptDt`, `tkDptTm`, `tkTrnNo`, `tkTripChgFlg` | Ticket-change related fields. |" 확인.
- `docs/analysis/ref-srtgo_plus.md:415` — "| **Change (변경)** | **NOT** | srtgo_plus has no seat/train change endpoint. Still capture-blocked for us. |" 줄번호까지 정확.
- `src/srt_mobile_api/payloads.py:641-644` — `"tkDptDt": "", "tkDptTm": "", "tkTrnNo": "", "tkTripChgFlg": ""` 확인.
- 알려진 공백, 신규 발견 아님 → info 그대로.

---

## P2INC-09 — 곁다리 dsOutput0 가 resultMap FAIL 을 덮음 → **PARTIAL (low)**

- **S7-01 과 같은 한 줄(`parsers.py:1113-1117`)의 다른 분기**다. 같은 근본원인에 high 를 두 번 줄 수 없다.
- **직접 실행 재현**: `{"outDataSets":{"dsOutput0":[{"strResult":"SUCC"}]}, "resultMap":[{"strResult":"FAIL","msgCd":"X","msgTxt":"y"}]}`
  → `parse_refund_response` / `parse_unpaid_cancel_response` / `parse_card_payment_response` 셋 다 `status='SUCC'`. 재현 성공.
- **그러나 이 분기는 문서화된 우선순위가 설계대로 동작한 결과다.** `parsers.py:1546-1553` 이 "routes through `normalize_result_row`, which accepts BOTH container spellings (`outDataSets.dsOutput0` first, `resultMap` as the fallback)" 라고 명시한다. dsOutput0 에 진짜 행이 있을 때 그것을 우선하는 것 자체는 의도된 계약이며, S7-01 분기(빈 dsOutput0 → 폴백 실패)와 달리 무조건 잘못이라 말할 수 없다.
- 주장 본문도 "outDataSets+resultMap 동시 적재는 픽스처 전수 확인 결과 관측된 적 없다"고 자인.
- "같은 파일이 같은 API 패밀리에 정반대 우선순위" 프레이밍도 과장: `parsers.py:2069` 예약목록 파서가 resultMap 만 읽는 것은 `:2027-2035` 가 실측 응답을 근거로 명시 설계한 것이다.
- high → **low**, PARTIAL.

---

## P2INC-05 — 숫자 PNR 정규화의 정책 불일치 → **PARTIAL (info)**

- 양쪽 근거 실재: `payloads.py:1772-1786` `_foreign_reservation_message` ("converting a numeric PNR drops any leading zeros, which would cancel the wrong reservation or none at all"), `parsers.py:1970-1971` `_reservation_list_optional_string` (`if isinstance(value, int) and not isinstance(value, bool): return str(value)`), 호출 `parsers.py:2101-2103`.
- **주장 자신이 실피해 부재를 인정**한다(JSON 정수 리터럴은 선행 0 을 표현할 수 없다).
- 더 결정적으로 **두 방어는 다른 입력을 막는다**: 쓰기 경로는 *호출자가 넘긴* int 를 거부하고, 읽기 경로는 *서버가 보낸* JSON 숫자를 수용한다. 후자는 `parsers.py:1960-1965` 가 "Raising over one odd field would cost the caller the PNRs of every reservation in the list, which is the outcome this read exists to prevent" 라며 근거를 대고 선택한 정책이다.
- "읽기 경로가 쓰기 경로의 방어를 세탁한다"는 규정은 두 정책의 대상 차이를 지운 것. 사실 참 / 결함 규정 과장 → PARTIAL, low → info.

---

## P2SAF-01 — 환승 홀드 해제 수단 부재 → **CONFIRMED (low)**

- 앱 근거 전부 정확(grep 로 확정): `ara0101v.js:92` `"jrnyCnt" :"1",`(직통 시드), `:292` `var nJrnyCnt = "1";`, `:302-303` `sJrnyTp = "14"; nJrnyCnt = "2";`, `:307` `$("#nJrnyCnt").val(nJrnyCnt);`, `:309-311` `oData = {"jrnyTpCd": sJrnyTp, "jrnyCnt": nJrnyCnt}`. 번들 전체에서 `jrnyCnt/nJrnyCnt` write 는 이 지점들뿐.
- 라이브러리 근거 전부 정확:
  - `scripts/recover_hold.py:79-81` `cancel_hold()` 가 `client.cancel(pnr, consent=build_cancel_consent())` 만 호출.
  - argparse(`:155-179`)는 `pnr` / `--list` / `--device-key` 뿐. `grep -n journey scripts/recover_hold.py` → **0건**.
  - `models.py:598-603` `SrtReservationHold` 필드 = `pnr_no, journey_list_key, total_seat_count, raw` — 여정건수 없음.
  - `payloads.py:1840-1842` 기본값 정당화, `payloads.py:1730-1770` `_cancel_journey_count` 는 "Never raises" 로 무엇이든 `"1"` 로 낙하, `payloads.py:1697` `payload["jrnyCnt"] = JOURNEY_COUNT_TRANSFER`.
- **상한이 있다**: `client.py:1398-1402` 가 "release it with `cancel(hold, journey_count=\"2\", consent=…)` … its default is wrong for this shape, and getting it wrong is how a hold survives a cancel that looked like it worked" 라고 명시하고 `README.md:143-144` 도 같은 경고를 한다. 표현수단은 API 에 존재·문서화돼 있고, 빠진 것은 **recover_hold.py 한 곳**이다.
- 게다가 `reserve_transfer` 는 라이브 전송된 적이 없고(S4-03), 서버가 잘못된 `jrnyCnt` 에 어떻게 반응하는지도 미검증.
- 최후수단 스크립트가 라이브러리 자신이 필요하다고 서술한 값을 표현 못 한다는 실체는 실재 → CONFIRMED. high → **low**.

---

## P2SAF-05 — 데이터 기반 가드가 카드 4필드에만 걸림 → **PARTIAL (low)**

- **프로브 직접 재실행**:
  - `SrtHttpClient.post_form("/ara/selectListAra10007_n.do", {"tkRetPwd":"1234","dscp_no":"0123456789","dscp_pwd":"9999","hmpgPwdCphd":"abc"})`
    → 전송됨: `SENT POST /ara/selectListAra10007_n.do b'tkRetPwd=1234&dscp_no=0123456789&dscp_pwd=9999&hmpgPwdCphd=abc'`
  - 같은 라우트 + `{"stlCrCrdNo1":"4111111111111111"}` → `SrtProtocolError: SRT request carries card-secret fields (stlCrCrdNo1) on a route that is not the card payment …`
  - 비대칭 재현 성공.
- 근거 라인 전부 실재: `safety.py:797-804` `CARD_SECRET_FIELDS` 4개, `:774-796` 취지("stated on the DATA rather than on the route"), `:27-32` "would happily send a PAN or a ticket return password", `:834-857` `_assert_empty_body_request`(`REFUND_TICKET_INFO_PATH` 한 경로), `redaction.py:91-99` 쿠폰=베어러 자격증명.
- **그러나 게이트에 '구멍'은 없다.** `CARD_SECRET_FIELDS` 는 카드비밀 데이터 게이트이고 카드비밀에 대해서는 뚫린 곳이 없다. 그리고 **출하된 어떤 메서드도** 이 값들을 엉뚱한 라우트에 싣지 않는다: `tkRetPwd` 는 `payloads.py:2208,2226` refund 폼에서만, `dscp_no/dscp_pwd` 는 쿠폰등록 mutation(`client.py:1509`, `payloads.py:2234`)에서만 쓰인다(grep 전수).
- 남는 악용 경로는 호출자가 `post_form` 을 오용하거나 미래 리팩터가 실수하는 경우뿐 — 게이트 우회가 아니라 **미적용 범위**다. 하드닝 제안으로서는 타당하나 안전게이트 관통은 아니다. medium → **low**, PARTIAL.

---

## P2SAF-09 — READ_ONLY_ROUTES 는 개수만 카나리 → **PARTIAL (low)**

- 비대칭 자체는 사실: `tests/test_safety.py:166` `assert len(READ_ONLY_ROUTES) == 26` (개수만) vs `tests/test_mutation_live_paths.py:573-590` `assert SRT_LIVE_MUTATION_CATEGORIES == frozenset({"reserve","cancel","payment","refund"})` + "If this fails … do NOT 'fix' the test" 주석. 둘 다 직접 확인.
- **그러나 "라우트 하나를 빼고 다른 하나를 넣으면 어떤 테스트도 깨지지 않는다"는 거짓이다.** `safety.py:887` `if route not in READ_ONLY_ROUTES: raise` 때문에 테스트가 실제로 호출하는 라우트는 그 테스트 자체가 핀이 된다.
- 26개 전체를 스크립트로 검사한 결과 **모든 라우트가 최소 3개 테스트 파일에서 참조**된다 (최소 3건 `/atc/getListAtc14087.do`, 최대 23건 `/ts.wseq`; **UNPINNED = []**). 즉 *제거*는 확실히 잡힌다. 추가로 `test_reservation_list.py:353`, `test_discount_reads.py:50,272,294`, `test_refund_mutation.py:337`, `test_seat_designation.py:450` 등 명시적 멤버십 단언도 존재.
- 실제로 안 잡히는 것은 *추가*(아무도 안 쓰는 라우트를 빼고 가짜를 넣는 조합)뿐. 주장의 절반만 성립 → PARTIAL, low 유지.

---

## P2CRO-01 — cancel jrnyCnt 기본값 정당화가 거짓 → **PARTIAL (low)**

- 인용문 실재 확인: `payloads.py:1840-1842` — "Defaulting to \"1\" is also what every hold this library can create actually is: `personal_reservation_payload` only ever sends `jrnyCnt=\"1\"`". 이 일반화는 `payloads.py:1697`(`transfer_reservation_payload` 가 `payload["jrnyCnt"] = JOURNEY_COUNT_TRANSFER` = "2")과 `client.py:1404-1415`(그 페이로드로 `SrtReservationHold` 반환) 앞에서 **거짓**이다. 이 절반은 확정.
- 앱 근거도 정확: `ara0101v.js:302-303` 이 번들에서 `jrnyCnt="2"` 를 쓰는 유일 지점. `payloads.py:1806-1814` 가 인용한 `function cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt)` 도 실재(라이브 티켓목록 인라인 스크립트 인용문).
- **그러나 "2여정 hold 를 흘릴 수 있다"는 두 곳을 무시해야 성립한다**: `client.py:1398-1402` 와 `README.md:143-144` 가 모두 전송 전에 `journey_count="2"` 를 넘기라고 지시한다. `client.py:1452-1453` 의 가정법 서술("if live capture ever shows a multi-leg PNR needing `jrnyCnt=\"2\"`")은 *캡처* 부재를 말하는 것이지 다여정 hold 생성을 부정하지 않는다.
- 실체는 주석 한 문장의 doc-drift. 1차의 "문서화된 캐치" 분류가 전적으로 틀리지는 않으나, 문장이 **거짓 사실을 단언**한다는 지적은 유효. medium → **low**, PARTIAL.

---

## P2CRO-04 — deviceKey="-" 참조문헌 오인용 → **CONFIRMED (low)**

- 값 자체 확인: `src/srt_mobile_api/session.py:66` `"deviceKey": "-",`.
- 0-hit 확인(직접 실행): `grep -rn "deviceKey" analysis/` → **0건**(21,673 파일 전체). 앱 자체 근거가 없다는 전제 성립.
- **인용 오류 확정.** `src/srt_mobile_api/session.py:57-60` 주석은 "Both wire refs agree: srtgo srt.py:704 (data[\"deviceKey\"] = \"-\") and ref-srtgo_plus.md:112,120-121" 라고 적는데, grep 로 확인한 실제 내용은:
  - `docs/analysis/ref-srtgo_plus.md:112` = "**Key reconciliation vs our APK analysis.** Our gap plan expected the *payment entry* to be `ard02017`/`ard02018` …" — 결제 엔드포인트 대조 문단. deviceKey 언급 전무.
  - `:121` = "## 3. Login / auth (`srt.py:673-731`)" — 섹션 제목. `:120` 은 빈 줄.
  - 실제 deviceKey 근거는 `:130` (`deviceKey=-,  # literally a hyphen — no real device key needed`) 과 `:138-139` ("`deviceKey` is the constant `\"-\"` (`srt.py:705`)").
- 앱 근거가 0-hit 인 항목에서 유일한 근거 포인터가 무관한 내용에 착지한다 → ±5줄 드리프트 면책 대상이 아니다. doc-drift/low 로 CONFIRMED.

---

## 요약

| id | 판정 | 보정 심각도 |
|---|---|---|
| S1-02 | CONFIRMED | low |
| S2-03 | CONFIRMED | low |
| S3-01 | PARTIAL | low |
| S4-03 | CONFIRMED | info |
| S6-01 | PARTIAL | info |
| S7-01 | CONFIRMED | low |
| S8-01 | CONFIRMED | low |
| P2MIS-04 | CONFIRMED | low |
| P2MIS-07 | CONFIRMED | info |
| P2INC-09 | PARTIAL | low |
| P2INC-05 | PARTIAL | info |
| P2SAF-01 | CONFIRMED | low |
| P2SAF-05 | PARTIAL | low |
| P2SAF-09 | PARTIAL | low |
| P2CRO-01 | PARTIAL | low |
| P2CRO-04 | CONFIRMED | low |

- **critical/high 로 승격할 항목 없음.** 원래 high 로 제기된 3건(S7-01, P2INC-09, P2SAF-01)은 모두 미관측 시나리오이거나 문서화된 대안이 존재하여 low 로 하향.
- S7-01 / P2INC-09 는 `parsers.py:1113-1117` **한 줄의 두 분기**이므로 수정은 1건(선택된 컨테이너가 빈 행을 내면 다른 컨테이너로 폴백)으로 족하다. 실질적으로 고칠 값어치가 있는 유일한 코드 결함.
- 나머지는 doc-drift(S8-01, P2CRO-01, P2CRO-04), 테스트/스크립트 커버리지(S1-02, P2SAF-09, P2SAF-01), 미구현 기능(P2MIS-04, S6-01) 범주.
