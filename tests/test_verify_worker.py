import json
import threading
import uuid
from types import SimpleNamespace

from property_scraper.config.settings import settings
from property_scraper.domain import Availability
from property_scraper.messaging import ExpirationCheckResponse, topology
from property_scraper.runtime import verify_worker
from property_scraper.runtime.verify_worker import VerifyWorker, handle_message


def body(**overrides) -> bytes:
	message = {"propertyId": str(uuid.uuid4()), "portal": "olx", "sourceUrl": "https://www.olx.pl/d/oferta/x"}
	message.update(overrides)
	return json.dumps(message).encode()


def test_valid_request_is_checked():
	def check(request):
		return ExpirationCheckResponse(property_id=request.property_id, status=Availability.ACTIVE, http_status=200)

	response = handle_message(body(), check)

	assert response.status == Availability.ACTIVE


def test_malformed_request_is_dropped():
	def never(request):
		raise AssertionError("must not check")

	assert handle_message(b"not json", never) is None
	assert handle_message(body(propertyId="not-a-guid"), never) is None
	assert handle_message(json.dumps({"portal": "olx"}).encode(), never) is None


def test_crashing_check_still_answers_unknown():
	property_id = uuid.uuid4()

	def check(request):
		raise RuntimeError("boom")

	response = handle_message(body(propertyId=str(property_id)), check)

	assert response.property_id == property_id
	assert response.status == Availability.UNKNOWN
	assert response.http_status is None


class FakeChannel:
	def __init__(self, deliveries, stop):
		self.deliveries = deliveries
		self.stop = stop
		self.events = []
		self.declared = []

	def confirm_delivery(self):
		self.events.append("confirm")

	def exchange_declare(self, **kwargs):
		pass

	def queue_declare(self, queue, **kwargs):
		self.declared.append((queue, kwargs))

	def queue_bind(self, **kwargs):
		pass

	def basic_qos(self, prefetch_count):
		self.events.append(f"qos:{prefetch_count}")

	def consume(self, queue, inactivity_timeout):
		assert queue == topology.EXPIRATION_CHECK_REQUEST
		for tag, body in enumerate(self.deliveries, start=1):
			yield SimpleNamespace(delivery_tag=tag), None, body
		yield None, None, None  # inactivity tick
		self.stop.set()
		yield None, None, None

	def basic_publish(self, exchange, routing_key, body, properties):
		self.events.append(("publish", routing_key, json.loads(body)))

	def basic_ack(self, tag):
		self.events.append(("ack", tag))

	def basic_reject(self, tag, requeue):
		self.events.append(("reject", tag, requeue))


def test_worker_publishes_response_before_ack_and_rejects_malformed(monkeypatch):
	stop = threading.Event()
	property_id = str(uuid.uuid4())
	channel = FakeChannel([body(propertyId=property_id), b"garbage"], stop)
	connection = SimpleNamespace(channel=lambda: channel, is_open=False, close=lambda: None)
	monkeypatch.setattr(verify_worker.topology, "open_connection", lambda config: connection)

	def check(request):
		return ExpirationCheckResponse(property_id=request.property_id, status=Availability.EXPIRED, http_status=404)

	context = SimpleNamespace(rabbitmq=settings.rabbitmq)
	VerifyWorker(context, check=check).run(stop)

	published = [event for event in channel.events if isinstance(event, tuple)]
	assert published == [
		("publish", topology.EXPIRATION_CHECK_RESPONSE, {"propertyId": property_id, "status": "expired", "httpStatus": 404}),
		("ack", 1),
		("reject", 2, False),
	]
	assert channel.events[:2] == ["confirm", "qos:1"]
	assert [queue for queue, _ in channel.declared] == [topology.EXPIRATION_CHECK_REQUEST, topology.EXPIRATION_CHECK_RESPONSE]
	assert all(kwargs == {"durable": True, "exclusive": False, "auto_delete": False} for _, kwargs in channel.declared)
