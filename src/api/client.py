from __future__ import annotations

from typing import Any

import requests

from config.settings import settings
from src.core.exceptions import APIError
from src.core.models import PropertyItem


class ApiClient:
    def __init__(self) -> None:
        self.base_url = settings.api_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        }

    def upsert_offers(self, offers: list[PropertyItem]) -> dict[str, Any]:
        payload = {"offers": [offer.to_dict() for offer in offers]}
        response = requests.post(
            f"{self.base_url}/offers/upsert-bulk",
            json=payload,
            headers=self.headers,
            timeout=60,
        )
        if response.status_code >= 400:
            raise APIError(f"upsert_offers failed: {response.status_code} {response.text}")
        return response.json() if response.content else {}

    def get_potentially_inactive(self, portal: str) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/offers/potentially-inactive",
            params={"portal": portal},
            headers=self.headers,
            timeout=60,
        )
        if response.status_code >= 400:
            raise APIError(
                f"get_potentially_inactive failed: {response.status_code} {response.text}"
            )
        data = response.json() if response.content else {}
        return data.get("offers", [])

    def mark_deleted(self, external_ids: list[str], portal: str) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/offers/mark-deleted",
            json={"portal": portal, "external_ids": external_ids},
            headers=self.headers,
            timeout=60,
        )
        if response.status_code >= 400:
            raise APIError(f"mark_deleted failed: {response.status_code} {response.text}")
        return response.json() if response.content else {}
