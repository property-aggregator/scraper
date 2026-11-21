import logging

from property_scraper.domain import Availability, SearchSpec
from property_scraper.net import FetchResult, HttpClient
from property_scraper.portals.base import Portal
from property_scraper.portals.olx import urls
from property_scraper.portals.olx.parser import prerendered_state
from property_scraper.portals.olx.scraper import OlxScraper

logger = logging.getLogger(__name__)

# Read from the ad's JSON state only. Do NOT match on "To ogłoszenie nie jest już dostępne":
# that text sits in the translations bundle of every (also active) offer page.
ACTIVE_STATUS = "active"


class OlxPortal(Portal):
	name = "olx"
	domains = ("olx.pl",)

	def supports(self, spec: SearchSpec) -> bool:
		return urls.supports(spec)

	def create_scraper(self, http: HttpClient, spec: SearchSpec) -> OlxScraper:
		return OlxScraper(http, spec)

	def is_offer_url(self, url: str) -> bool:
		return urls.is_offer_url(url)

	def availability_from_page(self, result: FetchResult) -> Availability:
		ad = ((prerendered_state(result.text) or {}).get("ad") or {}).get("ad")
		if not isinstance(ad, dict) or not ("isActive" in ad or "status" in ad):
			logger.error("Cannot parse OLX JSON: ad state missing in __PRERENDERED_STATE__ on %s", result.url)
			return Availability.UNKNOWN

		# Active offers carry status="active", isActive=true.
		if ad.get("isActive") is False or ad.get("status", ACTIVE_STATUS) != ACTIVE_STATUS:
			return Availability.EXPIRED
		return Availability.ACTIVE
