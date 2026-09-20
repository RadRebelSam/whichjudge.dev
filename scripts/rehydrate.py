#!/usr/bin/env python3
"""Restore the text that scripts/redact_text.py removed.

The public repo ships each sample's id, gold label and a SHA-256 of its text
instead of the text itself, for every dataset whose redistribution terms are
unclear or absent. This downloads the upstream split, matches rows by hash, and
writes the text back only when every hash agrees.

    python3 scripts/rehydrate.py                 # every redacted task
    python3 scripts/rehydrate.py sms_spam        # one task

Writes data/<task>.text.jsonl, which run_eval.py, verify_run.py,
run_tfidf_baseline.py, run_modern_baseline.py and cost_curve.py all pick up
automatically. Nothing is written if a hash does not match, because a partial
rehydration is not something you should trust.

Matching is by hash, not by row index: the frozen ids were reassigned during
sampling, so position carries no meaning. Hash matching is also stricter, since it
fails loudly if upstream ever edits the text.

Needs pandas and pyarrow (both in requirements.txt) and network access. Parquet
files are cached under raw/, which is gitignored.
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
RAW = ROOT / "raw"
DATA = ROOT / "data"

HF = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"

# task -> where its text came from, and which column holds it.
SOURCES = {
    "message_emotion": {
        "cache": "tweet_emotion_test.parquet", "column": "text",
        "url": HF.format(repo="cardiffnlp/tweet_eval",
                         path="emotion/test-00000-of-00001.parquet"),
        "why": "TweetEval: platform terms favour sharing ids over tweet text",
    },
    "content_offensive": {
        "cache": "tweet_offensive_test.parquet", "column": "text",
        "url": HF.format(repo="cardiffnlp/tweet_eval",
                         path="offensive/test-00000-of-00001.parquet"),
        "why": "TweetEval: platform terms favour sharing ids over tweet text",
    },
    "content_hate": {
        "cache": "tweet_hate_test.parquet", "column": "text",
        "url": HF.format(repo="cardiffnlp/tweet_eval",
                         path="hate/test-00000-of-00001.parquet"),
        "why": "TweetEval: platform terms favour sharing ids over tweet text",
    },
    "tweet_sentiment": {
        "cache": "tweet_sentiment_test.parquet", "column": "text",
        "url": HF.format(repo="cardiffnlp/tweet_eval",
                         path="sentiment/test-00000-of-00001.parquet"),
        "why": "TweetEval: platform terms favour sharing ids over tweet text",
    },
    "sms_spam": {
        "cache": "sms_spam.parquet", "column": "sms",
        "url": HF.format(repo="ucirvine/sms_spam",
                         path="plain_text/train-00000-of-00001.parquet"),
        "why": "upstream declares no licence",
    },
    "review_sentiment": {
        "cache": "sst2_validation.parquet", "column": "sentence",
        "url": HF.format(repo="stanfordnlp/sst2",
                         path="data/validation-00000-of-00001.parquet"),
        "why": "upstream declares no licence",
    },
    "news_topic": {
        "cache": "ag_news_test.parquet", "column": "text",
        "url": HF.format(repo="fancyzhx/ag_news",
                         path="data/test-00000-of-00001.parquet"),
        "why": "upstream declares no licence",
    },
}


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_public(task: str) -> list[dict]:
    path = DATA / f"{task}.jsonl"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def fetch(spec: dict) -> Path:
    RAW.mkdir(exist_ok=True)
    local = RAW / spec["cache"]
    if not local.exists():
        print(f"    downloading {spec['url']}")
        urllib.request.urlretrieve(spec["url"], local)
    return local


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install -r requirements.txt first (needs pandas + pyarrow)")

    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SOURCES)
    total = 0
    for task in wanted:
        spec = SOURCES.get(task)
        if spec is None:
            print(f"{task}: not a redacted task, skipping")
            continue
        rows = load_public(task)
        if not rows:
            continue
        if "text" in rows[0]:
            print(f"{task}: text already present, nothing to do")
            continue
        if "text_sha256" not in rows[0]:
            print(f"{task}: no text and no text_sha256, cannot rehydrate")
            continue

        print(f"{task}: {spec['why']}")
        df = pd.read_parquet(fetch(spec), columns=[spec["column"]])

        # The frozen samples were stripped when built, so index both the raw string
        # and its stripped form. Whichever the hash was taken over will match.
        by_hash: dict[str, str] = {}
        for raw in df[spec["column"]].astype(str):
            for candidate in (raw, raw.strip()):
                by_hash.setdefault(sha_text(candidate), candidate)

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
                f"changed since these samples were frozen, so nothing was written."
            )

        out = DATA / f"{task}.text.jsonl"
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for row in restored:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"    {len(restored)} rows restored and hash-checked -> {out.name}")
        total += len(restored)

    if total:
        print(f"\n{total} rows rehydrated. Run scripts/verify_run.py for the full check.")
    else:
        print("\nNothing to rehydrate.")


if __name__ == "__main__":
    main()
