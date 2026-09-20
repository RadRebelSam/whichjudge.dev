#!/usr/bin/env python3
"""Remove third-party text that this repo may not redistribute, keeping it verifiable.

Four tasks use tweet text from TweetEval. Platform terms for that content have
historically allowed sharing tweet IDs rather than tweet text, so publishing the raw
text here is a redistribution question this project does not need to take on.

This script replaces the text with its SHA-256 in the public files:

    data/<task>.jsonl                text -> text_sha256
    results/receipts/<task>.json     text and request.state -> null, text_sha256 added
    site/receipts/<task>.json        same

and writes the removed text to data/<task>.text.jsonl, which is gitignored. Anyone
else restores it with scripts/rehydrate.py, which re-downloads the upstream dataset
and checks every restored string against the stored hash.

What survives redaction without rehydration:
  - recounting accuracy from receipts (pred vs gold needs no text)
  - the response hashes
What needs rehydration:
  - the request hashes, because the request contains the text
  - sample-drift checks

Idempotent: running it twice is a no-op.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"
SITE_RECEIPTS = ROOT / "site" / "receipts"

# Only these carry third-party tweet text.
REDACT_TASKS = [
    "message_emotion",
    "content_offensive",
    "content_hate",
    "tweet_sentiment",
]

REDACTION_NOTE = (
    "Text removed for redistribution reasons; restore with scripts/rehydrate.py "
    "and verify against text_sha256."
)


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def dump_json(path: Path, obj) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def redact_samples(task: str) -> int:
    path = DATA / f"{task}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if all("text" not in r for r in rows):
        print(f"  {task}: samples already redacted")
        return 0

    sidecar = DATA / f"{task}.text.jsonl"
    with sidecar.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "text": r["text"]}, ensure_ascii=False) + "\n")

    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            out = {k: v for k, v in r.items() if k != "text"}
            out["text_sha256"] = sha_text(r["text"])
            out["text_redacted"] = True
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    print(f"  {task}: {len(rows)} samples redacted, text moved to {sidecar.name}")
    return len(rows)


def redact_receipts(path: Path) -> int:
    if not path.exists():
        return 0
    rec = json.loads(path.read_text(encoding="utf-8"))
    touched = 0
    for key in ("jev", "gpt4o_mini"):
        for r in rec.get(key, []):
            if r.get("text") is None:
                continue
            r["text_sha256"] = sha_text(r["text"])
            r["text"] = None
            req = r.get("request")
            if isinstance(req, dict) and req.get("state") is not None:
                req["state"] = None
            touched += 1
    if touched:
        rec["text_redacted"] = True
        rec["redaction_note"] = REDACTION_NOTE
        dump_json(path, rec)
    return touched


def repin_sample_hash(task: str) -> None:
    """data/<task>.jsonl changed, so anything that pinned its hash must follow.

    The original hash is kept as samples_sha256_original for provenance, while
    samples_sha256 tracks the file a visitor can actually download and hash.
    """
    new_hash = sha256_file(DATA / f"{task}.jsonl")
    for path in (RECEIPTS / f"{task}.json", SITE_RECEIPTS / f"{task}.json"):
        if not path.exists():
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("samples_sha256") != new_hash:
            rec.setdefault("samples_sha256_original", rec.get("samples_sha256"))
            rec["samples_sha256"] = new_hash
            dump_json(path, rec)

    summary_path = RESULTS / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for row in summary:
        if row["task_id"] == task and row.get("samples_sha256") != new_hash:
            row.setdefault("samples_sha256_original", row.get("samples_sha256"))
            row["samples_sha256"] = new_hash
    dump_json(summary_path, summary)


def main() -> None:
    print("Redacting third-party text from public files")
    total = 0
    for task in REDACT_TASKS:
        total += redact_samples(task)
        a = redact_receipts(RECEIPTS / f"{task}.json")
        b = redact_receipts(SITE_RECEIPTS / f"{task}.json")
        if a or b:
            print(f"  {task}: {a} results receipts, {b} site receipts redacted")
        repin_sample_hash(task)

    # data/*.jsonl bytes just changed, so the manifest has to record the new hashes
    # or verify_run.py would report drift on files this script rewrote on purpose.
    manifest_paths = [RESULTS / "manifest.json", SITE_RECEIPTS / "manifest.json"]
    for mp in manifest_paths:
        if not mp.exists():
            continue
        m = json.loads(mp.read_text(encoding="utf-8"))
        files = m.get("file_sha256") or {}
        for task in REDACT_TASKS:
            rel = f"data/{task}.jsonl"
            if rel in files:
                files[rel] = sha256_file(ROOT / rel)
        m["file_sha256"] = files
        m["redacted_tasks"] = REDACT_TASKS
        m["redaction_note"] = REDACTION_NOTE
        dump_json(mp, m)
    print("manifest hashes updated for the redacted samples")

    if total:
        print(f"\n{total} rows redacted. data/*.text.jsonl holds the text locally and is gitignored.")
    print("Run scripts/verify_run.py to confirm the table still recounts.")


if __name__ == "__main__":
    main()
