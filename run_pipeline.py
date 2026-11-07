"""CLI entry point for the gen-sim pipeline.

Examples:
  python run_pipeline.py                  # fetch -> merge -> simulate
  python run_pipeline.py --no-fetch       # rebuild from cached data only
  python run_pipeline.py --only simulate  # one stage
  python run_pipeline.py --no-fetch --as-of 2025-03-12T00:00   # historical window

  Merchant asset screen (Phase 1):
  python run_pipeline.py --asset fries                 # fetch (cached) -> calibrate -> value
  python run_pipeline.py --asset fries --only value    # valuation only
  python run_pipeline.py --asset fries --refresh       # refetch USGS / EIA-923
"""
import argparse
import sys
from datetime import datetime

from gensim.config import DEFAULT_CONFIG, DEFAULT_WORKDIR
from gensim.pipeline import ASSET_STAGES, run, run_asset

STAGES = ("fetch", "merge", "simulate")


def main(argv=None) -> int:
    # Status lines contain emoji; Windows consoles/pipes default to cp1252 and would crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="config JSON (default: %(default)s)")
    ap.add_argument("--workdir", default=str(DEFAULT_WORKDIR), help="data/output folder (default: %(default)s)")
    ap.add_argument("--no-fetch", action="store_true", help="skip network fetches; use cached files")
    ap.add_argument("--only", choices=STAGES + ASSET_STAGES, help="run a single stage")
    ap.add_argument("--asset", help="run the merchant asset screen for config/assets/<name>.yaml")
    ap.add_argument("--refresh", action="store_true", help="asset mode: refetch source data instead of using the cache")
    ap.add_argument("--as-of", type=datetime.fromisoformat, default=None,
                    help="treat this market-local time (or ISO with offset) as 'now' for the merge window")
    args = ap.parse_args(argv)

    if args.asset:
        stages = (args.only,) if args.only else tuple(s for s in ASSET_STAGES if not (args.no_fetch and s == "fetch"))
        run_asset(args.asset, stages=stages, refresh=args.refresh, workdir=args.workdir)
        return 0
    stages = {args.only} if args.only else set(STAGES) - ({"fetch"} if args.no_fetch else set())
    result = run(
        args.config,
        args.workdir,
        do_fetch="fetch" in stages,
        do_merge="merge" in stages,
        do_simulate="simulate" in stages,
        now=args.as_of,
    )
    errors = result["fetch_errors"]
    if errors:
        print(f"⚠️ {len(errors)} fetch step(s) failed: {', '.join(errors)} (cached data used)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
