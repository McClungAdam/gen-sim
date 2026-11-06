import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import os

from dotenv import load_dotenv
load_dotenv()
CONTACT = os.getenv("GENSIM_CONTACT_EMAIL", "").strip()
if not CONTACT:
    raise SystemExit("GENSIM_CONTACT_EMAIL is not set. Add it to .env (NWS requires a contact in User-Agent).")
USER_AGENT = f"gen-sim/0.1 ({CONTACT})"

# ── CONFIG ───────────────────────────────────────────────────────
STATION          = "KINT"                  # Winston-Salem Airport
ARCHIVE_FILE     = "weather_observed.csv"
MAX_LOOKBACK_HRS = 168                     # max NOAA window (~7 days)
# ────────────────────────────────────────────────────────────────

# 1) Determine time range to fetch
now = datetime.now(timezone.utc)
if os.path.exists(ARCHIVE_FILE):
    # load archive, find last timestamp
    old = pd.read_csv(ARCHIVE_FILE, parse_dates=["timestamp"])
    old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
    last_ts = old["timestamp"].max()
    # start one hour after last saved
    start = last_ts + timedelta(hours=1)
    # but NOAA only serves last ~7 days, so bound start to now–MAX_LOOKBACK_HRS
    cutoff = now - timedelta(hours=MAX_LOOKBACK_HRS)
    if start < cutoff:
        start = cutoff
else:
    # no archive yet: fetch the full lookback window
    start = now - timedelta(hours=MAX_LOOKBACK_HRS)

# 2) Build URL (strip microseconds, force Z)
start_str = start.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
end_str   = now  .replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
url = (
    f"https://api.weather.gov/stations/{STATION}/observations"
    f"?start={start_str}&end={end_str}"
)

# 3) Fetch & parse
headers = {"User-Agent": USER_AGENT}
r = requests.get(url, headers=headers)
r.raise_for_status()
records = []
for feat in r.json()["features"]:
    p = feat["properties"]
    ts = pd.to_datetime(p["timestamp"], utc=True)
    temp = p["temperature"]["value"]
    records.append({
        "timestamp": ts,
        "temp_f": temp * 9/5 + 32 if temp is not None else None,
        "condition": p["textDescription"],
        "windSpeed": p["windSpeed"]["value"],
        "temperatureUnit": "F"
    })

new = pd.DataFrame(records)

# 4) Append to archive, dedupe, sort
if os.path.exists(ARCHIVE_FILE):
    df = pd.concat([old, new], ignore_index=True)
else:
    df = new

df = (
    df
    .drop_duplicates(subset="timestamp")
    .sort_values("timestamp")
    .reset_index(drop=True)
)

# 5) Save
df.to_csv(ARCHIVE_FILE, index=False)
print(f"✅ Appended {len(new)} rows → {ARCHIVE_FILE} now has {len(df)} rows")
print(f"    Range: {df['timestamp'].min()} → {df['timestamp'].max()}")
