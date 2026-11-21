import json
import logging
from typing import Iterable, Optional

import pika
from pika.adapters.blocking_connection import BlockingChannel

from property_scraper.config.settings import RabbitMQSettings
from property_scraper.domain import Offer
from property_scraper.messaging import topology
from property_scraper.messaging.contracts import ScrapeFinishedEvent

logger = logging.getLogger(__name__)

PERSISTENT_JSON = pika.BasicProperties(delivery_mode=2, content_type="application/json")


def publish_json(channel: BlockingChannel, exchange: str, routing_key: str, body: bytes) -> None:
	"""Publishes a persistent JSON message. With confirm_delivery() on the channel this blocks
	until the broker has taken the message, and raises if it was nacked."""
	channel.basic_publish(exchange=exchange, routing_key=routing_key, body=body, properties=PERSISTENT_JSON)


class OfferPublisher:
	"""Publishes scraped offers. One connection per job; pika connections are not thread-safe."""

	def __init__(self, config: RabbitMQSettings):
		self._config = config
		self._connection: Optional[pika.BlockingConnection] = None
		self._channel: Optional[BlockingChannel] = None

	def __enter__(self) -> "OfferPublisher":
		self._connection = topology.open_connection(self._config)
		self._channel = self._connection.channel()
		self._channel.confirm_delivery()
		topology.declare_offers(self._channel, self._config)
		logger.info("Connected to RabbitMQ")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._connection and self._connection.is_open:
			self._connection.close()
			logger.info("Disconnected from RabbitMQ")

	def publish_offers(self, offers: Iterable[Offer]) -> int:
		count = 0
		for offer in offers:
			body = json.dumps(offer.to_dict(), ensure_ascii=False).encode("utf-8")
			publish_json(self._channel, self._config.exchange, topology.OFFER_ROUTING_KEY, body)
			count += 1
		logger.info("Published %s offers", count)
		return count

	def publish_scrape_finished(self, event: ScrapeFinishedEvent) -> None:
		publish_json(self._channel, self._config.exchange, topology.SCRAPE_EVENT_ROUTING_KEY, event.to_json())
		logger.info("Published scrape_finished event: %s / %s", event.source, event.scrape_type)
