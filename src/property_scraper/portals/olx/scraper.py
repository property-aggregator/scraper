import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional

from property_scraper.domain import Offer
from property_scraper.net import FetchError
from property_scraper.portals.base import ListingParseError, ListingScraper, ScrapeReport
from property_scraper.portals.olx import urls
from property_scraper.portals.olx.parser import ApiPage, parse_api_page
from property_scraper.portals.olx.urls import AreaRange

logger = logging.getLogger(__name__)

# OLX serves at most ~1000 offers per query, so a full scrape splits the search into area ranges
# small enough to fit. Ranges with more offers are halved (down to 0.01 m²).
MAX_OFFERS_PER_QUERY = 1000
# Starting ranges (m²), denser where most apartments are, so fewer ranges need halving.
INITIAL_AREA_BOUNDS = (0, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 120, 150, 10_000)
# Part of the ads are Otodom cross-listings (skipped), so fewer offers than the portal reports is expected.
LOW_COVERAGE_RATIO = 0.4
# Safety net: ~30k offers need well under 100 splits. Far more means the area filter is not applied
# (e.g. OLX renamed the parameter) and halving would go on down to 0.01 m² on every range.
MAX_SPLITS = 500
# Safety net against a `links.next` loop: 1000 offers / 50 per page = 20 pages (+ promoted overlap).
MAX_PAGES_PER_RANGE = 30


def initial_ranges() -> list[AreaRange]:
	ranges = [AreaRange.m2(INITIAL_AREA_BOUNDS[0], INITIAL_AREA_BOUNDS[1])]
	for low, high in zip(INITIAL_AREA_BOUNDS[1:], INITIAL_AREA_BOUNDS[2:]):
		ranges.append(AreaRange(round(low * 100) + 1, round(high * 100)))
	return ranges


def too_many(page: ApiPage) -> bool:
	if page.count is None:
		return False
	# total_elements is capped at 1000, so there it means "at least 1000"
	return page.count > MAX_OFFERS_PER_QUERY if page.count_exact else page.count >= MAX_OFFERS_PER_QUERY


@dataclass
class _FullScrapeRun:
	report: ScrapeReport
	seen_ids: set[str] = field(default_factory=set)
	portal_count: int = 0  # sum of the portal's counts for the scraped ranges
	splits: int = 0
	failed: bool = False


class OlxScraper(ListingScraper):
	"""Reads offers from OLX's JSON offers API (the one its own frontend uses)."""

	def scrape_first_page(self) -> list[Offer]:
		offers = self._load(urls.offers_api_url(self.spec)).offers
		logger.info("[%s] First page: %s offers", self.spec, len(offers))
		return offers

	def scrape_all(self, report: ScrapeReport) -> Iterator[list[Offer]]:
		run = _FullScrapeRun(report)

		for area in initial_ranges():
			if run.splits > MAX_SPLITS:
				break
			yield from self._scrape_range(run, area)

		logger.info("[%s] Scraped %s offers, portal reports %s", self.spec, report.offers, run.portal_count)
		if run.portal_count and report.offers < run.portal_count * LOW_COVERAGE_RATIO:
			logger.warning("[%s] Scraped only %s of %s offers", self.spec, report.offers, run.portal_count)
		report.completed = not run.failed

	def _scrape_range(self, run: _FullScrapeRun, area: AreaRange) -> Iterator[list[Offer]]:
		page = self._load_or_fail(run, area, urls.offers_api_url(self.spec, area))
		if page is None or page.count == 0:
			return

		if too_many(page):
			if run.splits >= MAX_SPLITS:
				if run.splits == MAX_SPLITS:
					message = f"more than {MAX_SPLITS} area splits, is the area filter still applied? Aborting"
					logger.error("[%s] %s", self.spec, message)
					run.report.errors.append(message)
					run.failed = True
				run.splits += 1
				return
			if area.can_split():
				run.splits += 1
				low, high = area.halves()
				logger.info("[%s] %s: %s offers, splitting into %s and %s", self.spec, area, page.count, low, high)
				yield from self._scrape_range(run, low)
				yield from self._scrape_range(run, high)
				return
			logger.warning("[%s] %s: %s offers, only the first %s are reachable",
				self.spec, area, page.count, MAX_OFFERS_PER_QUERY)
			run.failed = True

		run.portal_count += page.count or 0
		yield from self._scrape_range_pages(run, area, page)

	def _scrape_range_pages(self, run: _FullScrapeRun, area: AreaRange, page: ApiPage) -> Iterator[list[Offer]]:
		for number in range(1, MAX_PAGES_PER_RANGE + 1):
			offers = [offer for offer in page.offers if offer.source_id not in run.seen_ids]
			run.seen_ids.update(offer.source_id for offer in offers)
			run.report.pages += 1
			if offers:
				run.report.offers += len(offers)
				yield offers

			if not page.next_url:
				return
			if number == MAX_PAGES_PER_RANGE:
				self._fail(run, f"{area}: more than {MAX_PAGES_PER_RANGE} pages, stopping")
				return
			if not urls.is_api_url(page.next_url):
				self._fail(run, f"{area}: unexpected next page link {page.next_url!r}")
				return

			page = self._load_or_fail(run, area, page.next_url)
			if page is None:
				return

	def _load_or_fail(self, run: _FullScrapeRun, area: AreaRange, url: str) -> Optional[ApiPage]:
		try:
			return self._load(url)
		except (FetchError, ListingParseError) as e:
			self._fail(run, f"{area}: {e}")
			return None

	def _fail(self, run: _FullScrapeRun, message: str) -> None:
		logger.error("[%s] %s", self.spec, message)
		run.report.errors.append(message)
		run.failed = True

	def _load(self, url: str) -> ApiPage:
		result = self.http.get(url)
		if not result.ok:
			raise FetchError(result)
		return parse_api_page(result.content, self.spec)
