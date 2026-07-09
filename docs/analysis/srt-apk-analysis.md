# SRT APK Static Analysis

Analysis date: 2026-07-09  
Target artifact: `srt.apk`

## Executive Summary

The supplied APK is a hybrid Android WebView application. The native layer mainly boots a WebView, sets device/session state, exposes a broad JavaScript bridge named `srbridge`, manages push/FIDO/vendor SDK integration, and delegates most business behavior to web pages under `app.srail.or.kr`.

The confirmed production entry point is:

```text
https://app.srail.or.kr/main/main.do?deviceId=<android_id>[&pushMsg=<message>]
```

Most train search, reservation, fare, seat-selection, and ticket flows are visible in bundled offline HTML/JavaScript assets under `assets/offline/`. Those assets use jQuery Mobile POST navigation and AJAX calls against `.do` endpoints such as `/ara/selectListAra10007_n.do`, `/arc/selectListArc05013_n.do`, and `/ard/selectListArd02017_n.do`.

This document is static analysis only. Server-generated pages fetched at runtime may contain additional endpoints not bundled in the APK.

## Artifact Metadata

| Field | Value |
|---|---|
| File | `srt.apk` |
| Size | 25 MB (`26,427,764` bytes) |
| Type | ZIP archive / Android APK |
| SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| Archive file count | 2,574 entries |
| DEX files | `classes.dex` |
| Native libraries | none found under `lib/` |
| Package | `kr.co.srail.newapp` |
| Version | `2.0.41` / `versionCode=150` |
| SDK | `minSdk=18`, `targetSdk=35`, `compileSdk=35` |
| Notable assets | `assets/appiron/signCert.der`, `assets/asm.db`, `assets/auth_sw.db`, `assets/dev.html`, `assets/eula.html`, `assets/offline/` |

Evidence:

- APK listing: `build/apk-file-list.txt`
- Decoded APK: `build/apktool/`
- Decompiled Java: `build/jadx/`
- APK metadata: `build/apktool/apktool.yml`

## Application Metadata

| Item | Finding | Evidence |
|---|---|---|
| Environment | Manifest sets `ENV=PRD`; `GlobalApplication` defaults to `DEV` but overwrites from manifest metadata. | `build/apktool/AndroidManifest.xml:53-54`, `build/jadx/sources/kr/co/srail/newapp/GlobalApplication.java:25`, `:137-149` |
| Application class | `kr.co.srail.newapp.GlobalApplication` | `build/apktool/AndroidManifest.xml:53` |
| Main activity | `kr.co.srail.newapp.main.SRMainActivity`, exported, launcher, also handles `srapp://main`. | `build/apktool/AndroidManifest.xml:56-67` |
| Main WebView activity | `kr.co.srail.newapp.webview.SRWebActivity` | `build/apktool/AndroidManifest.xml:68` |
| Offline WebView activity | `kr.co.srail.newapp.webview.SROfflineActivity` | `build/apktool/AndroidManifest.xml:69` |
| Push service | `kr.co.srail.newapp.push.SrtFirebaseMessagingService`, exported. | `build/apktool/AndroidManifest.xml:107-111` |
| Widget | `kr.co.srail.newapp.widget.SRWidget`, exported, actions `BUTTON1`-`BUTTON4`. | `build/apktool/AndroidManifest.xml:89-98` |
| Network/security flags | `usesCleartextTraffic=true`; WebView safe browsing disabled. | `build/apktool/AndroidManifest.xml:53`, `:88` |
| Queried external packages | Korail Talk, Daum Map, Kakao Taxi, Rail Police, mobile fax, mobile ID packages. | `build/apktool/AndroidManifest.xml:3-10` |

Important permissions include `INTERNET`, `CAMERA`, `READ_PHONE_NUMBERS`, legacy phone/storage permissions, Wi-Fi/network state, notification, biometric/fingerprint, wake lock, FCM receive, and launcher badge permissions.

## Architecture

The runtime flow is:

1. `GlobalApplication` reads manifest `ENV`.
2. `SRWebActivity.onCreate` initializes CookieSyncManager, Facebook/Google/Firebase auth helpers, SharedPreferences, WebView settings, and OnePass FIDO.
3. `SRWebActivity.X0()` chooses the base host:
   - `PRD` -> `https://app.srail.or.kr`
   - non-PRD -> `https://devapp.srail.or.kr`
