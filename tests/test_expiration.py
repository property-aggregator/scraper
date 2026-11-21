import json
import uuid

import pytest
from conftest import FakeHttp, page

from property_scraper.domain import Availability
from property_scraper.jobs.expiration import check_offer
from property_scraper.messaging import ExpirationCheckRequest, ExpirationCheckResponse
from property_scraper.portals import default_registry

OTODOM_URL = "https://www.otodom.pl/pl/oferta/mieszkanie-2-pok-ID4E5M1"
OLX_URL = "https://www.olx.pl/d/oferta/mieszkanie-48m2-CID3-ID1cOKky.html"

# Snippets of real responses (2026-11): an active Otodom offer has the flag set to null,
# OLX keeps the ad state in __PRERENDERED_STATE__ and has the "inactive" text in its translations.
OTODOM_ACTIVE = '<script id="__NEXT_DATA__">{"ad":{"similarAdsLinkUrl":"","shouldShowExpiredAdPage":null}}</script>'
OTODOM_EXPIRED = '<script id="__NEXT_DATA__">{"ad":{"shouldShowExpiredAdPage":true}}</script>'
OLX_TRANSLATIONS = '{"ad.inactive.message.title":"To ogłoszenie nie jest już dostępne"}'


def olx_page(ad: dict) -> str:
	state = {"ad": {"ad": ad}}
	return f"<script>window.__PRERENDERED_STATE__= {json.dumps(json.dumps(state))};</script>{OLX_TRANSLATIONS}"


def check(portal: str, url: str, result) -> ExpirationCheckResponse:
	request = ExpirationCheckRequest(property_id=uuid.uuid4(), portal=portal, source_url=url)
	http = FakeHttp(lambda requested: result if not callable(result) else result(requested))
	response = check_offer(request, http, default_registry())
	assert response.property_id == request.property_id
	return response


@pytest.mark.parametrize("status, expected", [
	(404, Availability.EXPIRED),
	(410, Availability.EXPIRED),
	(403, Availability.UNKNOWN),
	(429, Availability.UNKNOWN),
	(500, Availability.UNKNOWN),
	(503, Availability.UNKNOWN),
	(None, Availability.UNKNOWN),
])
def test_status_codes(status, expected):
	response = check("otodom", OTODOM_URL, page(OTODOM_URL, status=status))

	assert response.status == expected
	assert response.http_status == status


def test_otodom_active_and_expired_pages():
	assert check("otodom", OTODOM_URL, page(OTODOM_URL, OTODOM_ACTIVE)).status == Availability.ACTIVE
	assert check("otodom", OTODOM_URL, page(OTODOM_URL, OTODOM_EXPIRED)).status == Availability.EXPIRED



def test_otodom_page_without_offer_data_is_unknown():
	# e.g. a captcha / interstitial served with 200
	assert check("otodom", OTODOM_URL, page(OTODOM_URL, "<html>captcha</html>")).status == Availability.UNKNOWN


def test_olx_active_page_is_not_expired_by_translation_text():
	result = page(OLX_URL, olx_page({"status": "active", "isActive": True}))

	assert check("olx", OLX_URL, result).status == Availability.ACTIVE


@pytest.mark.parametrize("ad", [
	{"status": "removed_by_user", "isActive": False},
	{"status": "outdated"},
	{"isActive": False},
])
def test_olx_inactive_ad_state_is_expired(ad):
	assert check("olx", OLX_URL, page(OLX_URL, olx_page(ad))).status == Availability.EXPIRED


def test_otodom_flag_false_is_active():
	body = '<script id="__NEXT_DATA__">{"props":{"ad":{"shouldShowExpiredAdPage":false}}}</script>'

	assert check("otodom", OTODOM_URL, page(OTODOM_URL, body)).status == Availability.ACTIVE


def test_otodom_next_data_without_flag_is_unknown(caplog):
	body = '<script id="__NEXT_DATA__">{"props":{}}</script>'

	assert check("otodom", OTODOM_URL, page(OTODOM_URL, body)).status == Availability.UNKNOWN
	assert "Cannot parse Otodom JSON" in caplog.text


def test_olx_html_marker_without_state_is_unknown(caplog):
	result = page(OLX_URL, '<div data-testid="ad-inactive-msg">...</div>')

	assert check("olx", OLX_URL, result).status == Availability.UNKNOWN
	assert "Cannot parse OLX JSON" in caplog.text


def test_olx_page_without_state_is_unknown():
	assert check("olx", OLX_URL, page(OLX_URL, f"<html>{OLX_TRANSLATIONS}</html>")).status == Availability.UNKNOWN


def test_redirect_to_listing_is_expired():
	result = page(OTODOM_URL, "<html>listing</html>", final_url="https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie")

	assert check("otodom", OTODOM_URL, result).status == Availability.EXPIRED


def test_redirect_to_other_offer_url_reads_the_page():
	final = OTODOM_URL + "-canonical"
	assert check("otodom", OTODOM_URL, page(OTODOM_URL, OTODOM_ACTIVE, final_url=final)).status == Availability.ACTIVE


def test_redirect_to_other_domain_is_unknown():
	result = page(OTODOM_URL, "<html></html>", final_url="https://example.com/")

	assert check("otodom", OTODOM_URL, result).status == Availability.UNKNOWN


def test_unknown_portal_is_unknown_without_request():
	def fail(url):
		raise AssertionError("must not fetch")

	response = check("morizon", "https://www.morizon.pl/oferta/1", fail)

	assert response.status == Availability.UNKNOWN
	assert response.http_status is None


@pytest.mark.parametrize("url", [
	"https://evil.example.com/pl/oferta/x",
	"https://www.otodom.pl.evil.com/pl/oferta/x",
	"file:///etc/passwd",
	"http://localhost:15672/api/users",
])
def test_url_outside_portal_domain_is_not_fetched(url):
	def fail(requested):
		raise AssertionError("must not fetch")

	assert check("otodom", url, fail).status == Availability.UNKNOWN


def test_portal_name_is_case_insensitive():
	assert check("OLX", OLX_URL, page(OLX_URL, status=404)).status == Availability.EXPIRED


def test_response_json_matches_backend_contract():
	property_id = uuid.uuid4()
	response = ExpirationCheckResponse(property_id=property_id, status=Availability.EXPIRED, http_status=None)

	assert json.loads(response.to_json()) == {"propertyId": str(property_id), "status": "expired", "httpStatus": None}


def test_request_parses_backend_json():
	property_id = uuid.uuid4()
	body = json.dumps({"propertyId": str(property_id), "portal": "olx", "sourceUrl": OLX_URL})

	request = ExpirationCheckRequest.model_validate_json(body)

	assert (request.property_id, request.portal, request.source_url) == (property_id, "olx", OLX_URL)
