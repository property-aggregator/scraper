import logging
import sys
import argparse

from property_scraper import pipeline
from property_scraper.scrapers.otodom_scraper import OtodomScraper

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
	from property_scraper.scheduler.scheduler import ScraperScheduler

	logger.info("Starting scraper in scheduler mode")
	scheduler = ScraperScheduler(SCRAPERS)
	scheduler.start()


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
		pipeline.run_first_page(SCRAPERS)
	elif args.mode == "full-scrape":
		pipeline.run_full_scrape(SCRAPERS)
	elif args.mode == "test":
		run_test()


if __name__ == "__main__":
	main()
