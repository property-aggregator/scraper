from __future__ import annotations

import logging
import random
import re
import time
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import InvalidSessionIdException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config.settings import settings
from src.browser.driver_manager import build_driver
from src.core.base_scraper import BaseScraper
from src.core.exceptions import ScrapingError
from src.core.models import PropertyItem
from src.scrapers.portals.otodom.config import BASE_URL, JSON_LD_XPATH, LISTING_CARD_LINK_CSS
from src.scrapers.portals.otodom.parser import parse_listing_jsonld, property_item_from_listing_card

logger = logging.getLogger(__name__)


class OtodomScraper(BaseScraper):
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self.driver = build_driver(headless=headless)

    def _recreate_driver(self) -> None:
        try:
            self.driver.quit()
        except Exception:  # noqa: BLE001 — session may already be dead
            pass
        self.driver = build_driver(headless=self._headless)
        logger.warning("WebDriver session recreated (browser was closed or crashed)")

    def close(self) -> None:
        self.driver.quit()

    def _delay(self) -> None:
        time.sleep(random.uniform(settings.default_delay_min, settings.default_delay_max))

    def _page_url(self, page: int) -> str:
        if page <= 1:
            return BASE_URL
        return f"{BASE_URL}&page={page}"

    @staticmethod
    def _get_page_number_from_url(url: str) -> int:
        query = parse_qs(urlparse(url).query)
        if "page" not in query:
            return 1
        try:
            return int(query["page"][0])
        except (ValueError, TypeError, IndexError):
            return 1

    def _listing_cards_present(self) -> bool:
        return bool(self.driver.find_elements(By.CSS_SELECTOR, LISTING_CARD_LINK_CSS))

    def _wait_for_listing_content(self) -> tuple[list[str], bool]:
        """Return (json_ld_scripts, use_html_cards). Prefer JSON-LD when it yields offers."""
        deadline = time.time() + settings.jsonld_wait_seconds
        cards_seen_at: float | None = None
        # If there is no JSON-LD script tag at all (common on page>1), use cards as soon as they render.
        # If tags exist (page 1), wait briefly so injected JSON-LD is not skipped in favor of cards.
        jsonld_grace_before_cards_s = 5.0

        while time.time() < deadline:
            payloads = self._extract_jsonld_payloads()
            has_ld_json_tags = bool(self.driver.find_elements(By.XPATH, JSON_LD_XPATH))
            if payloads:
                for payload in payloads:
                    try:
                        if parse_listing_jsonld(payload):
                            return (payloads, False)
                    except Exception:  # noqa: BLE001
                        continue
            if self._listing_cards_present():
                if not has_ld_json_tags:
                    return ([], True)
                if cards_seen_at is None:
                    cards_seen_at = time.time()
                if not payloads and cards_seen_at is not None:
                    if time.time() - cards_seen_at >= jsonld_grace_before_cards_s:
                        return ([], True)
            time.sleep(1)
        if self._listing_cards_present():
            return ([], True)
        return ([], False)

    def _load_listing_scripts(self, url: str) -> tuple[list[str], bool]:
        candidate_urls = [url]
        if "%2C" in url:
            candidate_urls.append(url.replace("%2C", ","))

        for candidate_url in candidate_urls:
            self.driver.get(candidate_url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            scripts, use_html = self._wait_for_listing_content()
            if scripts or use_html:
                logger.info(
                    "Listing content from %s: json_ld=%s cards=%s",
                    self.driver.current_url,
                    len(scripts),
                    use_html,
                )
                return (scripts, use_html)

            self._delay()

            # One extra refresh before declaring empty page.
            self.driver.refresh()
            scripts, use_html = self._wait_for_listing_content()
            if scripts or use_html:
                logger.info(
                    "Listing content after refresh from %s: json_ld=%s cards=%s",
                    self.driver.current_url,
                    len(scripts),
                    use_html,
                )
                return (scripts, use_html)

        logger.info("No JSON-LD or listing cards from %s", self.driver.current_url)
        return ([], False)

    def _parse_items_from_listing_cards(self) -> list[PropertyItem]:
        merged: dict[str, PropertyItem] = {}
        for link in self.driver.find_elements(By.CSS_SELECTOR, LISTING_CARD_LINK_CSS):
            try:
                href = link.get_attribute("href") or ""
                title_el = link.find_element(By.CSS_SELECTOR, 'p[data-cy="listing-item-title"]')
                title = title_el.text
                article = link.find_element(By.XPATH, "./ancestor::article[1]")
                price_els = article.find_elements(By.CSS_SELECTOR, '[data-sentry-element="MainPrice"]')
                price_text = price_els[0].text if price_els else ""
                addr_els = article.find_elements(By.CSS_SELECTOR, '[data-sentry-component="Address"]')
                address_text = addr_els[0].text if addr_els else ""
                dt_texts = [e.text for e in article.find_elements(By.CSS_SELECTOR, "dt")]
                dd_texts = [e.text for e in article.find_elements(By.CSS_SELECTOR, "dd")]
                item = property_item_from_listing_card(
                    href=href,
                    title=title,
                    price_text=price_text,
                    address_text=address_text,
                    dt_texts=dt_texts,
                    dd_texts=dd_texts,
                )
                if item:
                    merged[item.external_id] = item
            except NoSuchElementException:
                continue
        return list(merged.values())

    def _extract_jsonld_payloads(self) -> list[str]:
        scripts = self.driver.find_elements(By.XPATH, JSON_LD_XPATH)
        payloads: list[str] = []
        for script in scripts:
            content = script.get_attribute("innerHTML") or script.get_attribute("textContent")
            if content and content.strip():
                payloads.append(content)
        if payloads:
            return payloads

        matches = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            self.driver.page_source,
            flags=re.DOTALL | re.IGNORECASE,
        )
        return [m.strip() for m in matches if m and m.strip()]

    def scrape_page(self, page: int) -> list[PropertyItem]:
        target_url = self._page_url(page)
        last_error: Exception | None = None

        for attempt in range(1, settings.max_retries + 1):
            try:
                scripts, use_html = self._load_listing_scripts(target_url)
                if use_html:
                    merged_items = {i.external_id: i for i in self._parse_items_from_listing_cards()}
                    logger.info("Page %s parsed offers (cards): %s", page, len(merged_items))
                    return list(merged_items.values())

                merged_items: dict[str, PropertyItem] = {}
                for idx, script in enumerate(scripts):
                    try:
                        parsed_items = parse_listing_jsonld(script)
                    except Exception as parse_exc:  # noqa: BLE001
                        logger.warning(
                            "Skipping invalid JSON-LD script (page=%s, index=%s): %s",
                            page,
                            idx,
                            parse_exc,
                        )
                        continue
                    for item in parsed_items:
                        merged_items[item.external_id] = item
                logger.info("Page %s parsed offers: %s", page, len(merged_items))
                return list(merged_items.values())
            except InvalidSessionIdException as exc:
                last_error = exc
                logger.warning(
                    "Page %s attempt %s: invalid session (browser died); recreating driver",
                    page,
                    attempt,
                )
                self._recreate_driver()
                self._delay()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Page %s attempt %s failed: %s", page, attempt, exc)
                self._delay()

        raise ScrapingError(f"Failed scraping page={page}") from last_error

    def scrape_all_pages(self) -> list[PropertyItem]:
        all_items: dict[str, PropertyItem] = {}
        page = 1
        while True:
            url = self._page_url(page)
            logger.info("Scraping page %s", page)
            items = self.scrape_page(page)
            current_page = self._get_page_number_from_url(self.driver.current_url)

            if page > 1 and current_page != page:
                logger.info("Reached end by redirect (requested=%s got=%s)", page, current_page)
                break

            if not items:
                logger.info("No items on page %s, stop", page)
                break

            for item in items:
                all_items[item.external_id] = item
            page += 1

            interval = settings.driver_restart_interval_pages
            if interval > 0 and (page - 1) % interval == 0:
                logger.info(
                    "Proactive browser restart after %s pages (DRIVER_RESTART_INTERVAL_PAGES=%s)",
                    page - 1,
                    interval,
                )
                self._recreate_driver()

        return list(all_items.values())

    def is_offer_active(self, url: str) -> bool:
        last_error: Exception | None = None
        for _ in range(settings.max_retries):
            try:
                self.driver.get(url)
                self._delay()
                scripts = self.driver.find_elements(By.XPATH, JSON_LD_XPATH)
                return len(scripts) > 0
            except InvalidSessionIdException as exc:
                last_error = exc
                self._recreate_driver()
                self._delay()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._delay()
        raise ScrapingError(f"Could not verify offer url={url}") from last_error

