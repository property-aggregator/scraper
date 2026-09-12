import logging
from typing import Optional

from bs4 import BeautifulSoup, Tag

from property_scraper.scrapers.base_scraper import BaseScraper, ScrapeResult
from property_scraper.models.offer import Offer
from property_scraper.utils.parsers import (
	parse_price,
	parse_area,
	parse_rooms,
	extract_source_id,
	clean_text)

logger = logging.getLogger(__name__)


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
		soup: BeautifulSoup,
		page_number: int,
		scrape_type: str
	) -> ScrapeResult:

		offers = []

		# Znajdź listę kart
		cards_list = soup.select_one('ul[data-sentry-component="CardsList"]')

		if not cards_list:
			logger.warning("CardsList not found on page")
			return ScrapeResult(offers=[], has_next_page=False, page_number=page_number)

		# Znajdź wszystkie karty ogłoszeń
		cards = cards_list.select('article[data-sentry-component="AdvertCard"]')

		for position, card in enumerate(cards, start=1):
			try:
				offer = self._parse_card(card, page_number, position, scrape_type)
				if offer:
					offers.append(offer)
			except Exception as e:
				logger.error(f"Error parsing card {position} on page {page_number}: {e}")

		# Sprawdź czy jest następna strona
		has_next_page = self._check_next_page(soup)

		return ScrapeResult(
			offers=offers,
			has_next_page=has_next_page,
			page_number=page_number)

	def _parse_card(
		self,
		card: Tag,
		page_number: int,
		position: int,
		scrape_type: str
	) -> Optional[Offer]:
		"""Parsuje pojedynczą kartę ogłoszenia."""

		# Link i source_id
		link_el = card.select_one('a[data-cy="listing-item-link"]')
		if not link_el:
			return None

		href = link_el.get("href", "")
		source_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
		source_id = extract_source_id(href)

		if not source_id:
			return None

		# Tytuł
		title_el = card.select_one('[data-cy="listing-item-title"]')
		title = clean_text(title_el.get_text()) if title_el else None

		# Cena główna
		price_el = card.select_one('[data-sentry-element="MainPrice"]')
		price_text = price_el.get_text() if price_el else None
		price = parse_price(price_text)

		# Cena za m²
		price_wrapper = card.select_one('[data-sentry-component="CustomizedPrice"]')
		price_per_m2 = None
		if price_wrapper:
			spans = price_wrapper.select("span")
			if len(spans) >= 2:
				price_per_m2 = parse_price(spans[1].get_text())

		# Lokalizacja
		location_el = card.select_one('[data-sentry-component="Address"]')
		location_raw = clean_text(location_el.get_text()) if location_el else ""

		# Pierwsze zdjęcie
		image_el = card.select_one('img[data-cy="listing-item-image-source"]')
		image_url = image_el.get("src") if image_el else None

		# Specyfikacje (pokoje, metraż, piętro)
		specs = self._parse_specs(card)

		# Typ sprzedawcy
		seller_type = self._parse_seller_type(card)

		return Offer(
			portal=self.PORTAL_NAME,
			source_id=source_id,
			source_url=source_url,
			title=title or "",
			price=price,
			price_per_m2=price_per_m2,
			area_m2=specs.get("area"),
			rooms=specs.get("rooms"),
			floor=specs.get("floor"),
			location_raw=location_raw,
			image_url=image_url,
			transaction_type=self.TRANSACTION_TYPE,
			property_type=self.PROPERTY_TYPE,
			market_type=self.MARKET_TYPE,
			seller_type=seller_type)

	def _parse_specs(self, card: Tag) -> dict:
		"""Parsuje specyfikacje (pokoje, metraż, piętro) z karty."""
		specs = {
			"rooms": None,
			"area": None,
			"floor": None
		}

		# Znajdź listę specyfikacji
		dl = card.select_one('[data-sentry-component="DescriptionList"]')
		if not dl:
			return specs

		# Parsuj pary dt/dd
		dts = dl.select("dt")
		dds = dl.select("dd")

		for dt, dd in zip(dts, dds):
			label = clean_text(dt.get_text()).lower() if dt else ""
			value_el = dd.select_one("span")
			value = clean_text(value_el.get_text()) if value_el else ""

			if "pokoi" in label or "pokoje" in label:
				specs["rooms"] = parse_rooms(value)
			elif "metr" in label or "m²" in value:
				specs["area"] = parse_area(value)
			elif "piętro" in label or "parter" in value.lower():
				specs["floor"] = value

		return specs

	def _parse_seller_type(self, card: Tag) -> Optional[str]:
		"""Parsuje typ sprzedawcy."""
		seller_info = card.select_one('[data-sentry-component="SellerInfo"]')
		if not seller_info:
			return None

		owner_type_el = seller_info.select_one('[data-sentry-component="ConnectedOwnerType"]')
		if owner_type_el:
			text = clean_text(owner_type_el.get_text()).lower()
			if "biuro" in text:
				return "agency"
			elif "oferta" in text:
				return "private"
			elif "deweloper" in text:
				return "developer"

		return None

	def _check_next_page(self, soup: BeautifulSoup) -> bool:
		"""Sprawdza czy istnieje następna strona."""
		selectors = [
			'[data-cy="search-list-pagination"]',
			'[data-cy="pagination"]',
			'[aria-label="następna strona"]',
			'[aria-label="Next page"]',
			'a[aria-label*="następna"]',
			'a[aria-label*="next"]',
			'button[aria-label*="następna"]',
			'button[aria-label*="next"]',
			'a[rel="next"]',
		]

		for selector in selectors:
			element = soup.select_one(selector)
			if element:
				return True

		pagination = soup.select_one('[data-cy="search-list-pagination"]')
		if pagination:
			text = pagination.get_text(" ", strip=True).lower()
			if "następna" in text or "next" in text or "dalej" in text:
				return True

		cards = soup.select('article[data-sentry-component="AdvertCard"]')
		return len(cards) >= 20
