BASE_URL = (
    "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie%2Crynek-wtorny/"
    "cala-polska?limit=72&ownerTypeSingleSelect=ALL&by=LATEST&direction=DESC"
)
BASE_ORIGIN = "https://www.otodom.pl"
JSON_LD_XPATH = '//script[@type="application/ld+json"]'
# Listing cards (React SPA) — JSON-LD is often missing on page>1
LISTING_CARD_LINK_CSS = 'a[data-cy="listing-item-link"]'
PORTAL_NAME = "otodom"