4. The first URL is built with Android ID as `deviceId`.
5. The WebView loads server pages; web pages call native code through `window.srbridge.bridgeCall(action, json)`.
6. Native bridge callbacks are sent back into JavaScript using `evaluateJavascript` or `javascript:` URL injection.

Evidence:

- Base URL and first URL construction: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:1572-1595`
- Startup flow and OnePass init: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:2484-2524`
- WebView load wrapper: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:1997-2001`
- JS bridge entry point: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:1052-1189`

## Network Hosts

| Host / URL | Purpose | Evidence |
|---|---|---|
| `https://app.srail.or.kr` | Production WebView base host. | `SRWebActivity.java:1577-1585` |
| `https://devapp.srail.or.kr` | Non-production WebView base host. | `SRWebActivity.java:1579-1581` |
| `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0` | Foreground notification/dialog route for ticket list. Note the host differs from the main `or.kr` base. | `build/jadx/sources/kr/co/srail/newapp/main/SRForegroundDialogActivity.java:29-32` |
| `https://devapp.srail.co.kr/neo/common/rest/JongURi/view.do` | DEV-only URL checked by floating button UI logic. | `SRWebActivity.java:2055-2068` |
| `https://fido.srail.co.kr` | TouchEn OnePass/FIDO service endpoint initialized with site/service IDs. | `SRWebActivity.java:2517-2523` |
| `push.srail.co.kr:3101` | H2O SmartBroker push registration, message fetch, unregister, receipt. | `build/apktool/res/values/strings.xml:178-179`, `build/jadx/sources/b6/a.java:36-75` |
| `http://iron.srail.co.kr/authCheck.call` | AppIron anti-tamper/auth check resource configuration. Static references were found in resources/vendor code; no direct app-package caller was confirmed. | `build/apktool/res/values/strings.xml:73` |
| `https://<SRT-APP-FIREBASE-PROJECT-REDACTED>.firebaseio.com` | Firebase Realtime Database URL from resources. | `build/apktool/res/values/strings.xml:162` |
| `https://www.srail.co.kr` / `http://www.srail.co.kr` | CMS/news article and image links embedded in offline main page. | `build/apktool/assets/offline/sub/main.html:732-740` |
| `etk.srail.co.kr`, `etk.srail.kr`, `m.tour.srail.co.kr`, `www.srail.co.kr`, `play.google.com` | External-link allowlist opened outside the app. | `build/apktool/res/values/arrays.xml:3-9`, `SRWebActivity.java:478-492` |

## API Inventory

### Native-loaded Web URLs

| Area | Method | URL / Path | Parameters | Trigger / Behavior | Evidence |
|---|---:|---|---|---|---|
| Main page | GET/WebView load | `https://app.srail.or.kr/main/main.do` | `deviceId=<android_id>`, optional `pushMsg=<message>` | Default app launch. `deviceId` comes from `Settings.Secure.android_id`. | `SRWebActivity.java:1572-1595`, `:2514-2516` |
| Widget main | GET/WebView load | `https://app.srail.or.kr/main/main.do` | `deviceId=<android_id>` | Widget `btnNo=1`. | `SRWebActivity.java:1589-1591` |
| Widget ticket check | GET/WebView load | `https://app.srail.or.kr/atc/selectListAtc14017_n.do` | none visible | Widget `btnNo=2`. | `SRWebActivity.java:1591-1592` |
| Foreground ticket check | GET/WebView load | `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0` | `pageNo=0` | Foreground push/dialog OK button. | `SRForegroundDialogActivity.java:29-32` |
| Offline error recovery | GET/WebView redirect | `https://app.srail.or.kr/main/main.do` | none visible in asset | Offline error page home action. | `build/apktool/assets/offline/sub/error.html:116` |

### Bundled Web Business Endpoints

These are extracted from `assets/offline/` web assets. At runtime the live server may serve newer pages with additional endpoints.

