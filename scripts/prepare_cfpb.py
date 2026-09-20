#!/usr/bin/env python3
"""Freeze 500 CFPB consumer complaints as a real production routing decision.

Every other task on this bench is academic gold. This one is not: the Consumer
Financial Protection Bureau runs this as a live system, consumers write the
narrative themselves and pick the product it belongs to, and the complaint is
routed to the company on that basis.

Two sources, on purpose:

  text   BEE-spoke-data/consumer-finance-complaints (has-text config, CC0), a
         mirror of the CFPB database that keeps the narratives.
  label  files.consumerfinance.gov/ccdb/complaints.csv.zip, the Bureau's own
         export, joined on Complaint ID.

The Bureau's own export does not carry narratives and the search API that does is
not reachable from a script, so the text comes from the mirror. The label never
does: every row's Product is taken from the official file, and any row whose
mirror Product disagrees with the official one is dropped rather than guessed at.
The disagreement rate is recorded in the meta file.

    python3 scripts/prepare_cfpb.py

Writes data/cfpb_queue_route.jsonl and data/cfpb_queue_route.meta.json.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
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
MIN_CHARS = 200          # a real narrative, not a one-liner
MAX_CHARS = 4000         # keep one outlier from dominating cost
CANDIDATES_PER_QUEUE = 4000

OFFICIAL_ZIP = RAW / "cfpb_complaints.csv.zip"
MIRROR_PARQUET = RAW / "cfpb_has_text_0.parquet"

# The Bureau has renamed products several times. Collapse the history into eight
# queues that a real support organisation would actually staff.
QUEUES = {
    "credit_reporting": [
        "Credit reporting, credit repair services, or other personal consumer reports",
        "Credit reporting or other personal consumer reports",
        "Credit reporting",
    ],
    "debt_collection": ["Debt collection"],
    "cards": ["Credit card or prepaid card", "Credit card", "Prepaid card"],
    "bank_account": ["Checking or savings account", "Bank account or service"],
    "mortgage": ["Mortgage"],
    "money_transfer": [
        "Money transfer, virtual currency, or money service",
        "Money transfers",
        "Virtual currency",
    ],
    "loans": [
        "Vehicle loan or lease",
        "Payday loan, title loan, or personal loan",
        "Payday loan, title loan, personal loan, or advance loan",
        "Consumer Loan",
        "Payday loan",
    ],
    "student_loan": ["Student loan"],
}
PRODUCT_TO_QUEUE = {p: q for q, ps in QUEUES.items() for p in ps}


def official_products(ids: set[str]) -> dict[str, str]:
    """Product for each Complaint ID, straight from the Bureau's export."""
    if not OFFICIAL_ZIP.exists():
        raise SystemExit(
            f"missing {OFFICIAL_ZIP}. Download the Bureau's export first:\n"
            "  https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
        )
    found: dict[str, str] = {}
    with zipfile.ZipFile(OFFICIAL_ZIP) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
            for row in reader:
                cid = (row.get("Complaint ID") or "").strip()
                if cid in ids:
                    found[cid] = (row.get("Product") or "").strip()
                    if len(found) == len(ids):
                        break
    return found


