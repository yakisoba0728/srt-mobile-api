# docs/analysis/

SRT 앱 `kr.co.srail.newapp` v2.0.41(versionCode 150)을 정적 분석한 산출물입니다.
이 패키지의 라우트·필드·응답 모양이 어디서 왔는지의 근거가 여기 있습니다.

문서는 영어로 쓰여 있고 작성 시점의 형태 그대로 보존합니다. 패키지를 쓰는 데
읽어야 하는 것은 아니고, 어떤 주장의 출처를 확인할 때 찾아보면 됩니다.

| 문서 | 내용 |
| --- | --- |
| [srt-app-api-library-spec-2026-07-09.md](srt-app-api-library-spec-2026-07-09.md) | 라이브러리 명세. WebView API 전반과 `app.srail.or.kr` 호스트 기준의 요청·응답 정리 |
| [full-api-analysis-2026-07-20.md](full-api-analysis-2026-07-20.md) | 전체 API 분석. 앱 버전과 패키지 기준의 종합 정리 |
| [cross-validation-2026-07-21.md](cross-validation-2026-07-21.md) | 대조 보고서. `srtgo` 참조 구현과 이쪽의 독립 디컴파일 결과, 그리고 `src/` 를 서로 맞춰 본 기록 |
| [ref-srtgo_plus.md](ref-srtgo_plus.md) | 선행 클라이언트 `srtgo_plus` 의 요청·응답 모양 분석. 읽기만 한 외부 저장소 분석이며 코드를 실행하거나 네트워크를 쓰지 않았습니다. 루트 `NOTICE` 가 이 문서의 결론을 인용합니다 |

이 표가 빠짐없는지는 `tests/test_docs_site.py` 가 확인합니다. 문서를 더하면 여기
한 줄을 더해야 합니다.