| Area | Method | Path | Parameters / Payload | Trigger / Behavior | Evidence |
|---|---:|---|---|---|---|
| Login/logout | POST form | `/srail-app/login/loginOut.do` | Form submission | Logout form in bundled main/pushtest pages. | `offline/sub/main.html:455`, `offline/sub/pushtest.html:498` |
| Main page | jQuery Mobile page | `/srail-app/main/main.do` | none visible | Main page `data-url`. | `offline/sub/main.html:686`, `offline/sub/pushtest.html:724` |
| Booking entry/search form | POST form | `/apb/selectListApb01080_n.do` | Form fields from main booking form. | Main booking form submit. | `offline/sub/main.html:721`, `offline/sub/pushtest.html:759` |
| Station popup | POST pagecontainer | `/common/ARA/ARA0501P/view.do` | `reqCode`, departure/arrival station names and codes, current selection. | Station selector. | `offline/js/ara/ara0101v.js:155-173` |
| Date popup | POST pagecontainer | `/common/ARA/ARA0401P/view.do` | `reqCode`, `selectDay`, `selectDt`. | Departure/return date selector. | `offline/js/ara/ara0101v.js:176-208` |
| Passenger popup | POST pagecontainer | `/common/ARA/ARA0901P/view.do` | `reqCode`, `isOrg`, passenger counts 1-5, total passenger count. | Passenger selector and group mode passenger selector. | `offline/js/ara/ara0101v.js:212-248`, `:478-495` |
| Seat option popup | POST pagecontainer | `/common/ARA/ARA0701P/view.do` | `reqCode`, `rqSeatAttCd`, `locSeatAttCd`, `seatAttNm`. | Seat option selector. | `offline/js/ara/ara0101v.js:252-268` |
| Train group popup | POST pagecontainer | `/common/ARA/ARA0201V/view.do` | `reqCode`, `trnGpCd`, `trnGpCdNm`. | Train type selector. | `offline/js/ara/ara0101v.js:272-285` |
| Train search, personal | POST AJAX | `/ara/selectListAra10007_n.do` | Serialized `#seatSearchForm`; key values include `chtnDvCd`, `dptDt`, `dptTm`, `dptRsStnCd`, `arvRsStnCd`, `stlbTrnClsfCd`, `psgNum`, `seatAttCd`, `arriveTime=N`, `trnGpCd`, `trnNo`. | Train availability search for personal reservations. | `offline/js/ara/ara1001l.js:158-190` |
| Train search, group | POST AJAX | `/ara/selectListAra10082_n.do` | Same serialized search form. | Train availability search for group reservations. | `offline/js/ara/ara1001l.js:174-190` |
| Search pagination | POST AJAX | `/ara/selectListAra10007_n.do` or `/ara/selectListAra10082_n.do` | Serialized `#seatSearchForm`. | Re-fetches next schedule page until no more data. | `offline/js/ara/ara1001l.js:1818-1838` |
| Mutual verification | POST AJAX | `/ara/selectListAra10130_n.do` | none visible | Generates `mutMrkVrfCd` for Korail interoperability. | `offline/js/ara/ara1001l.js:225-245` |
| Train timetable | POST pagecontainer | `/ara/selectListAra12009_n.do` | `runDt`, `trnNo`, `trnSort`, `stnCourseNm`. | Timetable click from search result. | `offline/js/ara/ara1001l.js:1169-1194` |
| Fare lookup | POST pagecontainer | `/ara/selectListAra13010_n.do` | `chtnDvCd`, station codes, `runDt`, `trnNo`, `runDt1`, `trnNo1`, optional leg 2 fields, `trnSort`, `stnCourseNm`, passenger counts 1-5. | Fare click from search result. | `offline/js/ara/ara1001l.js:1196-1234` |
| Seat map/seat selection | POST pagecontainer | `/arc/selectListArc02012_n.do` | `reqCode`, `runDt`, `dptDt`, `trnNo`, `dptTm`, `trnGpCd=300`, station codes, `psrmClCd`, `seatAttCd`, station run order, `choiceSeatCount`. | Seat selection flow. | `offline/js/ara/ara1001l.js:1495-1520` |
| Reservation, personal | POST AJAX | `/arc/selectListArc05013_n.do` | Serialized `#rsvForm`. | Personal reservation execution. | `offline/js/ara/ara1001l.js:1527-1557` |
| Reservation, group | POST AJAX | `/arc/selectListArc06014_n.do` | Serialized `#rsvForm`. | Group reservation execution. | `offline/js/ara/ara1001l.js:1541-1557` |
| Payment/detail, personal | POST form | `/ard/selectListArd02017_n.do` | Form populated from reservation response, including `pnrNo`, journey/train/station/time fields. | Success path after personal reservation. | `offline/js/ara/ara1001l.js:1577-1633` |
| Payment/detail, group | POST form | `/ard/selectListArd02018_n.do` | Form populated with `pnrNo=-1`, `rcvdAmt`, `tmpJobSqno1`, `tmpJobSqno2=0`, seat/car, journey/train/station/time fields. | Success path after group reservation. | `offline/js/ara/ara1001l.js:1595-1633` |
| Discount/details | jQuery Mobile page | `/ata/selectListAta01032_n.do` | `pnrNo=${commandMap.pnrNo}` | Discount button in reservation detail asset. | `offline/js/arc/arc0102c.js:33-36` |
| Ticket list page | jQuery Mobile page marker | `/srail-app/atc/selectListAtc14016_n.do?pageNo=0` | `pageNo=0` | Bundled offline ticket list page marker; actual offline display reads cached data. | `offline/sub/ticketList.html:405` |
| CMS news list | Link | `/cms/article/list.do?pageId=KR0502000000` | `pageId=KR0502000000` | SR news link. | `offline/sub/main.html:732`, `offline/sub/pushtest.html:769` |
| CMS article view | Link | `https://www.srail.co.kr/cms/article/view.do` | `postNo`, `pageId`, optional `pageIndex`. | Embedded sample SR news links. | `offline/sub/main.html:735-739` |
| CMS image attach | Image URL | `http://www.srail.co.kr/cms/attach/image.do` | `source=<encoded>` | Background images for SR news items. | `offline/sub/main.html:735-740` |

