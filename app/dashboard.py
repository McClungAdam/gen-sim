import streamlit as st
import pandas as pd
import os
import json
import plotly.express as px
from datetime import datetime

from gensim import pipeline
from gensim.config import DEFAULT_CONFIG, DEFAULT_WORKDIR, Paths
from gensim.timeutil import market_tz

st.set_page_config(layout="wide")
st.title("🔌 Generator Dispatch Simulator Dashboard")

CONFIG_PATH   = DEFAULT_CONFIG
PATHS         = Paths(DEFAULT_WORKDIR).ensure()
RESULTS_PATH  = PATHS.simulation_results
MERGED_INPUTS = PATHS.merged_inputs


def _report_fetch_errors(errors):
    for step, msg in (errors or {}).items():
        st.warning(f"Fetch step '{step}' failed (cached data used): {msg}")

# ---------- Helpers ----------
def latest_from_csv(path, ts_col_candidates):
    """Return the latest timestamp-like value found in a CSV."""
    if not os.path.exists(path):
        return "⛔ not found"
    try:
        df = pd.read_csv(path)
        for col in ts_col_candidates:
            if col in df.columns:
                try:
                    ts = pd.to_datetime(df[col], utc=True, errors="coerce")
                    if ts.notna().any():
                        return str(ts.max())
                except Exception:
                    pass
                try:
                    return str(df[col].max())
                except Exception:
                    continue
        return "⚠️ no known timestamp columns"
    except Exception as e:
        return f"❌ read error: {e}"

def parse_windows(text):
    """Lines of 'start,end,reason' -> list of dicts."""
    wins = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            wins.append({"start": parts[0], "end": parts[1], "reason": parts[2] if len(parts) > 2 else ""})
    return wins

def serialize_windows(wins):
    return "\n".join(f"{w.get('start','')},{w.get('end','')},{w.get('reason','')}" for w in (wins or []))

# ---------- Load config ----------
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r") as f:
        CONFIG = json.load(f)
else:
    st.error(f"Config not found: {CONFIG_PATH}")
    st.stop()

# ---------- Load results ----------
if os.path.exists(RESULTS_PATH):
    df = pd.read_csv(RESULTS_PATH)
    # Pipeline files are tz-aware UTC; show market-local wall time (display only).
    DISPLAY_TZ = market_tz(CONFIG)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(DISPLAY_TZ).dt.tz_localize(None)
    st.caption(f"Times shown in {DISPLAY_TZ}.")
else:
    st.warning(f"{RESULTS_PATH.name} not found. Run a simulation to populate charts.")
    df = pd.DataFrame(columns=["timestamp"])

# Detect generator names from results (fallback to config)
if not df.empty:
    gen_names = [c.replace("_output_mw", "") for c in df.columns if c.endswith("_output_mw")]
else:
    gen_names = [g["name"] for g in CONFIG.get("generators", [])]

# Price series availability
def has_price_series():
    try:
        if os.path.exists(MERGED_INPUTS):
            cols = pd.read_csv(MERGED_INPUTS, nrows=1).columns
            return "price_mwh" in cols
    except Exception:
        pass
    return False

# Last updated
try:
    with open(PATHS.last_updated, "r") as f:
        st.caption(f"🕒 Last Updated: {f.read()}")
except FileNotFoundError:
    st.caption("🕒 Last Updated: Unknown")

# =============================
# Location & Market
# =============================
st.header("🌍 Location & Market")

market = CONFIG.get("market", {"source": "EIA", "ba": "DUK", "price_series": "DA"})
gas_cfg = CONFIG.get("gas", {"hub": "HenryHub", "basis_adder_per_mmbtu": 0.0})

ba_options = ["DUK", "PJM", "TVA"]
current_ba = market.get("ba", "DUK")
if current_ba not in ba_options:
    ba_options.append(current_ba)
ba = st.selectbox("Balancing Authority (BA)", ba_options, index=ba_options.index(current_ba))

series_options = ["DA", "RT"]
current_series = market.get("price_series", "DA")
price_series = st.selectbox("Price Series", series_options, index=ba_options.index(ba) if current_series not in series_options else series_options.index(current_series))

basis = st.number_input("Gas Basis Adder ($/MMBtu)", min_value=0.0, max_value=10.0,
                        value=float(gas_cfg.get("basis_adder_per_mmbtu", 0.0)), step=0.05,
                        help="Adds to Henry Hub to form gas_price_effective.")

