import logging
import threading

from property_scraper.runtime.scheduler import FULL_SCRAPE_JOB, ScraperScheduler

CONTEXT = object()


def make_scheduler() -> ScraperScheduler:
	return ScraperScheduler(CONTEXT, first_page_interval=10, full_scrape_time="02:00")


def wait_for_lock_release(scheduler: ScraperScheduler, name: str):
	lock = scheduler._locks[name]
	assert lock.acquire(timeout=2)
	lock.release()


def test_job_receives_context():
	received = []
	done = threading.Event()

	def job(context):
		received.append(context)
		done.set()

	make_scheduler()._run_job(FULL_SCRAPE_JOB, job)

	assert done.wait(2)
	assert received == [CONTEXT]


def test_running_job_is_not_started_twice(caplog):
	started = threading.Event()
	release = threading.Event()
	calls = []

	def slow_job(context):
		calls.append(1)
		started.set()
		release.wait(2)

	scheduler = make_scheduler()
	scheduler._run_job(FULL_SCRAPE_JOB, slow_job)
	assert started.wait(2)

	with caplog.at_level(logging.WARNING):
		scheduler._run_job(FULL_SCRAPE_JOB, slow_job)

	release.set()
	wait_for_lock_release(scheduler, FULL_SCRAPE_JOB)

	assert calls == [1]
	assert "still running" in caplog.text


def test_crashing_job_is_logged_and_lock_released(caplog):
	def broken_job(context):
		raise RuntimeError("boom")

	scheduler = make_scheduler()

	with caplog.at_level(logging.ERROR):
		scheduler._run_job(FULL_SCRAPE_JOB, broken_job)
		wait_for_lock_release(scheduler, FULL_SCRAPE_JOB)

	assert "crashed" in caplog.text
	assert "boom" in caplog.text


def test_run_returns_when_stopped(monkeypatch):
	import property_scraper.runtime.scheduler as module

	monkeypatch.setattr(module, "run_first_page", lambda context: None)
	stop = threading.Event()
	stop.set()

	make_scheduler().run(stop)  # returns instead of looping forever
