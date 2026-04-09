from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.models import PropertyItem


class BaseScraper(ABC):
    @abstractmethod
    def scrape_page(self, page: int) -> list[PropertyItem]:
        raise NotImplementedError

    @abstractmethod
    def scrape_all_pages(self) -> list[PropertyItem]:
        raise NotImplementedError

    @abstractmethod
    def is_offer_active(self, url: str) -> bool:
        raise NotImplementedError

