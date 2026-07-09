from dataclasses import dataclass


DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36 "
    "SRT-APP-Android V.2.0.41"
)


@dataclass(frozen=True)
class SrtConfig:
    base_url: str = "https://app.srail.or.kr"
    netfunnel_url: str = "https://nf.letskorail.com:443"
    user_agent: str = DEFAULT_UA
    device_key: str = "0123456789ABCDEF"
    timeout: float = 20.0
    live_env_var: str = "SRT_MOBILE_API_LIVE"
