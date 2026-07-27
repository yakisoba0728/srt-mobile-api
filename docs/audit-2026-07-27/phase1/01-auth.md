# SRT 인증·로그인·기기키·세션 감사 보고서

**감사 범위:** 로그인(회원번호/이메일/휴대폰), 기기키(deviceKey/deviceId) 발급과 역할,
세션 쿠키/토큰 유지, 자동로그인, 로그아웃, 회원정보 조회, 보안 벤더가 인증 흐름에
끼어드는 지점.

**대조 대상:** `src/srt_mobile_api/session.py`, `http.py`, `config.py`, `live.py`
(+ 보조: `client.py`의 `login/logout/get_main/get_booking_page/get_mutual_verification`,
`models.py`의 `SrtSession`, `parsers.py`의 로그인폼/만료 감지기, `redaction.py`).

## 0. 감사 배경 — 이 영역은 이미 5차례 감사됨

`docs/analysis/impl-audit-2026-07-22.md` ~ `impl-audit-reverify5-2026-07-22.md`
5개 문서가 이미 정확히 이 `auth-session` 서브시스템을 반복적으로 대조검증했다.
발견된 실결함(모두 이미 수정 확인됨, 현재 `session.py`/`http.py`에 반영):

- (reverify3) 로그인 `deviceKey` 필드값이 `config.device_key`(ANDROID_ID 형식)였던 것을
  `"-"` 상수로 수정 — **현재 `session.py:61`에 반영됨, 확인.**
- (reverify3) 실패 메시지를 `userMap.MSG`(중첩)에서만 읽던 것을 top-level `MSG` 우선으로
  수정 — **현재 `session.py:79-82`에 반영됨, 확인.**
- (reverify4) IP 차단 시 비-JSON 응답이 `SrtProtocolError`로 새던 것을 `SrtIpBlockedError`
  (⊂ `SrtAuthError`)로 분류하도록 수정 — **현재 `http.py:98-115`에 반영됨, 확인.**
- (reverify4) `seatAttCd` 출처 문제(시트맵 빌더, 다른 서브시스템) — 본 감사 범위 밖.

reverify5(최신, 2026-07-22)는 "0 provable divergences"로 결론짓고, 제기된 2건의 후보
결함(로그인 `X-Requested-With` 헤더값 주장, act_10 `user_data` 누락 주장)을 모두
오인용(mis-cited ground truth)으로 기각했다.

**본 감사는 이 5차 감사를 맹신하지 않고 독립적으로 재검증**했다: jadx/apktool 원본,
오프라인 자산(`main.html`), `srtgo`/`srtgo_plus` 참조 구현 소스 자체(단순히 docs의
인용을 신뢰하지 않고 `srtgo`,
`srtgo_plus`의 실제 `srt.py`를 직접 열람), 그리고
`tests/fixtures/login_success.json`을 직접 대조했다. 그 결과 기존 5차 감사의 결론(현재
코드는 이 서브시스템에서 입증가능한 결함이 없다)을 재확인했고, **기존에 없었던 새 발견
1건(doc-drift, 인용 오류)** 을 추가로 확인했다.

## 1. 기능 전체 목록

