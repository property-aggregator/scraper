from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, urlsplit

from property_scraper.domain import MarketType, PropertyType, SearchSpec, TransactionType

BASE_URL = "https://www.olx.pl"
API_URL = f"{BASE_URL}/api/v1/offers/"
PAGE_SIZE = 50

# OLX category ids (API `category_id`); 14 = nieruchomosci/mieszkania/sprzedaz.
CATEGORY_IDS = {
	(TransactionType.SALE, PropertyType.APARTMENT): 14,
	# Houses/plots use different params (no rooms/floor); add with a parser check.
}

MARKETS = {
	MarketType.SECONDARY: "secondary",
	MarketType.PRIMARY: "primary",
}


@dataclass(frozen=True)
class AreaRange:
	"""Area filter in hundredths of m² (integers, so halving never hits float rounding); both ends inclusive."""

	from_centi: int
	to_centi: int

	@classmethod
	def m2(cls, area_from: float, area_to: float) -> "AreaRange":
		return cls(round(area_from * 100), round(area_to * 100))

	def can_split(self) -> bool:
		return self.to_centi > self.from_centi

	def halves(self) -> tuple["AreaRange", "AreaRange"]:
		middle = (self.from_centi + self.to_centi) // 2
		return AreaRange(self.from_centi, middle), AreaRange(middle + 1, self.to_centi)

	@property
	def area_from(self) -> str:
		return _format_m2(self.from_centi)

	@property
	def area_to(self) -> str:
		return _format_m2(self.to_centi)

	def __str__(self) -> str:
		return f"{self.area_from}-{self.area_to} m²"


def _format_m2(centi: int) -> str:
	return f"{centi / 100:.2f}".rstrip("0").rstrip(".")


def supports(spec: SearchSpec) -> bool:
	return (spec.transaction, spec.property_type) in CATEGORY_IDS and spec.market in MARKETS


def offers_api_url(spec: SearchSpec, area: Optional[AreaRange] = None) -> str:
	"""First page of the offers API; further pages come from the response's `links.next`.

	Same offers as the listing page (checked 2026-11: identical ids), ~12x less data.
	"""
	params = {
		"offset": 0,
		"limit": PAGE_SIZE,
		"category_id": CATEGORY_IDS[(spec.transaction, spec.property_type)],
		"sort_by": "created_at:desc",
		"filter_enum_market[0]": MARKETS[spec.market],
	}
	if area:
		params["filter_float_m:from"] = area.area_from
		params["filter_float_m:to"] = area.area_to
	return f"{API_URL}?{urlencode(params, safe=':[]')}"


def is_api_url(url: str) -> bool:
	parts = urlsplit(url)
	return parts.scheme == "https" and parts.hostname == "www.olx.pl" and parts.path.rstrip("/") == "/api/v1/offers"


def is_offer_path(path: Optional[str]) -> bool:
	return bool(path) and path.startswith("/d/oferta/")


def is_offer_url(url: str) -> bool:
	return is_offer_path(urlsplit(url).path)
