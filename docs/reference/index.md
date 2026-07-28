# API 레퍼런스

`srt_mobile_api` 의 `__all__` 이 내보내는 이름이 공개면이다. 아래 쪽들은 그
이름을 정의한 모듈별로 나뉘어 있고, 내용은 소스의 docstring 을 그대로 렌더링한
것이다 — 이 사이트가 따로 관리하는 설명은 없다.

모듈 쪽은 모듈을 통째로 싣는다. 그래서 `__all__` 에 없는 모듈 상수도 여기서 볼
수 있다. 최상위에서 `from srt_mobile_api import ...` 로 꺼낼 수 있는 것만이
안정된 이름이고, 나머지는 모듈 경로로 가져다 쓰는 만큼 바뀔 수 있다.

| 모듈 | 무엇이 들어 있나 |
| --- | --- |
| [client](client.md) | `SrtClient`. 로그인·조회·상태변경 메서드 전부 |
| [config](config.md) | `SrtConfig` — 호스트, 앱 버전, 기기 값 |
| [consent](consent.md) | `MutationConsent`, `MutationCategory`, `require_mutation_consent` |
| [errors](errors.md) | 예외 계층과 서버 코드 매핑 |
| [models](models.md) | 요청·응답 타입과 `MutationPreview` |

docstring 이 없는 dataclass 도 필드를 보여 주려고 함께 싣는다. 설명이 붙어 있지
않다는 것은 그 타입이 서버 응답을 그대로 담는 그릇이라는 뜻이다.
