import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Iterator
from urllib.parse import urlsplit

from property_scraper.domain import Availability, Offer, SearchSpec
from property_scraper.net import FetchError, FetchResult, HttpClient

logger = logging.getLogger(__name__)


class ListingParseError(Exception):
	"""The portal's JSON data could not be read from a fetched page (layout change, captcha, ...)."""


@dataclass(frozen=True)
class ListingPage:
	offers: list[Offer]
	has_next_page: bool
	# The portal served something other than the requested page (e.g. a default page past the end)
	unexpected_page: bool = False


@dataclass
class ScrapeReport:
	"""Filled in by a scraper during a full scrape; read by the job afterwards."""

	spec: SearchSpec
	offers: int = 0
	pages: int = 0
	completed: bool = False  # True only when the scrape reached the last page without errors
	errors: list[str] = field(default_factory=list)


class ListingScraper(ABC):
	def __init__(self, http: HttpClient, spec: SearchSpec):
		self.http = http
		self.spec = spec

	@abstractmethod
	def scrape_first_page(self) -> list[Offer]:
		...

	@abstractmethod
	def scrape_all(self, report: ScrapeReport) -> Iterator[list[Offer]]:
		"""Yields batches of offers; records progress and errors in `report`."""


class PaginatedScraper(ListingScraper):
	"""Scraper for portals with plain page=N pagination."""

	@abstractmethod
	def fetch_page(self, page: int) -> ListingPage:
		"""Fetches and parses one listing page.

		Raises FetchError when the page cannot be fetched, ListingParseError when its JSON cannot be read.
		"""

	def scrape_first_page(self) -> list[Offer]:
		offers = self.fetch_page(1).offers
		logger.info("[%s] First page: %s offers", self.spec, len(offers))
		return offers

	def scrape_all(self, report: ScrapeReport) -> Iterator[list[Offer]]:
		"""Pages through the results until the portal reports no next page.

		A page without offers to publish (e.g. only skipped investment cards, or promoted offers
		already seen on earlier pages) does not end the scrape: only the portal's pagination does.
		"""
		seen_ids: set[str] = set()
		page = 1
		while True:
			try:
				result = self.fetch_page(page)
			except (FetchError, ListingParseError) as e:
				logger.error("[%s] Error on page %s: %s", self.spec, page, e)
				report.errors.append(str(e))
				return

			if result.unexpected_page:
				# Logged by the parser; the page count the portal gave earlier was wrong, stop here
				report.errors.append(f"page {page}: portal served an unexpected page")
				return

			report.pages += 1
			# Promoted offers are repeated on later pages
			offers = [offer for offer in result.offers if offer.source_id not in seen_ids]
			seen_ids.update(offer.source_id for offer in offers)
			logger.info("[%s] Page %s: %s offers (%s new)", self.spec, page, len(result.offers), len(offers))
			if offers:
				report.offers += len(offers)
				yield offers

			if not result.has_next_page:
				logger.info("[%s] No more pages after %s", self.spec, page)
				report.completed = True
				return
			page += 1


class Portal(ABC):
	name: ClassVar[str]
	domains: ClassVar[tuple[str, ...]]

	@abstractmethod
	def supports(self, spec: SearchSpec) -> bool:
		...

	@abstractmethod
	def create_scraper(self, http: HttpClient, spec: SearchSpec) -> ListingScraper:
		...

	@abstractmethod
	def is_offer_url(self, url: str) -> bool:
		"""True when the URL points at an offer page (not a listing or the home page)."""

	@abstractmethod
	def availability_from_page(self, result: FetchResult) -> Availability:
		"""Reads availability from an offer page fetched with HTTP 200."""

	def owns_url(self, url: str) -> bool:
		parts = urlsplit(url)
		host = (parts.hostname or "").lower()
		return parts.scheme in ("http", "https") and any(
			host == domain or host.endswith(f".{domain}") for domain in self.domains)
