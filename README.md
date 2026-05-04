#### Tryb testowy (bez RabbitMQ, tylko wyświetla wyniki)

```
cd src
python -m property_scraper.main test
```

#### Jednorazowy scrape pierwszej strony (wysyła do RabbitMQ)

```
cd src
python -m property_scraper.main first-page
```

#### Jednorazowy pełny scrape (wysyła do RabbitMQ)

```
cd src
python -m property_scraper.main full-scrape
```

#### Scheduler (co 10 min pierwsza strona, raz dziennie full)

```
cd src
python -m property_scraper.main schedulerscheduler
```