Inactive or non-endpoint matches:

- `ara/selectListAra10h01.do` appears only in commented-out legacy code for transmitting mutual verification to the homepage. It was not counted as an active call. Evidence: `offline/js/ara/ara1001l.js:253-279`.
- `document.do` and `item.do` were false positives from generic JavaScript identifiers.

### Native Push APIs

The push implementation uses H2O SmartBroker `ERBAPIs`, not ordinary HTTP calls in the app code.

| Command | Host / Port | Parameters | Trigger / Behavior | Evidence |
|---|---|---|---|---|
| `pushRegist` | `push.srail.co.kr:3101` | Android ID-derived user ID, FCM token, package name, timeout `30`. | Called on FCM token refresh and `SRWebActivity.onStart`; also callable from JS bridge action `regDevice`. | `SrtFirebaseMessagingService.java:93-98`, `SRWebActivity.java:2582-2586`, `b6/a.java:53-67` |
| `pushUnRegist` | `push.srail.co.kr:3101` | Android ID-derived user ID, FCM token, package name, timeout `30`. | JS bridge action `unRegDevice`; clears H2O/SRApp user IDs on success. | `b6/a.java:70-92`, `SRWebActivity.java:1105-1107` |
| `pushGetMsg` | `push.srail.co.kr:3101` | Android ID-derived user ID, package/project identifier, timeout `30`. | Fetches full push message body from H2O after FCM payload or explicit action. | `SrtFirebaseMessagingService.java:43-63`, `b6/a.java:36-47` |
| `pushReceipt` | `push.srail.co.kr:3101` | Android ID-derived user ID, stored `MSGIDX`, timeout `30`. | Receipt acknowledgment command. | `b6/a.java:49-51`, `:99-134` |

The app derives the push user ID from `Settings.Secure.android_id` with colon/hyphen removal and uppercase conversion. The Wi-Fi MAC call is present but the returned MAC address is not used. Evidence: `b6/a.java:27-34`, `SrtFirebaseMessagingService.java:100-107`.

## Request Mechanics

- Business web APIs are generally invoked from JavaScript via `$.ajax({ type: "POST", dataType: "json" })` or `$.mobile.pageContainer.pagecontainer("change", ..., { type: "POST", data })`.
- Main WebView navigation is a normal `WebView.loadUrl(...)` call.
- The native layer appends `SRT-APP-Android V.<version>` directly to the default WebView user agent.
- Cookies are globally enabled, including third-party cookies for the main WebView and pop-up WebViews.
- Initial app load exposes Android ID as `deviceId` query parameter.
- Push messages may be passed into the main URL as `pushMsg`.
- Reservation errors with `msgCd == "S111"` store serialized reservation params in `localStorage.userReservation` and then redirect to login.

