from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36 "
    "SRT-APP-Android V.2.0.41"
)
APP_ORIGIN = "https://app.srail.or.kr"
NETFUNNEL_ORIGIN = "https://nf.letskorail.com:443"


@dataclass(frozen=True)
class SrtConfig:
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
