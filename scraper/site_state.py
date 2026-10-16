"""The one shape every adapter must return. Pure data, no browser objects."""
from dataclasses import dataclass, asdict, field

@dataclass
class SiteState:
    seats: int | None = None
    available: bool = False
    price: str | None = None
    title: str | None = None
    blocked: bool = False          # login wall / captcha / 429 -> someone must look
    block_reason: str | None = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
