from enum import StrEnum

# Values match the backend enums (deserialized case-insensitively by JsonStringEnumConverter).


class TransactionType(StrEnum):
	SALE = "sale"
	RENT = "rent"


class PropertyType(StrEnum):
	APARTMENT = "apartment"
	HOUSE = "house"
	PLOT = "plot"


class MarketType(StrEnum):
	PRIMARY = "primary"
	SECONDARY = "secondary"


class SellerType(StrEnum):
	AGENCY = "agency"
	PRIVATE = "private"
	DEVELOPER = "developer"


class Availability(StrEnum):
	ACTIVE = "active"
	EXPIRED = "expired"
	UNKNOWN = "unknown"
