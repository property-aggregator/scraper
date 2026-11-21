import logging
import threading
from typing import Callable, Optional

from pika.exceptions import AMQPError
from pydantic import ValidationError

from property_scraper.domain import Availability
from property_scraper.jobs import JobContext, check_offer
from property_scraper.messaging import ExpirationCheckRequest, ExpirationCheckResponse, topology
from property_scraper.messaging.publisher import publish_json

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5.0
POLL_INTERVAL = 1.0  # how often the consume loop checks the stop flag

Checker = Callable[[ExpirationCheckRequest], ExpirationCheckResponse]


def handle_message(body: bytes, check: Checker) -> Optional[ExpirationCheckResponse]:
	"""Response to send for a request, or None when the message is malformed (to be dropped)."""
	try:
		request = ExpirationCheckRequest.model_validate_json(body)
	except ValidationError as e:
		logger.error("Dropping malformed expiration check request %r: %s", body[:500], e)
		return None

	try:
		return check(request)
	except Exception:
		# Must not happen (check_offer maps fetch errors to unknown), but never lose the reply.
		logger.exception("Expiration check of %s crashed", request.property_id)
		return ExpirationCheckResponse(property_id=request.property_id, status=Availability.UNKNOWN)


class VerifyWorker:
	"""Consumes expiration_check_request, replies on expiration_check_response.

	A request is acked only after its response is confirmed by the broker; if the connection
	drops in between, RabbitMQ redelivers the request (the check is idempotent).
	"""

	def __init__(self, context: JobContext, check: Optional[Checker] = None):
		self._context = context
		self._check = check or (lambda request: check_offer(request, context.http, context.portals))

	def run(self, stop: threading.Event) -> None:
		logger.info("Starting verify worker")
		while not stop.is_set():
			try:
				self._consume(stop)
			except AMQPError as e:
				logger.error("RabbitMQ connection lost (%r), reconnecting in %ss", e, RECONNECT_DELAY)
				stop.wait(RECONNECT_DELAY)
		logger.info("Verify worker stopped")

	def _consume(self, stop: threading.Event) -> None:
		config = self._context.rabbitmq
		connection = topology.open_connection(config)
		try:
			channel = connection.channel()
			channel.confirm_delivery()
			topology.declare_expiration_checks(channel, config)
			# One at a time: checks are rate-limited anyway, and others stay available on redelivery.
			channel.basic_qos(prefetch_count=1)
			logger.info("Consuming from queue '%s'", topology.EXPIRATION_CHECK_REQUEST)

			for method, _properties, body in channel.consume(
					topology.EXPIRATION_CHECK_REQUEST, inactivity_timeout=POLL_INTERVAL):
				if stop.is_set():
					break
				if method is None:
					continue

				response = handle_message(body, self._check)
				if response is None:
					channel.basic_reject(method.delivery_tag, requeue=False)
					continue

				publish_json(channel, config.exchange, topology.EXPIRATION_CHECK_RESPONSE, response.to_json())
				channel.basic_ack(method.delivery_tag)
		finally:
			if connection.is_open:
				connection.close()
