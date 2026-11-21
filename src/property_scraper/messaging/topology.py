import logging

import pika
from pika.adapters.blocking_connection import BlockingChannel

from property_scraper.config.settings import RabbitMQSettings

logger = logging.getLogger(__name__)

# Routing keys and queue names shared with the backend (PropertyAggregator RabbitMqConnection).
OFFER_ROUTING_KEY = "offer"
# Not consumed by the backend yet; published without a bound queue (RabbitMQ drops it) so it
# no longer lands in the offers queue, where the backend tried to read it as an offer.
SCRAPE_EVENT_ROUTING_KEY = "scrape_event"
EXPIRATION_CHECK_REQUEST = "expiration_check_request"  # queue name == routing key
EXPIRATION_CHECK_RESPONSE = "expiration_check_response"  # queue name == routing key


def open_connection(config: RabbitMQSettings) -> pika.BlockingConnection:
	parameters = pika.ConnectionParameters(
		host=config.host,
		port=config.port,
		credentials=pika.PlainCredentials(config.username, config.password),
		heartbeat=config.heartbeat,
		blocked_connection_timeout=300)
	return pika.BlockingConnection(parameters)


def declare_queue(channel: BlockingChannel, exchange: str, queue: str, routing_key: str) -> None:
	"""Same arguments as the backend; any difference makes RabbitMQ answer PRECONDITION_FAILED."""
	channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)
	channel.queue_declare(queue=queue, durable=True, exclusive=False, auto_delete=False)
	channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)


def declare_offers(channel: BlockingChannel, config: RabbitMQSettings) -> None:
	declare_queue(channel, config.exchange, config.queue, OFFER_ROUTING_KEY)


def declare_expiration_checks(channel: BlockingChannel, config: RabbitMQSettings) -> None:
	declare_queue(channel, config.exchange, EXPIRATION_CHECK_REQUEST, EXPIRATION_CHECK_REQUEST)
	declare_queue(channel, config.exchange, EXPIRATION_CHECK_RESPONSE, EXPIRATION_CHECK_RESPONSE)