Evidence:

- User-agent construction: `SRWebActivity.java:2642-2645`
- Cookie settings: `SRWebActivity.java:2663-2667`
- Initial URL parameters: `SRWebActivity.java:1582-1587`
- Reservation login redirect cache: `offline/js/ara/ara1001l.js:1560-1574`

## JavaScript Bridge

The WebView registers:

```java
W.addJavascriptInterface(new y(...), "srbridge")
```

Confirmed Android bridge actions:

| Action | Native behavior |
|---|---|
| `mkQRCode`, `mkQRCode2` | QR generation path. |
| `takePicture`, `selectPicture`, `selectPictureByCode`, `getTakePicture`, `getTakeIdCard` | Camera/gallery/media capture flows with runtime permissions. |
| `showTransKey` | Softsecurity TransKey secure keyboard. |
| `pkgVersion` | App version callback. |
| `getNetworkAddress` | Network address callback. |
| `snsLogin` | Social login flow. |
| `callExtApp` | External app invocation. |
| `savePrfs`, `loadPrfs` | `SRApp` SharedPreferences wrapper for web-visible persistent values. |
| `regDevice`, `unRegDevice` | H2O push registration/unregistration. |
| `mobileFAX` | Media/storage permission and fax app flow. |
| `getStorageItem`, `setStorageItem`, `removeStorageItem` | `SRAIL` SharedPreferences key/value wrapper. |
| `writeLog` | DEV-only logging. |
| `easypay` | Easy payment handoff. |
| `mainShow`, `windowOpen` | Main UI/popup WebView behavior. |
| `disableCapture`, `enableCapture` | Screen capture flag control. |
| `allowedAuthnr`, `requestServiceRegist`, `requestServiceRelease`, `requestServiceAuth` | OnePass/FIDO permission and service operations. |

Evidence:

- Bridge action dispatcher: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:1052-1189`
- Android bridge JavaScript caller: `build/apktool/assets/offline/js/common/bridge.js:50-57`
- `SRApp` preference storage: `build/jadx/sources/c6/d.java:22-47`
- `SRAIL` storage wrapper: `SRWebActivity.java:1544-1565`, `:1874-1897`, `:1342-1361`
- `savePrfs`/`loadPrfs`: `SRWebActivity.java:1394-1407`, `:1990-1994`

## Booking Logic

### Default Search State

The bundled booking page initializes with:

- Default departure station: `0551` / 수서.
- Default arrival station: `0020` / 부산.
- Default train group: `109` / 전체. Comments indicate `300` for SRT and `900` for KTX+SRT.
- Default journey type: `jrnyTpCd=11` / direct one-way.
- Transfer journey: `jrnyTpCd=14`, `jrnyCnt=2`.
- Group flag: `grpDv=0` for personal, `grpDv=1` for group.
- Round-trip flag: `rtnDv=0` or `1`.
- Default passenger count: one adult.
- Default seat request: `rqSeatAttCd=015`, `locSeatAttCd=000`, `dirSeatAttCd=009`.

Evidence: `build/apktool/assets/offline/js/ara/ara0101v.js:44-145`.

### Validation Rules

Confirmed client-side validation includes:

- Group reservation requires at least 10 passengers.
- Personal reservation rejects 10 or more passengers and asks the user to use group reservation.
- Group reservation cannot be round-trip.
- Transfer cannot be round-trip.
- Departure and arrival stations cannot be identical.
- Round-trip return date/time cannot precede outbound date/time.
- Group reservation is blocked for Korail stations.
- Wheelchair and electric wheelchair seat requests show an explicit agreement message before search.

Evidence:

- Direct/transfer logic: `offline/js/ara/ara0101v.js:288-314`
- Group/Korail/round-trip constraints: `offline/js/ara/ara0101v.js:428-522`
- Search button validation: `offline/js/ara/ara0101v.js:548-610`

### Search and Reservation Flow

1. The search page builds reservation/search state from station/date/passenger/seat/train options.
2. It posts the serialized `#seatSearchForm` to either:
   - `/ara/selectListAra10007_n.do` for personal reservations.
   - `/ara/selectListAra10082_n.do` for group reservations.
