import json
import logging
import re
from html import unescape
from typing import Generator, List, Optional

from property_scraper.models.offer import Offer
from property_scraper.scrapers.base_scraper import FETCH_ERRORS, BaseScraper, ScrapeResult
from property_scraper.utils.parsers import extract_source_id

logger = logging.getLogger(__name__)

ROOMS_PATTERN = re.compile(r"(\d+)\s*[- ]?pok", re.IGNORECASE)
FLOOR_PATTERN = re.compile(r"(\d+)\s*piętr", re.IGNORECASE)
PROVINCES = (
	"slaskie", "mazowieckie", "dolnoslaskie", "wielkopolskie", "pomorskie", "zachodniopomorskie",
	"malopolskie", "lodzkie", "kujawsko-pomorskie", "lubelskie", "warminsko-mazurskie",
	"podkarpackie", "lubuskie", "swietokrzyskie", "podlaskie", "opolskie")
MAX_PRICE = 50_000_000
MAX_OFFERS_PER_QUERY = 1000  # OLX pokazuje max 25 stron (~1000 ofert) na zapytanie
ROOMS_BY_PARAM = {"one": 1, "two": 2, "three": 3, "four": 4}


class OlxScraper(BaseScraper):
	PORTAL_NAME = "olx"
	BASE_URL = "https://www.olx.pl"

	TRANSACTION_TYPE = "sale"
	PROPERTY_TYPE = "apartment"
	MARKET_TYPE = "secondary"

	def get_listing_url(self, page: int) -> str:
		base = f"{self.BASE_URL}/nieruchomosci/mieszkania/sprzedaz/"
		params = "search%5Border%5D=created_at:desc&search%5Bfilter_enum_market%5D%5B0%5D=secondary"

		if page == 1:
			return f"{base}?{params}"
		return f"{base}?page={page}&{params}"

	def parse_listing_page(
		self,
		html: str,
		page_number: int,
		scrape_type: str
	) -> ScrapeResult:
		listing = self._prerendered_listing(html)
		state_page = listing.get("pageNumber")
		current_page = state_page + 1 if isinstance(state_page, int) else None
		if current_page is not None and current_page != page_number:
			logger.warning(
				"Requested page %s but portal returned page %s, treating as end of results",
				page_number, current_page)
			return ScrapeResult(offers=[], has_next_page=False, page_number=page_number)

		ads = self._ads_by_source_id(listing)
		offers = []
		seen_ids = set()

		for position, chunk in enumerate(html.split('data-testid="l-card"')[1:], start=1):
			try:
				offer = self._parse_offer(chunk, ads)
			except Exception as e:
				logger.exception("Error parsing OLX card %s on page %s: %s", position, page_number, e)
				continue

			if offer and offer.source_id not in seen_ids:
				seen_ids.add(offer.source_id)
				offers.append(offer)

		total_pages = listing.get("totalPages")
		if isinstance(state_page, int) and isinstance(total_pages, int):
			# Przycisk "Dalej" bywa nie wyrenderowany w HTML mimo kolejnych stron.
			has_next_page = state_page + 1 < total_pages
		else:
			has_next_page = 'data-testid="pagination-forward"' in html
		return ScrapeResult(offers=offers, has_next_page=has_next_page, page_number=page_number)

	def _parse_offer(self, chunk: str, ads: Optional[dict] = None) -> Optional[Offer]:
		url = self._first_match(chunk, r'href="((?:https://www\.olx\.pl)?/d/oferta/[^"]+)"')
		if not url:
			return None

		source_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"
		source_id = extract_source_id(source_url)
		if not source_id:
			logger.warning("Skipping OLX offer without source id: %s", source_url)
			return None

		title = self._clean_text(self._first_match(chunk, r"<h4[^>]*>(.*?)</h4>", flags=re.DOTALL))
		price_text = self._clean_text(
			self._first_match(chunk, r'data-testid="ad-price"[^>]*>\s*(.*?)\s*(?:<span|</p>)', flags=re.DOTALL))
		location_date = self._clean_text(
			self._first_match(chunk, r'data-testid="location-date"[^>]*>(.*?)</p>', flags=re.DOTALL))
		params_text = self._clean_text(
			self._first_match(
				chunk,
				r'data-testid="blueprint-card-param-icon"[^>]*>(?:(?!</svg>).)*</svg>\s*(.*?)\s*</span>',
				flags=re.DOTALL))

		price = self._parse_int(price_text)
		area_m2 = self._parse_decimal(self._first_match(params_text, r"([\d\s.,]+)\s*m²"))
		price_per_m2 = self._parse_int(self._first_match(params_text, r"([\d\s.,]+)\s*zł/m²"))
		rooms = self._parse_rooms(title)
		floor = self._parse_floor(title)
		city, district = self._parse_city_district(location_date)
		image_url = self._image_url(chunk)
		province = None
		seller_type = None

		ad = (ads or {}).get(source_id)
		if ad:
			params = {p.get("key"): p.get("normalizedValue") for p in ad.get("params") or []}
			location = ad.get("location") or {}
			area_m2 = self._parse_decimal(params.get("m")) or area_m2
			price_per_m2 = self._parse_int(params.get("price_per_m")) or price_per_m2
			rooms = self._rooms_from_param(params.get("rooms")) or rooms
			floor = self._floor_from_param(params.get("floor_select")) or floor
			city = location.get("cityName") or city
			district = location.get("districtName") or district
			province = location.get("regionName")
			seller_type = "agency" if ad.get("isBusiness") else "private"
			photo = (ad.get("photos") or [None])[0]
			if photo:
				image_url = photo.split(";s=")[0]

		return Offer(
			portal=self.PORTAL_NAME,
			source_id=source_id,
			source_url=source_url,
			title=title or "",
			price=price,
			price_per_m2=price_per_m2,
			area_m2=area_m2,
			rooms=rooms,
			floor=floor,
			street=None,
			district=district,
			city=city,
			province=province,
			image_url=image_url,
			transaction_type=self.TRANSACTION_TYPE,
			property_type=self.PROPERTY_TYPE,
			market_type=self.MARKET_TYPE,
			seller_type=seller_type)

	def scrape_all_pages(self) -> Generator[List[Offer], None, None]:
		"""OLX pokazuje max 25 stron na zapytanie, wiec dzielimy je na wojewodztwa i przedzialy cen."""
		logger.info(f"[{self.PORTAL_NAME}] Starting full scrape")

		self.completed = False
		self._failed = False
		self._requested = False
		self._seen_ids = set()
		total_offers = 0

		for province in PROVINCES:
			scraped = 0
			self._province_total = None
			for offers in self._scrape_segment(province, 0, MAX_PRICE):
				scraped += len(offers)
				yield offers

			total_offers += scraped
			logger.info(
				f"[{self.PORTAL_NAME}] {province}: {scraped} offers (portal reports {self._province_total})")
			# Czesc ogloszen to linki do Otodom (pomijane), wiec roznica jest oczekiwana.
			if self._province_total and scraped < self._province_total * 0.4:
				logger.warning(
					f"[{self.PORTAL_NAME}] {province}: scraped only {scraped} of {self._province_total} offers")

		self.completed = not self._failed
		logger.info(f"[{self.PORTAL_NAME}] Full scrape finished: {total_offers} total offers")

	def _segment_url(self, province: str, price_from: int, price_to: int, page: int) -> str:
		params = (
			"search%5Border%5D=created_at:desc&search%5Bfilter_enum_market%5D%5B0%5D=secondary"
			f"&search%5Bfilter_float_price%3Afrom%5D={price_from}"
			f"&search%5Bfilter_float_price%3Ato%5D={price_to}")
		page_param = f"page={page}&" if page > 1 else ""
		return f"{self.BASE_URL}/nieruchomosci/mieszkania/sprzedaz/{province}/?{page_param}{params}"

	def _fetch_segment_page(self, province: str, price_from: int, price_to: int, page: int) -> Optional[str]:
		if self._requested:
			self._delay()
		self._requested = True

		try:
			return self._fetch_page(self._segment_url(province, price_from, price_to, page))
		except FETCH_ERRORS as e:
			logger.error(
				f"[{self.PORTAL_NAME}] {province} {price_from}-{price_to} page {page} failed: {e}")
			self._failed = True
			return None

	def _scrape_segment(
		self,
		province: str,
		price_from: int,
		price_to: int
	) -> Generator[List[Offer], None, None]:
		html = self._fetch_segment_page(province, price_from, price_to, 1)
		if html is None:
			return

		# totalElements jest ucinane do 1000, wiec wartosc rowna limitowi oznacza "co najmniej tyle".
		total = self._prerendered_listing(html).get("totalElements")
		if price_from == 0 and price_to == MAX_PRICE:
			self._province_total = total
		if total == 0:
			return

		if isinstance(total, int) and total >= MAX_OFFERS_PER_QUERY:
			if price_from < price_to:
				middle = (price_from + price_to) // 2
				yield from self._scrape_segment(province, price_from, middle)
				yield from self._scrape_segment(province, middle + 1, price_to)
				return
			# Nie da sie podzielic ceną dalej - zbieramy tylko to, co widac w 25 stronach.
			logger.warning(
				f"[{self.PORTAL_NAME}] {province} price {price_from}: {total}+ offers, only the first pages are reachable")
			self._failed = True

		yield from self._scrape_segment_pages(province, price_from, price_to, html)

	def _scrape_segment_pages(
		self,
		province: str,
		price_from: int,
		price_to: int,
		html: str
	) -> Generator[List[Offer], None, None]:
		page = 1
		while True:
			result = self.parse_listing_page(html, page_number=page, scrape_type="FULL")
			if not result.offers:
				return

			offers = [offer for offer in result.offers if offer.source_id not in self._seen_ids]
			self._seen_ids.update(offer.source_id for offer in offers)
			if offers:
				yield offers

			if not result.has_next_page:
				return

			page += 1
			html = self._fetch_segment_page(province, price_from, price_to, page)
			if html is None:
				return

	@staticmethod
	def _first_match(text: Optional[str], pattern: str, flags: int = 0) -> Optional[str]:
		if not text:
			return None
		match = re.search(pattern, text, flags)
		return match.group(1) if match else None

	@staticmethod
	def _clean_text(value: Optional[str]) -> Optional[str]:
		if value is None:
			return None
		value = re.sub(r"<[^>]+>", " ", value)
		return " ".join(unescape(value).split())

	@staticmethod
	def _parse_int(value: Optional[str]) -> Optional[int]:
		if not value:
			return None
		normalized = value.replace("\xa0", " ")
		match = re.search(r"(\d[\d\s.,]*)", normalized)
		if not match:
			return None
		number = match.group(1).replace(" ", "").replace(",", ".")
		try:
			return round(float(number))
		except ValueError:
			return None

	@staticmethod
	def _parse_decimal(value: Optional[str]) -> Optional[float]:
		if not value:
			return None
		number = value.replace(" ", "").replace(",", ".")
		try:
			return float(number)
		except ValueError:
			return None

	@staticmethod
	def _parse_rooms(title: Optional[str]) -> Optional[int]:
		if not title:
			return None
		match = ROOMS_PATTERN.search(title)
		return int(match.group(1)) if match else None

	@staticmethod
	def _parse_floor(title: Optional[str]) -> Optional[str]:
		if not title:
			return None
		lower = title.lower()
		if "parter" in lower:
			return "parter"
		if "suterena" in lower:
			return "suterena"
		if "poddasz" in lower:
			return "poddasze"
		match = FLOOR_PATTERN.search(lower)
		return match.group(1) if match else None

	@staticmethod
	def _parse_city_district(location_date: Optional[str]) -> tuple[Optional[str], Optional[str]]:
		if not location_date:
			return None, None
		location = location_date.split(" - ", 1)[0].strip()
		if ", " in location:
			city, district = location.split(", ", 1)
			return city.strip() or None, district.strip() or None
		return location or None, None

	@staticmethod
	def _prerendered_listing(html: str) -> dict:
		marker = "__PRERENDERED_STATE__="
		start = html.find(marker)
		if start == -1:
			return {}
		try:
			raw, _ = json.JSONDecoder().raw_decode(html[start + len(marker):].lstrip())
			return json.loads(raw)["listing"]["listing"]
		except (ValueError, KeyError, TypeError):
			logger.warning("Could not read OLX prerendered state, falling back to HTML only")
			return {}

	@staticmethod
	def _ads_by_source_id(listing: dict) -> dict:
		return {
			source_id: ad for ad in listing.get("ads") or []
			if (source_id := extract_source_id(ad.get("url") or ""))}

	@staticmethod
	def _rooms_from_param(value: Optional[str]) -> Optional[int]:
		return ROOMS_BY_PARAM.get(value) if value else None

	@staticmethod
	def _floor_from_param(value: Optional[str]) -> Optional[str]:
		if not value or not value.startswith("floor_"):
			return None
		level = value[len("floor_"):]
		special = {"-1": "suterena", "0": "parter", "17": "poddasze"}
		return special.get(level, level)

	def _image_url(self, chunk: str) -> Optional[str]:
		src = self._first_match(chunk, r'<img[^>]+src="([^"]+)"')
		return src if src and src.startswith("http") else None
