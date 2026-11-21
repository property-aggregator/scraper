import logging

from property_scraper.domain import Availability
from property_scraper.messaging import ExpirationCheckRequest, ExpirationCheckResponse
from property_scraper.net import FetchResult, HttpClient
from property_scraper.portals import Portal, PortalRegistry

logger = logging.getLogger(__name__)

GONE_STATUSES = (404, 410)


def check_offer(request: ExpirationCheckRequest, http: HttpClient, portals: PortalRegistry) -> ExpirationCheckResponse:
	"""Never raises for fetch problems: anything undecidable is reported as `unknown`."""
	portal = portals.get(request.portal)

	if portal is None:
		logger.warning("Expiration check for unknown portal %r (%s)", request.portal, request.property_id)
		return _response(request, Availability.UNKNOWN, None)

	# Only fetch URLs of the portal itself: the URL comes from a queue, not from us.
	if not portal.owns_url(request.source_url):
		logger.warning("URL %s does not belong to portal %s (%s)", request.source_url, portal.name, request.property_id)
		return _response(request, Availability.UNKNOWN, None)

	result = http.get(request.source_url)
	status = classify(portal, result)

	logger.info(
		"Expiration check %s [%s] %s -> %s (%s)",
		request.property_id, portal.name, request.source_url, status, result.describe())
	return _response(request, status, result.status)


def classify(portal: Portal, result: FetchResult) -> Availability:
	if result.status in GONE_STATUSES:
		return Availability.EXPIRED
	if result.status != 200:
		return Availability.UNKNOWN  # 403, 429, 5xx, network error

	if result.redirected and not portal.is_offer_url(result.url):
		# Removed offers may redirect to a listing / home page; another domain is not conclusive.
		return Availability.EXPIRED if portal.owns_url(result.url) else Availability.UNKNOWN

	return portal.availability_from_page(result)


def _response(request: ExpirationCheckRequest, status: Availability, http_status) -> ExpirationCheckResponse:
	return ExpirationCheckResponse(property_id=request.property_id, status=status, http_status=http_status)
