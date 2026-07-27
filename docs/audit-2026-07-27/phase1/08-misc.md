# SRT 08 — 할인·복지·쿠폰·NetFunnel·브릿지·공통헤더·에러코드·안전계층 감사

감사 대상 저장소: `srt-mobile-api`
라이브러리: `src/srt_mobile_api/{discounts,netfunnel,errors,safety,redaction,consent,http,config,session}.py`
담당 범위: 할인/복지/쿠폰/마일리지, NetFunnel 대기열, 네이티브 브릿지, 공통 헤더/UA/기기정보, 에러코드 체계, 안전 계층

## 방법

1. `discounts.py`의 `DISCOUNT_KIND_NAMES_BY_CODE`(173개) 전체를
   `analysis/apktool/assets/offline/js/commCode.js`의 `dcntKndCd` 런과 코드/이름
   **1:1 바이트 단위**로 스크립트 대조 (일치 173/173, 불일치 0).
2. `netfunnel.py`의 URL 빌더(`build_act10_url`/`build_chk_enter_url`/
   `build_set_complete_url`)와 상태코드 테이블을
   `analysis/apktool/assets/offline/js/common/netfunnel.js`의
   `getTidChkEnterProc`/`chkEnterProc`/`TsClient.prototype.setComplete`
   원문과 대조.
3. `errors.py`의 `msgCd`→예외 매핑을 `messages.js`(error001/rsv071/mysrt006-008/
   notice006 등) 및 `tests/fixtures/*.json` 39건 중 `msgCd`가 나타나는 전체
   파일과 대조.
4. `safety.py`의 read-only 라우트 allowlist, mutation 라우트/카테고리 바인딩,
   `CARD_SECRET_FIELDS`, `EXCLUDED_API_DOMAINS`를 `docs/VERIFICATION.md`,
   `docs/RELEASE_GAP_PLAN.md`, `docs/analysis/*`와 대조.
5. `redaction.py`(`SENSITIVE_KEYS`), `consent.py`(`MutationConsent`,
   `require_mutation_consent`, `require_card_kind_claim`)를 코드 자체 로직으로
   검증 (게이트 우회 경로 탐색).
6. `bridge.js`/`bridge_old.js`/`const.js` (네이티브 브릿지) 전수 확인 — 라이브러리가
   WebView가 아니므로 구현 대상이 아님을 검증하고 "의도된 제외"로 분류.
7. `http.py`의 UA/헤더 구성을 `SRWebActivity.java:2632-2649`와 대조.
8. `session.py`의 `deviceKey`/`deviceId` 처리 확인 (과거 결함, 현재 상태 재검증).
9. 마일리지(적립/포인트) 전수 검색 — 앱 번들, docs, 라이브러리, fixtures 전체.
10. `PassengerCounts.total`의 청소년/유아 합산 의미가 공공할인 최소인원 가드
    (`rsv071`, `totalPessnger`)와 실제로 일치하는지 재검증.
11. `_release_netfunnel_slots`의 실패 스왈로우가 키 누적(무한 재시도) 버그를
    만들지 않는지 확인.

---

## 앱 기능 전체 목록 (담당 영역)

