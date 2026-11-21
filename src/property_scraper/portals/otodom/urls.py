from typing import Optional
from urllib.parse import quote, urlencode

from property_scraper.domain import MarketType, PropertyType, SearchSpec, TransactionType

BASE_URL = "https://www.otodom.pl"
PAGE_SIZE = 72

TRANSACTIONS = {
	TransactionType.SALE: "sprzedaz",
	# Rent is left out on purpose: prices are monthly and use different fields (rentPrice).
}

# Plots are not split by market on Otodom; add them together with a decision on market_type.
ESTATES = {
	(PropertyType.APARTMENT, MarketType.SECONDARY): "mieszkanie,rynek-wtorny",
	(PropertyType.APARTMENT, MarketType.PRIMARY): "mieszkanie,rynek-pierwotny",
	(PropertyType.HOUSE, MarketType.SECONDARY): "dom,rynek-wtorny",
	(PropertyType.HOUSE, MarketType.PRIMARY): "dom,rynek-pierwotny",
}


def supports(spec: SearchSpec) -> bool:
	return spec.transaction in TRANSACTIONS and (spec.property_type, spec.market) in ESTATES


def search_path(spec: SearchSpec) -> str:
	estate = quote(ESTATES[(spec.property_type, spec.market)], safe="")
	return f"/pl/wyniki/{TRANSACTIONS[spec.transaction]}/{estate}/cala-polska"


def search_params(page: int) -> str:
	# by=LATEST: newest first, so the first page holds the new offers (DEFAULT puts promoted ones first).
	params = {"limit": PAGE_SIZE, "ownerTypeSingleSelect": "ALL", "by": "LATEST", "direction": "DESC"}
	if page > 1:
		params["page"] = page
	return urlencode(params)


def listing_url(spec: SearchSpec, page: int) -> str:
	return f"{BASE_URL}{search_path(spec)}?{search_params(page)}"


def listing_data_url(spec: SearchSpec, page: int, build_id: str) -> str:
	"""Next.js data endpoint: the page's JSON props only (~6x smaller than the HTML)."""
	return f"{BASE_URL}/_next/data/{build_id}{search_path(spec)}.json?{search_params(page)}"


def offer_url(slug: str) -> str:
	return f"{BASE_URL}/pl/oferta/{slug}"


def is_offer_path(path: Optional[str]) -> bool:
	return bool(path) and path.startswith("/pl/oferta/")
