import json
import os
import re
from pathlib import Path

os.environ.setdefault("RABBITMQ_HOST", "localhost")
os.environ.setdefault("RABBITMQ_PORT", "5672")
os.environ.setdefault("RABBITMQ_USERNAME", "guest")
os.environ.setdefault("RABBITMQ_PASSWORD", "guest")
os.environ.setdefault("RABBITMQ_QUEUE", "offers")
os.environ.setdefault("RABBITMQ_EXCHANGE", "property_scraper")
os.environ.setdefault("REQUEST_DELAY", "3.0")
os.environ.setdefault("REQUEST_TIMEOUT", "15")
os.environ.setdefault("FIRST_PAGE_INTERVAL", "10")
os.environ.setdefault("FULL_SCRAPE_TIME", "22:00")

from property_scraper.scrapers.otodom_scraper import OtodomScraper

FIXTURE = Path(__file__).parent / "fixtures" / "otodom" / "next_data_page1.html"


def load_html() -> str:
	return FIXTURE.read_text(encoding="utf-8")


def test_parses_offers_from_next_data():
	result = OtodomScraper().parse_listing_page(load_html(), page_number=1, scrape_type="FIRST_PAGE")

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
	assert private.seller_type == "private"
	assert private.image_url.startswith("https://")

	assert agency.source_id == "ID4CGkp"
	assert agency.area_m2 == 44.42
	assert agency.rooms == 2
	assert agency.seller_type == "agency"
	assert agency.street is None
	assert agency.district == "Szopienice-Burowiec"
	assert agency.city == "Katowice"
	assert agency.province == "śląskie"

	assert private.street == "ul. Aleja Bzów"
	assert private.district is None
	assert private.city == "Józefosław"


def test_last_page_has_no_next_page():
	html = load_html().replace('"currentPage": 1', '"currentPage": 858')

	result = OtodomScraper().parse_listing_page(html, page_number=858, scrape_type="FULL")

	assert result.has_next_page is False


def test_page_beyond_last_returns_empty_result():
	# Fixture says currentPage=1; asking for page 859 mimics the portal serving a default page
	result = OtodomScraper().parse_listing_page(load_html(), page_number=859, scrape_type="FULL")

	assert result.offers == []
	assert result.has_next_page is False


def test_missing_next_data_returns_empty_result():
	result = OtodomScraper().parse_listing_page("<html></html>", page_number=1, scrape_type="FULL")

	assert result.offers == []
	assert result.has_next_page is False


def test_unknown_floor_is_none():
	html = load_html()
	data = json.loads(re.search(r'<script[^>]*>(.*?)</script>', html, re.DOTALL).group(1))
	data["props"]["pageProps"]["data"]["searchAds"]["items"][0]["floorNumber"] = None
	html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'

	result = OtodomScraper().parse_listing_page(html, page_number=1, scrape_type="FULL")

	assert result.offers[0].floor is None


def test_offer_json_uses_camel_case():
	offer = OtodomScraper().parse_listing_page(
		load_html(), page_number=1, scrape_type="FIRST_PAGE").offers[0]

	payload = offer.to_dict()

	assert payload["sourceId"] == "ID4CPyc"
	assert {"sourceUrl", "pricePerM2", "areaM2", "street", "district", "city", "province", "imageUrl",
			"transactionType", "propertyType", "marketType", "sellerType", "scrapedAt"} <= payload.keys()
	assert not any("_" in key for key in payload)


def make_scraper(pages: dict):
	"""Scraper whose pages come from a dict of page number -> HTML or Exception."""
	import requests

	scraper = OtodomScraper()
	scraper._delay = lambda: None

	def fetch(url):
		page = int(url.split("page=")[1]) if "page=" in url else 1
		value = pages[page]
		if isinstance(value, Exception):
			raise value
		return value

	scraper._fetch_page = fetch
	return scraper, requests


def page_html(current: int, total: int) -> str:
	return (load_html()
		.replace('"currentPage": 1', f'"currentPage": {current}')
		.replace('"totalPages": 858', f'"totalPages": {total}'))


def test_full_scrape_completed_on_last_page():
	scraper, _ = make_scraper({1: page_html(1, 2), 2: page_html(2, 2)})

	batches = list(scraper.scrape_all_pages())

	assert len(batches) == 2
	assert scraper.completed is True


def test_full_scrape_not_completed_on_request_error():
	scraper, requests = make_scraper({1: page_html(1, 3), 2: requests_error()})

	batches = list(scraper.scrape_all_pages())

	assert len(batches) == 1
	assert scraper.completed is False


def test_full_scrape_not_completed_on_empty_page():
	scraper, _ = make_scraper({1: page_html(1, 3), 2: "<html></html>"})

	list(scraper.scrape_all_pages())

	assert scraper.completed is False


def requests_error():
	import requests
	return requests.ConnectionError("boom")