col_market1, col_market2 = st.columns([1,1])
with col_market1:
    if st.button("💾 Save Market Settings"):
        CONFIG["market"] = {"source": "EIA", "ba": ba, "price_series": price_series}
        CONFIG["gas"] = {"hub": "HenryHub", "basis_adder_per_mmbtu": float(basis)}
        with open(CONFIG_PATH, "w") as f:
            json.dump(CONFIG, f, indent=2)
        st.success("Market settings saved.")

with col_market2:
    if st.button("📈 Fetch Market Prices Now"):
        _errs = pipeline.fetch(json.load(open(CONFIG_PATH, encoding="utf-8")), PATHS, only=["market_prices"])
        _report_fetch_errors(_errs)
        if not _errs:
            st.success("Fetched market_price.csv (see Diagnostics below).")

# =============================
# Controls
# =============================
st.header("🧭 Controls")

c1, c2 = st.columns([1, 1])
with c1:
    if st.button("🔁 Refresh All Data (Demand + Gas + Weather + Prices → Merge → Simulate)"):
        st.write("Fetching and updating data...")
        _res = pipeline.run(CONFIG_PATH, PATHS.workdir)
        _report_fetch_errors(_res["fetch_errors"])
        st.rerun()
with c2:
    if st.button("▶️ Run Simulation Only"):
        pipeline.run(CONFIG_PATH, PATHS.workdir, do_fetch=False, do_merge=False)
        st.rerun()

# =============================
# Data Diagnostics
# =============================
st.header("🧪 Data Diagnostics (latest available rows)")
diag = pd.DataFrame([
    {"file": "duke_demand.csv",        "latest": latest_from_csv(PATHS.workdir / "duke_demand.csv",        ["timestamp"])},
    {"file": "henry_hub_daily.csv",    "latest": latest_from_csv(PATHS.workdir / "henry_hub_daily.csv",    ["date"])},
    {"file": "weather_observed.csv",   "latest": latest_from_csv(PATHS.workdir / "weather_observed.csv",   ["timestamp"])},
    {"file": "weather_forecast.csv",   "latest": latest_from_csv(PATHS.workdir / "weather_forecast.csv",   ["timestamp"])},
    {"file": "merged_weather.csv",     "latest": latest_from_csv(PATHS.workdir / "merged_weather.csv",     ["timestamp"])},
    {"file": "market_price.csv",       "latest": latest_from_csv(PATHS.workdir / "market_price.csv",       ["timestamp"])},
    {"file": "merged_inputs.csv",      "latest": latest_from_csv(PATHS.workdir / "merged_inputs.csv",      ["timestamp"])},
    {"file": "simulation_results.csv", "latest": latest_from_csv(PATHS.workdir / "simulation_results.csv", ["timestamp"])},
])
st.dataframe(diag, use_container_width=True)

# =============================
# Generator Settings (editable)
# =============================
st.header("⚙️ Generator Settings")

st.markdown(
    "Use **ramp_to_full_minutes** for human-readable intent; minutes take priority over an explicit MW/hr rate.  \n"
    f"Price series available in merged inputs: **{'Yes' if has_price_series() else 'No'}** (expects `price_mwh`)."
)

