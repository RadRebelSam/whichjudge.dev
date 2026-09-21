#!/usr/bin/env python3
"""Check that the site being served is byte-for-byte the site in this commit.

Every other check in this repo runs against the working tree. That is how this
project once claimed eleven pages were "uniform" after sampling one CDN edge,
while another reader was served a mix of three generations. This script asks the
server, not the repo.

    python3 scripts/verify_live.py                      # https://whichjudge.dev
    python3 scripts/verify_live.py --base URL --wait 900

For each file under site/, it fetches the public URL with a fresh cache-busting
query, hashes the body, and compares it with the local file. It retries until
everything matches or --wait seconds pass.

What it proves: the public URL, asked with a query no cache has seen, returns exactly
this build. On GitHub Pages such a request is normally filled from origin, but this
script cannot see where a response came from, so it does not claim to.
What it cannot prove: that a request without the query, from any edge, gets the same
bytes. GitHub Pages sets Cache-Control: max-age=600 and does not let a site change
it, so an edge may serve an older file for up to ten minutes after a deploy. Every
generated page carries a build stamp so a reader can see which generation they got.
"""
from __future__ import annotations

import argparse
import hashlib
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

# Receipts are large and change only with a re-run; the pages and scripts are
# where a mixed deploy is visible. Include them with --all.
DEFAULT_GLOBS = ["*.html", "*.js", "*.xml", "*.txt", "*.svg", "decision/*.html"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch(url: str) -> tuple[str, bytes]:
    """Return (status, body). status is the HTTP code as text, or the error class."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "whichjudge-verify-live/1.0",
        "Cache-Control": "no-cache",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return str(r.status), r.read()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", b""
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        # DNS, TLS, reset, timeout: not a verdict on the deploy, so it is reported
        # and retried like a mismatch instead of crashing the check.
        return f"{type(e).__name__}: {getattr(e, 'reason', e)}", b""


def local_files(include_all: bool) -> list[Path]:
    globs = DEFAULT_GLOBS + (["receipts/*.json"] if include_all else [])
    files = []
    for g in globs:
        files.extend(p for p in SITE.glob(g) if p.is_file())
    return sorted(set(files))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://whichjudge.dev")
    ap.add_argument("--wait", type=int, default=0,
                    help="seconds to keep retrying mismatches, for use right after a deploy")
    ap.add_argument("--all", action="store_true", help="also check receipts")
    args = ap.parse_args()

    files = local_files(args.all)
    want = {p.relative_to(SITE).as_posix(): sha(p.read_bytes()) for p in files}
    deadline = time.time() + args.wait
    attempt = 0

    while True:
        attempt += 1
        bad = []
        for rel, expected in want.items():
            url = f"{args.base.rstrip('/')}/{rel}?verify={uuid.uuid4().hex}"
            status, body = fetch(url)
            if status != "200":
                bad.append((rel, status))
            elif sha(body) != expected:
                bad.append((rel, "content differs from this commit"))
        if not bad:
            print(f"LIVE MATCHES BUILD: {len(want)} files fetched from the public URL with a "
                  f"cache-busting query are byte-identical to this commit (attempt {attempt}).")
            print("Edge caches may still hold older copies for up to 600s; "
                  "this does not check plain, cacheable URLs.")
            return
        if time.time() >= deadline:
            print(f"LIVE DOES NOT MATCH BUILD after {attempt} attempt(s):")
            for rel, why in bad[:40]:
                print(f"  {rel}: {why}")
            raise SystemExit(f"{len(bad)} of {len(want)} file(s) differ")
        print(f"attempt {attempt}: {len(bad)} of {len(want)} differ, retrying...")
        time.sleep(20)


if __name__ == "__main__":
    main()
