import requests
from bs4 import BeautifulSoup

url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie%2Crynek-wtorny/cala-polska?limit=24&ownerTypeSingleSelect=ALL&by=DEFAULT&direction=DESC&page=2"
html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).text

soup = BeautifulSoup(html, "html.parser")
cards_list = soup.select_one('ul[data-sentry-component="CardsList"]')

if not cards_list:
    raise Exception("Nie znaleziono CardsList")

items = cards_list.find_all("li", recursive=False)

for li in items[2:]:
    li.decompose()

output = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <base href="https://www.otodom.pl">
    <title>CardsList test</title>
</head>
<body>
{str(cards_list)}
</body>
</html>
"""

with open("fixtures/otodom/cards_list_page2.html", "w", encoding="utf-8") as f:
    f.write(output)

print("Zapisano: cards_list_page2.html")
