import json
import os
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

from property_scraper.scrapers.olx_scraper import OlxScraper

FIXTURE = Path(__file__).parent / "fixtures" / "olx" / "listing_page1.html"


def load_html() -> str:
	return FIXTURE.read_text(encoding="utf-8")


def prerendered_state(page_number: int) -> str:
	state = {"listing": {"listing": {"pageNumber": page_number, "ads": []}}}
	return f"<script>window.__PRERENDERED_STATE__= {json.dumps(json.dumps(state))};</script>"


def test_parses_olx_cards_and_skips_external_listing():
	result = OlxScraper().parse_listing_page(load_html(), page_number=1, scrape_type="FIRST_PAGE")

	assert len(result.offers) == 2
	assert result.has_next_page is True

	first, second = result.offers

	assert first.source_id == "ID1cBZtL"
	assert first.source_url.startswith("https://www.olx.pl/d/oferta/")
	assert first.price == 235000
	assert first.price_per_m2 == 4866
	assert first.area_m2 == 48.29
	assert first.rooms == 2
	assert first.floor == "parter"
	assert first.city == "Białystok"
	assert first.district == "Centrum"

	assert second.source_id == "ID1abcde"
	assert second.price == 300000
	assert second.price_per_m2 == 5000
	assert second.area_m2 == 60.0
	assert second.rooms == 3
	assert second.floor == "1"
	assert second.city == "Warszawa"
	assert second.district == "Praga-Północ"


def test_page_mismatch_returns_empty_result():
	html = prerendered_state(page_number=4) + load_html()
	result = OlxScraper().parse_listing_page(html, page_number=2, scrape_type="FULL")

	assert result.offers == []
	assert result.has_next_page is False


def test_missing_pagination_forward_marks_last_page():
	html = load_html().replace(' data-testid="pagination-forward"', "")
	result = OlxScraper().parse_listing_page(html, page_number=1, scrape_type="FULL")

	assert len(result.offers) == 2
	assert result.has_next_page is False
