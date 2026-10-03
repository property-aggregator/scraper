import time
import logging
import random
from abc import ABC, abstractmethod
from typing import List, Generator
from dataclasses import dataclass

import requests
from curl_cffi import requests as curl_requests

from property_scraper.models.offer import Offer
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)

FETCH_ERRORS = (requests.RequestException, curl_requests.exceptions.RequestException)
FETCH_ATTEMPTS = 3


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
		self.completed = False  # True only when scrape_all_pages reached the last page
		# Plain requests gets 403 (TLS fingerprinting), so impersonate Chrome.
		# Headers, including User-Agent, come from the impersonation profile.
		self.session = curl_requests.Session(
			impersonate="chrome",
			headers={"Accept-Language": "pl-PL,pl;q=0.9"})

	def _fetch_page(self, url: str) -> str:
		for attempt in range(1, FETCH_ATTEMPTS + 1):
			logger.info(f"Fetching: {url}")

			try:
				response = self.session.get(
					url,
					timeout=settings.scraper.request_timeout)
				response.raise_for_status()
				return response.text
			except FETCH_ERRORS as e:
				status = getattr(e.response, "status_code", None)
				# Ponawiamy tylko bledy sieciowe, 429 i 5xx; 403/404 nie zmienia sie po ponowieniu.
				retriable = status is None or status == 429 or status >= 500
				if attempt == FETCH_ATTEMPTS or not retriable:
					raise
				logger.warning(f"Attempt {attempt}/{FETCH_ATTEMPTS} failed ({e}), retrying")
				time.sleep(attempt * settings.scraper.request_delay)

	def _delay(self):
		time.sleep(settings.scraper.request_delay + random.uniform(0, 1.5))

	@abstractmethod
	def get_listing_url(self, page: int) -> str:
		pass

	@abstractmethod
	def parse_listing_page(
		self,
		html: str,
		page_number: int,
		scrape_type: str
	) -> ScrapeResult:
		pass

	def scrape_first_page(self) -> List[Offer]:
		logger.info(f"[{self.PORTAL_NAME}] Starting first page scrape")

		url = self.get_listing_url(page=1)
		html = self._fetch_page(url)
		result = self.parse_listing_page(html, page_number=1, scrape_type="FIRST_PAGE")

		logger.info(f"[{self.PORTAL_NAME}] First page: {len(result.offers)} offers")
		return result.offers

	def scrape_all_pages(self) -> Generator[List[Offer], None, None]:
		logger.info(f"[{self.PORTAL_NAME}] Starting full scrape")

		self.completed = False
		page = 1
		total_offers = 0

		while True:
			url = self.get_listing_url(page=page)

			try:
				html = self._fetch_page(url)
				result = self.parse_listing_page(html, page_number=page, scrape_type="FULL")

				if not result.offers:
					logger.info(f"[{self.PORTAL_NAME}] No offers on page {page}, stopping")
					break

				total_offers += len(result.offers)
				logger.info(f"[{self.PORTAL_NAME}] Page {page}: {len(result.offers)} offers")

				yield result.offers

				if not result.has_next_page:
					logger.info(f"[{self.PORTAL_NAME}] No more pages after {page}")
					self.completed = True
					break

				page += 1
				self._delay()

			except FETCH_ERRORS as e:
				response = e.response
				detail = ""
				if response is not None:
					detail = (
						f" (status={response.status_code}, "
						f"retry-after={response.headers.get('Retry-After')})")
				logger.error(f"[{self.PORTAL_NAME}] Error on page {page}{detail}: {e}")
				break

		logger.info(f"[{self.PORTAL_NAME}] Full scrape finished: {total_offers} total offers")