| # | 기능 | 엔드포인트/파일 | 앱 근거 | 라이브러리 대응 | 상태 |
|---|------|-----------------|---------|------------------|------|
| 1 | 할인종류코드(dcntKndCd) 173건 디코드 | `commCode.js` code table | `analysis/apktool/assets/offline/js/commCode.js:8474-24610` (173 `cd_val`, 25 `rmk:"V"`, 133/191 `code_group_cd` 누락) | `discounts.py:54-228` `DISCOUNT_KIND_NAMES_BY_CODE` | 있음 (173/173 바이트 단위 일치, `discount_kind_name()` 정상) |
| 2 | 공공할인코드(PBL_DISC_CD 01-06 명칭) | `POST /common/ARA/ARA0901P/view.do` 주석블록 | live 2026-07-26 캡처, `docs/IMPLEMENTATION_PROGRESS.md:1461-1520`, `docs/VERIFICATION.md:968-1000` | `discounts.py:233-240` `PUBLIC_DISCOUNT_NAMES_BY_CODE` | 있음 |
| 3 | 공공할인 07/08 (이름 없음, 코드만 인정) | `/common/ARA/ARA0301V/view.do` if/else 체인 | `docs/IMPLEMENTATION_PROGRESS.md:1461-1520` | `payloads.py:29-31` `PUBLIC_DISCOUNT_CODES = {01..06} | {07,08}` | 있음 |
| 4 | 공공할인 최소인원 가드 (01/06, rsv071) | `if((pblDiscCd=="01"‖"06") && totalPessnger<3)` | live read, `discounts.py:242-247` 주석, `payloads.py:2372-2378` | `discounts.py:247` `PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE`; 시행처 `payloads.py:2399-2403` | 있음 (ValueError, I/O 이전 차단) |
| 5 | 청소년(공공할인 04) 승객타입 psgTpCd6 | `할인 승차권` 페이지 `setPassenger_callback`, `passenger7` | live 2026-07-26 왕복 검증 (`adult=1,youth=1`→`psgTpCd2="6"` echo) | `models.py:130` `PassengerCounts.youth`; `payloads.py:269-276` `PASSENGER_TYPE_CODES`; `discounts.py:271-272` | 있음 |
| 6 | 유아 폴드(어린이 슬롯+infantCnt) | `ara1001l.js` `goRevFn` `passenger+=passenger6; infantCnt=passenger6` | `docs/IMPLEMENTATION_PROGRESS.md:1565-1667` | `models.py:129,147-161` `PassengerCounts.infant`/`child_slot_count`; `payloads.py:294-299` `INFANT_COUNT_FIELD` | 있음 |
| 7 | 승객 합계(totPrnb, 유아 포함) | `ara0101v.js:35 getPsgTotCnt`, popup `setTotalPassenger` i=1..7 | live echo `totalPessnger=2` for adult=1+infant=1 | `models.py:164-181` `PassengerCounts.total` | 있음 (재검증, §하단 참조) |
| 8 | 할인쿠폰 조회 (GET) | `GET /apa/selectListApa03020_n.do` | live 2026-07-26, 77,056B, `ul.coupList` | `client.py:205-242` `get_discount_coupons`; `parsers.py:619-676` | 있음 |
| 9 | 할인쿠폰 등록 (POST, mutation) | `POST /arb/selectListArb02A01_n.do` `{dscp_no,dscp_pwd}` | live `couponReg()` 캡처, `safety.py:80-108` | `client.py:1499-1598` `register_discount_coupon`; `payloads.py:2241-2306`; `parsers.py:1628-1687`; consent category `"coupon"` | 있음 (프리뷰만, 전송 미허용 — 설계) |
| 10 | 공공할인 보유현황 조회 | `GET /common/ARA/ARA0301V/view.do` | live 2026-07-26, 206,268B, `var dataNCheck` ×8 | `client.py:244-282` `get_public_discounts`; `parsers.py:679-771` | 있음 |
| 11 | 공공할인 승차권 검색 | `POST /ara/selectListAra10131_n.do` (23필드 고정계약) | live `#seatSearchForm` 캡처, `safety.py:109-226` | `client.py:616-743`; `payloads.py:2309-2430` `public_discount_search_payload` | 있음 (미검증 — 승인계정 부재로 응답효과 미확인, 문서화됨) |
| 12 | NetFunnel getTidChkEnter (5101) | `netfunnel.js` `getTidChkEnterProc` | `netfunnel.js:84` 상수, 함수 원문 | `netfunnel.py:129-151` `build_act10_url` | 있음 (쿼리순서/타임스탬프 완전 일치) |
| 13 | NetFunnel chkEnter (5002) | `netfunnel.js` `chkEnterProc` | 상동 | `netfunnel.py:154-188` `build_chk_enter_url` (ttl 위치까지 재현) | 있음 |
| 14 | NetFunnel setComplete (5004) | `netfunnel.js` `TsClient.prototype.setComplete` | 상동 (sid/aid 없음 확인) | `netfunnel.py:191-224` `build_set_complete_url` | 있음 |
| 15 | NetFunnel 상태코드 분류 (200/300/201·202/301·302/502) | `netfunnel.js:84` 전체 상수, `_showResultChkEnter`/`_showResultSetComplete` 스위치 | 원문 대조 완료 | `netfunnel.py:60-96,241-397` | 있음 |
| 16 | NetFunnel ttl 클램프(1..5) | `TS_MAX_TTL=5`, `if(ttl>max_ttl)` | `netfunnel.js:18` | `netfunnel.py:80-96` `MAX_TTL_SECONDS=5`; `safety.py:746-756` 검증 | 있음 |
| 17 | NetFunnel 대기열 폴링(bounded) | 앱은 무제한(팝업), 라이브러리는 유한 | `client.py:420-493` `_get_act10_key` | 있음 (의도적 상한 — 설계, 앱과 다른 것이 정상) |
| 18 | NetFunnel 슬롯 해제(setComplete, best-effort) | `TS_AUTO_COMPLETE=true` | `netfunnel.js:27` | `client.py:495-523` `_release_netfunnel_slots` | 있음 (키 pop이 try 이전 — 실패해도 키 누적 없음, §하단 재검증) |
| 19 | 네이티브 브릿지: QR코드 생성 | `mkQRCode` | `common/bridge.js:1,61-65` | 없음 (WebView 전용) | 의도된 제외 |
| 20 | 네이티브 브릿지: 보안키패드(TransKey) | `showTransKey` | `common/bridge.js:2,66-70` | 없음 | 의도된 제외 (raonsecure 별도 벤더, safety.py `EXCLUDED_API_DOMAINS`의 "native-bridge") |
| 21 | 네이티브 브릿지: 사진촬영/선택 | `takePicture`/`getTakePicture`/`selectPicture` | `common/bridge.js:3-5,87-110` | 없음 | 의도된 제외 |
| 22 | 네이티브 브릿지: 패키지버전/네트워크주소 | `pkgVersion`/`getNetworkAddress` | `common/bridge.js:6-7,71-86` | 없음 | 의도된 제외 |
| 23 | 네이티브 브릿지: SNS 로그인 | `snsLogin` | `common/bridge.js:111-118` | 없음 | 의도된 제외 |
| 24 | 네이티브 브릿지: 외부앱 호출 | `callExtApp` | `common/bridge.js:119-126` | 없음 | 의도된 제외 |
| 25 | 네이티브 브릿지: PNR 로컬 저장/로드 | `pnrDataSave`/`pnrDataLoad` | `common/bridge.js:127-142` | 없음 | 의도된 제외 |
| 26 | (구버전) 네이티브 브릿지 | `common/bridge_old.js` (mkQRCode/showTransKey/takePicture/selectPicture/pkgVersion/getNetworkAddress, snsLogin·callExtApp·pnrData* 없음) | `common/bridge_old.js:1-82` | 없음 | 의도된 제외 (사용되지 않는 구버전 자산, bridge.js가 현행) |
| 27 | User-Agent 접미사 구성 | `settings.setUserAgentString(webviewUA + "SRT-APP-Android V." + ver)` (공백 없음) | `SRWebActivity.java:2642-2649` | `config.py:5-9` `DEFAULT_UA` (공백 없이 이어붙임, 정확히 재현) | 있음 |
| 28 | 기기 식별자: main.do?deviceId | `Y=Z+'/main/main.do?deviceId='+ANDROID_ID` | `SRWebActivity.java:1582-1592` | `config.py:19` `device_key`; `session.py:83-87` | 있음 |
| 29 | 기기 식별자: 로그인 deviceKey (상수 "-") | 서버렌더 필드, 앱 소스 無 (srtgo/srtgo_plus 근거 "-") | `docs/analysis/impl-audit-reverify3-2026-07-22.md:28-41` (과거 결함 기록) | `session.py:56-61` `"deviceKey": "-"` | 있음 (과거 결함 수정 확인됨 — device_key와 분리됨) |
| 30 | 에러코드: S111 세션만료 | `resultMap.msgCd=="S111"` 유일한 msgCd 분기 | `ara1001l.js:1562-1573` | `errors.py:36-68,314` `SrtSessionExpiredError`/`SESSION_EXPIRED_CODE` | 있음 |
| 31 | 에러코드: NET000001 큐 키 재시도 | 앱 자체엔 없음(넷퍼널 통합 주석 처리), srtgo 대응 | `errors.py:238-254`; fixture `search_netfunnel_failure.json` | `client.py:600-606,708-716` 1회 재시도 | 있음 |
| 32 | 에러코드: WRG000000/WRT300005 결과없음 | live capture 2026-07-26 | `errors.py:108-128,307` | `SrtNoResultsError`/`NO_RESULT_CODES` | 있음 |
| 33 | 에러코드: WRD000061 직통없음(환승가능) | live capture, 동대구→광주송정 | `errors.py:131-161,311` | `SrtNoDirectTrainError` | 있음 |
| 34 | 에러코드: WRP011002/WRR000100 입력오류 | `docs/analysis/srt-app-api-library-spec-2026-07-09.md:359,391` | `errors.py:164-179,312` | `SrtInvalidRequestError`/`INVALID_REQUEST_CODES` | 있음 |
| 35 | 에러코드: error001 좌석없음(HTML shell) | `messages.js:6` | `errors.py:182-201` | `SrtSeatUnavailableError` | 있음 |
| 36 | IP 차단 (에지, "Your IP Address Blocked") | 로그인 응답 plain-text | `http.py:98-115` | `SrtIpBlockedError` | 있음 (srtgo 근거, 앱 번들 無 — 명시됨) |
| 37 | Read-only 라우트 allowlist (26개) | 각 route별 근거 (본문 참조) | `safety.py:280-359` | `assert_read_only_request` | 있음 |
| 38 | Mutation 라우트/카테고리 바인딩 (5개: reserve/cancel/payment/refund/coupon) | 각 route별 근거 | `safety.py:412-534` | `assert_mutation_route`/`assert_mutation_route_category` | 있음 |
| 39 | Live-enablement 게이트 (4/5 카테고리) | 2026-07-25/26 실거래 검증 | `safety.py:440-522` | `SRT_LIVE_MUTATION_CATEGORIES`, `http.py:379-388` | 있음 |
| 40 | 카드비밀 필드 데이터 게이트 | payment 전용 필드 4종 | `safety.py:797-832` | `assert_no_card_secrets` (post_form/mutation 양쪽) | 있음 |
| 41 | 환불1단계 빈본문 강제 | `getListAtc14087.do` "Referer로만 PNR 전달, body 없음" | `safety.py:834-857` | `_assert_empty_body_request` | 있음 |
| 42 | 좌석페이지/좌석그리드/공공할인검색 정확계약 검증 | 고정필드+값패턴 | `safety.py:591-658` | `_assert_exact_form_contract` 등 | 있음 |
| 43 | NetFunnel 쿼리 정확계약 검증 (5101/5002/5004) | 옵코드별 필드 | `safety.py:661-768` | `_assert_netfunnel_request` | 있음 |
| 44 | Mutation dry_run 기본 + consent 게이트 (5카테고리) | 설계 (앱과 무관, 라이브러리 자체 안전장치) | `consent.py` 전체 | 있음 (설계, 구멍 없음 확인) |
| 45 | 결제 카드종류 명시 게이트 (fake_card_only XOR real_card_acknowledged) | 설계 | `consent.py:170-201` `require_card_kind_claim`; 이중 호출 (`client.py`+`http.py:403-404`) | 있음 |
| 46 | 민감정보 마스킹 (카드/PNR/쿠폰/환불비번/NetFunnel키 등) | 설계 + 앱 필드명 근거 | `redaction.py:10-105` `SENSITIVE_KEYS` | 있음 (쿠폰/환불 관련 최근 보강분 포함, 누락 없음) |
| 47 | 마일리지/포인트 적립 | **전 저장소 0-hit** (`마일리지`/`mileage` 검색 결과 없음; `포인트`는 OK캐쉬백 결제수단 문맥 `pay011-018`뿐, 마일리지 적립과 무관) | `analysis/apktool/assets/offline/**`, `docs/**`, `src/**`, `tests/fixtures/**` 전체 grep, 0 hits (mileage) | 없음 | 확인불가/무관 — 아래 상세 참조 |

