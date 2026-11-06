
import pandas as pd
from datetime import datetime, timezone

# Inputs/Outputs
OBS_FILE      = "weather_observed.csv"
FORECAST_FILE = "weather_forecast.csv"
OUTPUT_FILE   = "merged_weather.csv"

# Load
try:
    observed = pd.read_csv(OBS_FILE, parse_dates=["timestamp"])
    forecast = pd.read_csv(FORECAST_FILE, parse_dates=["timestamp"])
except Exception as e:
    print(f"❌ Failed to read input files: {e}")
    raise SystemExit(1)

# Filter windows
now = datetime.now(timezone.utc)
observed = observed[observed["timestamp"] <= now]
forecast = forecast[forecast["timestamp"] > now]

# Combine & dedupe
merged = pd.concat([observed, forecast], ignore_index=True)
merged = merged.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

# Normalize timestamps: strip timezone (KEEP native cadence; do NOT round to hour)
merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True).dt.tz_localize(None)

merged.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Saved {OUTPUT_FILE} with {len(merged)} rows "
      f"(from {merged['timestamp'].min()} to {merged['timestamp'].max()})")
