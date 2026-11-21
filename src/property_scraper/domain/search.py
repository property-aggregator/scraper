from dataclasses import dataclass

from property_scraper.domain.enums import MarketType, PropertyType, TransactionType


@dataclass(frozen=True)
class SearchSpec:
	"""What to scrape: one portal search (e.g. otodom / sale / apartment / primary)."""

	portal: str
	transaction: TransactionType
	property_type: PropertyType
	market: MarketType

	@property
	def label(self) -> str:
		return f"{self.portal}/{self.transaction}/{self.property_type}/{self.market}"

	@classmethod
	def from_label(cls, label: str) -> "SearchSpec":
		"""Inverse of `label`, e.g. "olx/sale/apartment/primary" (CLI, task queue arguments)."""
		try:
			portal, transaction, property_type, market = label.strip().lower().split("/")
			return cls(portal, TransactionType(transaction), PropertyType(property_type), MarketType(market))
		except ValueError as e:
			raise ValueError(f"Invalid source {label!r}, expected portal/transaction/property_type/market") from e

	def __str__(self) -> str:
		return self.label