for gi, gen in enumerate(CONFIG.get("generators", [])):
    name = gen.get("name", f"gen_{gi+1}")
    with st.expander(f"{name.upper()} settings", expanded=False):
        with st.form(f"{name}_form"):
            colA, colB, colC = st.columns(3)
            with colA:
                capacity_mw = st.number_input("Capacity (MW)", 0.0, value=float(gen.get("capacity_mw", 0.0)), step=0.1, format="%.4f")
                heat_rate = st.number_input("Heat Rate (Btu/kWh, NET)", 0.0, value=float(gen.get("heat_rate_btu_per_kwh", 0.0)), step=50.0, format="%.2f")
                availability_cap = st.number_input("Availability cap (0–1)", 0.0, 1.0, value=float(gen.get("availability_cap", 1.0)), step=0.01)
            with colB:
                min_margin = st.number_input("Min Margin Threshold ($/MWh)", 0.0, value=float(gen.get("min_margin_threshold", 0.0)), step=0.5, format="%.2f")
                revenue_source = st.selectbox("Revenue source", ["fixed", "timeseries"], index=0 if gen.get("revenue_source", "fixed")=="fixed" else 1)
                revenue = st.number_input("Revenue ($/MWh) — if fixed", 0.0, value=float(gen.get("revenue_per_mwh", 0.0)), step=1.0, format="%.2f")
                vom = st.number_input("Variable O&M ($/MWh)", 0.0, value=float(gen.get("vom_per_mwh", 0.0)), step=1.0, format="%.2f")
            with colC:
                ramp_minutes_default = float(gen.get("ramp_to_full_minutes")) if gen.get("ramp_to_full_minutes") is not None else 0.0
                ramp_minutes = st.number_input("Ramp to Full (minutes)", 0.0, value=ramp_minutes_default, step=1.0, format="%.0f")
                ramp_rate_default = float(gen.get("ramp_rate_mw_per_hr")) if gen.get("ramp_rate_mw_per_hr") is not None else 0.0
                ramp_rate = st.number_input("Ramp Rate (MW/hr) — fallback", 0.0, value=ramp_rate_default, step=0.1, format="%.4f")
                start_cost = st.number_input("Start cost ($ per start)", 0.0, value=float(gen.get("start_cost", 0.0)), step=5.0, format="%.2f")
                min_up = st.number_input("Min up (hrs)", 0.0, value=float(gen.get("min_up_hours", 0)), step=1.0, format="%.0f")
                min_down = st.number_input("Min down (hrs)", 0.0, value=float(gen.get("min_down_hours", 0)), step=1.0, format="%.0f")

            # Calculated ramp rate
            calculated_rate = (capacity_mw / (ramp_minutes / 60.0)) if ramp_minutes > 0 else ramp_rate
            st.caption(f"🧮 Calculated ramp rate: {calculated_rate:.4f} MW/hr " + ("(from minutes)" if ramp_minutes > 0 else "(explicit)"))

            st.markdown("**Maintenance windows** — one per line: `start,end,reason` (ISO or natural language accepted by pandas)")
            win_text = st.text_area("Windows", value=serialize_windows(gen.get("maintenance_windows", [])), height=120)

            saved = st.form_submit_button(f"💾 Save {name.upper()} Settings")
            if saved:
                gen["name"] = name
                gen["capacity_mw"] = float(capacity_mw)
                gen["heat_rate_btu_per_kwh"] = float(heat_rate)
                gen["min_margin_threshold"] = float(min_margin)
                gen["revenue_source"] = revenue_source
                gen["revenue_per_mwh"] = float(revenue)
                gen["vom_per_mwh"] = float(vom)
                gen["start_cost"] = float(start_cost)
                gen["min_up_hours"] = int(min_up)
                gen["min_down_hours"] = int(min_down)
                gen["availability_cap"] = float(availability_cap)
                gen["maintenance_windows"] = parse_windows(win_text)
                if ramp_minutes > 0:
                    gen["ramp_to_full_minutes"] = int(ramp_minutes)
                    gen["ramp_rate_mw_per_hr"] = float(calculated_rate)
                else:
                    gen["ramp_to_full_minutes"] = 0
                    gen["ramp_rate_mw_per_hr"] = float(ramp_rate)
                try:
                    with open(CONFIG_PATH, "w") as f:
                        json.dump(CONFIG, f, indent=2)
                    st.success(f"Saved settings for {name.upper()}.")
                except Exception as e:
                    st.error(f"Failed to save config: {e}")
                if st.checkbox(f"Run simulation now for {name.upper()}"):
                    pipeline.run(CONFIG_PATH, PATHS.workdir, do_fetch=False, do_merge=False)
                    st.success("Simulation complete. Click 'Run Simulation Only' to refresh charts.")
                    st.stop()

# =============================
# Config Preview (read-only)
# =============================
st.header("🧾 Config Preview")
try:
    preview_rows = []
    for g in CONFIG.get("generators", []):
        minutes = g.get("ramp_to_full_minutes", 0) or 0
        rate = g.get("ramp_rate_mw_per_hr", 0.0) or 0.0
        cap = float(g.get("capacity_mw", 0.0))
        derived_rate = (cap / (minutes / 60.0)) if minutes and minutes > 0 else float(rate)
        preview_rows.append({
            "name": g.get("name"),
            "capacity_mw": cap,
            "heat_rate_btu_per_kwh": float(g.get("heat_rate_btu_per_kwh", 0.0)),
            "min_margin_threshold": float(g.get("min_margin_threshold", 0.0)),
            "revenue_source": g.get("revenue_source", "fixed"),
            "revenue_per_mwh": float(g.get("revenue_per_mwh", 0.0)),
            "vom_per_mwh": float(g.get("vom_per_mwh", 0.0)),
            "start_cost": float(g.get("start_cost", 0.0)),
            "min_up_hours": int(g.get("min_up_hours", 0)),
            "min_down_hours": int(g.get("min_down_hours", 0)),
            "availability_cap": float(g.get("availability_cap", 1.0)),
            "maint_windows": len(g.get("maintenance_windows", [])),
            "ramp_to_full_minutes": int(minutes),
            "ramp_rate_mw_per_hr (effective)": round(derived_rate, 6)
        })
    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
