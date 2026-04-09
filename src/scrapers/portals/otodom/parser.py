from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from src.core.models import PropertyItem
from src.scrapers.portals.otodom.config import BASE_ORIGIN, PORTAL_NAME

ID_PATTERN = re.compile(r"-ID([A-Za-z0-9]+)")
_ROOMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*pok", re.IGNORECASE)
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*²|(\d+(?:[.,]\d+)?)\s*m2", re.IGNORECASE)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_external_id(url: str) -> str:
    match = ID_PATTERN.search(url)
    if match:
        return f"ID{match.group(1)}"
    path = urlparse(url).path.rstrip("/")
    return path.split("-")[-1].replace(".html", "")


def parse_price_pln_text(text: str) -> float | None:
    """Main price line, e.g. '2 445 910 zł' → 2445910.0."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.replace("\xa0", " "))
    if not digits:
        return None
    return float(digits)


def parse_city_region_from_address(address: str) -> tuple[str | None, str | None]:
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    if len(parts) == 1:
        return parts[0], None
    return None, None


def parse_specs_from_dl_labels(dt_texts: list[str], dd_texts: list[str]) -> tuple[float | None, float | None]:
    """Match dt/dd pairs for rooms and area (Polish)."""
    rooms: float | None = None
    area: float | None = None
    for dt, dd in zip(dt_texts, dd_texts, strict=False):
        label = (dt or "").strip().lower()
        value = (dd or "").strip()
        if "liczba pokoi" in label:
            m = _ROOMS_RE.search(value)
            if m:
                rooms = _to_float(m.group(1).replace(",", "."))
        if "metraż" in label or "powierzchnia" in label:
            m = _AREA_RE.search(value)
            if m:
                raw = m.group(1) or m.group(2)
                if raw:
                    area = _to_float(raw.replace(",", "."))
            else:
                m2 = re.search(r"(\d+(?:[.,]\d+)?)", value.replace(" ", ""))
                if m2:
                    area = _to_float(m2.group(1).replace(",", "."))
    return rooms, area


def property_item_from_listing_card(
    *,
    href: str,
    title: str,
    price_text: str,
    address_text: str,
    dt_texts: list[str],
    dd_texts: list[str],
) -> PropertyItem | None:
    url = urljoin(BASE_ORIGIN, href.strip()) if href.startswith("/") else href.strip()
    if not url or "/oferta/" not in url:
        return None
    city, region = parse_city_region_from_address(address_text)
    rooms, area_m2 = parse_specs_from_dl_labels(dt_texts, dd_texts)
    return PropertyItem(
        portal=PORTAL_NAME,
        external_id=_extract_external_id(url),
        title=title.strip(),
        url=url,
        price=parse_price_pln_text(price_text),
        currency="PLN",
        city=city,
        region=region,
        rooms=rooms,
        area_m2=area_m2,
    )


def parse_listing_jsonld(raw_json: str) -> list[PropertyItem]:
    data = json.loads(raw_json)
    graph: list[dict] = []
    if isinstance(data, dict):
        graph_data = data.get("@graph", [])
        if isinstance(graph_data, list):
            graph = [item for item in graph_data if isinstance(item, dict)]
        elif data.get("@type") == "Product":
            graph = [data]
    elif isinstance(data, list):
        graph = [item for item in data if isinstance(item, dict)]

    offers: list[dict] = []

    for node in graph:
        if node.get("@type") != "Product":
            continue
        aggregate = node.get("offers", {})
        raw_offers = aggregate.get("offers", [])
        if isinstance(raw_offers, list):
            offers = [item for item in raw_offers if isinstance(item, dict)]
        elif isinstance(raw_offers, dict):
            offers = [raw_offers]
        break

    parsed: list[PropertyItem] = []
    for offer in offers:
        url = str(offer.get("url", "")).strip()
        if not url:
            continue
        item_offered = offer.get("itemOffered", {})
        address = item_offered.get("address", {})
        parsed.append(
            PropertyItem(
                portal=PORTAL_NAME,
                external_id=_extract_external_id(url),
                title=str(offer.get("name", "")).strip(),
                url=url,
                price=_to_float(offer.get("price")),
                currency=offer.get("priceCurrency"),
                city=address.get("addressLocality"),
                region=address.get("addressRegion"),
                rooms=_to_float(item_offered.get("numberOfRooms")),
                area_m2=_to_float(item_offered.get("floorSize", {}).get("value")),
            )
        )
    return parsed

