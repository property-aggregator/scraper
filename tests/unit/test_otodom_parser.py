from src.scrapers.portals.otodom.parser import (
    parse_city_region_from_address,
    parse_listing_jsonld,
    parse_price_pln_text,
    parse_specs_from_dl_labels,
    property_item_from_listing_card,
)


def test_parse_listing_jsonld_extracts_basic_fields(otodom_listing_json: str) -> None:
    items = parse_listing_jsonld(otodom_listing_json)
    assert len(items) == 2

    first = items[0]
    assert first.external_id == "ID4xTHE"
    assert first.title == "Test offer 1"
    assert first.price == 2600000.0
    assert first.currency == "PLN"
    assert first.city == "Ruda Śląska"
    assert first.region == "śląskie"
    assert first.rooms == 3.0
    assert first.area_m2 == 126.75


def test_parse_price_pln_text() -> None:
    assert parse_price_pln_text("2\xa0445\xa0910 zł") == 2445910.0
    assert parse_price_pln_text("") is None


def test_parse_city_region_from_address() -> None:
    city, region = parse_city_region_from_address(
        "ul. Banacha, Górka Narodowa, Prądnik Biały, Kraków, małopolskie"
    )
    assert city == "Kraków"
    assert region == "małopolskie"


def test_parse_specs_from_dl_labels() -> None:
    dts = ["Liczba pokoi", "Metraż"]
    dds = ["1 pokój", "109 m²"]
    rooms, area = parse_specs_from_dl_labels(dts, dds)
    assert rooms == 1.0
    assert area == 109.0


def test_property_item_from_listing_card() -> None:
    item = property_item_from_listing_card(
        href="/pl/oferta/1-pokojowe-mieszkanie-109m2-taras-bezposrednio-ID4yBA6",
        title="1-pokojowe mieszkanie 109m2",
        price_text="2 445 910 zł",
        address_text="ul. Banacha, Kraków, małopolskie",
        dt_texts=["Liczba pokoi", "Metraż"],
        dd_texts=["1 pokój", "109 m²"],
    )
    assert item is not None
    assert item.external_id == "ID4yBA6"
    assert item.url.endswith("/pl/oferta/1-pokojowe-mieszkanie-109m2-taras-bezposrednio-ID4yBA6")
    assert item.price == 2445910.0
    assert item.currency == "PLN"
    assert item.city == "Kraków"
    assert item.region == "małopolskie"
    assert item.rooms == 1.0
    assert item.area_m2 == 109.0

