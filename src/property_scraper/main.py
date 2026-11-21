import argparse
import logging
import signal
import sys
import threading
import uuid

from property_scraper.config.settings import settings
from property_scraper.domain import SearchSpec
from property_scraper.jobs import (
	JobContext,
	build_context,
	check_offer,
	run_first_page,
	run_full_scrape,
	scrape_first_page,
	scrape_full,
)
from property_scraper.messaging import ExpirationCheckRequest
from property_scraper.runtime import ScraperScheduler, VerifyWorker

logger = logging.getLogger(__name__)

MODES = {
	"scheduler": "periodic scraping (first page + daily full scrape)",
	"verify-worker": "answer expiration check requests from the backend",
	"worker": "scheduler + verify-worker in one process (one shared rate limit per portal)",
	"first-page": "one-time first page scrape, published to RabbitMQ",
	"full-scrape": "one-time full scrape, published to RabbitMQ",
	"test": "first page of every source, printed instead of published",
	"check": "check whether one offer URL is still active (no RabbitMQ)",
}


def configure_logging() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
		handlers=[logging.StreamHandler(sys.stdout)])


def stop_on_signals() -> threading.Event:
	stop = threading.Event()

	def handler(signum, _frame):
		logger.info("Received signal %s, shutting down", signum)
		stop.set()

	for name in ("SIGINT", "SIGTERM"):
		if hasattr(signal, name):
			signal.signal(getattr(signal, name), handler)
	return stop


def run_scheduler(context: JobContext, stop: threading.Event) -> None:
	ScraperScheduler(context, settings.scraper.first_page_interval, settings.scraper.full_scrape_time).run(stop)


def run_verify_worker(context: JobContext, stop: threading.Event) -> None:
	VerifyWorker(context).run(stop)


def run_worker(context: JobContext, stop: threading.Event) -> None:
	verifier = threading.Thread(target=run_verify_worker, args=(context, stop), name="verify-worker")
	verifier.start()
	try:
		run_scheduler(context, stop)
	finally:
		stop.set()
		verifier.join()


def run_test(context: JobContext, sources: list[SearchSpec]) -> None:
	logger.info("Running in test mode (no RabbitMQ)")

	for spec in sources:
		offers = context.portals.get(spec.portal).create_scraper(context.http, spec).scrape_first_page()
		print(f"\n[{spec}] Found {len(offers)} offers:\n")

		for i, offer in enumerate(offers, 1):
			print(f"{i}. {offer.title}")
			print(f"   Cena: {offer.price} PLN ({offer.price_per_m2} PLN/m²)")
			print(f"   Metraż: {offer.area_m2} m² | Pokoje: {offer.rooms} | Piętro: {offer.floor}")
			print(f"   Lokalizacja: {offer.street}, {offer.district}, {offer.city}, {offer.province}")
			print(f"   Sprzedawca: {offer.seller_type}")
			print(f"   ID: {offer.source_id}")
			print(f"   URL: {offer.source_url}")
			print(f"   Image_URL: {offer.image_url}")
			print(f"   Scraped_at: {offer.scraped_at}")
			print()


def run_check(context: JobContext, portal: str, url: str) -> None:
	request = ExpirationCheckRequest(property_id=uuid.uuid4(), portal=portal, source_url=url)
	response = check_offer(request, context.http, context.portals)
	print(f"{url}\n  status={response.status} httpStatus={response.http_status}")


def parse_args(argv=None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Property Scraper",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="modes:\n" + "\n".join(f"  {name:<14} {help}" for name, help in MODES.items()))
	parser.add_argument("mode", choices=MODES, help="Tryb działania")
	parser.add_argument(
		"--source",
		help="first-page / full-scrape / test: only this source, e.g. olx/sale/apartment/primary "
			"(also when disabled in sources.toml)")
	parser.add_argument("--portal", help="check mode: portal name (otodom, olx)")
	parser.add_argument("--url", help="check mode: offer URL")
	args = parser.parse_args(argv)

	if args.mode == "check" and not (args.portal and args.url):
		parser.error("check mode needs --portal and --url")
	if args.source and args.mode not in ("first-page", "full-scrape", "test"):
		parser.error("--source works only with first-page, full-scrape and test")
	return args


def main(argv=None) -> None:
	args = parse_args(argv)
	configure_logging()
	context = build_context(settings)

	try:
		source = context.sources.find(args.source) if args.source else None
	except ValueError as e:
		sys.exit(f"error: {e}")

	if args.mode == "scheduler":
		run_scheduler(context, stop_on_signals())
	elif args.mode == "verify-worker":
		run_verify_worker(context, stop_on_signals())
	elif args.mode == "worker":
		run_worker(context, stop_on_signals())
	elif args.mode == "first-page":
		if source:
			scrape_first_page(context, source)
		else:
			run_first_page(context)
	elif args.mode == "full-scrape":
		if source:
			scrape_full(context, source)
		else:
			run_full_scrape(context)
	elif args.mode == "test":
		run_test(context, [source] if source else context.sources.enabled())
	elif args.mode == "check":
		run_check(context, args.portal, args.url)


if __name__ == "__main__":
	main()
