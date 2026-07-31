"""접속 설정 — :class:`SrtConfig` 하나와 그것이 고정하는 두 오리진.

기본값은 앱 v2.0.41 이 보내는 값이라 그대로 쓰면 됩니다. ``base_url`` 과
``netfunnel_url`` 은 :data:`APP_ORIGIN` 과 :data:`NETFUNNEL_ORIGIN` 이어야 하고,
:mod:`srt_mobile_api.safety` 의 경로 검사가 그 표준형을 전제합니다.
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

    기본값 그대로 쓰면 됩니다. ``user_agent`` 끝의 ``SRT-APP-Android V.2.0.41`` 은
    서버가 앱 요청으로 인정하는 표식입니다 (SRWebActivity.java:2645).

    ``base_url`` / ``netfunnel_url`` 은 각각 ``https://app.srail.or.kr`` /
    ``https://nf.letskorail.com`` 이어야 합니다. 스킴·호스트·포트가 다르거나
    경로·질의·프래그먼트가 붙으면 :class:`ValueError` 입니다.
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
