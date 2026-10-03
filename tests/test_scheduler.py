import logging
import os
import threading

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

from property_scraper.scheduler.scheduler import ScraperScheduler, FULL_SCRAPE_JOB


def wait_for_lock_release(scheduler: ScraperScheduler, name: str):
	lock = scheduler._locks[name]
	assert lock.acquire(timeout=2)
	lock.release()


def test_job_receives_scraper_classes():
	received = []
	done = threading.Event()

	def job(scrapers):
		received.append(scrapers)
		done.set()

	scheduler = ScraperScheduler(["scraper"])
	scheduler._run_job(FULL_SCRAPE_JOB, job)

	assert done.wait(2)
	assert received == [["scraper"]]


def test_running_job_is_not_started_twice(caplog):
	started = threading.Event()
	release = threading.Event()
	calls = []

	def slow_job(scrapers):
		calls.append(1)
		started.set()
		release.wait(2)

	scheduler = ScraperScheduler([])
	scheduler._run_job(FULL_SCRAPE_JOB, slow_job)
	assert started.wait(2)

	with caplog.at_level(logging.WARNING):
		scheduler._run_job(FULL_SCRAPE_JOB, slow_job)

	release.set()
	wait_for_lock_release(scheduler, FULL_SCRAPE_JOB)

	assert calls == [1]
	assert "still running" in caplog.text


def test_crashing_job_is_logged_and_lock_released(caplog):
	def broken_job(scrapers):
		raise RuntimeError("boom")

	scheduler = ScraperScheduler([])

	with caplog.at_level(logging.ERROR):
		scheduler._run_job(FULL_SCRAPE_JOB, broken_job)
		wait_for_lock_release(scheduler, FULL_SCRAPE_JOB)

	assert "crashed" in caplog.text
	assert "boom" in caplog.text
