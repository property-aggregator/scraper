from config.logging_config import setup_logging
from src.jobs.full_scrape import run_full_scrape


if __name__ == "__main__":
    setup_logging()
    result = run_full_scrape()
    print(result)

