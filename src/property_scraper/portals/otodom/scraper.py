import json
import logging
import threading
from typing import Optional

from property_scraper.domain import SearchSpec
from property_scraper.net import FetchError, HttpClient
from property_scraper.portals.base import ListingPage, ListingParseError, PaginatedScraper
from property_scraper.portals.otodom import urls
from property_scraper.portals.otodom.parser import extract_next_data, parse_search_page

logger = logging.getLogger(__name__)

NEXT_DATA_HEADERS = {"x-nextjs-data": "1"}


class BuildIdCache:
	"""Next.js build id of the Otodom frontend; changes on every Otodom deploy."""

	def __init__(self):
		self._value: Optional[str] = None
		self._lock = threading.Lock()

	def get(self) -> Optional[str]:
		with self._lock:
			return self._value

	def set(self, value: Optional[str]) -> None:
		with self._lock:
			self._value = value


class OtodomScraper(PaginatedScraper):
	"""Reads listing pages as JSON from the Next.js data endpoint.

	That endpoint needs the frontend's build id, which is only published in the HTML page
	(as part of the same __NEXT_DATA__ JSON). So the HTML page is requested only when no build id
	is known: on the first request and after Otodom deploys a new frontend (old id -> 404).
	"""

	def __init__(self, http: HttpClient, spec: SearchSpec, build_id: BuildIdCache):
		super().__init__(http, spec)
		self._build_id = build_id

	def fetch_page(self, page: int) -> ListingPage:
		return parse_search_page(self._fetch_page_props(page), page, self.spec)

	def _fetch_page_props(self, page: int) -> dict:
		build_id = self._build_id.get()
		if build_id:
			result = self.http.get(urls.listing_data_url(self.spec, page, build_id), headers=NEXT_DATA_HEADERS)
			if result.status != 404:
				if not result.ok:
					raise FetchError(result)
				return self._page_props_from_data_endpoint(result.content, page)

			logger.info("[%s] Next.js build id %s is stale, reading the new one from the HTML page", self.spec, build_id)
			self._build_id.set(None)

		return self._page_props_from_html_page(page)

	def _page_props_from_data_endpoint(self, content: bytes, page: int) -> dict:
		try:
			return json.loads(content)["pageProps"]
		except (ValueError, KeyError, TypeError) as e:
			raise ListingParseError(
				f"cannot parse Otodom JSON from the data endpoint on page {page}: {e!r}; "
				f"starts with {content[:200]!r}") from e

	def _page_props_from_html_page(self, page: int) -> dict:
		result = self.http.get(urls.listing_url(self.spec, page))
		if not result.ok:
			raise FetchError(result)

		next_data = extract_next_data(result.text)
		if next_data is None:
			raise ListingParseError(
				f"cannot parse Otodom JSON: __NEXT_DATA__ missing on page {page} "
				f"({len(result.content)} bytes, starts with {' '.join(result.text[:200].split())!r})")

		self._build_id.set(next_data.get("buildId"))
		return (next_data.get("props") or {}).get("pageProps") or {}
