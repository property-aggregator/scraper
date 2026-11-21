import threading
from types import SimpleNamespace

from conftest import spec

from property_scraper.domain import MarketType
from property_scraper.jobs.scraping import group_by_portal, run_per_portal

OTODOM_SECONDARY = spec("otodom")
OTODOM_PRIMARY = spec("otodom", MarketType.PRIMARY)
OLX = spec("olx")


def context(*sources, source_pause=(0.0, 0.0), sleep=None):
	return SimpleNamespace(
		sources=SimpleNamespace(enabled=lambda: list(sources)),
		source_pause=source_pause,
		sleep=sleep or (lambda seconds: None))


def test_sources_are_grouped_by_portal_in_order():
	assert group_by_portal([OTODOM_SECONDARY, OLX, OTODOM_PRIMARY]) == {
		"otodom": [OTODOM_SECONDARY, OTODOM_PRIMARY],
		"olx": [OLX],
	}


def test_portals_run_in_parallel_and_sources_of_one_portal_in_order():
	both_portals_running = threading.Barrier(2, timeout=2)
	calls = []
	lock = threading.Lock()

	def run_source(ctx, source):
		if source in (OTODOM_SECONDARY, OLX):
			# Deadlocks (BrokenBarrierError) unless Otodom and OLX run at the same time
			both_portals_running.wait()
		with lock:
			calls.append((source, threading.current_thread().name))

	run_per_portal(context(OTODOM_SECONDARY, OTODOM_PRIMARY, OLX), "full-scrape", run_source)

	otodom = [source for source, _ in calls if source.portal == "otodom"]
	assert otodom == [OTODOM_SECONDARY, OTODOM_PRIMARY]
	assert {name for _, name in calls} == {"full-scrape-otodom", "full-scrape-olx"}


def test_failing_source_does_not_stop_others(caplog):
	done = []

	def run_source(ctx, source):
		if source == OTODOM_SECONDARY:
			raise RuntimeError("blocked")
		done.append(source)

	run_per_portal(context(OTODOM_SECONDARY, OTODOM_PRIMARY, OLX), "first-page", run_source)

	assert sorted(done, key=str) == sorted([OTODOM_PRIMARY, OLX], key=str)
	assert "blocked" in caplog.text


def test_random_pause_between_sources_of_the_same_portal_only():
	pauses = []
	order = []
	lock = threading.Lock()

	def run_source(ctx, source):
		with lock:
			order.append(source)

	def sleep(seconds):
		with lock:
			pauses.append(seconds)
			order.append("pause")

	ctx = context(OTODOM_SECONDARY, OTODOM_PRIMARY, OLX, source_pause=(30.0, 90.0), sleep=sleep)
	run_per_portal(ctx, "full-scrape", run_source)

	assert len(pauses) == 1  # only between the two Otodom sources, none for OLX alone
	assert 30.0 <= pauses[0] <= 90.0
	otodom = [step for step in order if step != OLX]
	assert otodom == [OTODOM_SECONDARY, "pause", OTODOM_PRIMARY]


def test_portal_threads_are_daemons():
	daemon = []

	def run_source(ctx, source):
		daemon.append(threading.current_thread().daemon)

	run_per_portal(context(OTODOM_SECONDARY, OLX), "full-scrape", run_source)

	assert daemon == [True, True]