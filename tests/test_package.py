import pytest

import property_scraper
from property_scraper.config.settings import settings
from property_scraper.config.sources import SourceCatalog, SourceConfig, load_sources
from property_scraper.domain import MarketType, PropertyType, SearchSpec, TransactionType
from property_scraper.portals import default_registry


def test_package_version_exists():
	assert property_scraper.__version__


def test_settings_are_loaded():
	assert settings.rabbitmq.host == "localhost"
	assert settings.rabbitmq.port == 5672
	assert settings.scraper.request_timeout == 15
	assert settings.scraper.request_delay == 3.0
	assert settings.scraper.first_page_interval == 10
	assert settings.scraper.full_scrape_time == "22:00"
	assert settings.scraper.proxies == []
	assert settings.scraper.request_jitter == 3.0
	assert (settings.scraper.long_pause_after_min, settings.scraper.long_pause_after_max) == (40, 80)
	assert (settings.scraper.source_pause_min, settings.scraper.source_pause_max) == (30.0, 90.0)


def test_main_module_imports():
	import property_scraper.main  # noqa: F401


def spec_of(label: str) -> SearchSpec:
	return SearchSpec.from_label(label)


def entry(portal: str, market: str, enabled: str = "") -> str:
	line = f"enabled = {enabled}\n" if enabled else ""
	return (f'[[sources]]\nportal="{portal}"\ntransaction="sale"\nproperty_type="apartment"\n'
		f'market="{market}"\n{line}')


def test_bundled_sources_are_valid_and_enabled():
	sources = load_sources()

	default_registry().validate(source.spec for source in sources)
	assert {source.spec.label for source in sources if source.enabled} == {
		"otodom/sale/apartment/secondary", "otodom/sale/apartment/primary",
		"olx/sale/apartment/secondary", "olx/sale/apartment/primary"}


def test_sources_file_override_and_enabled_flag(tmp_path):
	path = tmp_path / "sources.toml"
	path.write_text(entry("olx", "primary") + entry("otodom", "secondary", "false"))

	assert load_sources(path) == [
		SourceConfig(spec_of("olx/sale/apartment/primary"), enabled=True),
		SourceConfig(spec_of("otodom/sale/apartment/secondary"), enabled=False)]


@pytest.mark.parametrize("content, message", [
	(entry("olx", "castle"), "Invalid source #1"),
	(entry("olx", "primary", '"no"'), "enabled must be true or false"),
	(entry("olx", "primary") + entry("olx", "primary"), "Duplicate sources"),
	("", "No sources"),
])
def test_invalid_sources_file_fails(tmp_path, content, message):
	path = tmp_path / "sources.toml"
	path.write_text(content)

	with pytest.raises(ValueError, match=message):
		load_sources(path)


def test_unsupported_source_fails_validation():
	plot = SearchSpec("otodom", TransactionType.SALE, PropertyType.PLOT, MarketType.SECONDARY)
	unknown = SearchSpec("morizon", TransactionType.SALE, PropertyType.APARTMENT, MarketType.SECONDARY)

	with pytest.raises(ValueError, match="does not support"):
		default_registry().validate([plot])
	with pytest.raises(ValueError, match="Unknown portal"):
		default_registry().validate([unknown])


def test_catalog_rereads_file_on_every_call(tmp_path):
	path = tmp_path / "sources.toml"
	path.write_text(entry("olx", "primary") + entry("otodom", "secondary"))
	catalog = SourceCatalog(path, default_registry().validate)

	assert len(catalog.enabled()) == 2

	path.write_text(entry("olx", "primary") + entry("otodom", "secondary", "false"))
	assert catalog.enabled() == [spec_of("olx/sale/apartment/primary")]


def test_catalog_keeps_last_valid_sources_when_file_breaks(tmp_path, caplog):
	path = tmp_path / "sources.toml"
	path.write_text(entry("olx", "primary"))
	catalog = SourceCatalog(path, default_registry().validate)

	path.write_text("[[sources]\nbroken")

	assert catalog.enabled() == [spec_of("olx/sale/apartment/primary")]
	assert "Cannot reload sources" in caplog.text


def test_catalog_fails_fast_on_invalid_file_at_startup(tmp_path):
	path = tmp_path / "sources.toml"
	path.write_text(entry("morizon", "primary"))

	with pytest.raises(ValueError, match="Unknown portal"):
		SourceCatalog(path, default_registry().validate)


def test_catalog_finds_disabled_source_for_manual_runs(tmp_path):
	path = tmp_path / "sources.toml"
	path.write_text(entry("otodom", "secondary", "false"))
	catalog = SourceCatalog(path, default_registry().validate)

	assert catalog.find("otodom/sale/apartment/secondary") == spec_of("otodom/sale/apartment/secondary")
	with pytest.raises(ValueError, match="not configured"):
		catalog.find("olx/sale/apartment/primary")
	with pytest.raises(ValueError, match="Invalid source"):
		catalog.find("olx/apartment")


def test_search_spec_label_round_trip():
	spec = spec_of("OLX/sale/apartment/primary")

	assert spec == SearchSpec("olx", TransactionType.SALE, PropertyType.APARTMENT, MarketType.PRIMARY)
	assert SearchSpec.from_label(spec.label) == spec

def test_pause_ranges_are_validated(monkeypatch):
	from pydantic import ValidationError

	from property_scraper.config.settings import ScraperSettings

	monkeypatch.setenv("SOURCE_PAUSE_MIN", "100")
	with pytest.raises(ValidationError, match="SOURCE_PAUSE_MIN must not be greater"):
		ScraperSettings()

	monkeypatch.delenv("SOURCE_PAUSE_MIN")
	monkeypatch.setenv("LONG_PAUSE_AFTER_MAX", "0")  # disabled: the min/max check does not apply
	assert ScraperSettings().long_pause_after_max == 0