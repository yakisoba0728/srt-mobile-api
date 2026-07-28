"""접속 설정 — :class:`SrtConfig` 하나와 그것이 고정하는 두 오리진.

기본값은 앱 v2.0.41 이 보내는 값이라 그대로 쓰면 된다. 이 모듈이 하는 실제
일은 값을 담는 것보다 오리진을 좁히는 쪽이다. ``base_url`` 과
``netfunnel_url`` 은 :data:`APP_ORIGIN` 과 :data:`NETFUNNEL_ORIGIN` 이어야
하고, 통과한 값은 표준형으로 다시 쓰인다. :mod:`srt_mobile_api.safety` 의
경로 검사가 그 표준형을 전제로 하므로, 이 클라이언트를 임의의 호스트로 돌릴
방법은 없다.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36"
    "SRT-APP-Android V.2.0.41"
)
APP_ORIGIN = "https://app.srail.or.kr"
NETFUNNEL_ORIGIN = "https://nf.letskorail.com:443"


@dataclass(frozen=True)
class SrtConfig:
    """:class:`~srt_mobile_api.client.SrtClient` 의 접속 설정.

    기본값 그대로 쓰면 된다. 전부 앱 v2.0.41 이 쓰는 값이고, 특히
    ``user_agent`` 끝의 ``SRT-APP-Android V.2.0.41`` 은 서버가 앱 요청으로 인정하는
    표식이라 지우면 안 된다.

    **오리진은 고정이다.** ``base_url`` 과 ``netfunnel_url`` 은 각각
    ``https://app.srail.or.kr`` 와 ``https://nf.letskorail.com`` 이어야 한다. 스킴이
    HTTPS 가 아니거나, 호스트가 다르거나, 443 아닌 포트·경로·질의·프래그먼트·
    사용자정보가 붙어 있으면 :class:`ValueError` 다. 통과한 값은 표준형 상수로 다시
    쓰이므로, 프록시나 다른 호스트로 돌려 이 클라이언트를 임의의 서버에 겨눌 수 없다.
    :mod:`~srt_mobile_api.safety` 의 경로 검사가 이 표준형을 전제로 한다.

    ``device_key`` 는 비어 있으면 안 되고 ``timeout`` 은 양수여야 한다.

    ``live_env_var`` 는 라이브 실행을 켜는 환경변수의 **이름**을 적어 둔 것이다.
    바꿔도 게이트가 따라오지 않는다 — :mod:`~srt_mobile_api.live` 는 이 필드가 아니라
    ``SRT_MOBILE_API_LIVE`` 라는 이름을 직접 읽는다.
    """

    base_url: str = APP_ORIGIN
    netfunnel_url: str = NETFUNNEL_ORIGIN
    user_agent: str = DEFAULT_UA
    device_key: str = "0123456789ABCDEF"
    timeout: float = 20.0
    live_env_var: str = "SRT_MOBILE_API_LIVE"

    def __post_init__(self) -> None:
        origins = (
            ("base_url", "app.srail.or.kr", APP_ORIGIN),
            ("netfunnel_url", "nf.letskorail.com", NETFUNNEL_ORIGIN),
        )
        for name, expected_host, canonical in origins:
            parsed = urlsplit(getattr(self, name))
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError(f"{name} must use the canonical SRT HTTPS origin") from exc
            if (
                parsed.scheme != "https"
                or parsed.hostname != expected_host
                or port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
                or bool(parsed.path)
                or bool(parsed.query)
                or bool(parsed.fragment)
            ):
                raise ValueError(f"{name} must use the canonical SRT HTTPS origin")
            object.__setattr__(self, name, canonical)
        if not self.device_key:
            raise ValueError("device_key must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