| # | 기능 | 엔드포인트/메커니즘 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|---|---|---|---|---|
| 1 | 로그인 페이지 취득(쿠키 확보) | `GET /login/login.do` | `srt-app-api-library-spec-2026-07-09.md:250` (runtime); `analysis/apktool/assets/offline/sub/main.html:721` form 존재 | `session.py:46` | 있음 |
| 2 | 로그인 제출 | `POST /apb/selectListApb01080_n.do` | `main.html:721-728` (form+6개 hidden input); `srtgo/srt.py:700-712`; `srtgo_plus`도 동일 경로 | `session.py:47-69` | 있음 |
| 2a | 로그인 ID 타입 자동판별 (이메일→`2`, 휴대폰→`3`, 회원번호→`1`) | `srchDvCd` | `srtgo/srt.py:691-698` (`EMAIL_REGEX`/`PHONE_NUMBER_REGEX`, 대시필수); 앱 자체 판별 로직은 서버렌더링이라 APK에 없음 | `session.py:20-29` `_detect_login_type` | 있음 — **의도적으로 srtgo보다 개선**: 대시 없는 `01X` 휴대폰번호도 `3`으로 인식(주석에 근거 명시), 원본 대시필수 정규식의 한계를 보완 |
| 2b | 휴대폰 로그인 시 대시 제거 | `srchDvNm` | `srtgo/srt.py:697-698` `re.sub("-", "", srt_id)` | `session.py:44` | 있음, 일치 |
| 2c | 비밀번호 평문 전송 | `hmpgPwdCphd` | `srt-app-api-library-spec-2026-07-09.md:135` "Password; secret", 이름의 "Cphd"(cipher)와 달리 평문 확인됨; `main.html:727` | `session.py:55` | 있음, 일치 |
| 2d | 로그인 deviceKey 상수 | `deviceKey="-"` | **오프라인 번들 전체에 `deviceKey` 0-hit** (`grep -rn deviceKey analysis/apktool/assets/offline` 결과 없음). 유일한 근거는 `srtgo/srt.py:704` `"deviceKey": "-"` 와 `srtgo_plus` 동일 | `session.py:61` | 있음, srtgo와 일치. **주의: 앱 자체(디컴파일) 근거는 없음 — 참조구현에만 의존.** 이미 session.py 주석이 이 사실을 정직하게 명시함 |
| 2e | 나머지 필드 (`check`,`auto`,`login_referer`,`page`,`customerYn`,`ciUptYn`,`dupInfoVal`) | 빈 문자열 기본값 | `check`/`auto`/`login_referer` 3개는 `main.html:724-726`에 `value=""`로 실재; `page`/`customerYn`/`ciUptYn`/`dupInfoVal` 4개는 **오프라인 번들에 0-hit**(직접 grep 확인), `srt-app-api-library-spec-2026-07-09.md`의 사전 런타임 캡처만 근거 | `session.py:52-66` | 있음. 6개 중 3개는 정적 자산으로 직접 확인됨, 나머지 4개는 이전 런타임 캡처에만 의존(확인불가이지만 phantom은 아님, 이미 reverify5가 검토) |
| 3 | 로그인 성공 판정 | `userMap.RTNCD == "Y"` | 디컴파일 0-hit(서버렌더링). `srt-app-api-library-spec-2026-07-09.md:620` "Login | Success, app JSON RTNCD=Y" (사전 런타임 스모크 기록) | `session.py:71` | 있음, 유일 근거와 일치 |
| 4 | 로그인 실패 메시지 파싱 | top-level `MSG` 우선, 없으면 `userMap.MSG` | `srtgo/srt.py:713-716`: `raise SRTLoginError(r.json()["MSG"])` (top-level) | `session.py:79-82` | 있음, 일치 (reverify3에서 수정 확인) |
| 5 | IP 차단 처리 | 비-JSON 평문 "Your IP Address Blocked" → `SrtIpBlockedError` | `srtgo/srt.py:719-720` | `http.py:98-115`, `errors.py:70` | 있음 (reverify4에서 수정 확인), `SrtIpBlockedError ⊂ SrtAuthError` 계층 확인 |
| 6 | 로그인 후 메인페이지 검증 | `GET /main/main.do?deviceId=<android_id>` | `SRWebActivity.java:1582-1584` `X0()` (앱 콜드스타트 시 로드하는 홈 URL; ANDROID_ID를 `Settings.Secure.getString(..., "android_id")`로 읽음, 대시/콜론 제거 없음 — main.do용은 그대로 사용) | `session.py:83-87`, `client.py:172-175`, `config.py:19` `device_key` 기본값 | 있음. `deviceId` 파라미터명, 값 형식(16자리 ANDROID_ID 포맷) 일치 |
| 7 | 로그인 후 예약시작페이지 검증 | `GET /ara/ara0101v.do` | `SRWebActivity.java:2414` (백버튼 특례로만 언급); 서버렌더링이라 직접적 "로그인 직후 호출" 증거는 앱에 없음 | `session.py:88-92`, `client.py:177-180` | 있음. 인증확인 목적의 방어적 호출로 보이며 하네스에 문제 없음(5차 감사 미지적) |
| 8 | 세션 쿠키(JSESSIONID) 유지 | 표준 `Set-Cookie`/`Cookie` | `main.html:479-480` `KR_JSESSIONID`/`SR_JSESSIONID`(둘 다 `JSESSIONID=...`) | `httpx.Client`의 쿠키 자동 관리, `http.py:64-65` | 있음 |
| 9 | 세션 만료 감지(HTML 200, 로그인폼) | `is_login_form` | `main.html`의 로그인 form (action=`.../apb/selectListApb01080_n.do`, `hmpgPwdCphd` input) | `parsers.py:150-177` `_LoginFormParser`/`is_login_form` | 있음, form action 경로+필드 매칭 정확 |
| 10 | 세션 만료 감지(HTML 200, 로그인 리다이렉트 알럿) | `is_login_redirect_page` | 2026-07-26 라이브캡처: `Sr.msgs.login020` + `srtAlertBoxDivShow` in `<script>` (오프라인 `messages.js`엔 `login020` 0-hit, 라이브 전용) | `parsers.py:180-240` | 있음, 라이브검증됨(주석에 명시) |
| 11 | 세션 만료 감지(HTTP 3xx → 로그인) | `_is_login_redirect` | (일반적 서버 리다이렉트 패턴) | `http.py:36-50` | 있음, host/scheme/port/path 엄격검사 |
| 12 | 로그아웃 | 로컬 쿠키 클리어만, 서버 미호출 | 오프라인 `main.html:455` `<form action="/srail-app/login/loginOut.do">`; `srtgo_plus/srt.py:92,745` `POST /login/loginOut.do`(접두사 없음, 바디 없음) — **두 참조 소스 자체가 경로 불일치**(`/srail-app/` 접두 유무) | `client.py:161-162` `logout()` → `clear_session()` | **부분구현(의도적)** — 3차례 선행감사(impl-audit, reverify, reverify2)에서 이미 검토되어 "deliberate read-only design"으로 결론남. 새 발견 아님, info로만 기록 — §S1-03 |
| 13 | 회원번호 추출 | `SrtSession.membership_number` ← `user_map["MB_CRD_NO"]` | **디컴파일 0-hit** (서버렌더링). `srtgo/srt.py:721` `user_info["MB_CRD_NO"]`(무조건 읽음, KeyError 방어 없음 — 즉 실제 응답에 반드시 존재한다는 강한 방증); `docs/VERIFICATION.md:303-304` 2026-07-26 라이브 결제런에서 이 값이 없으면 `pay_with_card`가 즉시 `SrtAuthError`로 막히므로, 그 라이브런이 성공했다는 사실 자체가 실응답에 `MB_CRD_NO`가 채워짐을 실증 | `models.py:38-61` | 있음(기능적으로 정확, 라이브검증 간접 실증). **단, 코드 주석의 인용이 틀림 — §S1-01. 정식 fixture엔 이 값이 없어 종단테스트 부재 — §S1-02** |
| 14 | 회원정보(상호검증) | `POST /ara/selectListAra10130_n.do` | `full-api-analysis-2026-07-20.md:195` `ara1001l.js:227-242`; `msgCd`/`strResult`/`mutMrkVrfCd` | `client.py:404-415`, `parsers.py:1120-1160` | 있음 |
| 15 | 자격증명 로그 마스킹 | `srchDvNm`,`hmpgPwdCphd` 등 | N/A(설계) | `redaction.py:13-14` `SENSITIVE_KEYS` | 있음 |
| 16 | `application.gds_userInfo` (부킹페이지 임베디드 회원정보: `MB_CRD_NO`,`USER_DV`,`CUST_MG_NO`,`ABRD_RS_STN_CD`,`GOFF_RS_STN_CD`) | 서버렌더링 JS 전역객체 | `full-api-analysis-2026-07-20.md:429-432`; `ara0101v.js:52-62`; 좌석선택 게이팅에 쓰임(`ara1001l.js:1288-1306`) | **파싱 안 함** — `get_booking_page()`(`client.py:177-180`)는 `parse_html_page`로 가시텍스트만 추출, `gds_userInfo` 값은 읽지 않음 | 없음(단, 저위험) — `MB_CRD_NO`는 이미 `userMap`으로 확보되고, `USER_DV`/`ABRD_RS_STN_CD`/`GOFF_RS_STN_CD`는 클라이언트측 UI 편의필드(서버가 최종 검증을 하므로 라이브러리 정확성에 영향 없음). 새 finding으로 올리지 않음(정보성) |
| 17 | FIDO/OnePass 생체인증 (`requestServiceRegist/Release/Auth`, `allowedAuthnr`) | 네이티브 `srbridge` 전용, `fido.srail.co.kr` UAF 프로토콜 | `SRWebActivity.java` bridgeCall 디스패처; `com/raonsecure/**`(OnePass SDK 전체); `srt-app-api-library-spec-2026-07-09.md:531-563` §8 "Not an HTTP API" | 미구현 | **의도된 제외** — 순수 HTTP 클라이언트로는 재현 불가(하드웨어 attestation 필요). 결함 아님 |
| 18 | SNS 로그인(Google/Kakao) | `snsLogin` bridge → 네이티브 SDK → `{id,type}` 콜백만 | `SRWebActivity.java:2188-2194,2315-2348` | 미구현 | **의도된 제외** — 실제 서버 엔드포인트가 오프라인 번들/jadx에 전혀 없고(서버렌더링 JS가 `id`/`type`을 어느 endpoint로 보내는지 근거 전무), OAuth SDK 흐름 자체가 스크립트로 재현 불가 |
| 19 | 푸시 디바이스 등록(`regDevice`/`unRegDevice`) | H2O SmartBroker 바이너리 프로토콜, `push.srail.co.kr:3101` | `b6/a.java`, `com/H2OSystech/SmartBrokerAPIs/` | 미구현 | **의도된 제외** — HTTP/JSON이 아닌 별도 바이너리 TCP 프로토콜, 로그인/부킹 세션과 무관 |
| 20 | TransKey 보안키패드(`showTransKey`) | 로그인 UI 자체의 네이티브 입력 보안(SEED 암호화 후 평문 반환) | `SRWebActivity.java:2352-2390` | N/A | 실제 와이어 필드(`hmpgPwdCphd`)는 평문이므로 이 계층은 UI 전용, 라이브러리에 불필요 |
| 21 | 자동로그인 플래그 | `auto` hidden field | `main.html:725` `value=""` (기본 미체크) | `session.py:52` 항상 `""` | 있음 — 디바이스 로컬 저장 기반 UX 기능이라 스크립트 클라이언트에는 해당사항 없음(값을 `"Y"`로 바꿔 보내도 서버가 관용적으로 처리한다고 reverify5가 이미 확인) |
| 22 | `login_type` 명시적 오버라이드 파라미터 | N/A(라이브러리 자체 확장) | 없음(srtgo는 이 파라미터가 아예 없음) | `session.py:38,41` | 있음 — 정당한 라이브러리 편의 확장, 결함 아님 |

