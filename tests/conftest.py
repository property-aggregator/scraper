import os
from pathlib import Path
from typing import Callable, Mapping, Optional, Union

import pytest

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

from property_scraper.domain import MarketType, PropertyType, SearchSpec, TransactionType  # noqa: E402
from property_scraper.net import FetchResult  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(*parts: str) -> str:
	return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


def spec(portal: str, market: MarketType = MarketType.SECONDARY,
		property_type: PropertyType = PropertyType.APARTMENT) -> SearchSpec:
	return SearchSpec(portal, TransactionType.SALE, property_type, market)


def page(url: str, body: Union[str, bytes] = "", status: Optional[int] = 200,
		final_url: Optional[str] = None, headers: Optional[Mapping[str, str]] = None) -> FetchResult:
	content = body.encode("utf-8") if isinstance(body, str) else body
	return FetchResult(
		requested_url=url, url=final_url or url, status=status, content=content,
		headers=dict(headers or {}), error="boom" if status is None else None)


class FakeHttp:
	"""Stands in for HttpClient: `responder(url)` returns body text, a FetchResult, or raises."""

	def __init__(self, responder: Callable[[str], Union[str, FetchResult]]):
		self._responder = responder
		self.requests: list[str] = []

	def get(self, url: str, headers=None) -> FetchResult:
		self.requests.append(url)
		value = self._responder(url)
		return value if isinstance(value, FetchResult) else page(url, value)


@pytest.fixture
def fake_http():
	return FakeHttp
