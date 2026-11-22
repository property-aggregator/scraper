# Property Scraper

Python-based scraper for real-estate listings that publishes offers to RabbitMQ.

## Requirements

- Python 3.11+
- RabbitMQ (for publication mode)

## Installation

```bash
python -m venv .venv
. .venv/bin/activate  # Linux/macOS
# or .\.venv\Scripts\activate  # Windows
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuration

The app reads its settings from environment variables and, if present, from a `.env` file in the working directory (run from the project root). Real environment variables take precedence over `.env`. Docker Compose also reads `.env`. All variables from the example below are required, except `SCRAPER_MODE`, which is only used by Docker Compose.

Create `.env` from the template first:

```powershell
Copy-Item .env.example .env
```

Example:

```bash
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_QUEUE=offers
RABBITMQ_EXCHANGE=property_scraper
REQUEST_DELAY=3.0
REQUEST_TIMEOUT=15
FIRST_PAGE_INTERVAL=10
FULL_SCRAPE_TIME=02:00
SCRAPER_MODE=scheduler
```

When running with `docker compose`, `RABBITMQ_HOST` is automatically overridden with `rabbitmq`, so keep `localhost` in `.env`.

## Run modes

Run these commands from the project root, not from inside `src/`. The package must be installed first (see Installation), otherwise `python -m property_scraper.main` will not find it.

```bash
python -m property_scraper.main <mode>
```

| Mode | What it does |
|---|---|
| `worker` | `scheduler` + `verify-worker` in one process, sharing one rate limit per portal (recommended, Docker default) |
| `scheduler` | periodic scraping only: first page every `FIRST_PAGE_INTERVAL` minutes, full scrape daily at `FULL_SCRAPE_TIME` |
| `verify-worker` | only answers expiration checks from the backend (see [docs/expiration-check.md](docs/expiration-check.md)) |
| `first-page` | one-time first page scrape of every enabled source (or `--source <label>`), published to RabbitMQ |
| `full-scrape` | one-time full scrape of every enabled source (or `--source <label>`), published to RabbitMQ |
| `test` | first page of every enabled source (or `--source <label>`), printed instead of published (no RabbitMQ) |
| `check` | checks one offer URL like the verify worker would, e.g. `check --portal olx --url https://www.olx.pl/d/oferta/...` |

`SIGTERM`/`Ctrl+C` stops the long-running modes gracefully.

## What is scraped

Searches are listed in [`src/property_scraper/config/sources.toml`](src/property_scraper/config/sources.toml)
(override with `SOURCES_FILE`). Each source is a portal + transaction + property type + market:

```toml
[[sources]]
portal = "otodom"
transaction = "sale"
property_type = "apartment"
market = "primary"
enabled = true   # optional, default true
```

The file is re-read on every job run: `enabled = false` skips a source from the next run on, without a restart.
A source is identified by its label `portal/transaction/property_type/market` (e.g. `olx/sale/apartment/primary`);
`--source <label>` runs one source by hand, also a disabled one:

```bash
python -m property_scraper.main full-scrape --source olx/sale/apartment/primary
```

In Docker the bundled file is part of the image; to edit it on a running container, mount your own file and point
`SOURCES_FILE` at it (see `docker-compose.yml`).

Supported combinations are defined per portal (`portals/<portal>/urls.py`); an unsupported one fails at startup.
Currently: Otodom sale of apartments and houses (primary and secondary), OLX sale of apartments (primary and secondary).

Only the data needed for an offer is downloaded: a single document per listing page, no images or scripts.
Offers are read from the portals' embedded JSON only (no HTML markup parsing); if that JSON cannot be read,
the error is logged ("cannot parse … JSON") and a full scrape is reported as not completed.

- **Otodom:** listing pages come as JSON from the Next.js data endpoint (~6x smaller than the HTML page).
  Its build id is only published in the HTML page, so that page is requested once at start and again only
  after Otodom deploys a new frontend.
- **OLX:** the JSON offers API its own frontend uses (`/api/v1/offers/`), ~12x less data than the listing page
  with the same offers (checked: identical offer ids). Pages are followed through the response's `links.next`;
  Otodom cross-listings and repeated promoted ads are skipped. OLX serves at most 1000 offers per query, so a full
  scrape splits the search by area (`filter_float_m`): it starts from fixed ranges (0-25, 25.01-30, ...
  150.01-10000 m²) and halves every range the portal reports more than 1000 offers for (`visible_total_count`).
  For ~11k primary-market offers that is 21 ranges, found with 26 requests.

