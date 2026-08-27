import logging
import schedule
import time
from typing import List, Type

from property_scraper.scrapers.base_scraper import BaseScraper
from property_scraper.publishers.rabbitmq_publisher import RabbitMQPublisher
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)


class ScraperScheduler:

    def __init__(self, scrapers: List[Type[BaseScraper]]):
        self.scraper_classes = scrapers
        self.publisher = RabbitMQPublisher()

    def run_first_page_scrape(self):
        logger.info("Running first page scrape for all scrapers")

        for scraper_class in self.scraper_classes:
            try:
                scraper = scraper_class()
                offers = scraper.scrape_first_page()

                with RabbitMQPublisher() as publisher:
                    publisher.publish_offers(offers)
                    publisher.publish_scrape_finished(
                        portal=scraper.PORTAL_NAME,
                        scrape_type="FIRST_PAGE",
                        total_offers=len(offers))

            except Exception as e:
                logger.error(f"Error in first page scrape for {scraper_class.PORTAL_NAME}: {e}")

    def run_full_scrape(self):
        logger.info("Running full scrape for all scrapers")

        for scraper_class in self.scraper_classes:
            try:
                scraper = scraper_class()
                total_offers = 0

                with RabbitMQPublisher() as publisher:
                    for offers_batch in scraper.scrape_all_pages():
                        publisher.publish_offers(offers_batch)
                        total_offers += len(offers_batch)

                    publisher.publish_scrape_finished(
                        portal=scraper.PORTAL_NAME,
                        scrape_type="FULL",
                        total_offers=total_offers)

            except Exception as e:
                logger.error(f"Error in full scrape for {scraper_class.PORTAL_NAME}: {e}")

    def start(self):
        logger.info("Starting scheduler")

        schedule.every(settings.scraper.first_page_interval).minutes.do(self.run_first_page_scrape)
        schedule.every().day.at(settings.scraper.full_scrape_time).do(self.run_full_scrape)

        self.run_first_page_scrape()

        while True:
            schedule.run_pending()
            time.sleep(60)
