from typing import Iterable, Optional

from property_scraper.domain import SearchSpec
from property_scraper.portals.base import Portal
from property_scraper.portals.olx import OlxPortal
from property_scraper.portals.otodom import OtodomPortal


class PortalRegistry:
	def __init__(self, portals: Iterable[Portal]):
		self._portals = {portal.name: portal for portal in portals}

	def get(self, name: str) -> Optional[Portal]:
		return self._portals.get((name or "").lower())

	def validate(self, sources: Iterable[SearchSpec]) -> None:
		"""Fails fast at startup on a misconfigured source."""
		for spec in sources:
			portal = self.get(spec.portal)
			if portal is None:
				raise ValueError(f"Unknown portal in source {spec}; known: {sorted(self._portals)}")
			if not portal.supports(spec):
				raise ValueError(f"Portal '{spec.portal}' does not support {spec}")


def default_registry() -> PortalRegistry:
	return PortalRegistry([OtodomPortal(), OlxPortal()])
