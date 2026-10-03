import logging
from typing import List, Type

from property_scraper.scrapers.base_scraper import BaseScraper
from property_scraper.publishers.rabbitmq_publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)


def run_first_page(scraper_classes: List[Type[BaseScraper]]):
	logger.info("Running first page scrape")

	for scraper_class in scraper_classes:
		try:
			scraper = scraper_class()
			offers = scraper.scrape_first_page()

			logger.info(f"[{scraper.PORTAL_NAME}] Found {len(offers)} offers")
			for offer in offers[:3]:
				logger.info(f"  - {offer.title[:50]}... | {offer.price} PLN | {offer.source_id}")

			with RabbitMQPublisher() as publisher:
				publisher.publish_offers(offers)
				publisher.publish_scrape_finished(
					portal=scraper.PORTAL_NAME,
					scrape_type="FIRST_PAGE",
					total_offers=len(offers))

		except Exception as e:
			logger.exception(f"[{scraper_class.PORTAL_NAME}] First page scrape failed: {e}")


def run_full_scrape(scraper_classes: List[Type[BaseScraper]]):
	logger.info("Running full scrape")

	for scraper_class in scraper_classes:
		try:
			scraper = scraper_class()
			total_offers = 0

			with RabbitMQPublisher() as publisher:
				try:
					for offers_batch in scraper.scrape_all_pages():
						publisher.publish_offers(offers_batch)
						total_offers += len(offers_batch)
				except Exception as e:
					logger.exception(f"[{scraper.PORTAL_NAME}] Full scrape interrupted: {e}")

				publisher.publish_scrape_finished(
					portal=scraper.PORTAL_NAME,
					scrape_type="FULL",
					total_offers=total_offers,
					completed=scraper.completed)

			logger.info(
				f"[{scraper.PORTAL_NAME}] Total: {total_offers} offers (completed={scraper.completed})")

		except Exception as e:
			logger.exception(f"[{scraper_class.PORTAL_NAME}] Full scrape failed: {e}")
