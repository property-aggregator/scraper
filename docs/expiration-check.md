# Expiration check contract (backend ⇄ scraper)

The backend periodically asks the scraper whether stored offers are still listed on their portal.

## RabbitMQ

Exchange `property_scraper` (direct, durable). Both queues are declared by both sides with the same
arguments: `durable=True, exclusive=False, auto_delete=False`, no extra arguments (any difference gives
`PRECONDITION_FAILED`). Queue name = routing key.

| Direction | Queue / routing key | Body (JSON, camelCase) |
|---|---|---|
| backend → scraper | `expiration_check_request` | `{ "propertyId": "<guid>", "portal": "olx", "sourceUrl": "https://…" }` |
| scraper → backend | `expiration_check_response` | `{ "propertyId": "<guid>", "status": "active" \| "expired" \| "unknown", "httpStatus": 200 }` |

- `propertyId` in the response is the one from the request.
- `httpStatus` is `null` when no HTTP response was received (network error, URL not checked).
- Responses are persistent (`delivery_mode=2`, `content_type=application/json`).

## Scraper side (`verify-worker` / `worker` mode)

- `prefetch_count=1`; the request is acked only **after** the broker confirms the response
  (publisher confirms). If the connection drops in between, the request is redelivered; the check is idempotent.
- A malformed request (invalid JSON, missing fields, bad GUID) is rejected without requeue and logged.
- Fetch problems never raise: they are answered with `unknown`.
- The URL is fetched only if its host belongs to the portal (`otodom.pl`, `olx.pl`), otherwise `unknown`.
- Requests share the per-domain rate limit with scraping (`REQUEST_DELAY` + `REQUEST_JITTER`) when run in
  `worker` mode (one process).

### Rules

| Response | Status |
|---|---|
| 404, 410 | `expired` |
| 403, 429, 5xx, network error, unknown portal, foreign URL | `unknown` |
| 200 after a redirect to a non-offer page of the portal (listing, home page) | `expired` |
| 200 after a redirect to another domain | `unknown` |
| 200, Otodom: `shouldShowExpiredAdPage` in `__NEXT_DATA__` is `true` | `expired` |
| 200, Otodom: `shouldShowExpiredAdPage` present but not `true` (active pages have `null`) | `active` |
| 200, OLX: `__PRERENDERED_STATE__.ad.ad` with `isActive=false` or `status != "active"` | `expired` |
| 200, OLX: `__PRERENDERED_STATE__.ad.ad` with `status="active"` | `active` |
| 200 without that JSON (captcha, layout change) | `unknown`, logged as "Cannot parse … JSON" |

Only the portal's JSON is read, never HTML markup.

Checked on real responses (2026-11): non-existent offers return a plain 404 on both portals (no redirect);
active pages match the `active` rules. **The OLX text "To ogłoszenie nie jest już dostępne" must not be
used** – it is part of the translations embedded in every offer page, including active ones.
Not yet confirmed on a real expired offer (200): the exact OLX `status` values and the Otodom flag. Use
`python -m property_scraper.main check --portal <portal> --url <url>` to verify a known expired offer.

## Backend side

- `unknown` must **not** refresh `LastSeenAt` (`MarkSeen`): otherwise an offer behind a persistent block
  (403) never expires. `ExpirationCheckRequestedAt` is already set when the request is sent, so the offer is
  asked again after `RetryAfter` (6 h).
- Lost requests/responses are harmless for the same reason.
