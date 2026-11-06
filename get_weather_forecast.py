import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
CONTACT = os.getenv("GENSIM_CONTACT_EMAIL", "").strip()
if not CONTACT:
    raise SystemExit("GENSIM_CONTACT_EMAIL is not set. Add it to .env (NWS requires a contact in User-Agent).")
USER_AGENT = f"gen-sim/0.1 ({CONTACT})"

# Winston-Salem grid point info (can be auto-discovered via get_weather_grid.py)
grid_id = "RAH"
grid_x = 76
grid_y = 45
ARCHIVE_FILE = "weather_forecast.csv"

url = f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
headers = {"User-Agent": USER_AGENT}

response = requests.get(url, headers=headers)
data = response.json()

periods = data["properties"]["periods"]
df = pd.DataFrame(periods)
df["timestamp"] = pd.to_datetime(df["startTime"])
df["temp_f"] = df["temperature"]
df["condition"] = df["shortForecast"]
df["windSpeed"] = df["windSpeed"]
df["temperatureUnit"] = df["temperatureUnit"]
df = df[["timestamp", "temp_f", "temperatureUnit", "windSpeed", "condition"]]

# Save forecast (overwrite)
df.to_csv(ARCHIVE_FILE, index=False)
print(f"✅ Saved {ARCHIVE_FILE} with {len(df)} hourly forecast rows")
