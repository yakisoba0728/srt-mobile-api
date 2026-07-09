# SRT APK Deep Dive Static Analysis

대상 파일: `srt.apk`

분석 기준일: 2026-07-09

이 문서는 `srt.apk`를 정적 분석해서 앱 내부에서 확인되는 API 표면, WebView 라우팅, JavaScript 브리지, 예약 검색/예약/결제 진입 로직, 오프라인 승차권 처리, 푸시/인증/외부앱 연동을 정리한 것이다. 실제 운영 서버에 요청을 보내지 않았으므로, 서버의 전체 응답 계약이 아니라 **클라이언트 코드가 전송하거나 읽는 필드**를 기준으로 작성했다.

## 1. 분석 범위와 방법

### 1.1 수행 방식

- APK 원본을 보존한 상태에서 `apktool`과 `jadx` 산출물을 생성했다.
- `AndroidManifest.xml`, `res/values/*.xml`, `assets/offline/**`, `assets/appiron/**`, decompiled Java, smali, 문자열 후보를 교차 검증했다.
- URL 후보, WebView 호출 지점, Ajax 호출 지점, 응답 필드 후보를 자동 추출했다.
- 20개 병렬 에이전트가 독립 영역을 나눠 재조사했고, 최종 결과를 충돌/누락 기준으로 병합했다.
- 네트워크 호출은 수행하지 않았다. 인증 우회, 결제 우회, 서버 검증 우회도 시도하지 않았다.

### 1.2 산출물 위치

- APK 디컴파일: `build/apktool/`
- Java 디컴파일: `build/jadx/`
- 자동 추출 결과: `build/deep-analysis/`
- 초기 분석 문서: `docs/analysis/srt-apk-analysis.md`
- 본 상세 문서: `docs/analysis/srt-apk-deep-dive.md`

### 1.3 신뢰도 표기

- `확정`: 코드에서 직접 전송/읽기/분기하는 필드가 확인됨.
- `추론`: 폼 직렬화, 서버 주입 변수, SDK 내부 호출처럼 전체 정의는 없지만 사용 맥락상 의미가 명확함.
- `후보`: 문자열 또는 주석/비활성 코드에만 남아 있어 실제 런타임 호출 여부가 불확실함.

## 2. APK 개요

| 항목 | 값 |
|---|---|
| 파일 | `srt.apk` |
| 크기 | 26,427,764 bytes |
| SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| 패키지 | `kr.co.srail.newapp` |
| versionName | `2.0.41` |
| versionCode | `150` |
| minSdk | `18` |
| targetSdk / compileSdk | `35` |
| Application | `kr.co.srail.newapp.GlobalApplication` |
| 환경 플래그 | manifest meta-data `ENV=PRD` |
| 운영 WebView base | `https://app.srail.or.kr` |
| 개발 WebView base | `https://devapp.srail.or.kr` |

### 2.1 APK 구조상 중요한 점

- 앱은 네이티브 화면보다 원격 WebView와 bundled offline web assets가 중심이다.
- `assets/offline/`에 예약 검색, 예매, 오프라인 승차권, 공통 코드, 브리지 코드가 들어 있다.
- `lib/` 하위 네이티브 라이브러리는 APK 트리에서 확인되지 않았다. 다만 `ERBAPIs`는 `erb` 네이티브 라이브러리를 로드하려는 코드가 있다. 라이브러리가 런타임에 별도 제공되는지, 제거된 잔재인지는 정적 분석만으로 확정할 수 없다.
- 직접적인 1st-party Retrofit/OkHttp API 클라이언트는 확인되지 않았다. 주 API 호출은 WebView 내부 JavaScript의 Ajax/page navigation, H2O/ERB 푸시 브로커, FIDO/OnePass SDK 내부 통신으로 나뉜다.

## 3. Manifest와 실행 표면

### 3.1 권한

| 권한 | 용도 추정 |
|---|---|
| `android.permission.INTERNET` | WebView, SDK, 푸시 통신 |
| `android.permission.ACCESS_NETWORK_STATE` | 네트워크 상태 감지 |
| `android.permission.ACCESS_WIFI_STATE` | 네트워크 주소/상태 확인 |
| `android.permission.CHANGE_WIFI_STATE` | 레거시 네트워크 제어 가능성 |
| `android.permission.CHANGE_NETWORK_STATE` | 레거시 네트워크 제어 가능성 |
| `android.permission.CAMERA` | `takePicture`, QR/신분증 이미지 처리 |
| `android.permission.READ_PHONE_STATE` `maxSdk=29` | FIDO/단말 식별 관련 |
| `android.permission.READ_PHONE_NUMBERS` | Android 30+ FIDO `allowedAuthnr` 전 권한 확인 |
| `android.permission.READ_EXTERNAL_STORAGE` `maxSdk=32` | 이미지 선택 |
| `android.permission.WRITE_EXTERNAL_STORAGE` `maxSdk=32` | 레거시 이미지 접근 |
| `android.permission.READ_MEDIA_IMAGES` `minSdk=33` | Android 13+ 이미지 선택 |
| `android.permission.VIBRATE` | 알림/UX |
| `android.permission.POST_NOTIFICATIONS` `minSdk=33` | Android 13+ 알림 |
| `android.permission.USE_BIOMETRIC` | 생체 인증 |
| `android.permission.USE_FINGERPRINT` | 레거시 지문 인증 |
| `com.google.android.c2dm.permission.RECEIVE` | FCM |
| Install Referrer permission | 설치 유입 추적 |
| Badge vendor permissions | 제조사별 배지 카운트 |

### 3.2 패키지 조회 대상

Manifest `queries`에 다음 패키지가 명시되어 있다.

| 패키지 | 의미 |
|---|---|
| `com.korail.talk` | 코레일톡 |
| `net.daum.android.map` | 다음/카카오 지도 |
| `com.kakao.taxi` | 카카오 택시 |
| `com.RLP.railpolice` | 철도경찰 |
| `com.dho.mobilefax` | 모바일 팩스 |
| `kr.go.mobileid.tbe` | 모바일 신분증 테스트/베타 계열 |
| `kr.go.mobileid` | 모바일 신분증 |

### 3.3 주요 컴포넌트

| 컴포넌트 | exported | 역할 |
|---|---:|---|
| `SRMainActivity` | true | 런처, `srapp://main` deep link 처리 |
| `SRWebActivity` | false | 주 WebView 컨테이너 |
| `SROfflineActivity` | false | 오프라인 승차권 네이티브 화면 |
| `SRForegroundDialogActivity` | false | 포그라운드 알림/팝업 |
| `SRWidget` | true | 위젯 |
| `SRNetworkMonitor` | true | 네트워크 모니터 receiver |
| `SrtFirebaseMessagingService` | true | FCM 수신/토큰 갱신 |
| Firebase/IID library services | true | Google/Firebase 라이브러리 |
| Facebook CustomTabActivity | true | Facebook 로그인/브라우저 연동 |

### 3.4 Deep link

| 항목 | 값 |
|---|---|
| scheme | `srapp` |
| host/path | `main` |
| 처리 Activity | `SRMainActivity` |
| 읽는 extra/query | `type`, `iv1`, `iv2`, `iv3` |

`SRMainActivity`는 `type`, `iv1`, `iv2`, `iv3` 값을 읽지만 정적 분석상 이후 핵심 로직에서 사용하지 않고 버리는 흐름이다.

## 4. WebView 실행 구조

### 4.1 초기 URL 결정

`SRWebActivity.X0()` 기준으로 시작 URL이 구성된다.

| 조건 | URL |
|---|---|
| PRD 기본 | `https://app.srail.or.kr/main/main.do?deviceId=<android_id>` |
| DEV 기본 | `https://devapp.srail.or.kr/main/main.do?deviceId=<android_id>` |
| push 메시지 존재 | 위 URL에 `&pushMsg=<msg>` 추가 |
| 위젯 `btnNo=1` | 기본 메인 URL |
| 위젯 `btnNo=2` | `https://app.srail.or.kr/atc/selectListAtc14017_n.do` |

`SRForegroundDialogActivity`의 확인 버튼은 별도 도메인을 연다.

```text
https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0
```

### 4.2 WebView 설정

| 설정 | 값/동작 |
|---|---|
| JavaScript | enabled |
| DOM storage | enabled |
| multiple windows | enabled |
| JavaScript window open | enabled |
| User-Agent | 기본 UA 뒤에 `SRT-APP-Android V.<version>` 추가 |
| WebView debugging | enabled |
| Mixed content | `MIXED_CONTENT_ALWAYS_ALLOW`에 해당하는 `0` |
| Third-party cookies | allowed |
| file access | enabled |
| file URL universal access | enabled |
| file URL file access | enabled |
| Safe Browsing | manifest에서 disabled |
| SSL error | 사용자 다이얼로그에서 `계속` 선택 시 `proceed()` |

