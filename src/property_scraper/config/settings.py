from pydantic_settings import BaseSettings, SettingsConfigDict


class RabbitMQSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RABBITMQ_")

    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    queue: str = "offers"
    exchange: str = "property_scraper"


class ScraperSettings(BaseSettings):
    request_delay: float = 3.0
    request_timeout: int = 15
    first_page_interval: int = 10
    full_scrape_hour: int = 2
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class Settings:
    def __init__(self):
        self.rabbitmq = RabbitMQSettings()
        self.scraper = ScraperSettings()


settings = Settings()
