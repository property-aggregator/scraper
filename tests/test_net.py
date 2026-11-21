import random
from types import SimpleNamespace

from curl_cffi import requests as curl_requests

from property_scraper.net import HttpClient, LongPause, RateLimiter, RetryPolicy, RoundRobinProxyPool
from property_scraper.net.result import FetchResult


class FakeClock:
	def __init__(self):
		self.now = 0.0
		self.sleeps = []

	def __call__(self):
		return self.now

	def sleep(self, seconds):
		self.sleeps.append(seconds)
		self.now += seconds


def test_rate_limiter_waits_per_key():
	clock = FakeClock()
	limiter = RateLimiter(min_delay=3.0, jitter=0.0, clock=clock, sleep=clock.sleep)

	limiter.wait("otodom.pl")
	limiter.wait("olx.pl")  # other domain: no wait
	assert clock.sleeps == []

	clock.now += 1.0
	limiter.wait("otodom.pl")
	assert clock.sleeps == [2.0]


def test_rate_limiter_jitter_stays_in_range():
	clock = FakeClock()
	limiter = RateLimiter(min_delay=3.0, jitter=3.0, clock=clock, sleep=clock.sleep, rng=random.Random(1))

	for _ in range(50):
		limiter.wait("olx.pl")

	assert all(3.0 <= pause <= 6.0 for pause in clock.sleeps)
	assert max(clock.sleeps) - min(clock.sleeps) > 1.0  # actually random, not a fixed tick


def test_rate_limiter_inserts_long_pauses_per_domain():
	clock = FakeClock()
	limiter = RateLimiter(
		min_delay=3.0, jitter=0.0, long_pause=LongPause(40, 80, 20.0, 60.0),
		clock=clock, sleep=clock.sleep, rng=random.Random(7))

	for _ in range(400):
		limiter.wait("olx.pl")

	long_pauses = [pause - 3.0 for pause in clock.sleeps if pause > 3.0]
	regular = [pause for pause in clock.sleeps if pause == 3.0]
	assert 400 // 80 <= len(long_pauses) <= 400 // 40
	assert all(20.0 <= pause <= 60.0 for pause in long_pauses)
	assert len(regular) + len(long_pauses) == len(clock.sleeps)

	# Another domain has its own counter: no long pause in its first requests
	before = len(clock.sleeps)
	clock.now += 1000
	for _ in range(10):
		limiter.wait("otodom.pl")
	assert all(pause == 3.0 for pause in clock.sleeps[before:])


def test_long_pause_can_be_disabled():
	clock = FakeClock()
	limiter = RateLimiter(
		min_delay=1.0, long_pause=LongPause(0, 0, 20.0, 60.0), clock=clock, sleep=clock.sleep)

	for _ in range(200):
		limiter.wait("olx.pl")

	assert set(clock.sleeps) == {1.0}


class FakeSession:
	def __init__(self, outcomes):
		self.outcomes = list(outcomes)
		self.calls = 0

	def get(self, url, timeout, headers):
		self.calls += 1
		outcome = self.outcomes.pop(0)
		if isinstance(outcome, Exception):
			raise outcome
		status, headers = outcome
		return SimpleNamespace(url=url, status_code=status, content=b"ok", headers=headers)


def client(session, attempts=3, proxies=None):
	sleeps = []
	http = HttpClient(
		rate_limiter=RateLimiter(0.0),
		timeout=5,
		retry=RetryPolicy(attempts=attempts, backoff=1.0),
		proxies=proxies,
		session_factory=lambda proxy: session,
		sleep=sleeps.append)
	return http, sleeps


def test_returns_status_instead_of_raising():
	session = FakeSession([(404, {})])
	http, sleeps = client(session)

	result = http.get("https://www.otodom.pl/pl/oferta/x")

	assert result.status == 404
	assert session.calls == 1  # 404 is not retried
	assert sleeps == []


def test_retries_network_errors_and_5xx_then_succeeds():
	session = FakeSession([curl_requests.exceptions.RequestException("reset"), (503, {}), (200, {})])
	http, sleeps = client(session)

	result = http.get("https://www.olx.pl/")

	assert result.ok
	assert session.calls == 3
	assert sleeps == [1.0, 2.0]


def test_honours_retry_after_and_gives_up():
	session = FakeSession([(429, {"Retry-After": "7"}), (429, {"Retry-After": "7"})])
	http, sleeps = client(session, attempts=2)

	result = http.get("https://www.olx.pl/")

	assert result.status == 429
	assert result.headers["retry-after"] == "7"
	assert sleeps == [7.0]


def test_network_error_after_last_attempt_has_no_status():
	session = FakeSession([curl_requests.exceptions.RequestException("timeout")])
	http, _ = client(session, attempts=1)

	result = http.get("https://www.olx.pl/")

	assert result.status is None
	assert "timeout" in result.error


def test_proxy_pool_rotates_and_skips_blocked_proxy():
	clock = FakeClock()
	pool = RoundRobinProxyPool(["http://a", "http://b"], cooldown=60, clock=clock)
	blocked = FetchResult(requested_url="u", url="u", status=403)

	assert pool.acquire("olx.pl") == "http://a"
	pool.report("http://a", "olx.pl", blocked)

	assert [pool.acquire("olx.pl") for _ in range(3)] == ["http://b", "http://b", "http://b"]
	assert pool.acquire("otodom.pl") == "http://a"  # blocks are per domain

	clock.now += 61
	assert {pool.acquire("olx.pl") for _ in range(2)} == {"http://a", "http://b"}
