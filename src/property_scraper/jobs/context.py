import time
from dataclasses import dataclass, field
from typing import Callable

from property_scraper.config.settings import RabbitMQSettings, Settings
from property_scraper.config.sources import SourceCatalog
from property_scraper.messaging import OfferPublisher
from property_scraper.net import HttpClient, LongPause, RateLimiter, RetryPolicy, create_proxy_provider
from property_scraper.portals import PortalRegistry, default_registry


@dataclass(frozen=True)
class JobContext:
	"""Everything a job needs. Built once per process so all jobs share one rate limiter."""

	http: HttpClient
	portals: PortalRegistry
	sources: SourceCatalog
	rabbitmq: RabbitMQSettings
	publisher_factory: Callable[[], OfferPublisher]
	source_pause: tuple[float, float] = (0.0, 0.0)  # random pause (s) between sources of one portal
	sleep: Callable[[float], None] = field(default=time.sleep, repr=False)


def build_context(settings: Settings) -> JobContext:
	scraper = settings.scraper
	portals = default_registry()

	rate_limiter = RateLimiter(
		scraper.request_delay,
		scraper.request_jitter,
		long_pause=LongPause(
			scraper.long_pause_after_min, scraper.long_pause_after_max,
			scraper.long_pause_min, scraper.long_pause_max))

	http = HttpClient(
		rate_limiter=rate_limiter,
		timeout=scraper.request_timeout,
		retry=RetryPolicy(attempts=scraper.fetch_attempts, backoff=scraper.request_delay),
		proxies=create_proxy_provider(scraper.proxies, scraper.proxy_cooldown))

	return JobContext(
		http=http,
		portals=portals,
		sources=SourceCatalog(scraper.sources_file, portals.validate),
		rabbitmq=settings.rabbitmq,
		publisher_factory=lambda: OfferPublisher(settings.rabbitmq),
		source_pause=(scraper.source_pause_min, scraper.source_pause_max))
