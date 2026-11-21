import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_ID_PATTERN = re.compile(r"-(ID[A-Za-z0-9]+)(?:\.html)?(?:\?.*)?$")


def extract_source_id(slug: str) -> Optional[str]:
	"""Wyciąga ID oferty ze sluga typu 'mieszkanie-2-pokoje-ID4BaPI'."""
	if not slug:
		return None
	match = SOURCE_ID_PATTERN.search(slug.rstrip("/"))
	return match.group(1) if match else None


def extract_json_assignment(html: str, marker: str) -> Optional[object]:
	"""Decodes the JSON value that follows `marker` in the HTML (e.g. 'window.__STATE__=')."""
	start = html.find(marker)
	if start == -1:
		return None
	try:
		value, _ = json.JSONDecoder().raw_decode(html[start + len(marker):].lstrip())
		return value
	except ValueError:
		logger.warning("Invalid JSON after %r", marker)
		return None
