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

## Run modes

Run these commands from the project root, not from inside `src/`.

### Test mode
Runs the scraper in a local test flow without publishing to RabbitMQ.

```bash
python -m property_scraper.main test
```

### First page scrape
Scrapes the first page and publishes results to RabbitMQ.

```bash
python -m property_scraper.main first-page
```

### Full scrape
Scrapes all pages and publishes the results.

```bash
python -m property_scraper.main full-scrape
```

### Scheduler
Runs periodic scraping tasks.

```bash
python -m property_scraper.main scheduler
```

## Configuration

Create a `.env` file before running the app. All variables from the example below are required.

Example:

```bash
RABBITMQ_HOST=rabbitmq
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

By default, `docker compose up -d` starts scraper in `scheduler` mode.
That means periodic scraping is executed based on:
- `FIRST_PAGE_INTERVAL` (required, in minutes, must be > 0)
- `FULL_SCRAPE_TIME` (required, format `HH:MM`, e.g. `02:00`)

Stop:

```bash
docker compose down
```

RabbitMQ management UI:

```text
http://localhost:15672
```

Default credentials: `guest` / `guest`.

To change scraper mode (default: `scheduler`), set `SCRAPER_MODE`:

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
src/
  property_scraper/
    config/
    models/
    publishers/
    schedulers/
    scrapers/
    utils/
    main.py
    __init__.py
```
