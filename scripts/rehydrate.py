#!/usr/bin/env python3
"""Restore the tweet text that scripts/redact_text.py removed.

The public repo ships tweet IDs, gold labels and a SHA-256 of each text instead of
the text itself. This script downloads the upstream TweetEval split, matches rows by
position in the original split, and checks every restored string against the stored
hash before writing anything.

    python3 scripts/rehydrate.py

Writes data/<task>.text.jsonl, which run_eval.py and verify_run.py pick up
automatically. Nothing is written if a hash does not match.

Needs `pandas` and `pyarrow` (already in requirements.txt) and network access.
Parquet files are cached under raw/, which is gitignored.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# task -> TweetEval config used when the samples were built
SOURCES = {
    "message_emotion": "emotion",
    "content_offensive": "offensive",
    "content_hate": "hate",
    "tweet_sentiment": "sentiment",
}

BASE = ("https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/"
        "{config}/test-00000-of-00001.parquet")
CACHE = ROOT / "raw"


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_public(task: str):
    path = DATA / f"{task}.jsonl"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install -r requirements.txt first (needs pandas + pyarrow)")

    total_ok = 0
    for task, config in SOURCES.items():
        rows = load_public(task)
        if not rows:
            continue
        if "text" in rows[0]:
            print(f"{task}: text already present, nothing to do")
            continue
        if "text_sha256" not in rows[0]:
            print(f"{task}: no text and no text_sha256, cannot rehydrate")
            continue

        url = BASE.format(config=config)
        CACHE.mkdir(exist_ok=True)
        local = CACHE / f"tweet_{config}_test.parquet"
        if not local.exists():
            print(f"{task}: downloading {url}")
            urllib.request.urlretrieve(url, local)
        else:
            print(f"{task}: using cached {local.name}")
        df = pd.read_parquet(local)

        # The frozen ids were reset during sampling, so the upstream row index is
        # gone. Match on the hash instead: build hash -> text for the whole split
        # and look each sample up. More robust than an index, and it fails loudly
        # if upstream ever edits the text.
        by_hash = {}
        for text in df["text"].astype(str):
            by_hash.setdefault(sha_text(text), text)

        restored, missing = [], []
        for r in rows:
            text = by_hash.get(r["text_sha256"])
            if text is None:
                missing.append(r["id"])
                continue
            restored.append({"id": r["id"], "text": text})

        if missing:
            raise SystemExit(
                f"{task}: {len(missing)} of {len(rows)} rows not found in the current "
                f"upstream split (first: id {missing[0]}). The dataset revision has "
                f"changed since these samples were frozen; a partial rehydration is "
                f"not trustworthy, so nothing was written."
            )

        out = DATA / f"{task}.text.jsonl"
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for row in restored:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{task}: {len(restored)} rows restored and hash-checked -> {out.name}")
        total_ok += len(restored)

    if total_ok:
        print(f"\n{total_ok} rows rehydrated. Now run scripts/verify_run.py for the full check.")
    else:
        print("\nNothing to rehydrate.")


if __name__ == "__main__":
    main()
