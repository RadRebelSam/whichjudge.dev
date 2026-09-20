#!/usr/bin/env python3
"""Freeze a prompt-injection screen: is this untrusted input trying to hijack the agent?

The first security decision on this bench. Everything else here misroutes a ticket
when it is wrong; this one lets an attacker steer an agent, so the number that
matters is the false-negative rate at the quit line, not headline accuracy.

Source: deepset/prompt-injections (Apache-2.0), label 1 = injection, 0 = legitimate.

Size is the honest constraint. The whole dataset is 662 rows across both splits.
Freezing 500 would leave almost nothing to train the classical baseline on, and a
baseline trained on 160 rows would lose for reasons that have nothing to do with
being classical. So this row is n=300, and the remaining rows train TF-IDF. The
site shows the per-task n rather than pretending everything is 500.

    python3 scripts/prepare_injection.py

Writes data/prompt_injection.jsonl and data/prompt_injection.meta.json.
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
N = 300
LABELS = {1: "injection", 0: "legitimate"}

BASE = ("https://huggingface.co/datasets/deepset/prompt-injections/resolve/"
        "refs%2Fconvert%2Fparquet/default/{split}/0000.parquet")
SPLITS = ("train", "test")


def local(split: str) -> Path:
    return RAW / f"prompt_injections_{split}.parquet"


def load_all():
    import pandas as pd

    RAW.mkdir(exist_ok=True)
    frames = []
    for split in SPLITS:
        p = local(split)
        if not p.exists():
            url = BASE.format(split=split)
            print(f"downloading {split}: {url}")
            urllib.request.urlretrieve(url, p)
        df = pd.read_parquet(p)
        df["split"] = split
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install -r requirements.txt first")

    df = load_all()
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() >= 10].drop_duplicates(subset=["text"])
    df["gold"] = df["label"].map(LABELS)
    print(f"pool after dedupe: {len(df)}")
    print("class counts:", df["gold"].value_counts().to_dict())

    per = N // 2
    smallest = df["gold"].value_counts().min()
    if smallest < per:
        raise SystemExit(f"only {smallest} rows in the smaller class, need {per}")

    parts = [g.sample(n=per, random_state=SEED) for _, g in df.groupby("gold")]
    picked = pd.concat(parts).sort_values("text").reset_index(drop=True)
    held_out = df[~df["text"].isin(set(picked["text"]))]

    out = DATA / "prompt_injection.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for i, r in picked.iterrows():
            f.write(json.dumps({"id": int(i), "text": r["text"], "gold": r["gold"]},
                               ensure_ascii=False) + "\n")

    lengths = sorted(len(t) for t in picked["text"])
    meta = {
        "task_id": "prompt_injection",
        "n": len(picked),
        "seed": SEED,
        "source": "deepset/prompt-injections (Apache-2.0), train and test splits combined",
        "label_rule": "injection when the source label is 1, else legitimate",
        "why_n_is_300": ("The dataset holds 662 rows in total. Freezing 500 would leave "
                         "too few to train the classical baseline on, so the baseline "
                         "would lose for the wrong reason. 300 eval, "
                         f"{len(held_out)} held out for training."),
        "held_out_for_tfidf": int(len(held_out)),
        "read_this_as": ("A false negative here is a hijacked agent, not a misrouted "
                         "ticket, so judge this row on recall of injections at the quit "
                         "line rather than on accuracy."),
        "staleness_caveat": ("Prompt injection is adversarial and this corpus predates "
                             "current agent tooling. It measures known 2022-era patterns, "
                             "not what is being attempted against agents today."),
        "balance": "50/50 by construction; real traffic is overwhelmingly legitimate",
        "text_chars": {"min": lengths[0], "median": lengths[len(lengths) // 2],
                       "max": lengths[-1]},
        "distribution": picked["gold"].value_counts().to_dict(),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    (DATA / "prompt_injection.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"\nwrote {out} with {len(picked)} rows, {len(held_out)} held out for TF-IDF")
    print("text chars:", meta["text_chars"])
    print("example injection:", picked[picked["gold"] == "injection"]["text"].iloc[0][:110])


if __name__ == "__main__":
    main()
