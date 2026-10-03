from typing import Optional
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Offer(BaseModel):
	model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

	portal: str
	source_id: str
	source_url: str

	title: str
	price: Optional[int]
	price_per_m2: Optional[int]
	area_m2: Optional[float]
	rooms: Optional[int]
	floor: Optional[str] = None

	street: Optional[str] = None
	district: Optional[str] = None
	city: Optional[str] = None
	province: Optional[str] = None

	image_url: Optional[str] = None

	transaction_type: str  # sale / rent
	property_type: str  # apartment / house / plot
	market_type: str  # primary / secondary

	seller_type: Optional[str] = None  # agency / private / developer

	scraped_at: str = Field(
		default_factory=lambda: datetime
		.now(timezone.utc)
		.strftime("%Y-%m-%dT%H:%M:%SZ"))

	def to_dict(self) -> dict:
		return self.model_dump(by_alias=True)

	def is_publishable(self) -> bool:
		# if not self.source_id or not self.source_url or not self.title:
		# 	return False
		# if self.price is None or self.price <= 0:
		# 	return False
		# if self.area_m2 is None or self.area_m2 <= 0:
		# 	return False
		# if self.rooms is None or self.rooms <= 0:
		# 	return False
		# if not self.portal or not self.transaction_type or not self.property_type:
		# 	return False
		return True