### 4.3 WebView URL 라우팅

| URL 패턴 | 처리 |
|---|---|
| `intent://` | Android intent 파싱/외부 실행 |
| `mobileid://` | 모바일 신분증 앱 연동 |
| `tel:` | 전화 앱 실행 |
| 외부 링크 목록 | 외부 브라우저/앱 실행 |
| 그 외 | WebView 내부 로드 |

외부 링크 목록:

- `etk.srail.co.kr`
- `etk.srail.kr`
- `m.tour.srail.co.kr`
- `www.srail.co.kr`
- `play.google.com`

### 4.4 오류 처리

| 조건 | 처리 |
|---|---|
| SRT URL에서 error code `-2`, `-6`, `-14` | `file:///android_asset/offline/sub/error.html` 로드 |
| page timeout | `${Z}/error.html` 로드 |
| 네트워크 없음 | 오프라인/오류 화면으로 유도 |

## 5. 전체 네트워크/API 표면

### 5.1 1st-party WebView endpoints

| 구분 | Method | Endpoint | 상태 | 트리거 |
|---|---|---|---|---|
| 메인 | GET | `https://app.srail.or.kr/main/main.do` | 확정 | `SRWebActivity` 시작 |
| 메인 DEV | GET | `https://devapp.srail.or.kr/main/main.do` | 확정 | 비 PRD |
| 위젯 | GET | `/atc/selectListAtc14017_n.do` | 확정 | 위젯 버튼 2 |
| 알림 | GET | `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0` | 확정 | 포그라운드 다이얼로그 |
| 알림/오프라인 참조 | GET | `/srail-app/atc/selectListAtc14016_n.do?pageNo=0` | 후보 | offline asset marker |
| 로그아웃 | POST | `/srail-app/login/loginOut.do` | 후보 | offline form |
| 메인 jQuery page | GET | `/srail-app/main/main.do` | 후보 | offline `data-url` |
| 로그인/비밀번호 | POST | `/apb/selectListApb01080_n.do` | 후보 | offline form |

### 5.2 예약 UI popup/page endpoints

| Endpoint | Method | 요청 필드 | 응답/결과 |
|---|---|---|---|
| `/common/ARA/ARA0501P/view.do` | POST page | `reqCode`, `sDptStnNm`, `sArvStnNm`, `sDptStnCd`, `sArvStnCd`, `sNowSel` | 역 선택 popup |
| `/common/ARA/ARA0401P/view.do` | POST page | `reqCode`, `selectDay`, `selectDt` | 날짜 선택 popup |
| `/common/ARA/ARA0901P/view.do` | POST page | `reqCode`, `isOrg`, `passenger1`..`passenger5`, `totalPessnger` | 승객 선택 popup |
| `/common/ARA/ARA0701P/view.do` | POST page | `reqCode`, `rqSeatAttCd`, `locSeatAttCd`, `seatAttNm` | 좌석 속성 popup |
| `/common/ARA/ARA0201V/view.do` | POST page | `reqCode`, `trnGpCd`, `trnGpCdNm` | 열차 종류 popup |

`totalPessnger`는 source에 있는 오탈자 그대로다.

### 5.3 예약 검색/스케줄 endpoints

| Endpoint | Method | 상태 | 의미 |
|---|---|---|---|
| `/ara/selectListAra10007_n.do` | POST Ajax | 확정 | 개인/일반 열차 조회 |
| `/ara/selectListAra10082_n.do` | POST Ajax | 확정 | 단체 열차 조회 |
| `/ara/selectListAra10130_n.do` | POST Ajax | 확정 | 예약 전 검증/상호표식 검증값 조회 |
| `/ara/selectListAra12009_n.do` | POST page | 확정 | 열차 시간표 |
| `/ara/selectListAra13010_n.do` | POST page | 확정 | 운임/요금 조회 |
| `ara/selectListAra10h01.do` | POST/Ajax | 비활성 후보 | 주석 처리된 레거시 예약 상세 |

### 5.4 좌석/예약/결제 진입 endpoints

| Endpoint | Method | 상태 | 의미 |
|---|---|---|---|
| `/arc/selectListArc02012_n.do` | POST page | 확정 | 좌석 선택 화면 |
| `/arc/selectListArc05013_n.do` | POST Ajax | 확정 | 개인 예약 요청 |
| `/arc/selectListArc06014_n.do` | POST Ajax | 확정 | 단체 예약 요청 |
| `/ard/selectListArd02017_n.do` | POST page | 확정 | 개인 결제/예약 상세 진입 |
| `/ard/selectListArd02018_n.do` | POST page | 확정 | 단체 결제/예약 상세 진입 |
| `/ata/selectListAta01032_n.do` | POST page | 확정 | 할인/추가 화면 진입 |

### 5.5 CMS/static endpoints

| Endpoint | 의미 |
|---|---|
| `/cms/article/list.do?pageId=KR0502000000` | 공지/콘텐츠 목록 |
| `https://www.srail.co.kr/cms/article/view.do?postNo=111&pageId=KR0502000000` | 콘텐츠 상세 |
| `https://www.srail.co.kr/cms/article/view.do?postNo=112&pageId=KR0502000000` | 콘텐츠 상세 |
| `https://www.srail.co.kr/cms/article/view.do?postNo=113&pageId=KR0502000000` | 콘텐츠 상세 |
| `https://www.srail.co.kr/cms/article/view.do?postNo=114&pageId=KR0502000000` | 콘텐츠 상세 |
| `https://www.srail.co.kr/cms/article/view.do?postNo=115&pageId=KR0502000000&pageIndex=1` | 콘텐츠 상세 |
| `http://www.srail.co.kr/cms/attach/image.do?source=<encoded>` | 이미지 첨부 |

### 5.6 SDK/third-party endpoints

| 구분 | Endpoint/host | 상태 | 의미 |
|---|---|---|---|
| H2O push | `push.srail.co.kr:3101` | 확정 | H2O/ERB push broker |
| OnePass/FIDO | `https://fido.srail.co.kr` | 확정 | FIDO base |
| OnePass | `/interfToken/processRequest.do` | SDK 내부 | 토큰/인터페이스 |
| OnePass | `/fido/deviceUaf/processUafRequest.do` | SDK 내부 | UAF request |
| OnePass | `/fido/deviceUaf/processUafResponse.do` | SDK 내부 | UAF response |
| OnePass | `/interfDeviceBiz/processRequest.do` | SDK 내부 | 단말 비즈니스 |
| OnePass | `/interfBiz/processRequest.do` | SDK 내부 | 비즈니스 request |
| OnePass | `/bioDevice/serviceRequest.do` | dormant 후보 | base 연동 확인 안 됨 |
| AppIron | `http://iron.srail.co.kr/authCheck.call` | 확정 문자열 | 앱 위변조/보안 SDK |
| NetFunnel | `https://nf.letskorail.com/ts.wseq` | 코드 존재 | 대기열, 현재 핵심 호출 주석 |
| Firebase DB | `https://<SRT-APP-FIREBASE-PROJECT-REDACTED>.firebaseio.com` | 설정 | Firebase |
| Kakao | `kauth.kakao.com`, `kapi.kakao.com` 등 | SDK/JS | 소셜 연동 |
| Naver | `nid.naver.com`, `static.nid.naver.com` | asset | 로그인/SDK 잔재 |

## 6. JavaScript 브리지 API

### 6.1 호출 방식

웹 코드의 표준 Android 브리지 호출은 다음 형태다.

```javascript
window.srbridge.bridgeCall(action, JSON.stringify(params));
```

네이티브 entrypoint:

```java
@JavascriptInterface
bridgeCall(String action, String json)
```

### 6.2 표준 콜백 방식

대부분의 action은 네이티브에서 다음 형태의 JSON 문자열을 JavaScript로 돌려준다.

```json
{
  "action": "<action>",
  "resultCode": 1,
  "data": {},
  "image": "<imgData가 있을 경우 같은 값>"
}
```

JavaScript `bridge.js`는 `bridgeCallBack("<json string>")`을 수신한 뒤 JSON으로 파싱한다. `resultCode != 1`이면 기본적으로 무시한다. `getTakePicture`는 `bridgeCallBackLeft`, 그 외는 `bridgeCallBackWeb`로 라우팅한다.