**요약**: 총 47개 항목. 이 중 "있음"(라이브러리에 올바르게 구현됨)은 **38개**(#1-18, #27-46). "의도된 제외"(네이티브 브릿지 8종, #19-26 — WebView 전용이라 라이브러리 대응 없음이 정상)는 구현 대상이 아니므로 "있음" 집계에서 제외. #47(마일리지)은 앱 자체에 해당 기능이 없어 "있음"/"없음" 어느 쪽도 아닌 무관 항목. #11(공공할인 검색)은 "있음"으로 집계했지만 요청 형태만 검증되었고 응답 효과는 승인 계정 부재로 라이브 미검증임이 코드 docstring에 이미 명시되어 있어 별도 결함으로 보지 않음.

---

## 문제 항목 상세

### S8-01: `EXCLUDED_API_DOMAINS`가 실제로는 구현·전송되는 카테고리를 "제외 도메인"으로 계속 명명함 (doc-drift)

- **분류**: doc-drift / **심각도**: low
- **앱 근거**: 해당 없음 (이 항목은 라이브러리 내부 문서/데이터 불일치이며 앱 대조 대상 아님)
- **라이브러리 근거**: `src/srt_mobile_api/safety.py:911-922`
  ```python
  EXCLUDED_API_DOMAINS = frozenset({
      "reservation", "ard-payment-entry", "payment", "refund",
      "cancellation", "ata-detail", "native-bridge", "external-seatmap",
  })
  ```
  그리고 `tests/test_redaction_safety.py:165-168`:
  ```python
  def test_safety_excludes_dangerous_domains_without_stub_apis():
      assert "reservation" in EXCLUDED_API_DOMAINS
      assert "ard-payment-entry" in EXCLUDED_API_DOMAINS
      assert "payment" in EXCLUDED_API_DOMAINS
  ```
- **내용**: 이 frozenset과 그 이름을 검증하는 테스트는, `reservation`/`payment`/`refund`/`cancellation`이 아직 "영구적으로 구현 불가능한 도메인"이었던 초기 설계 단계(2026-07 초)의 잔재다. 그러나 현재 저장소는 이 네 카테고리를 모두 **실제 mutation으로 구현**했고, `payment`는 2026-07-26에 실카드로 라이브 결제까지 검증했다(`safety.py:452-453` "LIVE-VERIFIED 2026-07-26... charged a real card"). `docs/RELEASE_GAP_PLAN.md:520-527`은 이미 "`EXCLUDED_API_DOMAINS`의 의미를 분리해야 한다(native-bridge/external-seatmap만 영구 제외, reservation/cancellation/refund/payment는 opt-in mutation 티어로 이동)"고 명시적으로 지시했지만, 그 수정이 `safety.py`의 상수/테스트에는 반영되지 않았다. 결과적으로 "payment는 실제로 실카드를 청구할 수 있는 라이브 전송 카테고리"인데, 같은 파일의 상수 이름은 여전히 이를 "EXCLUDED"(제외됨)이라 부르고, 테스트 이름은 `..._without_stub_apis`(스텁 API 없이 위험 도메인을 제외)라 단언한다.
- **영향**: 기능적 게이트로는 전혀 사용되지 않음(`grep` 결과 이 상수를 읽는 코드는 테스트 1곳뿐, 실제 전송 경로는 `SRT_LIVE_MUTATION_CATEGORIES`/`assert_mutation_route`가 담당하며 이들은 정확함 — §항목 38-40 확인). 따라서 **런타임 안전성에는 영향 없음**. 다만 이 파일을 읽는 사람(리뷰어/향후 유지보수자)에게 "reservation/payment/refund/cancellation은 이 라이브러리가 건드리지 않는다"는 잘못된 신호를 준다. 실제로는 이 네 카테고리 모두 `MutationConsent(dry_run=False, allow_*=True)`로 전송 가능하다.
- **제안**: `docs/RELEASE_GAP_PLAN.md:520-527`이 이미 지시한 대로 `EXCLUDED_API_DOMAINS`를 `native-bridge`/`external-seatmap`(및 실제로 영구 제외인 `ard-payment-entry`, `ata-detail`)만 남기고 `reservation`/`payment`/`refund`/`cancellation`을 제거하거나, 상수명을 `PERMANENTLY_EXCLUDED_API_DOMAINS` 등으로 바꾸고 테스트명도 함께 정정.

### S8-02 (info): 마일리지(적립) 기능 — 저장소 전체 0-hit, SRT 앱에 해당 기능 없음

- **분류**: info (의도된 제외가 아니라, 애초에 앱에 존재하지 않는 기능) / **심각도**: info
- **앱 근거**: 없음 — `analysis/apktool/assets/offline/js/**`, `analysis/jadx/sources/**`(java/smali 포함 grep 대상), `docs/**`, `src/srt_mobile_api/**`, `tests/fixtures/**` 전체에 대해 `마일리지`/`mileage`를 대소문자 무시 검색한 결과 **0건**. `포인트`(point)는 발견되지만 전부 `analysis/apktool/assets/offline/js/common/messages.js:29-39`의 **OK캐쉬백 결제수단**(복합결제 시 포인트 사용) 문맥이며, 승차권 마일리지 적립과는 무관하다.
- **라이브러리 근거**: 없음 (구현 대상 자체가 없음)
- **내용**: 코레일(KORAIL)과 달리 SRT 앱/서버 프로토콜에는 마일리지 적립·조회·사용 기능이 어디에도 존재하지 않는 것으로 보인다(적어도 이 프로젝트가 읽은 모든 증거— 오프라인 번들, jadx/smali, 라이브 캡처 문서 — 기준). 담당 지시문의 "할인·복지·쿠폰·마일리지"에 마일리지가 명시되어 있어 전수 검색했으나, 앱 자체에 대응하는 기능이 없으므로 라이브러리의 "누락"으로 분류하지 않는다. `M11`(철도회원) 같은 할인종류코드는 마일리지가 아니라 회원구분 코드다.
- **제안**: 없음 (구현할 대상이 존재하지 않음). 혹시 향후 다른 세션에서 마일리지 관련 서버 렌더 페이지를 라이브로 발견하면 그때 반영.

---

## 검증했으나 결함이 아니었던 항목 (조언자 지적 사항 재확인)

- **`PassengerCounts.total`의 유아 포함 여부**: `models.py:164-181`은 유아를 합계에 포함한다. 이는 앱의 `totPrnb += passenger`가 어린이 슬롯 폴드 **이후**에 실행되는 것과 일치하며 (`docs/IMPLEMENTATION_PROGRESS.md:1647,1663-1667`), `passenger_selector_payload`가 `totalPessnger`로 내보내는 값도 동일 `total`을 사용한다(`payloads.py:406`). 2026-07-26 라이브 프로브에서 `adult=1,infant=1` → 서버가 `totalPessnger=2`로 에코한 것이 이를 실측 확인한다(`payloads.py:388` 주석). 공공할인 최소인원 가드(`payloads.py:2399-2403`)도 동일 `total`을 검사하므로 앱의 `totalPessnger < 3` 규칙과 정확히 일치. **결함 없음.** (참고: `docs/analysis/impl-audit-reverify2-2026-07-22.md:66`에 과거 "Medium" 결함 기록이 있으나, 이는 2026-07-26 유아 폴드 규칙 발견 이전 상태를 지적한 것으로 현재는 해소됨.)
- **`_release_netfunnel_slots`의 키 누적 위험**: `client.py:510-523`에서 `key = self._netfunnel_slots.pop()`이 `try` 블록 **이전**에 실행되므로, `setComplete` 전송이 실패(`SrtApiError`)하거나 파싱이 실패(`ValueError`)해도 해당 키는 리스트에서 이미 제거된 상태다. 즉 실패한 키가 재시도 큐에 남아 무한정 쌓이는 구조가 아니다. **결함 없음.**
- **fixtures 39건의 `msgCd` 커버리지**: `IRG000000`/`IRZ000005`/`IRZ000008`(성공), `WRP011002`(INVALID_REQUEST_CODES), `WRT300005`(NO_RESULT_CODES), `S111`(SESSION_EXPIRED_CODE), `NET000001`(NETFUNNEL_KEY_REQUIRED_CODE) 전부 `errors.py`에 매핑되어 있고 바닥으로 떨어지는(`SrtAppError` 그대로) 미분류 실패 코드는 fixtures 안에 없었다. **결함 없음.**
- **`bridge_old.js`**: 구버전 브릿지 자산으로, 현행 `bridge.js`보다 액션이 적다(snsLogin/callExtApp/pnrDataSave/pnrDataLoad 없음). 사용되지 않는 레거시 자산으로 판단되며 라이브러리가 참조할 이유가 없다. **결함 아님, 참고사항.**
- **User-Agent 문자열 구성**: `config.py`의 `DEFAULT_UA`가 `"...Safari/537.36" + "SRT-APP-Android V.2.0.41"`로 공백 없이 이어붙는데, 이는 오타가 아니라 `SRWebActivity.java:2645`의 `userAgentString + "SRT-APP-Android V." + strH0` (공백 없음)을 정확히 재현한 것. **결함 아님.**
- **로그인 `deviceKey` 필드**: 과거(`docs/analysis/impl-audit-reverify3-2026-07-22.md`) `config.device_key`(ANDROID_ID 형식 상수)를 로그인 `deviceKey`에도 재사용하던 결함이 있었으나, 현재 `session.py:56-61`은 로그인 시 리터럴 `"-"`를 보내고 `config.device_key`는 `/main/main.do?deviceId=`에만 사용한다. **이미 수정되어 있음.**
- **할인종류코드 173건**: 코드/이름 스크립트 바이트 단위 대조 173/173 완전 일치 (000 일반 ~ ZZ8 영업할인6, 133/191의 `code_group_cd` 누락 특이사항 포함). `rmk:"V"` 25건도 정확히 일치. **결함 없음.**

---

## 확인불가 항목

없음 — 담당 영역 내에서 근거를 찾지 못해 "확인불가"로 남긴 개별 기능 항목은 없다. (공공할인 검색의 *응답 효과*는 라이브 승인 계정 부재로 미검증이지만, 이는 라이브러리 코드 자체가 이미 스스로 문서화하고 있는 한계이며 별도의 "확인불가" 판정을 추가할 필요가 없다고 판단.)
