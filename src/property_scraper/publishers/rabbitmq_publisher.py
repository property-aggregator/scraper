import json
import logging
from typing import List

import pika
from pika.exceptions import AMQPConnectionError

from property_scraper.models.offer import Offer
from property_scraper.config.settings import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:

	def __init__(self):
		self.connection = None
		self.channel = None

	def connect(self):
		try:
			credentials = pika.PlainCredentials(
				settings.rabbitmq.username,
				settings.rabbitmq.password)

			parameters = pika.ConnectionParameters(
				host=settings.rabbitmq.host,
				port=settings.rabbitmq.port,
				credentials=credentials,
				heartbeat=600,
				blocked_connection_timeout=300)

			self.connection = pika.BlockingConnection(parameters)
			self.channel = self.connection.channel()

			self.channel.exchange_declare(
				exchange=settings.rabbitmq.exchange,
				exchange_type="direct",
				durable=True)

			self.channel.queue_declare(
				queue=settings.rabbitmq.queue,
				durable=True)

			self.channel.queue_bind(
				queue=settings.rabbitmq.queue,
				exchange=settings.rabbitmq.exchange,
				routing_key="offer")
			self.channel.queue_bind(
				queue=settings.rabbitmq.queue,
				exchange=settings.rabbitmq.exchange,
				routing_key="scrape_event")

			logger.info("Connected to RabbitMQ")

		except AMQPConnectionError as e:
			logger.error(f"Failed to connect to RabbitMQ: {e}")
			raise

	def disconnect(self):
		if self.connection and not self.connection.is_closed:
			self.connection.close()
			logger.info("Disconnected from RabbitMQ")

	def publish_offer(self, offer: Offer):
		if not self.channel:
			self.connect()

		if not offer.is_publishable():
			logger.warning(
				"Invalid offer payload: source_id=%s portal=%s title=%s price=%s area_m2=%s rooms=%s",
				offer.source_id,
				offer.portal,
				offer.title,
				offer.price,
				offer.area_m2,
				offer.rooms)
			return

		message = json.dumps(offer.to_dict(), ensure_ascii=False)

		self.channel.basic_publish(
			exchange=settings.rabbitmq.exchange,
			routing_key="offer",
			body=message.encode("utf-8"),
			properties=pika.BasicProperties(
				delivery_mode=2,  # persistent
				content_type="application/json"))

		logger.debug(f"Published offer: {offer.source_id}")

	def publish_offers(self, offers: List[Offer]):
		for offer in offers:
			self.publish_offer(offer)

		logger.info(f"Published {len(offers)} offers")

	def publish_scrape_finished(self, portal: str, scrape_type: str, total_offers: int, completed: bool = True):
		if not self.channel:
			self.connect()

		message = json.dumps({
			"event": "scrape_finished",
			"portal": portal,
			"scrapeType": scrape_type,
			"totalOffers": total_offers,
			"completed": completed,
		}, ensure_ascii=False)

		self.channel.basic_publish(
			exchange=settings.rabbitmq.exchange,
			routing_key="scrape_event",
			body=message.encode("utf-8"),
			properties=pika.BasicProperties(
				delivery_mode=2,
				content_type="application/json"))

		logger.info(f"Published scrape_finished event: {portal} / {scrape_type}")

	def __enter__(self):
		self.connect()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.disconnect()