except Exception as e:
    st.error(f"Unable to render config preview: {e}")

# =============================
# Summary & Charts
# =============================
st.header("📊 Total Generation Summary")

# ---- Global generator selection (shared for Summary + MTD/YTD) ----
selected_gen = None
if gen_names:
    if "selected_gen_global" not in st.session_state:
        st.session_state["selected_gen_global"] = gen_names[0]
    selected_gen = st.selectbox("Choose Generator (applies to Summary & MTD/YTD)", gen_names, key="selected_gen_global")
# ------------------------------------------------------------------

if not df.empty and gen_names:
    # Ensure date column
    if "date" not in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    today = datetime.now().date()
    ytd_start = today.replace(month=1, day=1)

    cols = st.columns(len(gen_names))
    for i, gen in enumerate(gen_names):
        out_col = f"{gen}_output_mw"
        prof_col = f"{gen}_profit"
        run_col = f"{gen}_run"
        if all(c in df.columns for c in [out_col, prof_col, run_col]):
            dfg = df[df["date"] >= ytd_start]
            # Use dt_hours for runtime and weighted average when present
            if "dt_hours" in dfg.columns:
                ytd_runtime = (dfg[run_col].astype(float) * dfg["dt_hours"]).sum()
                ytd_avg_output = (dfg[out_col] * dfg["dt_hours"]).sum() / dfg["dt_hours"].sum()
            else:
                ytd_runtime = dfg[run_col].sum()
                ytd_avg_output = dfg[out_col].mean()
            ytd_profit = dfg[prof_col].sum()

            cols[i].metric(f"{gen.upper()} NET YTD Profit (margin)", f"${ytd_profit:,.0f}")
            cols[i].metric(f"{gen.upper()} Runtime (hrs)", f"{ytd_runtime:.1f}")
            cols[i].metric(f"{gen.upper()} Avg Output", f"{ytd_avg_output:.2f} MW")
        else:
            cols[i].write(f"⚠️ Columns missing for {gen}. Run simulation.")

# ===== MTD/YTD (All Generators) =====
if not df.empty and gen_names:
    if "date" not in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    st.subheader("📆 NET Month-to-Date and NET Year-to-Date Profit — All Generators")

    profit_cols = [f"{g}_profit" for g in gen_names if f"{g}_profit" in df.columns]
    today = datetime.now().date()
    first_of_month = today.replace(day=1)
    ytd_start = today.replace(month=1, day=1)
    end_date = df["date"].max() if not df.empty else today

    mtd_profit = df[df["date"] >= first_of_month][profit_cols].sum().sum() if profit_cols else 0.0
    ytd_profit = df[df["date"] >= ytd_start][profit_cols].sum().sum() if profit_cols else 0.0

    cA, cB = st.columns(2)
    cA.metric("Month-to-Date Profit (All Gens)", f"${mtd_profit:,.0f}")
    cB.metric("Year-to-Date Profit (All Gens)", f"${ytd_profit:,.0f}")

    def fmt_month_day(d):
        return f"{d.strftime('%b')} {d.day}"

    mtd_label = f"{fmt_month_day(first_of_month)}–{end_date.day}"
    ytd_label = f"Jan 1–{fmt_month_day(end_date)}"
    st.caption(f"MTD range: {mtd_label} • YTD range: {ytd_label}")