중요한 예외:

- `savePrfs`: 표준 콜백이 아니라 전달된 `callback(resultCodeInt)`를 직접 호출한다.
- `loadPrfs`: 전달된 callback에 `{"resultCode":1,"data":...}` 형태의 문자열을 넘긴다.
- `regDevice`, `unRegDevice`, `easypay`, `disableCapture`, `enableCapture`, `mainShow` 등은 명시 콜백이 없거나 side effect 중심이다.
- FIDO 계열은 SDK `resultCode`가 `1200` 같은 값일 수 있는데, bundled `bridge.js`는 `1`이 아니면 콜백을 drop할 수 있다.

### 6.3 브리지 action 상세

#### `mkQRCode`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "data": "...", "width": <number> }` |
| 처리 | 입력 문자열로 QR bitmap 생성 |
| 성공 콜백 | `{ "imgData": "data:image/png;base64,..." }` |
| 실패 콜백 | `{ "error": "..." }` |

#### `mkQRCode2`

`mkQRCode`와 같은 계열이다. 입력/출력 구조도 동일하게 확인된다.

#### `takePicture`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` 또는 없음 |
| 권한 | `CAMERA` |
| 처리 | 카메라 intent 실행 |
| 저장 | SharedPreferences `SRApp/getTakePicture` |
| 콜백 | `{ "imgData": "data:image/..." }` |

#### `selectPicture`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` 또는 없음 |
| 권한 | Android 33+ `READ_MEDIA_IMAGES`, 그 외 레거시 storage 권한 |
| 처리 | 갤러리/이미지 선택 |
| 저장 | SharedPreferences `SRApp/getTakePicture` |
| 콜백 | `{ "imgData": "data:image/..." }` |

#### `selectPictureByCode`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "code": "..." }` |
| 처리 | 이미지 선택, caller code 보존 |
| 콜백 | `{ "imgData": "data:image/...", "code": "...", "filename": "..." }` |
| 차이 | `getTakePicture` preference에는 저장하지 않는다 |

#### `getTakePicture`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 읽기 | SharedPreferences `SRApp/getTakePicture` |
| 콜백 | `{ "imgData": "data:image/..." }` |

#### `getTakeIdCard`

`getTakePicture`와 같은 저장소를 읽는 것으로 보인다.

#### `showTransKey`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "keyType": "...", "title": "...", "hint": "...", "maxLength": n, "minLength": n, "useAllDelete": "...", "useCursor": "...", "keydata": "...", "disableSymbol": "...", "language": "..." }` |
| 처리 | TransKey 보안 키패드 표시 |
| 성공 콜백 | `{ "plainData": "..." }` |
| 실패 콜백 | `{ "errorMsg": "..." }` |
| 특이점 | SEED 복호화 결과 plaintext가 JavaScript로 반환되고 Toast에도 노출되는 코드 흐름이 있다 |

#### `pkgVersion`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 콜백 | `{ "pkgVersion": "2.0.41" }` |

#### `getNetworkAddress`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 콜백 | `{ "mac": "<ANDROID_ID uppercase>", "ip": "<ip address>" }` |
| 주의 | `mac` 필드는 실제 MAC 주소가 아니라 Android ID를 대문자화한 값이다 |

#### `snsLogin`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "type": "G" }` |
| 처리 | Google Sign-In |
| 성공 콜백 | `{ "id": "...", "type": "G" }` |
| 실패/기타 | Kakao requestCode `201` 처리 흔적은 있으나 first-party trigger는 확인되지 않음 |

Kakao dormant path 콜백 후보:

```json
{ "id": "...", "type": "K" }
```

또는

```json
{ "msg": "..." }
```

#### `callExtApp`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "pkgName": "...", "viewName": "...", "values": "..." }` |
| 패키지 미설치 | Play Store 또는 market fallback |
| viewName 없음 | 패키지 launch intent 실행 |
| viewName 있음 | component 시작, extra `PARAM=<values>` |
| 철도경찰 특수 | `krailwaypolice://crime.report?<values>` |
| 콜백 | 일부 경로에서 `{ "pkgName": "...", "viewName": "..." }` |

#### `savePrfs`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "prfsKey": "...", "values": "...", "callback": "callbackName" }` |
| 저장 | SharedPreferences `SRApp` |
| 콜백 | `callbackName(<int resultCode>)` |

#### `loadPrfs`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "prfsKey": "...", "callback": "callbackName" }` |
| 읽기 | SharedPreferences `SRApp` |
| 콜백 일반 | `callbackName('{"resultCode":1,"data":...}')` |
| 콜백 `offTicketListCallback` | data를 raw string으로 유지 |
| 일반 data 처리 | 가능하면 `JSONArray(value)`로 파싱 |

#### `regDevice`

| 항목 | 내용 |
|---|---|
| 입력 | JSON parse만 수행, 필드 사용 확인 안 됨 |
| 처리 | H2O `pushRegist` |
| 콜백 | 없음 |

#### `unRegDevice`

| 항목 | 내용 |
|---|---|
| 입력 | JSON parse만 수행, 필드 사용 확인 안 됨 |
| 처리 | H2O `pushUnRegist` |
| 콜백 | 없음 |

#### `mobileFAX`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "image": "data:image/...;base64,..." }` |
| 처리 | base64 decode, 0.5 resize, private filesDir `SRT/<timestamp>.jpg` 저장 |
| 외부 앱 | `com.dho.mobilefax`로 `ACTION_SEND image/*` |
| 미설치 | Play Store 설치 안내 |
| 콜백 | 없음 |

#### `getStorageItem`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "key": "...", "defaultValue": "...", "pageId": "..." }` |
| 읽기 | SharedPreferences `SRAIL` |
| 콜백 | `{ "key": "...", "value": "...", "pageId": "..." }` |

#### `setStorageItem`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "key": "...", "value": "...", "pageId": "..." }` |
| 저장 | SharedPreferences `SRAIL` |
| 콜백 | `{ "key": "...", "value": "...", "pageId": "..." }` |

#### `removeStorageItem`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "key": "...", "pageId": "..." }` |
| 삭제 | SharedPreferences `SRAIL` |
| 콜백 | `{ "key": "...", "pageId": "..." }` |

#### `writeLog`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "type": "console", "msg": "..." }` |
| 처리 | DEV에서 console/debug 출력 또는 Toast |
| 콜백 | 표준 빈 data |

#### `easypay`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "type": "shinhanfan" }` |
| 설치 시 | `shinhan-sr-ansimclick-srt://srCode=aaa` 실행 |
| 미설치 | market fallback |
| 콜백 | 없음 |

#### `mainShow`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 처리 | splash/main overlay 숨김 |
| 콜백 | 없음 |

#### `windowOpen`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "url": "..." }` |
| 처리 | popup flag 설정, 별도 popup WebView 흐름 |
| 콜백 | `{ "url": "..." }` |

#### `disableCapture`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 처리 | `FLAG_SECURE` 설정 |
| 콜백 | 없음 |

#### `enableCapture`

| 항목 | 내용 |
|---|---|
| 입력 | `{}` |
| 처리 | `FLAG_SECURE` 해제 |
| 콜백 | 없음 |

#### `allowedAuthnr`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "aaidList": ["..."] }` |
| 권한 | Android 30+ `READ_PHONE_NUMBERS`, 그 외 `READ_PHONE_STATE` |
| 처리 | OnePass `isSupportedDevice` |
| 콜백 action | `allowedAuthnr` |
| 콜백 resultCode | SDK result code. 예: `1200` |
| 콜백 data | `{ "resultMsg": "...", "isSupported": true/false }` |
| 주의 | `bridge.js`가 `resultCode != 1`을 drop할 수 있다 |

#### `requestServiceRegist`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "trId": "...", ... }` |
| 처리 | OnePass registration request, requestCode `20001` |
| 콜백 data | `{ "resultMsg": "...", "requestParam": <원본 JSON> }` |
| 즉시 오류 | `resultCode=9`, `{ "resultMsg": "..." }` |

#### `requestServiceRelease`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "trId": "...", ... }` |
| 처리 | OnePass release request, requestCode `30001` |
| 콜백 data | `{ "resultMsg": "...", "requestParam": <원본 JSON> }` |
| 즉시 오류 | `resultCode=9`, `{ "resultMsg": "..." }` |

#### `requestServiceAuth`

| 항목 | 내용 |
|---|---|
| 입력 | `{ "trId": "...", ... }` |
| 처리 | OnePass auth request, requestCode `40001` |
| 콜백 data | `{ "resultMsg": "...", "requestParam": <원본 JSON> }` |
| 즉시 오류 | `resultCode=9`, `{ "resultMsg": "..." }` |