Portals are scraped in parallel (one thread per portal); sources of the same portal run one after another,
since they share the portal's rate limit.

### Optional settings

| Variable | Default | Meaning |
|---|---|---|
| `REQUEST_JITTER` | `3.0` | random extra delay (0..jitter s) on top of `REQUEST_DELAY` between requests to the same portal |
| `LONG_PAUSE_AFTER_MIN` / `_MAX` | `40` / `80` | after a random number of requests to a portal in this range, a long pause; `LONG_PAUSE_AFTER_MAX=0` disables it |
| `LONG_PAUSE_MIN` / `_MAX` | `20` / `60` | length of that long pause (s, random) |
| `SOURCE_PAUSE_MIN` / `_MAX` | `30` / `90` | random pause (s) between two sources of the same portal |
| `FETCH_ATTEMPTS` | `3` | attempts for network errors, 429 and 5xx (honours `Retry-After`) |
| `PROXY_URLS` | empty | comma-separated proxy URLs; rotated round-robin, a proxy blocked (403/429) by a portal is skipped for `PROXY_COOLDOWN` s |
| `PROXY_COOLDOWN` | `300` | see above |
| `SOURCES_FILE` | bundled | path to a custom `sources.toml` |

## Extending

- **New market / property type on an existing portal:** add the URL mapping in `portals/<portal>/urls.py`
  (and parser handling if the cards differ), then a `[[sources]]` entry.
- **New portal:** create `portals/<name>/` with a `Portal` subclass (URL ownership, scraper factory,
  `availability_from_page`) and a `ListingScraper` (usually `PaginatedScraper` with `fetch_page`), then register
  it in `portals/registry.py`.
- **Proxies:** implement `net.proxy.ProxyProvider` (`acquire` / `report`) for a paid rotating service.
- **Task queue (e.g. Celery):** jobs in `jobs/` are plain functions of `JobContext`; only `runtime/` needs to change.
## Development

Install the dev dependencies:

```bash
python -m pip install -e .[dev]
```

Run tests:

```bash
python -m pytest
```

## Docker Compose

Run scraper + RabbitMQ:

```bash
docker compose up -d
```

First run (or after Dockerfile changes) builds the scraper image automatically.
`docker compose` uses variables from the same `.env` file.

By default, `docker compose up -d` starts the scraper in `worker` mode (scraping + expiration checks).
Scraping is scheduled based on:
- `FIRST_PAGE_INTERVAL` (required, in minutes, must be > 0)
- `FULL_SCRAPE_TIME` (required, format `HH:MM`, e.g. `02:00`) in the container's time zone, `TZ` (default `Europe/Warsaw`)

Stop:

```bash
docker compose down
```

RabbitMQ management UI:

```text
http://localhost:15672
```

Default credentials: `guest` / `guest`.

To change scraper mode (default: `worker`), set `SCRAPER_MODE`:

- `first-page` — one-time first page scrape:

```bash
SCRAPER_MODE=first-page docker compose up scraper
```

- `full-scrape` — one-time full scrape:

```bash
SCRAPER_MODE=full-scrape docker compose up scraper
```

- `test` — one-time test mode (no RabbitMQ publish):

```bash
SCRAPER_MODE=test docker compose up scraper
```

## Project structure

```text
src/property_scraper/
  config/      settings (env), sources.toml + loader
  domain/      Offer, SearchSpec, enums shared with the backend
  net/         HttpClient (FetchResult instead of exceptions), per-domain RateLimiter, retries, proxies
  portals/     Portal / ListingScraper base classes, registry
    otodom/    urls, parser, scraper (Next.js data endpoint), portal (expiration rules)
    olx/       urls, parser (offers API), scraper (area-range segmentation), portal (expiration rules)
  messaging/   RabbitMQ topology, message contracts, publisher (with publisher confirms)
  jobs/        first page / full scrape / expiration check; JobContext
  runtime/     scheduler, verify worker
  main.py      CLI
```