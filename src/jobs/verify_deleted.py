from __future__ import annotations

import logging

from config.settings import settings
from src.api.client import ApiClient
from src.scrapers.portals.otodom.config import PORTAL_NAME
from src.scrapers.portals.otodom.scraper import OtodomScraper

logger = logging.getLogger(__name__)


def run_verify_deleted() -> dict:
    if not settings.api_enabled:
        logger.info("API disabled. Skipping verify_deleted job.")
        return {"api_enabled": False, "checked": 0, "deleted": 0}

    api = ApiClient()
    candidates = api.get_potentially_inactive(PORTAL_NAME)
    if not candidates:
        logger.info("No potentially inactive offers")
        return {"checked": 0, "deleted": 0}

    scraper = OtodomScraper()
    deleted_ids: list[str] = []
    try:
        for candidate in candidates:
            external_id = candidate.get("external_id")
            url = candidate.get("url")
            if not external_id or not url:
                continue
            active = scraper.is_offer_active(url)
            if not active:
                deleted_ids.append(external_id)
    finally:
        scraper.close()

    if not deleted_ids:
        logger.info("Verified candidates, no deleted offers")
        return {"checked": len(candidates), "deleted": 0}

    result = api.mark_deleted(deleted_ids, PORTAL_NAME)
    return {"checked": len(candidates), "deleted": len(deleted_ids), "api": result}

