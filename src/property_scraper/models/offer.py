from dataclasses import dataclass, asdict, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class Offer:
	portal: str
	source_id: str
	source_url: str

	title: str
	price: Optional[int]
	price_per_m2: int
	area_m2: float
	rooms: int
	floor: Optional[str]

	location_raw: str

	image_url: str

	transaction_type: str  # sale / rent
	property_type: str  # apartment / house / plot
	market_type: str  # primary / secondary

	seller_type: Optional[str]  # agency / private / developer

	scraped_at: str = field(
		default_factory=lambda: datetime
		.now(timezone.utc)
		.strftime("%Y-%m-%dT%H:%M:%SZ"))

	def to_dict(self) -> dict:
		return asdict(self)
