from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from property_scraper.domain import Availability


class _Message(BaseModel):
	model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

	def to_json(self) -> bytes:
		return self.model_dump_json(by_alias=True).encode("utf-8")


class ExpirationCheckRequest(_Message):
	"""backend -> scraper (OfferExpirationCheckRequest)."""

	property_id: UUID
	portal: str
	source_url: str


class ExpirationCheckResponse(_Message):
	"""scraper -> backend (OfferExpirationCheckResponse)."""

	property_id: UUID
	status: Availability
	http_status: Optional[int] = None


class ScrapeFinishedEvent(_Message):
	event: str = "scrape_finished"
	portal: str
	scrape_type: str
	source: str
	total_offers: int
	completed: bool