3. Search results use `outDataSets.dsOutput0` for result metadata and `outDataSets.dsOutput1` for train rows.
4. Timetable and fare buttons navigate to `/ara/selectListAra12009_n.do` and `/ara/selectListAra13010_n.do`.
5. Seat selection for SRT posts to `/arc/selectListArc02012_n.do` with `trnGpCd=300`.
6. Reservation posts serialized `#rsvForm` to:
   - `/arc/selectListArc05013_n.do` for personal reservations.
   - `/arc/selectListArc06014_n.do` for group reservations.
7. On success, the form is populated from `resultMap`, `reservListMap`, and `trainListMap`, then submitted to:
   - `/ard/selectListArd02017_n.do` for personal payment/detail.
   - `/ard/selectListArd02018_n.do` for group payment/detail.
8. For round-trip, outbound reservation data is temporarily stored in the client state and the return train search starts next.

Evidence:

- Search payload and endpoint selection: `offline/js/ara/ara1001l.js:158-190`
- Search response handling: `offline/js/ara/ara1001l.js:193-214`
- Timetable/fare navigation: `offline/js/ara/ara1001l.js:1169-1234`
- Seat selection: `offline/js/ara/ara1001l.js:1495-1520`
- Reservation call: `offline/js/ara/ara1001l.js:1527-1557`
- Success path and payment/detail form population: `offline/js/ara/ara1001l.js:1577-1633`

### Korail Interoperability

The result-list logic has a Korail interop path. If the selected train row indicates the Korail reservation image/marker, the app requests a mutual verification code through `/ara/selectListAra10130_n.do` and stores it as `application.gs_mutMrkVrfCd`. A legacy call to `ara/selectListAra10h01.do` exists only in commented code.

Evidence: `offline/js/ara/ara1001l.js:225-245`, `:253-279`, `:1326-1359`.

## Ticket and Offline Data Logic

Offline ticket pages do not fetch ticket details directly in the bundled asset. They call the native bridge `loadPrfs` with `prfsKey=offTicketList`, then decode the returned value:

1. Native reads `SRApp` SharedPreferences through `c6.d`.
2. JavaScript parses bridge result JSON.
3. `data` is Base64-decoded.
4. The decoded string is `decodeURIComponent(...)`.
5. The result is parsed as JSON and appended into the ticket list/detail DOM.

Evidence:

- Ticket list `loadPrfs`: `build/apktool/assets/offline/sub/ticketList.html:39-46`
- Ticket list decode/render: `build/apktool/assets/offline/sub/ticketList.html:48-72`
- Ticket detail decode/render by `pnrNo`: `build/apktool/assets/offline/sub/ticket_view.html:33-82`
- Native `loadPrfs`: `SRWebActivity.java:1990-1994`
- `SRApp` SharedPreferences helper: `build/jadx/sources/c6/d.java:22-47`

## WebView and External Handoff Flows

The main WebView handles:

- `intent://` URLs: resolves installed app, otherwise uses `browser_fallback_url` or Play Store.
- `mobileid://` URLs: targets `kr.go.mobileid`, otherwise opens Play Store.
- `tel:` URLs: opens dialer.
- URLs matching `extLinkList` are opened in external browser.
- Other URLs are loaded inside the WebView.
- On selected network errors for `srail.or.kr`, the app loads `file:///android_asset/offline/sub/error.html`.
- SSL errors show a dialog with "continue" and "cancel"; choosing continue proceeds with the SSL error.

Evidence:

- Main URL override logic: `SRWebActivity.java:423-492`
- Pop-up WebView URL override logic: `SRWebActivity.java:884-918`
- Offline error page fallback: `SRWebActivity.java:402-410`
- SSL error behavior: `SRWebActivity.java:414-420`
- External link list: `build/apktool/res/values/arrays.xml:3-9`

## Security and Device Notes

These are observations from static analysis, not exploit claims:

