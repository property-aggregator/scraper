import json
import logging
from dataclasses import dataclass
from typing import Optional

from property_scraper.domain import Offer, SearchSpec, SellerType
from property_scraper.portals.base import ListingParseError
from property_scraper.portals.common import extract_json_assignment, extract_source_id

logger = logging.getLogger(__name__)

PORTAL = "olx"
STATE_MARKER = "__PRERENDERED_STATE__="

# OLX also lists Otodom offers; they are scraped from Otodom directly.
SKIPPED_PARTNERS = {"otodom_pl"}

ROOMS_BY_PARAM = {"one": 1, "two": 2, "three": 3, "four": 4}  # "four" = 4 or more
SPECIAL_FLOORS = {"-1": "suterena", "0": "parter", "17": "poddasze"}


@dataclass(frozen=True)
class ApiPage:
	offers: list[Offer]
	next_url: Optional[str]
	count: Optional[int]  # offers matching the query
	count_exact: bool  # False when only the capped total_elements (max 1000) is known


def parse_api_page(content: bytes, spec: SearchSpec) -> ApiPage:
	"""Parses one response of /api/v1/offers/. Raises ListingParseError on an unexpected payload."""
	try:
		payload = json.loads(content)
		ads = payload["data"]
		metadata = payload.get("metadata") or {}
		links = payload.get("links") or {}
		if not isinstance(ads, list):
			raise TypeError("data is not a list")
	except (ValueError, KeyError, TypeError, AttributeError) as e:
		raise ListingParseError(
			f"cannot parse OLX JSON from the offers API: {e!r}; starts with {content[:200]!r}") from e

	offers = []
	seen_ids = set()
	for position, ad in enumerate(ads, start=1):
		if ((ad.get("partner") or {}).get("code")) in SKIPPED_PARTNERS:
			continue
		try:
			offer = parse_ad(ad, spec)
		except Exception:
			logger.exception("[%s] Error parsing OLX ad %s (id=%s)", spec, position, ad.get("id"))
			continue
		# Promoted ads are repeated on every page
		if offer and offer.source_id not in seen_ids:
			seen_ids.add(offer.source_id)
			offers.append(offer)

	visible = metadata.get("visible_total_count")
	total = metadata.get("total_elements")
	if isinstance(visible, int):
		count, exact = visible, True
	else:
		count, exact = (total if isinstance(total, int) else None), False

	next_url = (links.get("next") or {}).get("href") if ads else None
	return ApiPage(offers=offers, next_url=next_url, count=count, count_exact=exact)


def parse_ad(ad: dict, spec: SearchSpec) -> Optional[Offer]:
	# Drop tracking params (?search_reason=...): they change between scrapes.
	source_url = (ad.get("url") or "").split("?", 1)[0]
	source_id = extract_source_id(source_url)
	if not source_id:
		logger.warning("Skipping OLX ad without source id: id=%s url=%r", ad.get("id"), source_url)
		return None

	params = {p.get("key"): p.get("value") or {} for p in ad.get("params") or []}
	location = ad.get("location") or {}

	return Offer(
		portal=PORTAL,
		source_id=source_id,
		source_url=source_url,
		title=(ad.get("title") or "").strip(),
		price=_price(params.get("price")),
		price_per_m2=_round(_key(params, "price_per_m")),
		area_m2=_decimal(_key(params, "m")),
		rooms=ROOMS_BY_PARAM.get(_key(params, "rooms")),
		floor=_floor(_key(params, "floor_select")),
		district=_name(location, "district"),
		city=_name(location, "city"),
		province=_name(location, "region"),
		image_url=_image_url(ad.get("photos")),
		transaction_type=spec.transaction,
		property_type=spec.property_type,
		market_type=spec.market,
		seller_type=SellerType.AGENCY if ad.get("business") else SellerType.PRIVATE)


def prerendered_state(html: str) -> Optional[dict]:
	"""window.__PRERENDERED_STATE__ of an offer page (a JSON string containing JSON), or None."""
	value = extract_json_assignment(html, STATE_MARKER)
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	return value if isinstance(value, dict) else None


def _image_url(photos: Optional[list]) -> Optional[str]:
	# Links are templates like ".../image;s={width}x{height}"; without ";s=" the original size is served.
	link = (photos[0] or {}).get("link") if photos else None
	return link.split(";s=")[0] if link else None


def _key(params: dict, name: str) -> Optional[str]:
	return (params.get(name) or {}).get("key")


def _name(location: dict, level: str) -> Optional[str]:
	return (location.get(level) or {}).get("name")


def _price(price: Optional[dict]) -> Optional[int]:
	price = price or {}
	if price.get("currency", "PLN") != "PLN":
		return None  # the backend assumes PLN
	return _round(price.get("value"))


def _decimal(value) -> Optional[float]:
	try:
		return float(value) if value not in (None, "") else None
	except (TypeError, ValueError):
		return None


def _round(value) -> Optional[int]:
	number = _decimal(value)
	return round(number) if number is not None else None


def _floor(value: Optional[str]) -> Optional[str]:
	if not value or not value.startswith("floor_"):
		return None
	level = value[len("floor_"):]
	return SPECIAL_FLOORS.get(level, level)