#### `exitApp`

| 항목 | 내용 |
|---|---|
| 호출 | `window.srbridge.exitApp()` |
| 입력 | 없음 |
| 처리 | Activity finish |

### 6.4 iOS-only 또는 Android 미구현 브리지

`bridge.js`에 `pnrDataSave`, `pnrDataLoad` 같은 iOS 계열 함수 흔적이 있으나 Android native dispatch에서 확인되지 않는다. Android WebView에서 호출하면 명시 처리 없이 빠질 가능성이 높다.

## 7. 예약 상태 모델

### 7.1 상태 저장 방식

`ara0101v.js`의 예약 상태는 서버 주입 또는 offline HTML의 hidden input DOM에 저장된다.

```javascript
lfn_setRsv(obj) // obj의 각 key와 같은 id를 가진 DOM element value에 저장
lfn_getRsv(key) // $("#" + key).val() 읽기, 없으면 ""
```

`contextPath`는 offline asset 자체에 정의되어 있지 않고 서버 렌더링 환경에서 주입되는 값으로 보인다.

### 7.2 초기 예약 값

| 필드 | 초기값 | 의미 |
|---|---|---|
| `jobId` | `1101` | 일반 예약 작업 |
| `jrnyTpCd` | `11` | 편도/직통 |
| `jrnyCnt` | `1` | 여정 수 |
| `grpDv` | `0` | 개인/단체 구분 |
| `rtnDv` | `0` | 왕복 여부 |
| `stlbTrnClsfCd1` | `05` | 전체 열차 |
| `stndFlg` | `N` | 입석 관련 flag |
| `jrnySqno1` | `001` | 여정 순번 |
| `trnGpCd1` | `109` | 전체 |
| `trnGpNm1` | `전체` | 열차 그룹명 |
| `dptRsStnCd1` | `0551` | 출발역, 기본 수서 |
| `dptRsStnNm1` | `수서` | 출발역명 |
| `arvRsStnCd1` | `0020` | 도착역, 기본 부산 |
| `arvRsStnNm1` | `부산` | 도착역명 |
| `dptDt1` | 오늘 날짜 | 출발일 |
| `dptTm1` | `000000` | 출발시간 |
| `dptDtTmNm1` | 오늘 + `00시 이후` | 표시용 |
| `back_dptDt1` | 오늘 날짜 | 왕복/복귀 기준일 |
| `back_dptTm1` | `000000` | 왕복/복귀 기준시간 |
| `totPrnb` | `1` | 총 승객 수 |
| `totPrnbNm` | `1명` | 표시용 승객 수 |
| `psgGridcnt` | `1` | 승객 grid count |
| `psgTpCd1` | `1` | 어른 |
| `psgInfoPerPrnb1` | `1` | 어른 1명 |
| `psgTpCd2`..`psgTpCd5` | empty | 추가 승객 유형 |
| `psgInfoPerPrnb2`..`5` | `0` | 추가 승객 수 |
| `smkSeatAttCd1/2` | `000` | 흡연/기타 좌석 속성 |
| `dirSeatAttCd1/2` | `009` | 순방향 |
| `locSeatAttCd1/2` | `000` | 기본 위치 |
| `rqSeatAttCd1/2` | `015` | 일반 좌석 |
| `etcSeatAttCd1/2` | `000` | 기타 |
| `seatAttNm1/2` | `일반/기본` | 표시명 |
| `go_baseDsXml` | empty | 서버/레거시 dataset |
| `go_seatDsXml` | empty | 좌석 dataset |

### 7.3 모드별 검증

| 모드 | 코드 동작 |
|---|---|
| 직통 | `jrnyTpCd=11`, `jrnyCnt=1` |
| 환승 | `jrnyTpCd=14`, `jrnyCnt=2`; 왕복과 동시 선택 불가 |
| 왕복 | 국회의원 회원번호 prefix `11`, 환승, 코레일역, 단체와 조합 불가 |
| 단체 | 코레일역, 왕복과 조합 불가; 승객/좌석 상태 초기화 후 승객 popup |
| 조회 | 단체는 `totPrnb >= 10` 필요, 개인은 `totPrnb > 9` 거부 |
| 조회 | 출발역과 도착역 동일하면 거부 |
| 왕복 조회 | 복귀 일시가 출발 일시보다 빠르면 거부 |
| 휠체어 | `rqSeatAttCd1`가 `021` 또는 `028`이면 확인 prompt 후 조회 |

### 7.4 Popup callback 입력

| Popup | callback data |
|---|---|
| 역 선택 | `{ "startStnNm": "...", "startStnCd": "...", "arrivalStnNm": "...", "arrivalStnCd": "..." }` |
| 날짜 선택 | `{ "choiceDate": "YYYY-MM-DD..." }` |
| 좌석 속성 | `{ "seatOption": "...", "seatPosition": "...", "seatOptionString": "..." }` |
| 승객 선택 | `{ "passenger1": n, "passenger2": n, "passenger3": n, "passenger4": n, "passenger5": n }` |
| 열차 그룹 | `{ "trainOption": "300|900|109|...", "trainOptionNm": "..." }` |
| 좌석 선택 | `{ "scarSeatNo": "...", "scarSeatNm": "...", "scarNo": "..." }` |

열차 그룹 mapping:

| `trainOption` | `trnGpCd` | `stlbTrnClsfCd` |
|---|---|---|
| `300` | SRT | `17` |
| `900` | KTX+SRT | `00` |
| `109` | 전체 | `05` |

승객 callback은 0이 아닌 승객 수를 순서대로 압축해 `psgTpCdN`/`psgInfoPerPrnbN`에 넣는다.

좌석 선택 callback은 `seatNo1_N`, `scarGridcnt1`, `scarGridcnt2`, `scarNo1`, `scarNo2`를 채운 뒤 단일 여정은 `fn_submit()`, 왕복은 다음 여정 예약 흐름으로 들어간다.

## 8. 예약 검색 API 상세

### 8.1 `/ara/selectListAra10007_n.do`

개인/일반 열차 조회 Ajax endpoint다.

| 항목 | 내용 |
|---|---|
| Method | POST |
| Content | `#seatSearchForm.serialize()` |
| 성공 응답 | JSON |
| 실패 처리 | `ErrorCode`, `ErrorMsg`, `strResult`, `msgTxt` 기준 alert/중단 |

#### 요청 필드

폼 전체가 직렬화되므로 실제 body에는 hidden input 전체가 포함될 수 있다. 코드가 조회 전 명시 세팅하는 핵심 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `chtnDvCd` | 열차/역 관련 구분 |
| `dptDt` | 출발일 |
| `dptTm` | 출발시각 |
| `dptRsStnCd` | 출발역 코드 |
| `arvRsStnCd` | 도착역 코드 |
| `stlbTrnClsfCd` | 열차 종류 코드 |
| `psgNum` | 승객 수 |
| `seatAttCd` | 좌석 속성 |
| `arriveTime` | 도착시간 기준 여부. 코드상 `N` |
| `trnGpCd` | 열차 그룹 |
| `trnNo` | 열차 번호. 특정 열차 선택 시 |

#### 응답 top-level

```json
{
  "ErrorCode": "...",
  "ErrorMsg": "...",
  "outDataSets": {
    "dsOutput0": [{}],
    "dsOutput1": []
  }
}
```

| 필드 | 의미 |
|---|---|
| `ErrorCode` | 서버 오류 코드. 존재하면 오류 처리 |
| `ErrorMsg` | 서버 오류 메시지 |
| `outDataSets.dsOutput0[0].strResult` | 결과. `FAIL`이면 실패 |
| `outDataSets.dsOutput0[0].msgTxt` | 사용자 메시지 |
| `outDataSets.dsOutput0[0].fllwPgExt` | 다음 페이지/확장 후보 |
| `outDataSets.dsOutput1[]` | 열차 row 배열 |

#### `dsOutput1` 열차 row 필드

