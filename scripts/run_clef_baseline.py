#!/usr/bin/env python3
"""Cloudflare Workers AI clef on the same frozen samples. Thin entry point.

    python3 scripts/run_clef_baseline.py [tasks] [--dry N] [--recompute]
    python3 scripts/run_clef_baseline.py --flash ...   # clef-flash, a separate column

The engine, request builders and scoring live in run_decisions_baseline.py. clef
takes the same {state, questions} body Jev does, so this column sees the schema
questions byte for byte. Needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_decisions_baseline import main  # noqa: E402

if __name__ == "__main__":
    flash = "--flash" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--flash"]
    main("clef-flash" if flash else "clef")
