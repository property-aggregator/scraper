from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel

from property_scraper.domain.enums import MarketType, PropertyType, SellerType, TransactionType


def _utc_now() -> datetime:
	return datetime.now(timezone.utc).replace(microsecond=0)


class Offer(BaseModel):
	"""Offer as published to the backend (OfferMessage contract, camelCase JSON)."""

	model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

	portal: str
	source_id: str
	source_url: str

	title: str
	price: Optional[int] = None
	price_per_m2: Optional[int] = None
	area_m2: Optional[float] = None
	rooms: Optional[int] = None
	floor: Optional[str] = None

	street: Optional[str] = None
	district: Optional[str] = None
	city: Optional[str] = None
	province: Optional[str] = None

	image_url: Optional[str] = None

	transaction_type: TransactionType
	property_type: PropertyType
	market_type: MarketType
	seller_type: Optional[SellerType] = None

	scraped_at: datetime = Field(default_factory=_utc_now)

	@field_serializer("scraped_at")
	def _serialize_scraped_at(self, value: datetime) -> str:
		return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

	def to_dict(self) -> dict:
		return self.model_dump(mode="json", by_alias=True)