| 필드 | 의미/사용 |
|---|---|
| `stlbTrnClsfCd` | 열차 분류 |
| `trnNo` | 열차 번호 |
| `dptRsStnCd` | 출발역 코드 |
| `dptTm` | 출발시각 |
| `arvRsStnCd` | 도착역 코드 |
| `arvTm` | 도착시각 |
| `sprmRsvPsbStr` | 특실 예약 가능 표시 문자열 |
| `sprmRsvPsbColor` | 특실 표시 색 |
| `sprmRsvPsbImg` | 특실 예약 가능 이미지 |
| `gnrmRsvPsbStr` | 일반실 예약 가능 표시 문자열 |
| `gnrmRsvPsbColor` | 일반실 표시 색 |
| `gnrmRsvPsbImg` | 일반실 예약 가능 이미지 |
| `trainDiscGenRt` | 할인율 |
| `rcvdAmt` | 수신/결제 예정 금액 표시 |
| `stmpRsvPsbFlgCd` | 예약 가능 flag |
| `runDt` | 운행일 |
| `trnClsfCd` | 열차 class |
| `chtnDvCd` | 구간/역 구분 |
| `dptStnConsOrdr` | 출발역 구성 순번 |
| `arvStnConsOrdr` | 도착역 구성 순번 |
| `dptStnRunOrdr` | 출발역 운행 순번 |
| `arvStnRunOrdr` | 도착역 운행 순번 |
| `dptDt` | 출발일 |
| `arvDt` | 도착일 |
| `trnGpCd` | 열차 그룹 |

클라이언트가 row에 추가하는 필드:

| 필드 | 의미 |
|---|---|
| `timeTable` | 시간표 버튼/링크 상태 |
| `payTable` | 운임 버튼/링크 상태 |
| `seatSelect` | 좌석 선택 버튼 상태 |
| `doReserv` | 예약 버튼 상태 |

### 8.2 `/ara/selectListAra10082_n.do`

단체 열차 조회 endpoint다. 요청 구조는 `#seatSearchForm.serialize()` 기반으로 `selectListAra10007_n.do`와 거의 동일하다. 단체 모드에서는 승객 수 검증이 `10명 이상`이어야 하며, 예약 가능 버튼은 단체 예약 흐름으로 연결된다.

### 8.3 조회 결과 렌더링 로직

| 조건 | 처리 |
|---|---|
| 일반실/특실 이미지가 예약 가능 이미지 | 예약/좌석 선택 버튼 활성 |
| `trainDiscGenRt > 0` | 할인 문구 추가 |
| 수서-지제 구간 | 할인 표시 예외 |
| Korail 열차 이미지 | 좌석 선택 비활성 |
| 단체 예약 | 좌석 선택 비활성 또는 단체 예약 흐름 |

할인 표시 로직:

- 일반실/특실이 예약 가능이고 할인율이 있으면 일반실 문구가 `{rate}% 할인<br />{rcvdAmt}원` 형태가 된다.
- 특실은 `{rate}% 할인` 문구를 붙인다.
- 색상은 녹색 계열로 변경된다.

### 8.4 `/ara/selectListAra10130_n.do`

예약 직전 검증/상호표식 코드 조회로 보인다.

| 항목 | 내용 |
|---|---|
| Method | POST |
| 요청 data | 코드상 명시 data 없음 |
| 응답 | JSON |

응답 필드:

| 필드 | 의미 |
|---|---|
| `outDataSets.dsOutput0[0].strResult` | 결과 |
| `outDataSets.dsOutput0[0].msgTxt` | 메시지 |
| `outDataSets.dsOutput0[0].mutMrkVrfCd` | 상호표식/검증 코드 |

성공 시 `application.gs_mutMrkVrfCd`에 `mutMrkVrfCd`를 저장한다.

### 8.5 `/ara/selectListAra12009_n.do`

열차 시간표 page navigation endpoint다.

| 필드 | 의미 |
|---|---|
| `runDt` | 운행일 |
| `trnNo` | 열차 번호 |
| `trnSort` | 열차 정렬/종류 |
| `stnCourseNm` | 역 경로명 |

### 8.6 `/ara/selectListAra13010_n.do`

운임/요금 page navigation endpoint다.

| 필드 | 의미 |
|---|---|
| `chtnDvCd` | 구간/열차 구분 |
| `dptRsStnCd1` | 1구간 출발역 |
| `arvRsStnCd1` | 1구간 도착역 |
| `dptRsStnCd2` | 2구간 출발역. 코드상 empty 가능 |
| `arvRsStnCd2` | 2구간 도착역. 코드상 empty 가능 |
| `runDt` | 운행일 |
| `trnNo` | 열차 번호 |
| `runDt1` | 1구간 운행일 |
| `trnNo1` | 1구간 열차 번호 |
| `runDt2` | 2구간 운행일. 코드상 empty 가능 |
| `trnNo2` | 2구간 열차 번호. 코드상 empty 가능 |
| `trnSort` | 열차 정렬/종류 |
| `stnCourseNm` | 역 경로명 |
| `passenger1`..`passenger5` | 승객 유형별 수 |

## 9. 좌석/예약/결제 진입 API 상세

### 9.1 `/arc/selectListArc02012_n.do`

좌석 선택 화면으로 이동하는 page endpoint다.

| 항목 | 내용 |
|---|---|
| Method | POST |
| 호출 조건 | 좌석 선택 버튼 클릭 |
| 응답 | HTML/page |

요청 필드:

| 필드 | 의미 |
|---|---|
| `reqCode` | 요청 코드 |
| `runDt` | 운행일 |
| `dptDt` | 출발일 |
| `trnNo` | 열차 번호 |
| `dptTm` | 출발시각 |
| `trnGpCd` | 열차 그룹. 코드상 SRT는 `300` |
| `dptRsStnCd` | 출발역 코드 |
| `arvRsStnCd` | 도착역 코드 |
| `psrmClCd` | 객실 등급. 일반실 `1`, 특실 `2` |
| `seatAttCd` | 좌석 속성 |
| `dptStnRunOrdr` | 출발역 운행 순번 |
| `arvStnRunOrdr` | 도착역 운행 순번 |
| `choiceSeatCount` | 선택 좌석 수 |

### 9.2 `/arc/selectListArc05013_n.do`

개인 예약 Ajax endpoint다.

| 항목 | 내용 |
|---|---|
| Method | POST |
| Content | `#rsvForm.serialize()` |
| 성공 응답 | JSON |
| 실패 조건 | `resultMap[0].strResult == "FAIL"` |

### 9.3 `/arc/selectListArc06014_n.do`

단체 예약 Ajax endpoint다.

| 항목 | 내용 |
|---|---|
| Method | POST |
| Content | `#rsvForm.serialize()` |
| 성공 응답 | JSON |
| 실패 조건 | `resultMap[0].strResult == "FAIL"` |

### 9.4 예약 요청 form 핵심 필드

`rsvForm` 전체 정의가 offline snippet에 완전하게 있지는 않지만, 조회 row와 예약 상태에서 다음 필드를 구성한다.

| 필드 | 의미 |
|---|---|
| `jobId` | 예약 작업. 일반 `1101`, 좌석선택 `1103`, 예약대기 `1102` |
| `jrnyTpCd` | 여정 타입 |
| `jrnyCnt` | 여정 수 |
| `jrnySqno1` | 여정 순번 |
| `stlbTrnClsfCd1` | 열차 분류 |
| `trnGpCd1` | 열차 그룹 |
| `trnNo1` | 열차 번호 |
| `runDt1` | 운행일 |
| `dptDt1` | 출발일 |
| `dptTm1` | 출발시각 |
| `arvDt1` | 도착일 |
| `arvTm1` | 도착시각 |
| `dptRsStnCd1` | 출발역 코드 |
| `arvRsStnCd1` | 도착역 코드 |
| `dptStnRunOrdr1` | 출발역 운행 순번 |
| `arvStnRunOrdr1` | 도착역 운행 순번 |
| `dptStnConsOrdr1` | 출발역 구성 순번 |
| `arvStnConsOrdr1` | 도착역 구성 순번 |
| `psrmClCd1` | 객실. 일반 `1`, 특실 `2` |
| `seatAttCd1` | 좌석 속성 |
| `scarNo1` | 차량 번호 |
| `seatNo1_N` | 선택 좌석 번호 |
| `totPrnb` | 총 승객 수 |
| `psgTpCd1`..`5` | 승객 유형 |
| `psgInfoPerPrnb1`..`5` | 승객 수 |
| `mutMrkVrfCd` | `/ara/selectListAra10130_n.do` 응답에서 저장된 검증 코드 |

### 9.5 예약 응답 구조

예약 성공/실패 응답은 다음 배열들을 읽는다.

```json
{
  "resultMap": [{}],
  "reservListMap": [{}],
  "trainListMap": [{}],
  "commandMap": [{}]
}
```

#### `resultMap[0]`

