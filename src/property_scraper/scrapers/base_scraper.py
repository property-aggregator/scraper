import time
import logging
import random
from abc import ABC, abstractmethod
from typing import List, Generator
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from property_scraper.models.offer import Offer
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
	offers: List[Offer]
	has_next_page: bool
	page_number: int


class BaseScraper(ABC):
	PORTAL_NAME: str = ""
	BASE_URL: str = ""
	TRANSACTION_TYPE: str = ""  # sale / rent
	PROPERTY_TYPE: str = ""  # apartment / house / plot
	MARKET_TYPE: str = ""  # primary / secondary

	def __init__(self):
		self.session = requests.Session()
		self.session.headers.update({
			"User-Agent": settings.scraper.user_agent,
			"Accept": "text/html,application/xhtml+xml",
			"Accept-Language": "pl-PL,pl;q=0.9",
		})

	def _fetch_page(self, url: str) -> BeautifulSoup:
		logger.info(f"Fetching: {url}")

		response = self.session.get(
			url,
			timeout=settings.scraper.request_timeout)
		response.raise_for_status()

		return BeautifulSoup(response.text, "html.parser")

	def _delay(self):
		time.sleep(settings.scraper.request_delay + random.uniform(0, 1.5))

	@abstractmethod
	def get_listing_url(self, page: int) -> str:
		pass

	@abstractmethod
	def parse_listing_page(
		self,
		soup: BeautifulSoup,
		page_number: int,
		scrape_type: str
	) -> ScrapeResult:
		pass

	def scrape_first_page(self) -> List[Offer]:
		logger.info(f"[{self.PORTAL_NAME}] Starting first page scrape")

		url = self.get_listing_url(page=1)
		soup = self._fetch_page(url)
		result = self.parse_listing_page(soup, page_number=1, scrape_type="FIRST_PAGE")

		logger.info(f"[{self.PORTAL_NAME}] First page: {len(result.offers)} offers")
		return result.offers

	def scrape_all_pages(self) -> Generator[List[Offer], None, None]:
		logger.info(f"[{self.PORTAL_NAME}] Starting full scrape")

		page = 1
		total_offers = 0

		while True:
			url = self.get_listing_url(page=page)

			try:
				soup = self._fetch_page(url)
				result = self.parse_listing_page(soup, page_number=page, scrape_type="FULL")

				if not result.offers:
					logger.info(f"[{self.PORTAL_NAME}] No offers on page {page}, stopping")
					break

				total_offers += len(result.offers)
				logger.info(f"[{self.PORTAL_NAME}] Page {page}: {len(result.offers)} offers")

				if not result.has_next_page and len(result.offers) >= 24:
					result.has_next_page = True
					logger.info(
						f"[{self.PORTAL_NAME}] Pagination signal missing, continuing because current page has {len(result.offers)} offers")

				yield result.offers

				if not result.has_next_page:
					logger.info(f"[{self.PORTAL_NAME}] No more pages after {page}")
					break

				page += 1
				self._delay()

			except requests.RequestException as e:
				logger.error(f"[{self.PORTAL_NAME}] Error on page {page}: {e}")
				break

		logger.info(f"[{self.PORTAL_NAME}] Full scrape finished: {total_offers} total offers")
