from enum import Enum


class OfferStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"