**요약 집계** (표의 상위 항목 #1~#22를 집계 단위로 함; #2a~#2e는 #2 하위 상세이므로
별도 집계하지 않음): 추출 22개 중 — 네이티브 전용이라 라이브러리 범위 밖(#17
FIDO, #18 SNS로그인, #19 푸시등록, #20 TransKey) 4개 제외, 나머지 18개가 실제
비교대상. 그중 정확히 구현됨 16개, 부분구현(의도적 설계, §S1-03) 1개(#12 로그아웃),
미구현이나 저위험(§1 #16 설명) 1개(#16 `gds_userInfo`). 16+1+1 = 18.

## 2. 문제 항목 상세

### S1-01 — `SrtSession.membership_number`의 docstring 인용이 잘못된 절을 가리킴 (doc-drift, low)

**앱 근거:** `docs/analysis/full-api-analysis-2026-07-20.md:429-432` (섹션 4.5,
`UserInfo (application.gds_userInfo)`) — 이 절은 **부킹페이지에 서버가 렌더링하는
전역 JS 객체 `application.gds_userInfo`** 를 설명하는 것이며, `ara0101v.js:52-62`,
`ara1001l.js:1288,1316-1318`을 근거로 한다. 로그인 응답(`POST
/apb/selectListApb01080_n.do`)의 JSON `userMap`과는 **다른 객체**다.

**라이브러리 근거:** `src/srt_mobile_api/models.py:40-47`
```
"""The account's 회원번호, read from the login response's ``userMap``.

This is NOT newly captured: :class:`SrtSession` has always kept the whole
``userMap`` the login returned, and ``MB_CRD_NO`` is one of its keys
(``docs/analysis/full-api-analysis-2026-07-20.md:431`` ...
```
이 인용은 "`userMap`이 `MB_CRD_NO`를 키로 가진다"는 구체적 주장의 근거로
`full-api-analysis:431`을 지목하지만, 그 줄은 `userMap`이 아니라 `gds_userInfo`를
설명한다. 인용된 근거가 실제로 뒷받침하는 대상과 코드가 주장하는 대상이 다르다.

**실제 검증한 결과(이번 감사에서 독립적으로 확인):**
- `userMap`이 `MB_CRD_NO`를 담는다는 근거는 앱 디컴파일에는 전혀 없다
  (`/apb/selectListApb01080_n.do`의 응답 처리는 서버렌더링, APK 0-hit).
- 그러나 `srtgo/srtgo/srt.py:721`에서
  `user_info = json.loads(r.text)["userMap"]; self.membership_number =
  user_info["MB_CRD_NO"]` — **가드 없이 무조건 읽음** (없으면 `KeyError`),
  이는 실응답에 이 키가 항상 존재한다는 강한 정황증거다.
- `tests/fixtures/login_success.json`은 `{"userMap":{"RTNCD":"Y","MSG":"...",
  "CUST_NM":"TEST"}}`로 `MB_CRD_NO`가 **없다** — 이 fixture 자체는 단순화된
  합성 데이터라 반증은 아니지만, docstring의 "always kept the whole userMap"
  주장과 나란히 두면 혼란을 준다.
- `docs/VERIFICATION.md:303-304`: 2026-07-26 라이브 카드결제 실행이 성공했고,
  `client.py:1678-1684`(`pay_with_card`)는 `membership_number`가 비어있으면
  네트워크 호출 전에 `SrtAuthError`로 즉시 막으므로, **그 라이브런의 성공 자체가
  실제 로그인 응답에 `MB_CRD_NO`가 채워져 있었음을 실증**한다. 이것이 진짜
  1차 근거이며 docstring이 인용해야 할 자료다.

**결론:** 기능적 주장(`userMap.MB_CRD_NO`를 읽는 것)은 srtgo 소스 + 2026-07-26
라이브 결제런으로 간접 실증되어 **정확하다.** 다만 코드 주석이 그 근거로 엉뚱한
문서 절(부킹페이지의 `gds_userInfo`)을 인용하고 있어, 차후 유지보수자가 "앱
디컴파일에 `userMap.MB_CRD_NO`가 직접 나온다"고 오해할 소지가 있다.

**제안:** `models.py:44`의 인용을 `docs/analysis/full-api-analysis-2026-07-20.md:429-432`
대신 (a) `srtgo/srt.py:721`(무조건적 키 접근)과 (b) `docs/VERIFICATION.md`의
2026-07-26 라이브 결제런(간접 실증)으로 교체. `application.gds_userInfo`도
별도 개념으로 앱에 실재하지만(§1 표 #16) 이는 `userMap`과 다른 객체이므로
혼동하지 않도록 명시.

### S1-02 — 정식 로그인 fixture에 `MB_CRD_NO`가 없어 로그인→결제 종단 경로가 테스트되지 않음 (partial/unverifiable, low)

**근거:** `tests/fixtures/login_success.json`(로그인 성공 응답의 정식 fixture,
`test_session.py`의 모든 로그인 테스트가 이걸 씀) 은
```json
{"userMap":{"RTNCD":"Y","MSG":"로그인 성공","CUST_NM":"TEST"}}
```
로 **`MB_CRD_NO` 키가 없다.** 반면 `client.py:1678-1684`(`pay_with_card`)는
`session.membership_number`(=`user_map.get("MB_CRD_NO")`)가 빈 문자열이면 네트워크
호출 전에 즉시 `SrtAuthError`를 던진다. srtgo(`srt.py:721`)는 이 키를 가드 없이
읽으므로, 이 fixture를 srtgo에 넣으면 `KeyError`가 난다.

그런데 `tests/test_payment_mutation.py`의 결제 테스트들(`_client()` 헬퍼,
`test_pay_with_card_threads_the_membership_number_from_the_session` 등, :477-500)은
`client.session.current = SrtSession(login_id="synthetic",
user_map={"MB_CRD_NO": FAKE_MEMBERSHIP})`로 **`membership_number`가 이미 채워진
세션을 직접 주입**하고, 실제 `client.login()` 호출은 거치지 않는다. 즉 저장소 전체에
**"정식 `login_success.json`으로 `login()`을 수행 → 그 결과로 `pay_with_card`가
성공적으로 `mbCrdNo`를 채운다"를 종단으로 검증하는 테스트가 하나도 없다.**

`docs/VERIFICATION.md:303-304`의 2026-07-26 라이브 결제런이 실제로 `MB_CRD_NO`가
채워진 응답을 받았음을 간접 실증하므로(§S1-01) **현재 라이브 서버는 문제없이
동작할 가능성이 높다.** 다만 (a) 정식 fixture가 이 사실과 불일치하는 채로 남아있고,
(b) 그 불일치를 잡아낼 테스트가 없다는 것은 실제 결함은 아니되 **회귀 방지망의
구멍**이다 — 예컨대 `login_success.json`을 "더 사실적으로" 다듬으려는 후속 변경이
실수로 `MB_CRD_NO`를 넣지 않은 채로 남겨도 아무 테스트도 이를 알아채지 못한다.

**제안:** `login_success.json`(또는 별도 fixture)에 `MB_CRD_NO`를 추가하고,
`client.login(...)` → `client.pay_with_card(...)`가 실제로 `mbCrdNo`를 페이로드에
채우는 것을 검증하는 종단 테스트를 1개 추가. `MB_CRD_NO`가 라이브 응답에 항상
존재한다는 §S1-01의 근거(srtgo 무조건 접근 + 2026-07-26 라이브런)도 이 fixture
갱신의 근거로 문서화.

### S1-03 — 로그아웃이 서버 엔드포인트를 호출하지 않음 (info, 이미 3차 검토된 의도적 설계)

**앱 근거:** `analysis/apktool/assets/offline/sub/main.html:455`
`<form id="form1" action="/srail-app/login/loginOut.do" method="POST"
data-ajax="false">`(hidden `login_referer`); 참조구현
`srtgo_plus/srtgo/srt.py:92,745`는 `POST /login/loginOut.do`(접두사 없음, 빈 바디)를
호출함 — **두 참조 소스 간에도 경로가 다름**(`/srail-app/` 접두 유무), 어느 쪽이
현재 앱이 실제로 쓰는 경로인지 이 저장소의 증거만으로는 확정 불가.

**라이브러리 근거:** `src/srt_mobile_api/client.py:161-162`
```python
def logout(self) -> None:
    self.clear_session()
```
서버로 아무 요청도 보내지 않고 로컬 쿠키만 지운다.

**상태:** 이미 `docs/analysis/impl-audit-2026-07-22.md:89`,
`impl-audit-reverify-2026-07-22.md:96-97`, `impl-audit-reverify2-2026-07-22.md:139-140`
세 차례 걸쳐 검토되었고, reverify2가 "deliberate read-only design, not a wire
divergence"로 확정했다. 로그아웃은 SRT_LIVE_MUTATION_CATEGORIES(예약/취소/결제/환불)에
속하지 않는 저위험 동작이라 안전모델의 구멍은 아니다. 새 결함 아님 — info로만 기록.

## 3. 확인했으나 결함 없음으로 결론난 항목 (기록용)

- **deviceKey="-" vs config.device_key**: 로그인폼과 main.do 각각 올바른 값을 씀
  (§1 #2d, #6). 실제 코드 확인.
- **RTNCD=Y 성공게이트**: 유일한 근거(사전 런타임 스모크)와 일치, false-negative
  리스크는 있으나(실응답이 RTNCD를 생략하는 경우) 증명 불가능한 잔여 리스크로
  이미 reverify5가 결론.
- **로그인 실패 메시지 top-level MSG 우선 읽기**: `srtgo/srt.py:713-716`과
  직접 대조 확인, 일치.
- **IP 차단 → `SrtIpBlockedError(SrtAuthError)`**: 클래스 계층 `errors.py:70`
  직접 확인, `SrtAuthError` 상속 맞음.
- **로그인 자격증명 마스킹**: `srchDvNm`,`hmpgPwdCphd` 모두 `redaction.py:13-14`
  `SENSITIVE_KEYS`에 포함 확인.
- **세션만료 3중 감지**(로그인폼 HTML / 로그인리다이렉트 알럿 HTML / HTTP 3xx
  리다이렉트): 세 경로 모두 존재하고 각각 다른 실제 서버 응답 형태에 대응,
  중복이 아니라 상호보완임을 코드 주석과 실제 파서 로직으로 확인.
- **로그인 타입 자동판별의 srtgo 대비 개선**(대시없는 01X 번호 처리): 의도적
  개선이며 실제 정규식 비교로 확인(srtgo는 대시 필수, 라이브러리는 옵션).

## 4. 확인 방법 메모

- `analysis/apktool/assets/offline/`, `analysis/jadx/sources/`에서 직접 grep
  (jadx만 신뢰하지 않고 원본 asset 텍스트인 `main.html`을 1차 근거로 사용 —
  이건 디컴파일 왜곡 가능성이 없는 순수 텍스트 자산이므로 smali 대조가 불필요함).
- `SRWebActivity.java` 전체(2709줄)에서 `login`/`deviceKey`/`ANDROID_ID`/
  `bridgeCall` 관련 부분을 직접 읽어 네이티브 브릿지 액션 30종을 전수 확인,
  인증 관련 항목(FIDO/SNS/푸시/TransKey)이 모두 HTTP JSON API가 아님을 직접 검증.
- `srtgo/srtgo/srt.py`,
  `srtgo_plus/srtgo/srt.py`를 **docs의 인용을
  거치지 않고 직접** 열람하여 로그인 필드, 정규식, `MB_CRD_NO` 접근 방식을 재검증.
- `tests/fixtures/login_success.json`, `login_failure.json`,
  `login_failure_toplevel.json`을 직접 열람.
- 기존 5개 auth-session 감사 문서(`impl-audit*.md`)를 선행자료로 참고하되,
  그 결론을 그대로 베끼지 않고 인용된 1차 소스(앱 asset, srtgo 소스, fixture)를
  재추적하여 독립 검증.