- `android:usesCleartextTraffic="true"` is enabled.
- WebView Safe Browsing is disabled through manifest metadata.
- The main WebView enables JavaScript, DOM storage, multiple windows, JavaScript window open, universal access from file URLs, and file access from file URLs.
- Mixed content mode is set to `0` (`MIXED_CONTENT_ALWAYS_ALLOW`) on SDK >= 21.
- Third-party cookies are accepted.
- WebView debugging is enabled for SDK >= 19.
- SSL errors can be user-overridden through a native dialog.
- `addJavascriptInterface` exposes broad native capability to web content through `srbridge`.
- Device identifiers are used in multiple places:
  - Initial WebView query parameter `deviceId=<android_id>`.
  - Push user ID derived from Android ID.
  - OnePass app/device IDs are stored into the `SRAIL` SharedPreferences through the bridge storage helper.
- Push registration logs include IP, port, user ID, token, package name, and result.
- AppIron anti-tamper resources are present, including an HTTP auth-check URL and `assets/appiron/signCert.der`; a direct app-package call path was not confirmed in decompiled SRT app classes.

Evidence:

- Manifest flags: `build/apktool/AndroidManifest.xml:53`, `:88`
- WebView settings: `SRWebActivity.java:2632-2677`
- SSL error handling: `SRWebActivity.java:414-420`
- Device ID in main URL: `SRWebActivity.java:1582-1587`
- Push Android ID derivation/logging: `b6/a.java:27-34`, `:53-67`
- OnePass init and stored IDs: `SRWebActivity.java:2517-2523`
- AppIron resources: `build/apktool/res/values/strings.xml:49-73`, `assets/appiron/signCert.der`

## External SDK / Service Configuration

| Service | Static values |
|---|---|
| Firebase / Google | `gcm_defaultSenderId=<SRT-APP-GCM-SENDER-ID-REDACTED>`, `google_app_id=<SRT-APP-GOOGLE-APP-ID-REDACTED>`, `google_project_id=<SRT-APP-GCM-SENDER-ID-REDACTED>`, `google_storage_bucket=<SRT-APP-FIREBASE-PROJECT-REDACTED>.appspot.com`, `firebase_database_url=https://<SRT-APP-FIREBASE-PROJECT-REDACTED>.firebaseio.com` |
| Google OAuth client | `<SRT-APP-GCM-SENDER-ID-REDACTED>-9f7fmobvstk0t6ga1mp1gdo68uhsf2d9.apps.googleusercontent.com` |
| Kakao | `kakao_app_key=<SRT-APP-KAKAO-APP-KEY-REDACTED>` |
| Facebook | `facebook_app_id=<SRT-APP-FACEBOOK-APP-ID-REDACTED>`, `fb_login_protocol_scheme=fb1895864877391407` |
| H2O push | `h2o_ip=push.srail.co.kr`, `h2o_port=3101` |
| OnePass/FIDO | Base `https://fido.srail.co.kr`, site `SIT02SR0000000000000`, service `SVC01SIT02SR00000000` |

Evidence: `build/apktool/res/values/strings.xml:139-179`, `SRWebActivity.java:2517-2523`.

## Evidence Search Log

| Step | Output |
|---|---|
| APK file list | `build/apk-file-list.txt` |
| Manifest facts | `build/manifest-facts.txt` |
| Apktool URL candidates | `build/apktool-url-candidates.txt` |
| Jadx URL candidates | `build/jadx-url-candidates.txt` |
| Network implementation candidates | `build/network-impl-candidates.txt` |
| App package key findings | `build/app-package-key-findings.txt` |
| SRT string resources | `build/srt-app-strings.txt` |
| Offline web endpoint extraction | `build/custom-web-do-unique.txt`, `build/custom-web-do-unique-unfiltered.txt` |
| Host URL lines | `build/host-url-lines.txt` |

## Limitations

- This is static analysis only; no runtime proxy capture or live authentication flow was performed.
- `jadx` completed with eight decompilation errors, but produced usable Java output. Some generated library or obfuscated methods may be incomplete.
- The live server pages loaded from `https://app.srail.or.kr` may contain additional endpoints beyond the bundled offline assets.
- Vendor SDK internals such as H2O SmartBroker, AppIron, RaonSecure OnePass, Firebase, Facebook, Kakao, and Naver are summarized only where statically visible and relevant to the SRT app.
- No attempt was made to bypass authentication, authorization, certificate checks, app integrity checks, payment controls, or server-side business rules.