| 필드 | 의미 |
|---|---|
| `strResult` | `FAIL`이면 실패 |
| `msgCd` | 메시지 코드 |
| `msgTxt` | 사용자 메시지 |
| `totRcvdAmt` | 총 결제/수신 금액 |
| `tmpJobSqno1` | 임시 작업 순번 1 |

실패 처리:

- `strResult == "FAIL"`이면 `msgTxt` alert.
- `msgCd == "S111"`이면 예약 파라미터를 `localStorage.userReservation`에 저장하고 로그인 화면으로 유도한다.

#### `reservListMap[0]`

| 필드 | 의미 |
|---|---|
| `pnrNo` | 예약번호 |
| `JRNYLIST_KEY` | 여정 list key |
| `arvDt` | 도착일 |
| `arvRsStnCd` | 도착역 코드 |
| `arvTm` | 도착시각 |
| `dlayAcptFlg` | 지연 수락 flag |
| `dptDt` | 출발일 |
| `dptRsStnCd` | 출발역 코드 |
| `dptTm` | 출발시각 |
| `lumpStlTgtNo` | 일괄 결제 대상 번호 |
| `proyStlTgtFlg` | 대리/위임 결제 대상 flag |
| `stlbTrnClsfCd` | 열차 분류 |
| `totSeatNum` | 총 좌석 수 |
| `trnGpCd` | 열차 그룹 |
| `trnNo` | 열차 번호 |

#### `trainListMap[0]`

| 필드 | 의미 |
|---|---|
| `seatNo` | 좌석 번호 |
| `scarNo` | 차량 번호 |

왕복/복합 흐름에서는 `trainListMap` object 전체가 다음 단계에 보존될 수 있다.

#### `commandMap[0]`

`commandMap`은 읽히지만 `ara1001l.js` 일반 흐름에서는 강하게 쓰이지 않는다. `arc0102c.js`에서는 `${commandMap.pnrNo}` 형태로 할인/추가 화면 진입에 쓰는 흔적이 있다.

### 9.6 개인 예약 성공 후 `/ard/selectListArd02017_n.do`

개인 예약 성공 시 결제/예약 상세 page로 POST 이동한다.

요청 필드:

| 필드 | 값/출처 |
|---|---|
| `pnrNo` | `reservListMap[0].pnrNo` |
| `jrnySqno` | `1` |
| `JRNYLIST_KEY` | `reservListMap[0].JRNYLIST_KEY` |
| `arvDt` | `reservListMap[0].arvDt` |
| `arvRsStnCd` | `reservListMap[0].arvRsStnCd` |
| `arvTm` | `reservListMap[0].arvTm` |
| `dlayAcptFlg` | `reservListMap[0].dlayAcptFlg` |
| `dptDt` | `reservListMap[0].dptDt` |
| `dptRsStnCd` | `reservListMap[0].dptRsStnCd` |
| `dptTm` | `reservListMap[0].dptTm` |
| `jrnyTpCd` | 예약 상태 |
| `lumpStlTgtNo` | `reservListMap[0].lumpStlTgtNo` |
| `proyStlTgtFlg` | `reservListMap[0].proyStlTgtFlg` |
| `stlbTrnClsfCd` | `reservListMap[0].stlbTrnClsfCd` |
| `totSeatNum` | `reservListMap[0].totSeatNum` |
| `trnGpCd` | `reservListMap[0].trnGpCd` |
| `trnNo` | `reservListMap[0].trnNo` |

### 9.7 단체 예약 성공 후 `/ard/selectListArd02018_n.do`

단체 예약 성공 시 단체 결제/예약 상세 page로 POST 이동한다.

추가/차이 필드:

| 필드 | 값/출처 |
|---|---|
| `pnrNo` | `-1` |
| `rcvdAmt` | `resultMap[0].totRcvdAmt` |
| `tmpJobSqno1` | `resultMap[0].tmpJobSqno1` |
| `tmpJobSqno2` | `0` |
| `seatNo1` | `trainListMap[0].seatNo` |
| `scarNo1` | `trainListMap[0].scarNo` |

그 외 여정/열차 필드는 개인 예약과 동일한 계열이다.

### 9.8 `/ata/selectListAta01032_n.do`

`arc0102c.js`에서 할인/추가 화면으로 이동할 때 사용한다.

| 필드 | 값 |
|---|---|
| `pnrNo` | `${commandMap.pnrNo}` |

## 10. 오프라인 승차권

### 10.1 Web offline page 저장 키

| 페이지 | key | 처리 |
|---|---|---|
| `ticketList.html` | `offTicketList` | `loadPrfs`로 raw string 읽기 |
| `ticket_view.html` | `offTicketList` | URL query의 `pnrNo`와 매칭 |

`ticketList.html` 처리:

1. `window.srbridge.bridgeCall("loadPrfs", {"prfsKey":"offTicketList","callback":"offTicketListCallback"})`
2. callback data 길이가 `<= 88`이면 승차권 없음 처리.
3. `atob(data)` 실행.
4. `decodeURIComponent(...)` 실행.
5. JSON parse.
6. `parseList["list"]` HTML을 `#ticketList`에 append.

`ticket_view.html` 처리:

1. 같은 `offTicketList`를 decode한다.
2. URL query에서 `pnrNo`를 읽는다.
3. key를 `:`와 `_` 기준으로 split한다.
4. split 결과 중 `data[2] == pnrNo`인 항목 HTML만 표시한다.

### 10.2 Native offline activity 저장 키

Native `SROfflineActivity` 계열은 `SRAIL.ticketListOffline`을 읽는다. 값은 Base64 decode 후 URLDecode 하고 JSON array로 parse한다.

### 10.3 Offline ticket DTO 필드

| 필드 | 의미 |
|---|---|
| `saleWctNo` | 판매 창구 번호 |
| `saleDt` | 판매일 |
| `saleSqno` | 판매 순번 |
| `retPwd` | 반환/환불 비밀번호 계열 |
| `buyPsNm` | 구매자명 |
| `pnrNo` | 예약번호 |
| `dptRsStnCd` | 출발역 코드 |
| `pbpAcepTgtFlg` | 대상 flag |
| `tkKndCd` | 승차권 종류 코드 |
| `dptRsStnNm` | 출발역명 |
| `dptDt` | 출발일 |
| `dptTm` | 출발시각 |
| `arvRsStnNm` | 도착역명 |
| `arvDt` | 도착일 |
| `arvTm` | 도착시각 |
| `seatNo` | 좌석 번호 |
| `seatNum` | 좌석 수 |
| `scarNo` | 차량 번호 |
| `psgTpDvCd` | 승객 유형 |
| `stdrAmt` | 기준 금액 |
| `totDcntAmt` | 총 할인 금액 |
| `rcvdAmt` | 수신/결제 금액 |
| `stdrPrc` | 기준 가격 |
| `stdrFare` | 기준 운임 |
| `dcntPrc` | 할인 가격 |
| `rcvdAmt1` | 1구간 금액 |
| `stdrPrc1` | 1구간 기준 가격 |
| `stdrFare1` | 1구간 기준 운임 |
| `dcntPrc1` | 1구간 할인 가격 |
| `rcvdAmt2` | 2구간 금액 |
| `stdrPrc2` | 2구간 기준 가격 |
| `stdrFare2` | 2구간 기준 운임 |
| `dcntPrc2` | 2구간 할인 가격 |
| `trainType` | 열차 유형 |
| `psrmClCd1` | 1구간 객실 |
| `psrmClCd2` | 2구간 객실 |
| `dptRsStnNm2` | 2구간 출발역명 |
| `dptDt2` | 2구간 출발일 |
| `dptTm2` | 2구간 출발시각 |
| `arvRsStnNm2` | 2구간 도착역명 |
| `arvDt2` | 2구간 도착일 |
| `arvTm2` | 2구간 도착시각 |
| `seatNo2` | 2구간 좌석 번호 |
| `scarNo2` | 2구간 차량 번호 |
| `psgTpDvCd2` | 2구간 승객 유형 |
| `isTransfer` | 환승 여부 |
| `stlbTrnClsfNm` | 1구간 열차명 |
| `stlbTrnClsfNm2` | 2구간 열차명 |
| `trnNo` | 1구간 열차 번호 |
| `trnNo2` | 2구간 열차 번호 |
| `roomType1` | 1구간 객실 표시 |
| `roomType2` | 2구간 객실 표시 |

## 11. 푸시/H2O/FCM

### 11.1 FCM payload

FCM 수신 서비스는 data payload의 `PUSH_MSG`를 읽고, 그 안의 JSON 문자열을 다시 parse한다.

