import json
import logging
import re
from typing import Optional

from property_scraper.scrapers.base_scraper import BaseScraper, ScrapeResult
from property_scraper.models.offer import Offer
from property_scraper.utils.parsers import extract_source_id

logger = logging.getLogger(__name__)

NEXT_DATA_PATTERN = re.compile(
	r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
	re.DOTALL)

ROOMS = {
	"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
	"SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10,
}

FLOORS = {
	"CELLAR": "suterena",
	"GROUND": "parter",
	"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5",
	"SIXTH": "6", "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9", "TENTH": "10",
	"ABOVE_TENTH": ">10",
}


class OtodomScraper(BaseScraper):
	PORTAL_NAME = "otodom"
	BASE_URL = "https://www.otodom.pl"

	TRANSACTION_TYPE = "sale"
	PROPERTY_TYPE = "apartment"
	MARKET_TYPE = "secondary"

	def get_listing_url(self, page: int) -> str:
		base = f"{self.BASE_URL}/pl/wyniki/sprzedaz/mieszkanie,rynek-wtorny/cala-polska"
		params = "limit=72&ownerTypeSingleSelect=ALL&by=DEFAULT&direction=DESC"

		if page == 1:
			return f"{base}?{params}"
		return f"{base}?{params}&page={page}"

	def parse_listing_page(
		self,
		html: str,
		page_number: int,
		scrape_type: str
	) -> ScrapeResult:

		search_ads = self._extract_search_ads(html)

		if search_ads is None:
			logger.warning(
				"searchAds not found in __NEXT_DATA__ on page %s (%s chars, starts with: %r)",
				page_number, len(html), " ".join(html[:300].split())[:200])
			return ScrapeResult(offers=[], has_next_page=False, page_number=page_number)

		pagination = search_ads.get("pagination") or {}
		current_page = pagination.get("currentPage")

		# Past the last page Otodom ignores the page number and serves a default page
		if current_page is not None and current_page != page_number:
			logger.warning(
				"Requested page %s but portal returned page %s, treating as end of results",
				page_number, current_page)
			return ScrapeResult(offers=[], has_next_page=False, page_number=page_number)

		offers = []
		seen_ids = set()

		for position, item in enumerate(search_ads.get("items") or [], start=1):
			try:
				offer = self._parse_item(item)
			except Exception as e:
				logger.exception(
					f"Error parsing item {position} (slug={item.get('slug')}) on page {page_number}: {e}")
				continue

			if offer and offer.source_id not in seen_ids:
				seen_ids.add(offer.source_id)
				offers.append(offer)

		total_pages = pagination.get("totalPages") or 0

		return ScrapeResult(
			offers=offers,
			has_next_page=page_number < total_pages,
			page_number=page_number)

	def _extract_search_ads(self, html: str) -> Optional[dict]:
		match = NEXT_DATA_PATTERN.search(html)
		if not match:
			return None

		try:
			data = json.loads(match.group(1))
		except json.JSONDecodeError as e:
			logger.error(f"Invalid __NEXT_DATA__ JSON: {e}")
			return None

		return (
			data.get("props", {})
			.get("pageProps", {})
			.get("data", {})
			.get("searchAds"))

	def _parse_item(self, item: dict) -> Optional[Offer]:
		slug = item.get("slug")
		source_id = extract_source_id(slug)

		if not source_id:
			logger.warning("Skipping item without valid slug: id=%s slug=%r", item.get("id"), slug)
			return None

		price_per_m2 = self._money(item.get("pricePerSquareMeter"))
		area = item.get("areaInSquareMeters")
		images = item.get("images") or []

		return Offer(
			portal=self.PORTAL_NAME,
			source_id=source_id,
			source_url=f"{self.BASE_URL}/pl/oferta/{slug}",
			title=item.get("title") or "",
			price=self._money(item.get("totalPrice")),
			price_per_m2=price_per_m2,
			area_m2=float(area) if area is not None else None,
			rooms=ROOMS.get(item.get("roomsNumber")),
			floor=FLOORS.get(item.get("floorNumber")),
			**self._location(item.get("location") or {}),
			image_url=images[0].get("large") if images else None,
			transaction_type=self.TRANSACTION_TYPE,
			property_type=self.PROPERTY_TYPE,
			market_type=self.MARKET_TYPE,
			seller_type=self._seller_type(item))

	@staticmethod
	def _money(money: Optional[dict]) -> Optional[int]:
		value = (money or {}).get("value")
		return round(value) if value is not None else None

	@staticmethod
	def _location(location: dict) -> dict:
		address = location.get("address") or {}
		street = address.get("street") or {}
		levels = (location.get("reverseGeocoding") or {}).get("locations") or []

		street_name = " ".join(
			part for part in (street.get("name"), street.get("number")) if part)
		district = next(
			(loc.get("name") for loc in levels if loc.get("locationLevel") == "district"),
			None)

		return {
			"street": street_name or None,
			"district": district,
			"city": (address.get("city") or {}).get("name"),
			"province": (address.get("province") or {}).get("name"),
		}

	@staticmethod
	def _seller_type(item: dict) -> Optional[str]:
		if item.get("isPrivateOwner"):
			return "private"
		if item.get("developmentId"):
			return "developer"
		if item.get("agency"):
			return "agency"
		return None
