import property_scraper
from property_scraper.config.settings import settings


def test_package_version_exists():
    assert property_scraper.__version__


def test_settings_defaults_are_loaded():
    assert settings.rabbitmq.host == "localhost"
    assert settings.rabbitmq.port == 5672
    assert settings.scraper.request_timeout == 15
    assert settings.scraper.user_agent.startswith("Mozilla/")


def test_main_module_imports():
    import property_scraper.main  # noqa: F401
