from functools import cached_property

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQSettings(BaseSettings):
	model_config = SettingsConfigDict(env_prefix="RABBITMQ_", env_file=".env", extra="ignore")

	host: str
	port: int
	username: str
	password: str
	queue: str
	exchange: str

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

	request_delay: float
	request_timeout: int
	first_page_interval: int
	full_scrape_time: str
	user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

	@field_validator("request_delay")
	@classmethod
	def validate_request_delay(cls, value: float) -> float:
		if value <= 0:
			raise ValueError("REQUEST_DELAY must be greater than 0")
		return value

	@field_validator("request_timeout")
	@classmethod
	def validate_request_timeout(cls, value: int) -> int:
		if value <= 0:
			raise ValueError("REQUEST_TIMEOUT must be greater than 0")
		return value

	@field_validator("first_page_interval")
	@classmethod
	def validate_first_page_interval(cls, value: int) -> int:
		if value <= 0:
			raise ValueError("FIRST_PAGE_INTERVAL must be greater than 0")
		return value

	@field_validator("full_scrape_time")
	@classmethod
	def validate_full_scrape_time(cls, value: str) -> str:
		parts = value.split(":")
		if len(parts) != 2 or any(not part.isdigit() for part in parts):
			raise ValueError("FULL_SCRAPE_TIME must be in HH:MM format")

		hour, minute = map(int, parts)
		if not (0 <= hour <= 23 and 0 <= minute <= 59):
			raise ValueError("FULL_SCRAPE_TIME must be a valid 24h time (00:00-23:59)")

		return value


class Settings:
	@cached_property
	def rabbitmq(self) -> RabbitMQSettings:
		return RabbitMQSettings()

	@cached_property
	def scraper(self) -> ScraperSettings:
		return ScraperSettings()


settings = Settings()
