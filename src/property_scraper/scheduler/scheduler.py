import logging
import schedule
import threading
import time
from typing import Callable, List, Type

from property_scraper import pipeline
from property_scraper.scrapers.base_scraper import BaseScraper
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)

FIRST_PAGE_JOB = "first-page"
FULL_SCRAPE_JOB = "full-scrape"


class ScraperScheduler:

	def __init__(self, scrapers: List[Type[BaseScraper]]):
		self.scraper_classes = scrapers
		self._locks = {
			FIRST_PAGE_JOB: threading.Lock(),
			FULL_SCRAPE_JOB: threading.Lock(),
		}

	def _run_job(self, name: str, job: Callable[[List[Type[BaseScraper]]], None]):
		lock = self._locks[name]

		if not lock.acquire(blocking=False):
			logger.warning(f"Job '{name}' is still running, skipping this run")
			return

		def target():
			try:
				job(self.scraper_classes)
			except Exception:
				logger.exception(f"Job '{name}' crashed")
			finally:
				lock.release()

		threading.Thread(target=target, name=name, daemon=True).start()

	def start(self):
		logger.info("Starting scheduler")

		schedule.every(settings.scraper.first_page_interval).minutes.do(
			self._run_job, FIRST_PAGE_JOB, pipeline.run_first_page)
		schedule.every().day.at(settings.scraper.full_scrape_time).do(
			self._run_job, FULL_SCRAPE_JOB, pipeline.run_full_scrape)

		self._run_job(FIRST_PAGE_JOB, pipeline.run_first_page)

		try:
			while True:
				try:
					schedule.run_pending()
				except Exception:
					logger.exception("Scheduler loop error")
				time.sleep(1)
		except KeyboardInterrupt:
			logger.info("Scheduler stopped")
