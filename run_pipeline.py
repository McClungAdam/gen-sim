"""CLI entry point for the gen-sim pipeline.

Examples:
  python run_pipeline.py                  # fetch -> merge -> simulate
  python run_pipeline.py --no-fetch       # rebuild from cached data only
  python run_pipeline.py --only simulate  # one stage
  python run_pipeline.py --no-fetch --as-of 2025-03-12T00:00   # historical window
"""
import argparse
import sys
from datetime import datetime

from gensim.config import DEFAULT_CONFIG, DEFAULT_WORKDIR
from gensim.pipeline import run

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
    ap.add_argument("--only", choices=STAGES, help="run a single stage")
    ap.add_argument("--as-of", type=datetime.fromisoformat, default=None,
                    help="treat this market-local time (or ISO with offset) as 'now' for the merge window")
    args = ap.parse_args(argv)

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
