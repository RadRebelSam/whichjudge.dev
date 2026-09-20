#!/usr/bin/env python3
"""Freeze 500 Civil Comments as a content-gating decision on clean gold.

The existing hate-speech row uses TweetEval, whose text this repo cannot
redistribute and whose labels are thin. Civil Comments is CC0, so the text ships
with the repo, and each comment carries a toxicity score that is the fraction of
crowd annotators who called it toxic.

This row exists to test whether the Don't verdict on hate speech is a property of
the model or of the TweetEval gold. Same decision, better labels, published side
by side rather than quietly swapped in.

Label rule, stated so it can be argued with:
  toxic      toxicity >= 0.5, a majority of annotators called it toxic
  not_toxic  toxicity <  0.5
Balanced 50/50, like every other task here. Real traffic is nowhere near 50%
toxic, so read accuracy as a discrimination measure, not a production rate.

    python3 scripts/prepare_civil.py

Writes data/civil_toxicity.jsonl and data/civil_toxicity.meta.json.
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

SEED = 7
N = 500
MIN_CHARS = 40
MAX_CHARS = 2000
TOXIC_AT = 0.5

URL = ("https://huggingface.co/datasets/google/civil_comments/resolve/main/"
       "data/test-00000-of-00001.parquet")
LOCAL = RAW / "civil_comments_test.parquet"


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install -r requirements.txt first")

    RAW.mkdir(exist_ok=True)
    if not LOCAL.exists():
        print(f"downloading {URL}")
        urllib.request.urlretrieve(URL, LOCAL)
    df = pd.read_parquet(LOCAL, columns=["text", "toxicity"])
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len().between(MIN_CHARS, MAX_CHARS)]
    df["gold"] = (df["toxicity"] >= TOXIC_AT).map({True: "toxic", False: "not_toxic"})
    print(f"usable comments: {len(df)}")
    print("class counts:", df["gold"].value_counts().to_dict())

    per = N // 2
    parts = [g.sample(n=per, random_state=SEED) for _, g in df.groupby("gold")]
    picked = pd.concat(parts).sort_values("text").reset_index(drop=True)

    out = DATA / "civil_toxicity.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for i, r in picked.iterrows():
            f.write(json.dumps({"id": int(i), "text": r["text"], "gold": r["gold"],
                                "toxicity": round(float(r["toxicity"]), 4)},
                               ensure_ascii=False) + "\n")

    lengths = sorted(len(t) for t in picked["text"])
    scores = picked["toxicity"].astype(float)
    meta = {
        "task_id": "civil_toxicity",
        "n": len(picked),
        "seed": SEED,
        "source": "google/civil_comments test split (CC0)",
        "why": ("Clean-licence gold for the same content-gating decision as the "
                "TweetEval hate row, kept alongside it so the Don't verdict can be "
                "attributed to the model or to the gold."),
        "label_rule": f"toxic when toxicity >= {TOXIC_AT}, else not_toxic",
        "label_meaning": ("toxicity is the fraction of crowd annotators who rated the "
                          "comment toxic, not an expert judgement"),
        "balance": "50/50 by construction; real comment streams are far less toxic",
        "text_chars": {"min": lengths[0], "median": lengths[len(lengths) // 2],
                       "max": lengths[-1]},
        "toxicity_score": {"min": round(scores.min(), 4),
                           "median": round(scores.median(), 4),
                           "max": round(scores.max(), 4)},
        "borderline_rows": int(((scores >= 0.4) & (scores < 0.6)).sum()),
        "distribution": picked["gold"].value_counts().to_dict(),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    (DATA / "civil_toxicity.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"\nwrote {out} with {len(picked)} rows")
    print("text chars:", meta["text_chars"])
    print("borderline (0.4-0.6):", meta["borderline_rows"])


if __name__ == "__main__":
    main()
