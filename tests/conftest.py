import json
from pathlib import Path

import pytest


@pytest.fixture
def otodom_listing_json() -> str:
    fixture_path = Path("tests/fixtures/otodom/listing_page.json")
    return json.dumps(json.loads(fixture_path.read_text(encoding="utf-8")))

