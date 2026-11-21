"""Scrape jobs.

`scrape_first_page` / `scrape_full` handle a single source: they are the unit of work to schedule
separately (e.g. one Celery task per source). `run_first_page` / `run_full_scrape` run every
enabled source, portals in parallel.
"""
import logging
import random
import threading
from typing import Callable, Iterable

from property_scraper.domain import SearchSpec
from property_scraper.jobs.context import JobContext
from property_scraper.messaging import ScrapeFinishedEvent
from property_scraper.portals import ListingScraper, ScrapeReport

logger = logging.getLogger(__name__)

FIRST_PAGE = "FIRST_PAGE"
FULL = "FULL"

SourceJob = Callable[[JobContext, SearchSpec], None]


def run_first_page(context: JobContext) -> None:
	logger.info("Running first page scrape")
	run_per_portal(context, "first-page", scrape_first_page)


def run_full_scrape(context: JobContext) -> None:
	logger.info("Running full scrape")
	run_per_portal(context, "full-scrape", scrape_full)


def group_by_portal(sources: Iterable[SearchSpec]) -> dict[str, list[SearchSpec]]:
	groups: dict[str, list[SearchSpec]] = {}
	for spec in sources:
		groups.setdefault(spec.portal, []).append(spec)
	return groups


def run_per_portal(context: JobContext, job_name: str, job: SourceJob) -> None:
	"""Runs `job` for every enabled source: portals in parallel, sources of one portal one after another
	with a random pause (`context.source_pause`) in between.

	Sources of the same portal share its rate limit, so running them in parallel would not be
	faster, only interleave their requests. A failing source or portal does not stop the others.
	"""
	sources = context.sources.enabled()
	if not sources:
		logger.warning("No enabled sources, nothing to do for %s", job_name)
		return
	logger.info("%s: %s", job_name, ", ".join(spec.label for spec in sources))
	def run_portal(specs: list[SearchSpec]) -> None:
		for index, spec in enumerate(specs):
			if index:
				_pause_between_sources(context, specs[index - 1], spec)
			try:
				job(context, spec)
			except Exception:
				logger.exception("[%s] %s failed", spec, job_name)

	# Daemon threads: on shutdown (SIGTERM) the process exits instead of waiting for a long scrape.
	threads = [
		threading.Thread(target=run_portal, args=(specs,), name=f"{job_name}-{portal}", daemon=True)
		for portal, specs in group_by_portal(sources).items()]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()


def _pause_between_sources(context: JobContext, previous: SearchSpec, following: SearchSpec) -> None:
	low, high = context.source_pause
	if high <= 0:
		return
	pause = random.uniform(low, high)
	logger.info("[%s] Pausing %.0fs before %s", previous.portal, pause, following)
	context.sleep(pause)


def _scraper(context: JobContext, spec: SearchSpec) -> ListingScraper:
	return context.portals.get(spec.portal).create_scraper(context.http, spec)


def scrape_first_page(context: JobContext, spec: SearchSpec) -> None:
	offers = _scraper(context, spec).scrape_first_page()
	logger.info("[%s] Found %s offers", spec, len(offers))

	# One connection per source and thread: pika connections are not thread-safe.
	with context.publisher_factory() as publisher:
		publisher.publish_offers(offers)
		publisher.publish_scrape_finished(ScrapeFinishedEvent(
			portal=spec.portal, source=spec.label, scrape_type=FIRST_PAGE,
			total_offers=len(offers), completed=True))


def scrape_full(context: JobContext, spec: SearchSpec) -> None:
	scraper = _scraper(context, spec)
	report = ScrapeReport(spec)

	with context.publisher_factory() as publisher:
		try:
			for batch in scraper.scrape_all(report):
				publisher.publish_offers(batch)
		except Exception as e:
			logger.exception("[%s] Full scrape interrupted", spec)
			report.errors.append(str(e))
			report.completed = False

		publisher.publish_scrape_finished(ScrapeFinishedEvent(
			portal=spec.portal, source=spec.label, scrape_type=FULL,
			total_offers=report.offers, completed=report.completed))

	logger.info(
		"[%s] Total: %s offers on %s pages (completed=%s, errors=%s)",
		spec, report.offers, report.pages, report.completed, len(report.errors))
