from functools import cached_property
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQSettings(BaseSettings):
	model_config = SettingsConfigDict(env_prefix="RABBITMQ_", env_file=".env", extra="ignore")

	host: str
	port: int
	username: str
	password: str
	queue: str  # offers queue consumed by the backend
	exchange: str
	heartbeat: int = 600

	@field_validator("host", "username", "password", "queue", "exchange")
	@classmethod
	def validate_non_empty(cls, value: str) -> str:
		if not value.strip():
			raise ValueError("RabbitMQ string settings must not be empty")
		return value

	@field_validator("port")
	@classmethod
	def validate_port(cls, value: int) -> int:
		if value <= 0:
			raise ValueError("RABBITMQ_PORT must be greater than 0")
		return value


class ScraperSettings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", extra="ignore")

	request_delay: float  # minimum delay between requests to the same portal (seconds)
	request_jitter: float = 3.0  # random extra delay (0..jitter) added on top of request_delay
	request_timeout: int

	# Every random 40-80 requests to a portal, a longer random pause of 20-60 s (more human-like traffic).
	# LONG_PAUSE_AFTER_MAX=0 disables it.
	long_pause_after_min: int = 40
	long_pause_after_max: int = 80
	long_pause_min: float = 20.0
	long_pause_max: float = 60.0

	# Random pause between two sources of the same portal (e.g. Otodom secondary -> primary).
	source_pause_min: float = 30.0
	source_pause_max: float = 90.0
	fetch_attempts: int = 3
	first_page_interval: int
	full_scrape_time: str

	# Comma-separated proxy URLs (e.g. "http://user:pass@host:port"); empty = direct connection.
	proxy_urls: str = ""
	proxy_cooldown: int = 300  # seconds a proxy is skipped after being blocked (403/429)

	# Optional TOML file with search sources; defaults to the bundled config/sources.toml.
	sources_file: Optional[Path] = None

	@field_validator("request_delay", "request_timeout", "fetch_attempts", "first_page_interval")
	@classmethod
	def validate_positive(cls, value, info):
		if value <= 0:
			raise ValueError(f"{info.field_name.upper()} must be greater than 0")
		return value

	@field_validator(
		"request_jitter", "proxy_cooldown", "long_pause_after_min", "long_pause_after_max",
		"long_pause_min", "long_pause_max", "source_pause_min", "source_pause_max")
	@classmethod
	def validate_non_negative(cls, value, info):
		if value < 0:
			raise ValueError(f"{info.field_name.upper()} must not be negative")
		return value

	@model_validator(mode="after")
	def validate_ranges(self) -> "ScraperSettings":
		for low, high in (
				("long_pause_after_min", "long_pause_after_max"),
				("long_pause_min", "long_pause_max"),
				("source_pause_min", "source_pause_max")):
			if self.long_pause_after_max == 0 and low.startswith("long_pause"):
				continue  # long pauses disabled
			if getattr(self, low) > getattr(self, high):
				raise ValueError(f"{low.upper()} must not be greater than {high.upper()}")
		return self

	@field_validator("full_scrape_time")
	@classmethod
	def validate_full_scrape_time(cls, value: str) -> str:
		parts = value.split(":")
		if len(parts) != 2 or any(not part.isdigit() for part in parts):
			raise ValueError("FULL_SCRAPE_TIME must be in HH:MM format")

		hour, minute = map(int, parts)
		if not (0 <= hour <= 23 and 0 <= minute <= 59):
			raise ValueError("FULL_SCRAPE_TIME must be a valid 24h time (00:00-23:59)")

		return f"{hour:02d}:{minute:02d}"

	@property
	def proxies(self) -> list[str]:
		return [url.strip() for url in self.proxy_urls.split(",") if url.strip()]


class Settings:
	@cached_property
	def rabbitmq(self) -> RabbitMQSettings:
		return RabbitMQSettings()

	@cached_property
	def scraper(self) -> ScraperSettings:
		return ScraperSettings()


settings = Settings()
