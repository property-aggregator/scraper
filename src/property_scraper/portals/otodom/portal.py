import logging
from urllib.parse import urlsplit

from property_scraper.domain import Availability, SearchSpec
from property_scraper.net import FetchResult, HttpClient
from property_scraper.portals.base import Portal
from property_scraper.portals.otodom import urls
from property_scraper.portals.otodom.parser import extract_next_data, find_key
from property_scraper.portals.otodom.scraper import BuildIdCache, OtodomScraper

logger = logging.getLogger(__name__)

# In __NEXT_DATA__ of every offer page: null on active offers, true on expired ones.
EXPIRED_FLAG = "shouldShowExpiredAdPage"


class OtodomPortal(Portal):
	name = "otodom"
	domains = ("otodom.pl",)

	def __init__(self):
		self._build_id = BuildIdCache()

	def supports(self, spec: SearchSpec) -> bool:
		return urls.supports(spec)

	def create_scraper(self, http: HttpClient, spec: SearchSpec) -> OtodomScraper:
		return OtodomScraper(http, spec, self._build_id)

	def is_offer_url(self, url: str) -> bool:
		return urls.is_offer_path(urlsplit(url).path)

	def availability_from_page(self, result: FetchResult) -> Availability:
		next_data = extract_next_data(result.text)
		if next_data is None:
			logger.error("Cannot parse Otodom JSON: __NEXT_DATA__ missing on %s", result.url)
			return Availability.UNKNOWN

		try:
			expired = find_key(next_data, EXPIRED_FLAG)
		except KeyError:
			logger.error("Cannot parse Otodom JSON: %s missing on %s", EXPIRED_FLAG, result.url)
			return Availability.UNKNOWN

		return Availability.EXPIRED if expired is True else Availability.ACTIVE
