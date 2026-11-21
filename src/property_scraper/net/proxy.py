import itertools
import logging
import threading
import time
from typing import Callable, Optional, Protocol, Sequence

from property_scraper.net.result import FetchResult

logger = logging.getLogger(__name__)


class ProxyProvider(Protocol):
	def acquire(self, domain: str) -> Optional[str]:
		"""Proxy URL to use for the next request to `domain`, or None for a direct connection."""

	def report(self, proxy: Optional[str], domain: str, result: FetchResult) -> None:
		"""Feedback after a request, so blocked proxies can be rotated out."""


class NoProxy:
	def acquire(self, domain: str) -> Optional[str]:
		return None

	def report(self, proxy: Optional[str], domain: str, result: FetchResult) -> None:
		pass


class RoundRobinProxyPool:
	"""Rotates proxies; a proxy blocked (403/429) by a domain is skipped for that domain for `cooldown` seconds."""

	def __init__(self, proxies: Sequence[str], cooldown: float, clock: Callable[[], float] = time.monotonic):
		if not proxies:
			raise ValueError("RoundRobinProxyPool needs at least one proxy")
		self._proxies = list(proxies)
		self._cycle = itertools.cycle(self._proxies)
		self._cooldown = cooldown
		self._clock = clock
		self._blocked_until: dict[tuple[str, str], float] = {}
		self._lock = threading.Lock()

	def acquire(self, domain: str) -> Optional[str]:
		with self._lock:
			now = self._clock()
			for _ in range(len(self._proxies)):
				proxy = next(self._cycle)
				if self._blocked_until.get((proxy, domain), 0) <= now:
					return proxy
			# Every proxy is cooling down: use the one that recovers first rather than stalling.
			return min(self._proxies, key=lambda p: self._blocked_until.get((p, domain), 0))

	def report(self, proxy: Optional[str], domain: str, result: FetchResult) -> None:
		if proxy is None or not result.blocked:
			return
		with self._lock:
			self._blocked_until[(proxy, domain)] = self._clock() + self._cooldown
		logger.warning("Proxy blocked by %s (%s), cooling down for %ss", domain, result.describe(), self._cooldown)


def create_proxy_provider(proxies: Sequence[str], cooldown: float) -> ProxyProvider:
	return RoundRobinProxyPool(proxies, cooldown) if proxies else NoProxy()
