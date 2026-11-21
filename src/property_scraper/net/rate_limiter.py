import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LongPause:
	"""After a random number of requests (after_min..after_max) to a key, wait pause_min..pause_max seconds."""

	after_min: int
	after_max: int
	pause_min: float
	pause_max: float

	@property
	def enabled(self) -> bool:
		return self.after_max > 0


class RateLimiter:
	"""Keeps a delay between requests sharing a key (a domain): `min_delay` + random 0..`jitter`,
	plus an occasional longer pause (`long_pause`), so traffic does not tick like a clock.

	Thread-safe: a scrape job and the verify worker hitting the same portal wait for each other.
	"""

	def __init__(
		self,
		min_delay: float,
		jitter: float = 0.0,
		long_pause: Optional[LongPause] = None,
		clock: Callable[[], float] = time.monotonic,
		sleep: Callable[[float], None] = time.sleep,
		rng: Optional[random.Random] = None,
	):
		self._min_delay = min_delay
		self._jitter = jitter
		self._long_pause = long_pause if long_pause and long_pause.enabled else None
		self._clock = clock
		self._sleep = sleep
		self._rng = rng or random.Random()
		self._next_allowed: dict[str, float] = {}
		self._until_long_pause: dict[str, int] = {}
		self._locks: dict[str, threading.Lock] = {}
		self._registry_lock = threading.Lock()

	def wait(self, key: str) -> None:
		with self._lock_for(key):
			now = self._clock()
			wait_for = self._next_allowed.get(key, now) - now
			if wait_for > 0:
				self._sleep(wait_for)
				now = self._clock()
			self._next_allowed[key] = now + self._next_delay(key)

	def _next_delay(self, key: str) -> float:
		delay = self._min_delay + self._rng.uniform(0, self._jitter)
		if not self._long_pause:
			return delay

		remaining = self._until_long_pause.get(key)
		if remaining is None:
			remaining = self._draw_requests_until_pause()
		remaining -= 1

		if remaining <= 0:
			pause = self._rng.uniform(self._long_pause.pause_min, self._long_pause.pause_max)
			logger.info("Pausing requests to %s for %.0fs", key, pause)
			delay += pause
			remaining = self._draw_requests_until_pause()

		self._until_long_pause[key] = remaining
		return delay

	def _draw_requests_until_pause(self) -> int:
		return self._rng.randint(self._long_pause.after_min, self._long_pause.after_max)

	def _lock_for(self, key: str) -> threading.Lock:
		with self._registry_lock:
			return self._locks.setdefault(key, threading.Lock())
