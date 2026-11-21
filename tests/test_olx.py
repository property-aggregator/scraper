import json
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import FakeHttp, fixture_text, page, spec

import property_scraper.portals.olx.scraper as scraper_module
from property_scraper.domain import MarketType, SellerType
from property_scraper.portals import ListingParseError, ScrapeReport
from property_scraper.portals.olx import OlxScraper, urls
from property_scraper.portals.olx.parser import parse_api_page
from property_scraper.portals.olx.scraper import _FullScrapeRun, initial_ranges
from property_scraper.portals.olx.urls import AreaRange

SECONDARY = spec("olx")
PRIMARY = spec("olx", MarketType.PRIMARY)


def payload() -> dict:
	# Trimmed real API response (2026-11): 3 ads, an Otodom cross-listing, and the first ad repeated
	# (promoted ads show up again on every page).
	return json.loads(fixture_text("olx", "api_offers_page1.json"))


def api_body(count=None, exact=True, next_url=None, ads=None) -> str:
	data = payload()
	if ads is not None:
		data["data"] = ads
	data["metadata"] = {"visible_total_count": count} if exact else {"total_elements": count}
	data["links"] = {"next": {"href": next_url}} if next_url else {}
	return json.dumps(data)


# --- parser -----------------------------------------------------------------

def test_parses_api_ads_skips_otodom_and_repeated_promoted_ads():
	result = parse_api_page(fixture_text("olx", "api_offers_page1.json").encode(), PRIMARY)

	assert [offer.source_id for offer in result.offers] == ["ID1dnGTp", "ID17AP3d", "ID1bIoBe"]
	assert (result.count, result.count_exact) == (308, True)
	assert result.next_url.startswith("https://www.olx.pl/api/v1/offers?offset=49&")

	first, second, third = result.offers

	assert first.source_url.startswith("https://www.olx.pl/d/oferta/") and first.source_url.endswith("-ID1dnGTp.html")
	assert (first.price, first.price_per_m2, first.area_m2, first.rooms, first.floor) == (597000, 6489, 92.0, 4, "2")
	assert (first.city, first.district, first.province) == ("Łódź", "Widzew", "Łódzkie")
	assert first.seller_type == SellerType.PRIVATE
	assert first.market_type == MarketType.PRIMARY
	assert first.image_url.startswith("https://") and ";s=" not in first.image_url

	assert (second.price, second.area_m2, second.floor, second.district) == (750000, 99.0, None, None)
	assert (third.area_m2, third.floor, third.seller_type) == (97.11, "1", SellerType.AGENCY)


def test_tracking_params_are_stripped_from_offer_url():
	data = payload()
	data["data"][0]["url"] += "?search_reason=search%7Cpromoted"

	first = parse_api_page(json.dumps(data).encode(), PRIMARY).offers[0]

	assert first.source_url.endswith("-ID1dnGTp.html")


def test_non_pln_price_is_dropped():
	data = payload()
	price = next(p for p in data["data"][0]["params"] if p["key"] == "price")
	price["value"]["currency"] = "EUR"

	assert parse_api_page(json.dumps(data).encode(), PRIMARY).offers[0].price is None


def test_capped_total_is_not_exact():
	result = parse_api_page(json.dumps({"data": [], "metadata": {"total_elements": 1000}}).encode(), PRIMARY)

	assert (result.count, result.count_exact, result.next_url) == (1000, False, None)


@pytest.mark.parametrize("body", [b"<html>captcha</html>", b"{}", b'{"data": "x"}', b"[]"])
def test_unexpected_payload_is_a_parse_error(body):
	with pytest.raises(ListingParseError, match="cannot parse OLX JSON"):
		parse_api_page(body, PRIMARY)


# --- urls -------------------------------------------------------------------

def test_api_urls():
	assert urls.offers_api_url(SECONDARY) == (
		"https://www.olx.pl/api/v1/offers/?offset=0&limit=50&category_id=14&sort_by=created_at:desc"
		"&filter_enum_market[0]=secondary")
	assert urls.offers_api_url(PRIMARY, AreaRange.m2(90.01, 100)) == (
		"https://www.olx.pl/api/v1/offers/?offset=0&limit=50&category_id=14&sort_by=created_at:desc"
		"&filter_enum_market[0]=primary&filter_float_m:from=90.01&filter_float_m:to=100")


def test_only_olx_api_links_are_followed():
	assert urls.is_api_url("https://www.olx.pl/api/v1/offers?offset=49&limit=50")
	assert not urls.is_api_url("https://evil.example.com/api/v1/offers?offset=49")
	assert not urls.is_api_url("http://www.olx.pl/api/v1/offers?offset=49")


def test_area_range_halves_without_gaps_or_overlap():
	low, high = AreaRange.m2(48.01, 50).halves()

	assert (low.area_from, low.area_to, high.area_from, high.area_to) == ("48.01", "49", "49.01", "50")
	assert AreaRange.m2(48.01, 48.02).halves() == (AreaRange.m2(48.01, 48.01), AreaRange.m2(48.02, 48.02))
	assert not AreaRange.m2(48.01, 48.01).can_split()


