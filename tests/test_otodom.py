import json

import pytest
from conftest import FakeHttp, fixture_text, page, spec

from property_scraper.domain import MarketType, PropertyType, SellerType
from property_scraper.net import FetchError
from property_scraper.portals import ListingParseError, ScrapeReport
from property_scraper.portals.otodom import BuildIdCache, OtodomScraper, urls
from property_scraper.portals.otodom.parser import extract_next_data, parse_search_page

SECONDARY = spec("otodom")
PRIMARY = spec("otodom", MarketType.PRIMARY)


def next_data() -> dict:
	return extract_next_data(fixture_text("otodom", "next_data_page1.html"))


def page_props(current: int = 1, total: int = 858) -> dict:
	props = next_data()["props"]["pageProps"]
	props["data"]["searchAds"]["pagination"].update(currentPage=current, totalPages=total)
	return props


def html_with(props: dict, build_id: str = "build-1") -> str:
	data = {"buildId": build_id, "props": {"pageProps": props}}
	return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


def primary_props() -> dict:
	return json.loads(fixture_text("otodom", "primary_page1.json"))["pageProps"]


# --- parser -----------------------------------------------------------------

def test_parses_offers_from_next_data():
	result = parse_search_page(page_props(), page_number=1, spec=SECONDARY)

	assert len(result.offers) == 2
	assert result.has_next_page is True

	private, agency = result.offers

	assert private.source_id == "ID4CPyc"
	assert private.source_url.startswith("https://www.otodom.pl/pl/oferta/")
	assert private.source_url.endswith("-ID4CPyc")
	assert private.price == 890000
	assert private.price_per_m2 == 10595
	assert private.area_m2 == 84.0
	assert private.rooms == 3
	assert private.floor == "1"
	assert private.seller_type == SellerType.PRIVATE
	assert private.image_url.startswith("https://")
	assert private.street == "ul. Aleja Bzów"
	assert private.district is None
	assert private.city == "Józefosław"

	assert agency.source_id == "ID4CGkp"
	assert agency.area_m2 == 44.42
	assert agency.rooms == 2
	assert agency.seller_type == SellerType.AGENCY
	assert agency.street is None
	assert agency.district == "Szopienice-Burowiec"
	assert agency.city == "Katowice"
	assert agency.province == "śląskie"


def test_offer_types_come_from_search_spec():
	offer = parse_search_page(page_props(), page_number=1, spec=PRIMARY).offers[0]

	assert offer.market_type == MarketType.PRIMARY
	assert offer.property_type == PropertyType.APARTMENT
	assert offer.to_dict()["marketType"] == "primary"


def test_city_and_province_fall_back_to_reverse_geocoding():
	props = page_props()
	for item in props["data"]["searchAds"]["items"]:
		item["location"]["address"]["city"] = None
		item["location"]["address"]["province"] = None

	private, agency = parse_search_page(props, page_number=1, spec=SECONDARY).offers

	assert (private.city, private.province) == ("Józefosław", "mazowieckie")
	assert (agency.city, agency.province) == ("Katowice", "śląskie")


def test_last_page_has_no_next_page():
	result = parse_search_page(page_props(current=858), page_number=858, spec=SECONDARY)

	assert result.has_next_page is False


def test_page_beyond_last_returns_empty_result():
	# Fixture says currentPage=1; asking for page 859 mimics the portal serving a default page
	result = parse_search_page(page_props(), page_number=859, spec=SECONDARY)

	assert result.offers == []
	assert result.has_next_page is False


def test_missing_search_ads_is_a_parse_error():
	with pytest.raises(ListingParseError, match="cannot parse Otodom JSON"):
		parse_search_page({}, page_number=1, spec=SECONDARY)


def test_unknown_floor_is_none():
	props = page_props()
	props["data"]["searchAds"]["items"][0]["floorNumber"] = None

	assert parse_search_page(props, page_number=1, spec=SECONDARY).offers[0].floor is None


def test_offer_json_uses_camel_case():
	payload = parse_search_page(page_props(), page_number=1, spec=SECONDARY).offers[0].to_dict()

	assert payload["sourceId"] == "ID4CPyc"
	assert payload["sellerType"] == "private"
	assert payload["transactionType"] == "sale"
	assert payload["scrapedAt"].endswith("Z")
	assert {"sourceUrl", "pricePerM2", "areaM2", "street", "district", "city", "province", "imageUrl",
			"transactionType", "propertyType", "marketType", "sellerType", "scrapedAt"} <= payload.keys()
	assert not any("_" in key for key in payload)