def main() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install -r requirements.txt first")

    if not MIRROR_PARQUET.exists():
        raise SystemExit(
            f"missing {MIRROR_PARQUET}. Fetch the narratives shard:\n"
            "  https://huggingface.co/datasets/BEE-spoke-data/consumer-finance-complaints"
            "/resolve/main/has-text/train-00000-of-00003.parquet"
        )

    df = pd.read_parquet(MIRROR_PARQUET, columns=[
        "Complaint ID", "Product", "Consumer complaint narrative", "Date received"])
    df = df.rename(columns={"Consumer complaint narrative": "text"})
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len().between(MIN_CHARS, MAX_CHARS)]
    df["queue"] = df["Product"].map(PRODUCT_TO_QUEUE)
    df = df[df["queue"].notna()]
    print(f"mirror rows usable: {len(df)}")

    # Take a generous candidate pool per queue, then keep only rows the Bureau's
    # own file agrees with. Sampling before the join keeps the official scan cheap.
    parts = []
    for queue, group in df.groupby("queue"):
        parts.append(group.sample(n=min(CANDIDATES_PER_QUEUE, len(group)), random_state=SEED))
    pool = pd.concat(parts, ignore_index=True)
    pool["Complaint ID"] = pool["Complaint ID"].astype(str)
    ids = set(pool["Complaint ID"])
    print(f"candidate pool: {len(pool)} rows across {pool['queue'].nunique()} queues")
    print("scanning the official export for those Complaint IDs (one pass, ~5 GB)")

    official = official_products(ids)
    print(f"matched in official export: {len(official)} / {len(ids)}")

    agree, disagree, missing = [], 0, 0
    for cid, text, queue in zip(pool["Complaint ID"], pool["text"], pool["queue"]):
        product = official.get(cid)
        if product is None:
            missing += 1
            continue
        if PRODUCT_TO_QUEUE.get(product) != queue:
            disagree += 1
            continue
        agree.append({"id": cid, "text": text, "gold": queue, "official_product": product})
    print(f"label agreement: {len(agree)} agree, {disagree} disagree, {missing} not found")

    by_queue: dict[str, list] = defaultdict(list)
    for row in agree:
        by_queue[row["gold"]].append(row)

    per = N // len(QUEUES)
    picked = []
    import random
    rng = random.Random(SEED)
    for queue in sorted(QUEUES):
        rows = sorted(by_queue.get(queue, []), key=lambda r: r["id"])
        if len(rows) < per:
            raise SystemExit(f"queue {queue} has only {len(rows)} verified rows, need {per}")
        picked.extend(rng.sample(rows, per))
    # top up deterministically to exactly N
    leftovers = [r for q in sorted(QUEUES) for r in sorted(by_queue[q], key=lambda r: r["id"])
                 if r not in picked]
    rng.shuffle(leftovers)
    picked.extend(leftovers[: N - len(picked)])
    picked.sort(key=lambda r: r["id"])

    out = DATA / "cfpb_queue_route.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for i, r in enumerate(picked):
            f.write(json.dumps({"id": i, "text": r["text"], "gold": r["gold"],
                                "complaint_id": r["id"]}, ensure_ascii=False) + "\n")

    lengths = sorted(len(r["text"]) for r in picked)
    meta = {
        "task_id": "cfpb_queue_route",
        "n": len(picked),
        "seed": SEED,
        "source_text": ("BEE-spoke-data/consumer-finance-complaints has-text config (CC0), "
                        "a mirror of the CFPB Consumer Complaint Database"),
        "source_labels": ("files.consumerfinance.gov/ccdb/complaints.csv.zip, the Bureau's "
                          "own export, joined on Complaint ID"),
        "why_two_sources": ("The Bureau's export omits narratives and its search API blocks "
                            "scripted clients, so text comes from the mirror. Labels never do."),
        "label_check": {"agree": len(agree), "disagree": disagree, "not_found": missing},
        "queues": {q: sorted(ps) for q, ps in QUEUES.items()},
        "narrative_chars": {"min": lengths[0], "median": lengths[len(lengths) // 2],
                            "max": lengths[-1]},
        "label_caveat": ("Product is selected by the consumer filing the complaint, not by an "
                         "expert annotator, and the Bureau has renamed products over time. "
                         "Treat it as a real routing signal, not a gold standard."),
        "pii": "The Bureau redacts personal details as XXXX before publication.",
        "distribution": dict(Counter(r["gold"] for r in picked)),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    (DATA / "cfpb_queue_route.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"\nwrote {out} with {len(picked)} rows")
    print("distribution:", meta["distribution"])
    print("narrative chars:", meta["narrative_chars"])


if __name__ == "__main__":
    main()
