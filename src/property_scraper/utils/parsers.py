import re
from typing import Optional


def parse_price(text: Optional[str]) -> Optional[int]:
	"""Parsuje cenę z tekstu typu '680 000 zł' na int 680000."""
	if not text:
		return None
	digits = re.sub(r"[^\d]", "", text)
	return int(digits) if digits else None


def parse_area(text: Optional[str]) -> Optional[float]:
	"""Parsuje metraż z tekstu typu '44 m²' na float 44.0."""
	if not text:
		return None
	match = re.search(r"([\d,\.]+)", text.replace(",", "."))
	if match:
		try:
			return float(match.group(1))
		except ValueError:
			return None
	return None


def parse_rooms(text: Optional[str]) -> Optional[int]:
	"""Parsuje liczbę pokoi z tekstu typu '2 pokoje' na int 2."""
	if not text:
		return None
	match = re.search(r"(\d+)", text)
	return int(match.group(1)) if match else None


def extract_source_id(url: str) -> Optional[str]:
	"""Wyciąga ID oferty z URL typu '/pl/oferta/...-ID4BaPI'."""
	if not url:
		return None
	match = re.search(r"-([A-Za-z0-9]+)$", url.rstrip("/"))
	return match.group(1) if match else None


def clean_text(text: Optional[str]) -> Optional[str]:
	"""Czyści tekst z nadmiarowych spacji i znaków."""
	if not text:
		return None
	return " ".join(text.split()).strip()
