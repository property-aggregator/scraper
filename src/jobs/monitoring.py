from __future__ import annotations

import logging

from config.settings import settings
from src.api.client import ApiClient
from src.scrapers.portals.otodom.scraper import OtodomScraper

logger = logging.getLogger(__name__)


def _log_scraped_offers(offers: list) -> None:
    if not offers:
        logger.info("No offers scraped")
        return
    logger.info("Scraped offers preview (count=%s):", len(offers))
    for offer in offers:
        logger.info(
            "SCRAPED | id=%s | title=%s | price=%s %s | url=%s",
            offer.external_id,
            offer.title,
            offer.price,
            offer.currency,
            offer.url,
        )


def run_monitoring() -> dict:
    scraper = OtodomScraper()
    api = ApiClient() if settings.api_enabled else None
    try:
        offers = []
        for page in (1, 2, 3):
            logger.info("Monitoring scrape page %s", page)
            offers.extend(scraper.scrape_page(page))
        _log_scraped_offers(offers)
        if not settings.api_enabled:
            logger.info("API disabled. Skipping upsert for %s offers", len(offers))
            return {"api_enabled": False, "offers_count": len(offers)}
        logger.info("Monitoring: upsert %s offers", len(offers))
        return api.upsert_offers(offers) if api else {"offers_count": len(offers)}
    finally:
        scraper.close()