def test_primary_market_skips_investment_cards():
	offers = parse_search_page(primary_props(), page_number=1, spec=PRIMARY).offers

	assert [offer.source_id for offer in offers] == ["ID4E5M1", "ID4E5LI"]
	assert offers[0].price == 334407
	assert offers[0].area_m2 == 42.33
	assert offers[0].rooms == 2
	assert all(offer.market_type == MarketType.PRIMARY for offer in offers)


def test_developer_agency_is_developer_seller():
	props = primary_props()
	props["data"]["searchAds"]["items"][0]["agency"]["type"] = "DEVELOPER"

	assert parse_search_page(props, page_number=1, spec=PRIMARY).offers[0].seller_type == SellerType.DEVELOPER


# --- urls -------------------------------------------------------------------

def test_listing_urls():
	assert urls.listing_url(PRIMARY, page=1) == (
		"https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie%2Crynek-pierwotny/cala-polska"
		"?limit=72&ownerTypeSingleSelect=ALL&by=LATEST&direction=DESC")
	assert urls.listing_url(SECONDARY, page=3).endswith("mieszkanie%2Crynek-wtorny/cala-polska"
		"?limit=72&ownerTypeSingleSelect=ALL&by=LATEST&direction=DESC&page=3")
	assert urls.listing_data_url(PRIMARY, page=2, build_id="abc").startswith(
		"https://www.otodom.pl/_next/data/abc/pl/wyniki/sprzedaz/mieszkanie%2Crynek-pierwotny/cala-polska.json?")


def test_supported_specs():
	assert urls.supports(spec("otodom", property_type=PropertyType.HOUSE))
	assert not urls.supports(spec("otodom", property_type=PropertyType.PLOT))


# --- scraper (fetching) -----------------------------------------------------

def make_scraper(responder, build_id: BuildIdCache = None):
	http = FakeHttp(responder)
	return OtodomScraper(http, SECONDARY, build_id or BuildIdCache()), http


def test_first_request_uses_html_then_data_endpoint():
	def responder(url):
		if "/_next/data/build-1/" in url:
			return json.dumps({"pageProps": page_props(current=2, total=2)})
		return html_with(page_props(current=1, total=2))

	scraper, http = make_scraper(responder)
	report = ScrapeReport(SECONDARY)

	batches = list(scraper.scrape_all(report))

	assert len(batches) == 2
	assert report.completed is True
	assert "/_next/data/" not in http.requests[0]
	assert "/_next/data/build-1/" in http.requests[1]


def test_stale_build_id_falls_back_to_html_and_refreshes_it():
	cache = BuildIdCache()
	cache.set("old")

	def responder(url):
		if "/_next/data/old/" in url:
			return page(url, "not found", status=404)
		return html_with(page_props(), build_id="new")

	scraper, http = make_scraper(responder, cache)

	assert len(scraper.scrape_first_page()) == 2
	assert cache.get() == "new"
	assert len(http.requests) == 2


def test_full_scrape_not_completed_on_fetch_error():
	def responder(url):
		if "page=2" in url:
			return page(url, status=None)
		# No build id in the page, so every page goes through the HTML path
		return html_with(page_props(current=1, total=3), build_id=None)

	scraper, _ = make_scraper(responder)
	report = ScrapeReport(SECONDARY)

	batches = list(scraper.scrape_all(report))

	assert len(batches) == 1
	assert report.completed is False
	assert len(report.errors) == 1


def test_full_scrape_not_completed_when_page_has_no_json(caplog):
	def responder(url):
		return "<html></html>" if "page=2" in url else html_with(page_props(current=1, total=3), build_id=None)

	scraper, _ = make_scraper(responder)
	report = ScrapeReport(SECONDARY)

	batches = list(scraper.scrape_all(report))

	assert len(batches) == 1
	assert report.completed is False
	assert "cannot parse Otodom JSON" in report.errors[0]
	assert "cannot parse Otodom JSON" in caplog.text


@pytest.mark.parametrize("body", ["<html>not json</html>", json.dumps({"pageProps": {"__N_REDIRECT": "/"}})])
def test_bad_data_endpoint_json_is_a_parse_error_without_html_fallback(body):
	cache = BuildIdCache()
	cache.set("build-1")
	scraper, http = make_scraper(lambda url: body, cache)

	with pytest.raises(ListingParseError, match="cannot parse Otodom JSON"):
		scraper.scrape_first_page()
	assert len(http.requests) == 1
	assert "/_next/data/" in http.requests[0]


def test_first_page_raises_on_blocked_request():
	scraper, _ = make_scraper(lambda url: page(url, status=403))

	with pytest.raises(FetchError) as error:
		scraper.scrape_first_page()
	assert error.value.result.status == 403
