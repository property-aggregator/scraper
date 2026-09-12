import os

os.environ.setdefault("RABBITMQ_HOST", "localhost")
os.environ.setdefault("RABBITMQ_PORT", "5672")
os.environ.setdefault("RABBITMQ_USERNAME", "guest")
os.environ.setdefault("RABBITMQ_PASSWORD", "guest")
os.environ.setdefault("RABBITMQ_QUEUE", "offers")
os.environ.setdefault("RABBITMQ_EXCHANGE", "property_scraper")
os.environ.setdefault("REQUEST_DELAY", "3.0")
os.environ.setdefault("REQUEST_TIMEOUT", "15")
os.environ.setdefault("FIRST_PAGE_INTERVAL", "10")
os.environ.setdefault("FULL_SCRAPE_TIME", "22:00")

import property_scraper
from property_scraper.config.settings import settings


def test_package_version_exists():
	assert property_scraper.__version__


def test_settings_are_loaded():
	assert settings.rabbitmq.host == "localhost"
	assert settings.rabbitmq.port == 5672
	assert settings.scraper.request_timeout == 15
	assert settings.scraper.request_delay == 3.0
	assert settings.scraper.first_page_interval == 10
	assert settings.scraper.full_scrape_time == "22:00"
	assert settings.scraper.user_agent.startswith("Mozilla/")


def test_main_module_imports():
	import property_scraper.main  # noqa: F401
