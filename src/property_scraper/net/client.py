import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional
from urllib.parse import urlsplit

from curl_cffi import requests as curl_requests

from property_scraper.net.proxy import NoProxy, ProxyProvider
from property_scraper.net.rate_limiter import RateLimiter
from property_scraper.net.result import FetchResult

logger = logging.getLogger(__name__)

MAX_RETRY_AFTER = 60.0
DEFAULT_HEADERS = {"Accept-Language": "pl-PL,pl;q=0.9"}


@dataclass(frozen=True)
class RetryPolicy:
	attempts: int = 3
	backoff: float = 3.0  # seconds, multiplied by the attempt number

	def delay(self, attempt: int, result: FetchResult) -> float:
		retry_after = _parse_retry_after(result.headers.get("retry-after"))
		if retry_after is not None:
			return min(retry_after, MAX_RETRY_AFTER)
		return attempt * self.backoff


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
	try:
		return float(value) if value is not None else None
	except ValueError:
		return None  # HTTP-date form is not worth supporting here


def _default_session_factory(proxy: Optional[str]):
	# Plain requests gets 403 (TLS fingerprinting), so impersonate Chrome.
	# Headers, including User-Agent, come from the impersonation profile.
	return curl_requests.Session(impersonate="chrome", headers=DEFAULT_HEADERS, proxy=proxy)


class HttpClient:
	"""Single entry point for HTTP: rate limiting per domain, retries, proxies.

	Returns a FetchResult instead of raising, so callers can act on the status code.
	Thread-safe: each thread gets its own curl_cffi session per proxy.
	"""

	def __init__(
		self,
		rate_limiter: RateLimiter,
		timeout: float,
		retry: RetryPolicy = RetryPolicy(),
		proxies: Optional[ProxyProvider] = None,
		session_factory: Callable[[Optional[str]], object] = _default_session_factory,
		sleep: Callable[[float], None] = time.sleep,
	):
		self._rate_limiter = rate_limiter
		self._timeout = timeout
		self._retry = retry
		self._proxies = proxies or NoProxy()
		self._session_factory = session_factory
		self._sleep = sleep
		self._local = threading.local()

	def get(self, url: str, headers: Optional[Mapping[str, str]] = None) -> FetchResult:
		domain = urlsplit(url).hostname or ""
		result = None

		for attempt in range(1, self._retry.attempts + 1):
			self._rate_limiter.wait(domain)
			proxy = self._proxies.acquire(domain)

			result = self._get_once(url, proxy, headers)
			self._proxies.report(proxy, domain, result)

			if not result.retriable or attempt == self._retry.attempts:
				break

			delay = self._retry.delay(attempt, result)
			logger.warning(
				"Attempt %s/%s for %s failed (%s), retrying in %.1fs",
				attempt, self._retry.attempts, url, result.describe(), delay)
			self._sleep(delay)

		return result

	def _get_once(self, url: str, proxy: Optional[str], headers: Optional[Mapping[str, str]]) -> FetchResult:
		logger.info("Fetching: %s", url)
		try:
			response = self._session(proxy).get(url, timeout=self._timeout, headers=dict(headers or {}))
		except curl_requests.exceptions.RequestException as e:
			return FetchResult(requested_url=url, url=url, status=None, error=str(e))

		return FetchResult(
			requested_url=url,
			url=str(response.url),
			status=response.status_code,
			content=response.content,
			headers={key.lower(): value for key, value in response.headers.items()})

	def _session(self, proxy: Optional[str]):
		sessions = getattr(self._local, "sessions", None)
		if sessions is None:
			sessions = self._local.sessions = {}
		if proxy not in sessions:
			sessions[proxy] = self._session_factory(proxy)
		return sessions[proxy]
