# Next Session Handoff

분석 대상은 `srt.apk`이며, 이번 세션에서는 정적 분석만 수행했다. 운영 서버 요청, 인증 우회, 결제 우회, 트래픽 재현은 수행하지 않았다.

## 현재 산출물

- 상세 분석 문서: `docs/analysis/srt-apk-deep-dive.md`
- 초기 분석 문서: `docs/analysis/srt-apk-analysis.md`
- 실행 계획 기록: `docs/superpowers/plans/2026-07-09-srt-apk-analysis.md`
- 로컬 추출물: `build/`
- 원본 APK: `srt.apk`

`build/`와 `srt.apk`는 크고 민감할 수 있어 git에는 포함하지 않았다. 로컬 작업공간에는 남아 있으므로 다음 세션에서 바로 참조하면 된다.

## 다음 세션 권장 시작점

1. `docs/analysis/srt-apk-deep-dive.md`의 `18. 한계와 추가 확인이 필요한 항목`을 먼저 읽는다.
2. 최신 서버 렌더링 web asset을 확보할 수 있으면 APK bundled offline asset과 diff한다.
3. 허가된 테스트 계정/환경이 준비되면 실제 WebView request/response를 캡처해 정적 schema와 대조한다.
4. 우선 검증할 항목은 FIDO callback `resultCode`, H2O push port 전달 불일치, `rsvForm`/`seatSearchForm`의 서버 렌더링 hidden input 전체다.
5. 보안 관찰은 별도 취약점 보고서로 분리하기 전, 런타임 재현 가능성부터 확인한다.

## 핵심 파일

- Manifest: `build/apktool/AndroidManifest.xml`
- WebView native: `build/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java`
- FCM/H2O: `build/jadx/sources/kr/co/srail/newapp/push/SrtFirebaseMessagingService.java`, `build/jadx/sources/b6/a.java`
- Bridge JS: `build/jadx/resources/assets/offline/js/common/bridge.js`
- 예약 초기화: `build/jadx/resources/assets/offline/js/ara/ara0101v.js`
- 예약 검색/예매: `build/jadx/resources/assets/offline/js/ara/ara1001l.js`
- 오프라인 승차권: `build/jadx/resources/assets/offline/sub/ticketList.html`, `build/jadx/resources/assets/offline/sub/ticket_view.html`

## 검증 메모

이번 문서 완료 전 수행한 로컬 검증:

- `wc -l docs/analysis/srt-apk-deep-dive.md` 결과: `1539`
- endpoint/action 대표 키워드 31개가 문서에 모두 존재함을 `rg`로 확인
- 미완성 자리표시 문구는 남기지 않음
