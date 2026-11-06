import requests
import pandas as pd
import datetime
import os

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("EIA_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("EIA_API_KEY is not set. Add it to .env (see .env.example).")

# Duke Energy's balancing authority ID
DUK_ID = "DUK"

# How far back to fetch (days)
DAYS_BACK = 60  # was 7

today = datetime.datetime.now()
start_date = (today - datetime.timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')

url = (
    f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
    f"?api_key={API_KEY}"
    f"&frequency=hourly"
    f"&data[0]=value"
    f"&facets[respondent][]=DUK"
    f"&facets[type][]=D"
    f"&start={start_date}"
)

r = requests.get(url)
j = r.json()
data = j["response"]["data"]

df = pd.DataFrame(data)
df['timestamp'] = pd.to_datetime(df['period'])
df = df[['timestamp', 'value']].sort_values('timestamp')

df.to_csv("duke_demand.csv", index=False)
print(f"✅ Saved duke_demand.csv with {len(df)} rows from {df['timestamp'].min()} to {df['timestamp'].max()}")
