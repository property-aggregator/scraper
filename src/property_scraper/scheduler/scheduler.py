import logging
import schedule
import time
from typing import List, Type

from property_scraper import pipeline
from property_scraper.scrapers.base_scraper import BaseScraper
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)


class ScraperScheduler:

	def __init__(self, scrapers: List[Type[BaseScraper]]):
		self.scraper_classes = scrapers

	def start(self):
		logger.info("Starting scheduler")

		schedule.every(settings.scraper.first_page_interval).minutes.do(
			pipeline.run_first_page, self.scraper_classes)
		schedule.every().day.at(settings.scraper.full_scrape_time).do(
			pipeline.run_full_scrape, self.scraper_classes)

		pipeline.run_first_page(self.scraper_classes)

		while True:
			schedule.run_pending()
			time.sleep(60)