if not df.empty and gen_names:
    st.header("📈 Generator Output Over Time")
    selected_gen = st.selectbox("Choose Generator", gen_names)
    df["date"] = df["timestamp"].dt.date

    out_col = f"{selected_gen}_output_mw"
    prof_col = f"{selected_gen}_profit"
    run_col  = f"{selected_gen}_run"

    if out_col in df.columns:
        fig_output = px.line(df, x="timestamp", y=out_col, title=f"{selected_gen.upper()} Output (MW)", labels={"value": "MW"})
        st.plotly_chart(fig_output, use_container_width=True)
    else:
        st.info("Run the simulation to populate output series.")

    if prof_col in df.columns:
        fig_profit = px.bar(df, x="timestamp", y=prof_col, title=f"{selected_gen.upper()} Interval Profit ($)", labels={"value": "Profit"})
        st.plotly_chart(fig_profit, use_container_width=True)

        # ===== NEW: Monthly Run Hours & NET Profit (clustered, not stacked) =====
        import plotly.graph_objects as go
        from pandas.tseries.offsets import DateOffset

        # Build month column and run-hours using dt_hours when available (from simulator) :contentReference[oaicite:2]{index=2}
        temp = df[["timestamp", prof_col, run_col]].copy()
        if "dt_hours" in df.columns:
            temp["run_hours"] = temp[run_col].astype(float) * df["dt_hours"]
        else:
            # Fallback: treat each interval as 1 hour if dt_hours is missing
            temp["run_hours"] = temp[run_col].astype(float)

        temp["month"] = pd.to_datetime(temp["timestamp"]).dt.to_period("M").dt.to_timestamp()

        monthly = (
            temp.groupby("month", as_index=True)
                .agg(net_profit=(prof_col, "sum"), run_hours=("run_hours", "sum"))
        )

        # Determine window: last 12 months by default; include next 3 months if future timestamps exist
        today_ts = pd.Timestamp.today().normalize()
        has_future = (pd.to_datetime(df["timestamp"]).dt.normalize() > today_ts).any()
        end_anchor = (today_ts + DateOffset(months=3)).normalize() if has_future else today_ts
        start_anchor = (today_ts - DateOffset(months=11)).normalize()

        start_month = pd.Timestamp(start_anchor.year, start_anchor.month, 1)
        end_month = pd.Timestamp(end_anchor.year, end_anchor.month, 1)

        month_index = pd.date_range(start=start_month, end=end_month, freq="MS")
        monthly = monthly.reindex(month_index, fill_value=0.0)

        # Clustered bars (side-by-side) even with dual axes:
        # - barmode="group"
        # - distinct offsetgroup for each series
        # - shared alignmentgroup so bars line up per-month
        fig_monthly = go.Figure()
        fig_monthly.add_trace(
            go.Bar(
                x=monthly.index, y=monthly["run_hours"],
                name="Run Hours (hrs)", yaxis="y1",
                offsetgroup="run", alignmentgroup="month",
                hovertemplate="%{x|%b %Y}<br>Run Hours: %{y:.2f}<extra></extra>"
            )
        )
        fig_monthly.add_trace(
            go.Bar(
                x=monthly.index, y=monthly["net_profit"],
                name="NET Profit ($)", yaxis="y2",
                offsetgroup="profit", alignmentgroup="month",
                hovertemplate="%{x|%b %Y}<br>NET Profit: $%{y:,.0f}<extra></extra>"
            )
        )

        fig_monthly.update_layout(
            title=f"{selected_gen.upper()} — Monthly Run Hours & NET Profit",
            barmode="group",
            xaxis=dict(title="Month", tickformat="%b %Y"),
            yaxis=dict(title="Run Hours (hrs)", side="left"),
            yaxis2=dict(title="NET Profit ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=-0.2)
        )

        st.plotly_chart(fig_monthly, use_container_width=True)
        # ===== END NEW SECTION =====

        st.subheader("💰 Daily Profit")
        daily = (
            df[["timestamp", prof_col]]
            .assign(date=lambda x: pd.to_datetime(x["timestamp"]).dt.date)
            .groupby("date", as_index=False)[prof_col].sum()
        )
        fig_daily = px.bar(daily, x="date", y=prof_col, title="Daily Profit ($)", labels={"date": "Date", prof_col: "Profit ($)"})
        fig_daily.update_xaxes(type="category")
        st.plotly_chart(fig_daily, use_container_width=True)
    else:
        st.info("Run the simulation to populate profit charts.")

# =============================
# Weather & Demand (dual axis)
# =============================
if not df.empty:
    st.header("🌡️ Weather & Demand")
    if "demand_mw" in df.columns and "temp_f" in df.columns:
        import plotly.graph_objects as go

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"], y=df["demand_mw"],
                name="Demand (MW)",
                mode="lines"
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"], y=df["temp_f"],
                name="Temperature (°F)",
                mode="lines",
                yaxis="y2"
            )
        )

        fig.update_layout(
            title="Demand and Temperature",
            xaxis=dict(title="Timestamp"),
            yaxis=dict(title="Demand (MW)", side="left"),
            yaxis2=dict(title="Temperature (°F)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=-0.2)
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No weather/demand columns found in simulation_results.csv.")
