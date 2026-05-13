import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import requests
from dotenv import load_dotenv

API_URL = "https://api.jquants.com/v2/equities/bars/daily"
BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = Path(__file__).with_name("results")


def one_month_ago_same_day(today: date) -> date:
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    day = min(today.day, monthrange(year, month)[1])
    return date(year, month, day)


def parse_api_date(value: str) -> datetime:
    if "-" in value:
        return datetime.fromisoformat(value)
    return datetime.strptime(value, "%Y%m%d")


load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("JQUANTS_API") or os.getenv("JQUANTS_API_KEY")
if not api_key:
    raise RuntimeError("Set JQUANTS_API in .env")

today = date.today()
to_date = today - timedelta(weeks=12)
from_date = one_month_ago_same_day(to_date)

resp = requests.get(
    API_URL,
    params={
        "code": "86970",
        "from": from_date.strftime("%Y%m%d"),
        "to": to_date.strftime("%Y%m%d"),
    },
    headers={"x-api-key": api_key},
    timeout=20,
)
resp.raise_for_status()
payload = resp.json()
print(payload)

rows = payload.get("data") or payload.get("daily_quotes") or []
points = []
for row in rows:
    date_text = row.get("Date") or row.get("date")
    close_value = row.get("Close") or row.get("C")
    if not date_text or close_value is None:
        continue
    points.append((parse_api_date(str(date_text)), float(close_value)))

if points:
    points.sort(key=lambda x: x[0])
    RESULTS_DIR.mkdir(exist_ok=True)
    chart_path = RESULTS_DIR / "close_chart.png"

    plt.figure(figsize=(8, 4.5))
    plt.plot([x[0] for x in points], [x[1] for x in points], marker="o")
    plt.title("JPX Close Price")
    plt.xlabel("Date")
    plt.ylabel("Close")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160)
    print(f"saved: {chart_path}")
    plt.show()
    plt.close()
