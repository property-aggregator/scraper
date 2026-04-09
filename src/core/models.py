from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .enums import OfferStatus


@dataclass
class PropertyItem:
    portal: str
    external_id: str
    title: str
    url: str
    price: float | None
    currency: str | None
    city: str | None
    region: str | None
    rooms: float | None
    area_m2: float | None
    status: OfferStatus = OfferStatus.ACTIVE
    scraped_at: str = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

