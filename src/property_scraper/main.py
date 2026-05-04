import logging
import sys
import argparse

from property_scraper.scrapers.otodom_scraper import OtodomScraper
from property_scraper.scheduler.scheduler import ScraperScheduler
from property_scraper.publishers.rabbitmq_publisher import RabbitMQPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

SCRAPERS = [
    OtodomScraper,
    # OlxScraper,
    # MorizonScraper,
]


def run_scheduler():
    logger.info("Starting scraper in scheduler mode")
    scheduler = ScraperScheduler(SCRAPERS)
    scheduler.start()


def run_first_page():
    logger.info("Running one-time first page scrape")

    for scraper_class in SCRAPERS:
        scraper = scraper_class()
        offers = scraper.scrape_first_page()

        logger.info(f"[{scraper.PORTAL_NAME}] Found {len(offers)} offers")

        for offer in offers[:3]:
            logger.info(f"  - {offer.title[:50]}... | {offer.price} PLN | {offer.source_id}")

        try:
            with RabbitMQPublisher() as publisher:
                publisher.publish_offers(offers)
                publisher.publish_scrape_finished(
                    portal=scraper.PORTAL_NAME,
                    scrape_type="FIRST_PAGE",
                    total_offers=len(offers))
        except Exception as e:
            logger.warning(f"Could not publish to RabbitMQ: {e}")


def run_full_scrape():
    logger.info("Running one-time full scrape")

    for scraper_class in SCRAPERS:
        scraper = scraper_class()
        total = 0

        try:
            with RabbitMQPublisher() as publisher:
                for offers_batch in scraper.scrape_all_pages():
                    publisher.publish_offers(offers_batch)
                    total += len(offers_batch)

                publisher.publish_scrape_finished(
                    portal=scraper.PORTAL_NAME,
                    scrape_type="FULL",
                    total_offers=total)
        except Exception as e:
            logger.warning(f"Could not publish to RabbitMQ: {e}")

        logger.info(f"[{scraper.PORTAL_NAME}] Total: {total} offers")


def run_test():
    logger.info("Running in test mode (no RabbitMQ)")

    for scraper_class in SCRAPERS:
        scraper = scraper_class()
        offers = scraper.scrape_first_page()

        logger.info(f"\n[{scraper.PORTAL_NAME}] Found {len(offers)} offers:\n")

        for i, offer in enumerate(offers, 1):
            print(f"{i}. {offer.title}")
            print(f"   Cena: {offer.price} PLN ({offer.price_per_m2} PLN/m²)")
            print(f"   Metraż: {offer.area_m2} m² | Pokoje: {offer.rooms} | Piętro: {offer.floor}")
            print(f"   Lokalizacja: {offer.location_raw}")
            print(f"   Sprzedawca: {offer.seller_type}")
            print(f"   ID: {offer.source_id}")
            print(f"   URL: {offer.source_url}")
            print(f"   Image_URL: {offer.image_url}")
            print(f"   Scraped_at: {offer.scraped_at}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Property Scraper")
    parser.add_argument(
        "mode",
        choices=["scheduler", "first-page", "full-scrape", "test"],
        help="Tryb działania")

    args = parser.parse_args()

    if args.mode == "scheduler":
        run_scheduler()
    elif args.mode == "first-page":
        run_first_page()
    elif args.mode == "full-scrape":
        run_full_scrape()
    elif args.mode == "test":
        run_test()


if __name__ == "__main__":
    main()
