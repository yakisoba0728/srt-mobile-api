EXCLUDED_API_DOMAINS = frozenset(
    {
        "reservation",
        "netfunnel-act-19",
        "ard-payment-entry",
        "payment",
        "refund",
        "cancellation",
        "ata-detail",
        "native-bridge",
        "external-seatmap",
    }
)

SAFETY_STATEMENTS = (
    "No user credentials, cookies, NetFunnel keys, raw response bodies, or payment tokens are stored here.",
    "Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or card-shaped values in the repository.",
    "Library rule: do not implement real card approval in the core client.",
)
