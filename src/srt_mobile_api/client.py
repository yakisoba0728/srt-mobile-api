from __future__ import annotations

from dataclasses import dataclass, field

from .config import SrtConfig


@dataclass(frozen=True, slots=True)
class SrtClient:
    config: SrtConfig = field(default_factory=SrtConfig)
