import logging
import threading
from typing import Callable

import schedule

from property_scraper.jobs import JobContext, run_first_page, run_full_scrape

logger = logging.getLogger(__name__)

FIRST_PAGE_JOB = "first-page"
FULL_SCRAPE_JOB = "full-scrape"

Job = Callable[[JobContext], None]


class ScraperScheduler:
	"""Runs scrape jobs on a timetable. Jobs are plain functions of JobContext, so this class
	can later be replaced by a task queue (e.g. Celery beat) without touching the jobs."""

	def __init__(self, context: JobContext, first_page_interval: int, full_scrape_time: str):
		self._context = context
		self._first_page_interval = first_page_interval
		self._full_scrape_time = full_scrape_time
		self._scheduler = schedule.Scheduler()
		self._locks = {FIRST_PAGE_JOB: threading.Lock(), FULL_SCRAPE_JOB: threading.Lock()}

	def _run_job(self, name: str, job: Job) -> None:
		lock = self._locks[name]

		if not lock.acquire(blocking=False):
			logger.warning("Job '%s' is still running, skipping this run", name)
			return

		def target():
			try:
				job(self._context)
			except Exception:
				logger.exception("Job '%s' crashed", name)
			finally:
				lock.release()

		threading.Thread(target=target, name=name, daemon=True).start()

	def run(self, stop: threading.Event) -> None:
		logger.info(
			"Starting scheduler (first page every %s min, full scrape at %s)",
			self._first_page_interval, self._full_scrape_time)

		self._scheduler.every(self._first_page_interval).minutes.do(self._run_job, FIRST_PAGE_JOB, run_first_page)
		self._scheduler.every().day.at(self._full_scrape_time).do(self._run_job, FULL_SCRAPE_JOB, run_full_scrape)
		self._run_job(FIRST_PAGE_JOB, run_first_page)

		while not stop.is_set():
			try:
				self._scheduler.run_pending()
			except Exception:
				logger.exception("Scheduler loop error")
			stop.wait(1)

		logger.info("Scheduler stopped")
