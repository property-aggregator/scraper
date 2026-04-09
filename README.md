# Property Scraper 

Najprostszy scraper dla:
- portale: Otodom
- kategoria: mieszkania na sprzedaż, rynek wtórny
- zakres: listing pages (bez wchodzenia w szczegóły oferty)

## Funkcje

- Parsowanie danych
- Monitoring stron 1-3 (co 30 min)
- Full scrape wszystkich stron (np. 1x dziennie)
- Weryfikacja potencjalnie usuniętych ofert
- Retry (3x), opóźnienia 2-5s
- Wysyłka danych do API

## Szybki start

1. Python 3.11+
2. Instalacja:

```bash
pip install -e .
```

3. Skopiuj i uzupełnij env:

```bash
copy .env.example .env
```

4. Uruchom:

```bash
python scripts/run_monitoring.py
python scripts/run_full_scrape.py
python scripts/run_verify_deleted.py
```

## Uwaga

Selenium wymaga dostępnego sterownika przeglądarki (np. ChromeDriver) zgodnego z wersją przeglądarki.
