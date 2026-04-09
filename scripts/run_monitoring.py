from config.logging_config import setup_logging
from src.jobs.monitoring import run_monitoring


if __name__ == "__main__":
    setup_logging()
    result = run_monitoring()
    print(result)