```json
{
  "PUSH_MSG": "{\"MSGIDX\":\"...\",\"message\":\"...\"}"
}
```

내부 payload:

| 필드 | 의미 |
|---|---|
| `MSGIDX` | 메시지 index |
| `message` | 알림 표시 메시지 |

처리:

- `MSGIDX`를 SharedPreferences `SRApp.MSGIDX`에 저장한다.
- notification body로 `message`를 사용한다.
- notification intent extra `msg`를 넣어 `SRWebActivity`를 연다.

### 11.2 FCM token refresh

토큰 갱신 시:

1. SharedPreferences `SRApp.TOKEN`에 저장.
2. H2O `pushRegist` 실행.

### 11.3 H2O 설정

| 항목 | 값 |
|---|---|
| host | `push.srail.co.kr` |
| port | `3101` |
| timeout | `30` |
| userID | Android ID uppercase에서 `:`/`-` 제거 |
| token | `SRApp.TOKEN` |
| packageName | 앱 패키지명 또는 일부 경로에서 google project id |

### 11.4 ERB API

| 함수 | 동작 | 성공 |
|---|---|---|
| `pushRegist(host, port, userID, token, packageName, timeout)` | native `Login` | return `1` |
| `pushUnRegist(host, port, userID, packageName, timeout)` | native `Logout` | return `1`, 성공 시 `H2O_PREF.USER_ID`, `SRApp.USERID` 정리 |
| `pushReceipt(host, port, userID, msgIdx, timeout)` | 수신 확인 | return `1` |
| `pushGetMsg(host, port, userID, packageName, timeout, GetMsgData)` | 메시지 조회 | return `1` |

`pushReceipt` body 구성:

```text
<userID right-padded 32>A<256 blanks><msgIdx>
```

`pushGetMsg` request body:

```text
<userID right-padded 32>00001<packageName right-padded 32>
```

`pushGetMsg` response parse:

| offset | 길이 | 의미 |
|---:|---:|---|
| 32 | 1 | return code |
| 118 | 18 | `msgIdx` |
| 140 | 10 | message length |
| 150 | variable | UTF-8 message |

### 11.5 구현상 불일치

일부 서비스 경로에서 `SrtFirebaseMessagingService`가 port로 실제 `3101` 문자열을 parse하지 않고 resource id 정수 자체를 넘기는 코드 흐름이 보인다. 반면 공통 H2O helper는 실제 package name과 parse된 port를 넘긴다. 런타임에서 어떤 경로가 주로 쓰이는지 동적 확인이 필요하다.

## 12. 인증, FIDO, SNS, 외부앱

### 12.1 OnePass/FIDO 초기화

`SRWebActivity.onCreate`에서 OnePass가 초기화된다.

| 항목 | 값 |
|---|---|
| base URL | `https://fido.srail.co.kr` |
| site | `SIT02SR0000000000000` |
| service | `SVC01SIT02SR00000000` |
| appId preference | 저장됨 |
| deviceId preference | 저장됨 |

### 12.2 FIDO SDK subpaths

| Path | 의미 |
|---|---|
| `/interfToken/processRequest.do` | 토큰/인터페이스 요청 |
| `/fido/deviceUaf/processUafRequest.do` | UAF 요청 |
| `/fido/deviceUaf/processUafResponse.do` | UAF 응답 |
| `/interfDeviceBiz/processRequest.do` | 단말 비즈니스 요청 |
| `/interfBiz/processRequest.do` | 비즈니스 요청 |
| `/bioDevice/serviceRequest.do` | dormant/SDK 내부 후보 |

### 12.3 Google login

| 항목 | 값 |
|---|---|
| action | `snsLogin` |
| type | `G` |
| 결과 | `{ "id": "...", "type": "G" }` |
| Google client id | `<SRT-APP-GCM-SENDER-ID-REDACTED>-9f7fmobvstk0t6ga1mp1gdo68uhsf2d9.apps.googleusercontent.com` |

### 12.4 Kakao/Naver/Facebook

| 서비스 | 확인된 값/host |
|---|---|
| Kakao app key | `<SRT-APP-KAKAO-APP-KEY-REDACTED>` |
| Kakao hosts | `kauth.kakao.com`, `kapi.kakao.com`, `story.kakao.com`, `talk-apps.kakao.com`, `accounts.kakao.com`, `sharer.kakao.com`, `apps.kakao.com` |
| Naver hosts | `nid.naver.com`, `static.nid.naver.com` |
| Facebook app id | `<SRT-APP-FACEBOOK-APP-ID-REDACTED>` |
| Facebook scheme | `fb1895864877391407` |

Kakao와 Naver는 asset/SDK 흔적은 있으나 현재 Android first-party bridge에서 강하게 호출되는 로그인 시작점은 Google만 명확하다.

### 12.5 외부앱 연동

| 앱/스킴 | 동작 |
|---|---|
| `com.RLP.railpolice` | `krailwaypolice://crime.report?<values>` |
| `com.dho.mobilefax` | 이미지 `ACTION_SEND` |
| `com.shcard.smartpay` | `shinhan-sr-ansimclick-srt://srCode=aaa` |
| `kr.go.mobileid`, `kr.go.mobileid.tbe` | `mobileid://` 처리 |
| Play Store | 미설치 fallback |

## 13. 공통 코드/역 데이터

### 13.1 SRT 역 코드

| 코드 | 역명 |
|---|---|
| `0551` | 수서 |
| `0552` | 동탄 |
| `0553` | 지제 |
| `0502` | 천안아산 |
| `0297` | 오송 |
| `0010` | 대전 |
| `0507` | 김천구미 |
| `0015` | 동대구 |
| `0508` | 신경주 |
| `0509` | 울산 |
| `0020` | 부산 |
| `0514` | 공주 |
| `0030` | 익산 |
| `0033` | 정읍 |
| `0036` | 광주송정 |
| `0037` | 나주 |
| `0041` | 목포 |

`stationInfo.js`는 SRT 17개 역과 Korail 341개 역 데이터를 포함한다. 필드 구조는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `gubun` | 구분 |
| `ln_cd` | 노선 코드 |
| `stn_cd` | 역 코드 |
| `stn_nm` | 역명 |
| `sel_yn` | 선택 가능 여부 |
| `rmk` | 비고 |
| `ordr` | 정렬 순서 |

### 13.2 열차 분류 코드 `stlbTrnClsfCd`

| 코드 | 의미 |
|---|---|
| `00` | KTX |
| `01` | 새마을호 |
| `02` | 무궁화호 |
| `03` | 통근열차 |
| `04` | 누리로 |
| `05` | 전체열차 |
| `06` | 공항직통 |
| `07` | KTX-산천 |
| `08` | ITX-새마을 |
| `09` | ITX-청춘 |
| `10` | KTX-산천 |
| `15` | ITX-청춘 |
| `17` | SRT |

### 13.3 열차 그룹 코드 `trnGpCd`

| 코드 | 의미 |
|---|---|
| `100` | KTX |
| `101` | 새마을 |
| `102` | 무궁화 |
| `103` | 통근 |
| `104` | ITX-청춘 |
| `105` | 공항철도 |
| `109` | 전체 |
| `201` | O-train |
| `202` | V-train |
| `203` | S-train |
| `204` | DMZ |
| `205` | 정선아리랑 |
| `206` | 서해금빛 |
| `300` | SRT |
| `900` | KTX+SRT |

### 13.4 승객/객실/좌석 코드

`psgTpCd`:

| 코드 | 의미 |
|---|---|
| `1` | 어른 |
| `2` | 장애 1~3급 |
| `3` | 장애 4~6급 |
| `4` | 만65세이상 |
| `5` | 만4~12세 |

`psgTpDvCd`:

| 코드 | 의미 |
|---|---|
| `1` | 어른 |
| `3` | 어린이 |
| `D` | Dummy |

`psrmClCd`:

| 코드 | 의미 |
|---|---|
| `1` | 일반실 |
| `2` | 특실 |
| `4` | 입석/자유석 |

`locSeatAttCd`:

| 코드 | 의미 |
|---|---|
| `000` | 기본 |
| `009` | 순방향 |
| `010` | 역방향 |
| `011` | 1인석 |
| `012` | 창측 |
| `013` | 내측 |
| `021` | 휠체어 |
| `028` | 전동휠체어 |

`rqSeatAttCd`:

| 코드 | 의미 |
|---|---|
| `015` | 일반 |
| `018` | 2층석 |
| `019` | 유아동반 |
| `021` | 휠체어 |
| `028` | 전동휠체어 |
| `031` | 노트북 |
| `032` | 자전거거치대 |

