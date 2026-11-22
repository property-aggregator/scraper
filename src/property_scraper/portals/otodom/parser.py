import json
import logging
import re
from typing import Optional

from property_scraper.domain import Offer, SearchSpec, SellerType
from property_scraper.portals.base import ListingPage, ListingParseError
from property_scraper.portals.common import extract_source_id
from property_scraper.portals.otodom.urls import offer_url

logger = logging.getLogger(__name__)

PORTAL = "otodom"

NEXT_DATA_PATTERN = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

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

# Primary-market listings mix in developer projects (no single price/area); their units are listed separately.
SKIPPED_ESTATES = {"INVESTMENT"}


def extract_next_data(html: str) -> Optional[dict]:
	match = NEXT_DATA_PATTERN.search(html)
	if not match:
		return None
	try:
		return json.loads(match.group(1))
	except json.JSONDecodeError as e:
		logger.error("Invalid __NEXT_DATA__ JSON: %s", e)
		return None


def search_ads(page_props: dict) -> Optional[dict]:
	return ((page_props or {}).get("data") or {}).get("searchAds")


def find_key(data, key: str):
	"""Value of the first `key` found anywhere in nested JSON, or KeyError."""
	stack = [data]
	while stack:
		node = stack.pop()
		if isinstance(node, dict):
			if key in node:
				return node[key]
			stack.extend(node.values())
		elif isinstance(node, list):
			stack.extend(node)
	raise KeyError(key)


def parse_search_page(page_props: dict, page_number: int, spec: SearchSpec) -> ListingPage:
	ads = search_ads(page_props)
	if ads is None:
		raise ListingParseError(f"cannot parse Otodom JSON: searchAds missing on page {page_number}")

	pagination = ads.get("pagination") or {}
	current_page = pagination.get("currentPage")

	# Past the last page Otodom ignores the page number and serves a default page
	if current_page is not None and current_page != page_number:
		logger.warning(
			"[%s] Requested page %s but portal returned page %s, treating as end of results",
			spec, page_number, current_page)
		return ListingPage(offers=[], has_next_page=False)

	offers = []
	seen_ids = set()

	for position, item in enumerate(ads.get("items") or [], start=1):
		if item.get("estate") in SKIPPED_ESTATES:
			continue
		try:
			offer = parse_item(item, spec)
		except Exception:
			logger.exception("[%s] Error parsing item %s (slug=%s) on page %s",
				spec, position, item.get("slug"), page_number)
			continue

		if offer and offer.source_id not in seen_ids:
			seen_ids.add(offer.source_id)
			offers.append(offer)

	total_pages = pagination.get("totalPages") or 0
	return ListingPage(offers=offers, has_next_page=page_number < total_pages)


def parse_item(item: dict, spec: SearchSpec) -> Optional[Offer]:
	slug = item.get("slug")
	source_id = extract_source_id(slug)

	if not source_id:
		logger.warning("Skipping item without valid slug: id=%s slug=%r", item.get("id"), slug)
		return None

	area = item.get("areaInSquareMeters")

	return Offer(
		portal=PORTAL,
		source_id=source_id,
		source_url=offer_url(slug),
		title=item.get("title") or "",
		price=_money(item.get("totalPrice")),
		price_per_m2=_money(item.get("pricePerSquareMeter")),
		area_m2=float(area) if area is not None else None,
		rooms=ROOMS.get(item.get("roomsNumber")),
		floor=FLOORS.get(item.get("floorNumber")),
		**_location(item.get("location") or {}),
		image_url=_image_url(item.get("images")),
		transaction_type=spec.transaction,
		property_type=spec.property_type,
		market_type=spec.market,
		seller_type=_seller_type(item))


def _image_url(images: Optional[list]) -> Optional[str]:
	# Current format (2026-11): [{"url": ...}]; older pages had [{"medium": ..., "large": ...}].
	image = (images or [None])[0] or {}
	return image.get("url") or image.get("large") or image.get("medium") or None


def _money(money: Optional[dict]) -> Optional[int]:
	value = (money or {}).get("value")
	return round(value) if value is not None else None


def _location(location: dict) -> dict:
	address = location.get("address") or {}
	street = address.get("street") or {}
	levels = (location.get("reverseGeocoding") or {}).get("locations") or []

	street_name = " ".join(part for part in (street.get("name"), street.get("number")) if part)

	def level_name(level: str) -> Optional[str]:
		return next((loc.get("name") for loc in levels if loc.get("locationLevel") == level), None)

	# address.city / address.province are often null, reverseGeocoding is always filled
	return {
		"street": street_name or None,
		"district": level_name("district"),
		"city": (address.get("city") or {}).get("name") or level_name("city_or_village"),
		"province": (address.get("province") or {}).get("name") or level_name("voivodeship"),
	}


def _seller_type(item: dict) -> Optional[SellerType]:
	agency = item.get("agency") or {}
	if item.get("isPrivateOwner"):
		return SellerType.PRIVATE
	if item.get("developmentId") or agency.get("type") == "DEVELOPER":
		return SellerType.DEVELOPER
	if agency:
		return SellerType.AGENCY
	return None
