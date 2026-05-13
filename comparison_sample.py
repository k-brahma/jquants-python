from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
from dotenv import load_dotenv

API_URL = "https://api.jquants.com/v2/equities/bars/daily"
BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = Path(__file__).with_name("results")
LOOKBACK_DAYS = 30
DELAY_DAYS = 90
STOCKS = {
    "86970": "JPX",
    "72030": "Toyota",
    "67580": "Sony Group",
}


def get_api_key() -> str:
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("JQUANTS_API") or os.getenv("JQUANTS_API_KEY")
    if not api_key:
        raise RuntimeError("Set JQUANTS_API in .env")
    return api_key


def extract_rows(payload: dict) -> list[dict]:
    rows = payload.get("data")
    if rows is None:
        rows = payload.get("daily_quotes")
    if not isinstance(rows, list):
        message = payload.get("message", "Unexpected response from J-Quants API")
        raise RuntimeError(str(message))
    return rows


def fetch_daily_bars(
    session: requests.Session,
    api_key: str,
    code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    params = {
        "code": code,
        "from": start_date.strftime("%Y%m%d"),
        "to": end_date.strftime("%Y%m%d"),
    }
    rows: list[dict] = []
    pagination_key = ""

    while True:
        page_params = dict(params)
        if pagination_key:
            page_params["pagination_key"] = pagination_key

        response = session.get(
            API_URL,
            params=page_params,
            headers={"x-api-key": api_key},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        rows.extend(extract_rows(payload))

        pagination_key = payload.get("pagination_key", "")
        if not pagination_key:
            return rows


def pick_value(row: dict, *keys: str) -> object:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def build_frame(rows: list[dict]) -> pd.DataFrame:
    normalized_rows = []
    for row in rows:
        normalized_rows.append(
            {
                "Date": pick_value(row, "Date", "date"),
                "Code": pick_value(row, "Code", "code"),
                "Close": pick_value(row, "AdjustmentClose", "AdjClose", "Close", "C"),
                "Volume": pick_value(row, "AdjustmentVolume", "AdjVolume", "Volume", "Vo"),
            }
        )

    frame = pd.DataFrame(normalized_rows)
    frame = frame.dropna(subset=["Date", "Close"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])
    frame = frame.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce")
    frame = frame.dropna(subset=["Close"])
    frame = frame.reset_index(drop=True)
    return frame


def save_chart(price_frames: dict[str, pd.DataFrame], chart_path: Path) -> None:
    plt.figure(figsize=(11, 6))

    for name, frame in price_frames.items():
        normalized = frame["Close"] / frame["Close"].iloc[0] * 100
        plt.plot(frame["Date"], normalized, linewidth=2.2, label=name)

    plt.title("J-Quants Demo: Relative Price Comparison")
    plt.xlabel("Date")
    plt.ylabel("Normalized Close (start=100)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160)
    plt.show()
    plt.close()


def main() -> None:
    api_key = get_api_key()
    RESULTS_DIR.mkdir(exist_ok=True)

    end_date = date.today() - timedelta(days=90)
    start_date = end_date - timedelta(days=30)

    print("J-Quants comparison demo")
    print(f"Reference date: {date.today().isoformat()}")
    print(f"Target window: {start_date.isoformat()} to {end_date.isoformat()}")
    print("-" * 72)

    price_frames: dict[str, pd.DataFrame] = {}

    with requests.Session() as session:
        for code, name in STOCKS.items():
            try:
                rows = fetch_daily_bars(session, api_key, code, start_date, end_date)
                frame = build_frame(rows)
            except requests.HTTPError as exc:
                print(f"{name:<12} request failed: {exc}")
                continue
            except RuntimeError as exc:
                print(f"{name:<12} {exc}")
                continue

            if frame.empty:
                print(f"{name:<12} no data")
                continue

            price_frames[name] = frame
            first_close = frame["Close"].iloc[0]
            last_close = frame["Close"].iloc[-1]
            change_pct = ((last_close / first_close) - 1) * 100
            latest_date = frame["Date"].iloc[-1].date().isoformat()
            latest_volume = frame["Volume"].iloc[-1]
            volume_text = f"{latest_volume:,.0f}" if pd.notna(latest_volume) else "n/a"
            print(
                f"{name:<12} {latest_date}  close={last_close:>9.1f}  "
                f"30d={change_pct:+6.2f}%  volume={volume_text}"
            )

    if not price_frames:
        raise RuntimeError("No price data returned. Check your plan range and API key.")

    chart_path = RESULTS_DIR / "jquants_comparison.png"
    save_chart(price_frames, chart_path)
    print("-" * 72)
    print(f"Saved chart: {chart_path}")


if __name__ == "__main__":
    main()