`jrnyTpCd`:

| 코드 | 의미 |
|---|---|
| `11` | 편도/직통 |
| `14` | 환승 편도 |

### 13.5 이벤트/예외 데이터

이벤트 열차 기간은 `2018-03-12`부터 `2018-03-20`까지로 하드코딩되어 있다. 분석 기준일 `2026-07-09`에는 항상 비활성이다.

이벤트 대상:

| 열차 | 분류 | 할인 |
|---|---|---|
| `321` | SRT `17` | 30% |
| `331` | SRT `17` | 30% |
| `335` | SRT `17` | 30% |
| `345` | SRT `17` | 30% |
| `351` | SRT `17` | 30% |
| `361` | SRT `17` | 30% |

`exceptStation.js`의 `getStationFlag(cd1, cd2)`는 특정 역쌍을 false로 반환한다. 데이터에는 `exceptSstn_cd2` 오탈자와 역 코드/명 충돌로 보이는 항목이 있어 서버 정책과 다를 수 있다.

## 14. NetFunnel

`assets/offline/js/common/netfunnel.js`에 대기열 클라이언트가 포함되어 있다.

| 항목 | 값 |
|---|---|
| host | `nf.letskorail.com` |
| protocol | `https` |
| port | `443` |
| path/query | `ts.wseq` |
| service id | `service_1` |
| action id | `act_10` |
| bypass flag | `TS_BYPASS=true` |

주요 opcode:

| opcode | 의미 |
|---|---|
| `5101` | getTidChkEnter |
| `5002` | chkEnter |
| `5003` | aliveNotice |
| `5004` | setComplete |
| `5105` | init |
| `5106` | stop |

Query 구성:

| 파라미터 | 의미 |
|---|---|
| `opcode` | 동작 코드 |
| `nfid` | NetFunnel id |
| `prefix` | `NetFunnel.gRtype=<opcode>;` |
| `sid` | service id |
| `aid` | action id |
| `key` | 대기열 key |
| `ttl` | TTL |
| `user_data` | 사용자 데이터 |
| `js` | `yes` |
| timestamp | cache busting |

다만 `ara0101v.fn_moveSearchPage`의 NetFunnel 호출은 주석 처리되어 있고 callback을 직접 호출하는 상태다. 운영 서버가 내려주는 최신 페이지에서는 다를 수 있다.

## 15. Embedded configuration

### 15.1 Firebase/Google

| 키 | 값 |
|---|---|
| Firebase DB | `https://<SRT-APP-FIREBASE-PROJECT-REDACTED>.firebaseio.com` |
| Firebase project | `<SRT-APP-FIREBASE-PROJECT-REDACTED>` |
| Firebase project number | `<SRT-APP-GCM-SENDER-ID-REDACTED>` |
| Firebase Android app id | `<SRT-APP-GOOGLE-APP-ID-REDACTED>` |
| Firebase storage | `<SRT-APP-FIREBASE-PROJECT-REDACTED>.appspot.com` |
| Google OAuth client | `<SRT-APP-GCM-SENDER-ID-REDACTED>-9f7fmobvstk0t6ga1mp1gdo68uhsf2d9.apps.googleusercontent.com` |
| Google API key | `<SRT-APP-GOOGLE-API-KEY-REDACTED>` |
| SRT GCM API key | `<SRT-APP-GCM-API-KEY-REDACTED>` |

### 15.2 AppIron

| 항목 | 값 |
|---|---|
| URL | `http://iron.srail.co.kr/authCheck.call` |
| 인증서 위치 | `assets/appiron/signCert.der` |
| 인증서 SHA-256 | `2c54bb5bb42afb27ef38f1406d5e06ac252870b7c53014a7e16dc57b4a41fe12` |
| subject | `CN=AppIron` |
| issuer | `CN=CA` |
| 만료 | `2023-07-05` |

### 15.3 기타 식별자

| 항목 | 값 |
|---|---|
| FIDO app id | `com.raon.fido.fidoclient` |
| Facebook app id | `<SRT-APP-FACEBOOK-APP-ID-REDACTED>` |
| Facebook scheme | `fb1895864877391407` |
| Kakao app key | `<SRT-APP-KAKAO-APP-KEY-REDACTED>` |

## 16. 보안/품질 관찰

이 절은 취약점 확정 보고서가 아니라 정적 분석으로 보이는 위험 표면이다. 실제 영향도는 서버 설정, 도메인 통제, 런타임 버전, 배포 정책 확인이 필요하다.

| 관찰 | 영향 |
|---|---|
| `usesCleartextTraffic=true` | HTTP 통신 허용 표면이 열려 있음 |
| Safe Browsing disabled | 악성/위험 URL 보호 약화 |
| WebView debugging enabled | 디버그 가능한 빌드/운영 빌드 구분 필요 |
| Mixed content always allow | HTTPS 페이지 내 HTTP 리소스 허용 |
| third-party cookies allowed | WebView 추적/세션 표면 확대 |
| file URL universal access | asset/file origin 경계 약화 |
| SSL error에서 proceed 가능 | 사용자 선택으로 인증서 오류 무시 가능 |
| `addJavascriptInterface`가 원격 WebView에 노출 | 원격 web content가 native 기능 호출 가능 |
| TransKey plaintext 반환/Toast | 민감 입력이 JS/화면에 평문 노출될 수 있음 |
| Embedded API keys | 키 제한 설정 확인 필요 |
| FileProvider `external-path path="/"` | provider는 exported가 아니더라도 path scope가 넓음 |
| FIDO resultCode mismatch | `allowedAuthnr` 등 SDK callback이 JS에서 drop될 수 있음 |
| H2O port 전달 불일치 | push 등록/수신 경로에서 런타임 오류 가능성 |
| offline fixture에 세션형 문자열/개인정보형 더미 존재 | 실제 live credential로 보면 안 되며 fixture 관리 필요 |

## 17. 비활성/오탐 후보

문자열 추출에서 `.do`가 포함되지만 실제 endpoint로 보기 어려운 값들:

| 후보 | 판단 |
|---|---|
| `https://__bridge_loaded__` | 브리지 로딩 sentinel |
| `document.do` | JS object/property false positive |
| `item.do` | JS object/property false positive |
| `.mobile.do` | jQuery mobile false positive |
| `.options.do` | JS property false positive |
| `this.documentUrl.do` | JS property false positive |

개발/레거시 URL:

| URL | 판단 |
|---|---|
| `http://172.16.113.100:8190/main/main.do` | 개발 asset |
| `/jelly/main/main.do` | 개발/레거시 asset |
| `https://app.srail.co.kr/neo/main/main.do` | 구 도메인/레거시 후보 |
| `ara/ara0101v.do` | back-button guard URL substring |
| `ara/selectListAra10h01.do` | 주석 처리된 레거시 예약 상세 |

## 18. 한계와 추가 확인이 필요한 항목

- 운영 서버에 실제 요청하지 않았으므로 전체 response schema, 필수/선택 필드, 오류 코드 목록은 완전하지 않다.
- `#seatSearchForm`, `#rsvForm`, `#passDetailPayStepFrm`은 서버 렌더링 페이지에서 보강될 수 있다. APK 내 offline asset만으로는 hidden input 전체를 100% 복원할 수 없다.
- 일부 JavaScript는 서버에서 최신 파일로 내려오는 버전과 APK bundled offline 버전이 다를 수 있다.
- `jadx`는 일부 클래스에서 decompile error가 있었지만 주요 WebView/bridge/assets 분석에는 충분한 산출물이 생성되었다.
- FIDO/OnePass, AppIron, TransKey SDK 내부 프로토콜은 난독화/SDK 캡슐화 영역이 있어 외부 요청 필드 전체를 정적 분석만으로 확정하기 어렵다.
- AppIron 인증서가 만료된 것으로 보이지만, 실제 SDK가 이 파일을 어떻게 검증하는지는 런타임 확인이 필요하다.

## 19. 우선순위별 후속 분석 제안

1. 서버 렌더링 최신 web asset을 별도 수집해 APK bundled offline asset과 diff한다.
2. 테스트 계정과 허가된 환경에서 WebView traffic을 캡처해 실제 request body와 response body를 본 문서의 정적 schema와 대조한다.
3. FIDO callback `resultCode` 처리와 `bridge.js` drop 조건을 런타임에서 확인한다.
4. H2O push 등록 경로의 port/resource id 전달 차이를 실제 로그로 검증한다.
5. WebView 보안 설정을 운영 빌드 정책과 비교해 의도된 예외인지 확인한다.