def test_initial_ranges_cover_all_areas_without_overlap():
	ranges = initial_ranges()

	assert ranges[0].from_centi == 0
	assert ranges[-1].to_centi == 1_000_000
	assert all(nxt.from_centi == prev.to_centi + 1 for prev, nxt in zip(ranges, ranges[1:]))


# --- scraper ----------------------------------------------------------------

def area_of(url: str):
	query = parse_qs(urlsplit(url).query)
	if "filter_float_m:from" not in query:
		return None
	return query["filter_float_m:from"][0], query["filter_float_m:to"][0]


def full_scrape(responder):
	http = FakeHttp(responder)
	report = ScrapeReport(SECONDARY)
	batches = list(OlxScraper(http, SECONDARY).scrape_all(report))
	return http, report, batches


def test_first_page_uses_api():
	http = FakeHttp(lambda url: api_body(count=308))

	offers = OlxScraper(http, PRIMARY).scrape_first_page()

	assert len(offers) == 3
	assert http.requests == [urls.offers_api_url(PRIMARY)]


def test_full_scrape_follows_next_links_and_deduplicates():
	next_url = "https://www.olx.pl/api/v1/offers?offset=49&limit=50&filter_float_m%3Afrom=0&filter_float_m%3Ato=25"

	def responder(url):
		if url == next_url:
			return api_body(count=60, ads=[])  # last page
		if area_of(url) == ("0", "25"):
			return api_body(count=60, next_url=next_url)
		return api_body(count=0, ads=[])

	http, report, batches = full_scrape(responder)

	assert next_url in http.requests
	assert report.offers == 3
	assert report.completed is True
	assert len(http.requests) == len(initial_ranges()) + 1


def test_full_scrape_halves_ranges_with_more_than_1000_offers():
	counts = {("45.01", "50"): 1500, ("45.01", "47.5"): 1001, ("45.01", "46.25"): 600, ("46.26", "47.5"): 401,
		("47.51", "50"): 499}

	def responder(url):
		return api_body(count=counts.get(area_of(url), 0), ads=None if area_of(url) in counts else [])

	http, report, _ = full_scrape(responder)

	requested = [area_of(url) for url in http.requests if area_of(url) in counts]
	assert requested == list(counts)  # depth-first: whole range, left half (split again), right half
	assert report.completed is True


def test_exactly_1000_visible_offers_fit_in_one_query():
	http, _, _ = full_scrape(lambda url: api_body(count=1000))

	assert len(http.requests) == len(initial_ranges())


def test_capped_total_without_visible_count_is_split():
	first = initial_ranges()[0]

	def responder(url):
		if area_of(url) == (first.area_from, first.area_to):
			return api_body(count=1000, exact=False)
		return api_body(count=0, ads=[])

	http, _, _ = full_scrape(responder)

	low = first.halves()[0]
	assert area_of(http.requests[1]) == (low.area_from, low.area_to)


def test_range_that_cannot_be_split_marks_scrape_incomplete(caplog):
	scraper = OlxScraper(FakeHttp(lambda url: api_body(count=5000)), SECONDARY)
	run = _FullScrapeRun(ScrapeReport(SECONDARY))

	offers = [offer for batch in scraper._scrape_range(run, AreaRange.m2(50, 50)) for offer in batch]

	assert len(offers) == 3  # what is reachable is still scraped
	assert run.failed is True
	assert "only the first 1000 are reachable" in caplog.text


def test_ignored_area_filter_stops_after_split_limit(caplog, monkeypatch):
	monkeypatch.setattr(scraper_module, "MAX_SPLITS", 5)

	# Every range claims all offers, as if OLX ignored the area filter
	http, report, _ = full_scrape(lambda url: api_body(count=28999))

	assert report.completed is False
	assert len(http.requests) < 20
	assert "is the area filter still applied" in caplog.text


def test_foreign_next_link_is_not_followed(caplog):
	http, report, _ = full_scrape(lambda url: api_body(count=3, next_url="https://evil.example.com/api/v1/offers"))

	assert not any("evil" in url for url in http.requests)
	assert report.completed is False
	assert "unexpected next page link" in caplog.text


def test_next_link_loop_is_cut_off(monkeypatch):
	monkeypatch.setattr(scraper_module, "MAX_PAGES_PER_RANGE", 3)
	loop = "https://www.olx.pl/api/v1/offers?offset=49&limit=50"
	first = initial_ranges()[0]

	def responder(url):
		if url == loop or area_of(url) == (first.area_from, first.area_to):
			return api_body(count=60, next_url=loop)
		return api_body(count=0, ads=[])

	http, report, _ = full_scrape(responder)

	assert http.requests.count(loop) == 2
	assert report.completed is False


def test_full_scrape_not_completed_on_fetch_error():
	_, report, _ = full_scrape(lambda url: page(url, status=503))

	assert report.completed is False
	assert len(report.errors) == len(initial_ranges())


def test_full_scrape_not_completed_on_parse_error(caplog):
	_, report, _ = full_scrape(lambda url: "<html>captcha</html>")

	assert report.completed is False
	assert "cannot parse OLX JSON" in caplog.text
