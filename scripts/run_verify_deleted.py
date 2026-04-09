from config.logging_config import setup_logging
from src.jobs.verify_deleted import run_verify_deleted


if __name__ == "__main__":
    setup_logging()
    result = run_verify_deleted()
    print(result)

