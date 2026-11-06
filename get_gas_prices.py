import requests
import pandas as pd
from datetime import datetime, timedelta
import os

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("EIA_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("EIA_API_KEY is not set. Add it to .env (see .env.example).")
series_id = "NG.RNGWHHD.D"  # Henry Hub daily spot price
url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={API_KEY}"

# How many days to keep
HISTORY_DAYS = 365
ARCHIVE_FILE = "henry_hub_daily.csv"

r = requests.get(url)
j = r.json()

if "response" in j and "data" in j["response"]:
    new_df = pd.DataFrame(j["response"]["data"])
    cols = [c for c in ["period", "value"] if c in new_df.columns]
    new_df = new_df[cols].rename(columns={"period": "date", "value": "price"})
    new_df["date"] = pd.to_datetime(new_df["date"])

    # Load existing if available
    if os.path.exists(ARCHIVE_FILE):
        old_df = pd.read_csv(ARCHIVE_FILE, parse_dates=["date"])
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    # Deduplicate and keep last N days
    df = df.drop_duplicates(subset="date")
    df = df.sort_values("date")
    df = df[df["date"] >= datetime.now() - timedelta(days=HISTORY_DAYS)]

    df.to_csv(ARCHIVE_FILE, index=False)
    print("✅ Saved", ARCHIVE_FILE, "with", len(df), "rows (through", df['date'].max().date(), ")")
else:
    print("❌ Unexpected response shape")
    print("Status:", r.status_code)
    print("Body:", r.text)
