import re
from typing import Optional


def extract_source_id(slug: str) -> Optional[str]:
	"""Wyciąga ID oferty ze sluga typu 'mieszkanie-2-pokoje-ID4BaPI'."""
	if not slug:
		return None
	match = re.search(r"-(ID[A-Za-z0-9]+)(?:\.html)?(?:\?.*)?$", slug.rstrip("/"))
	return match.group(1) if match else None
