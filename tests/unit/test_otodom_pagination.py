from src.scrapers.portals.otodom.config import BASE_URL
from src.scrapers.portals.otodom.scraper import OtodomScraper


def test_page_1_does_not_append_page_param() -> None:
    scraper = OtodomScraper.__new__(OtodomScraper)
    assert scraper._page_url(1) == BASE_URL
    assert scraper._page_url(0) == BASE_URL


def test_page_2_appends_page_param() -> None:
    scraper = OtodomScraper.__new__(OtodomScraper)
    assert scraper._page_url(2) == f"{BASE_URL}&page=2"

