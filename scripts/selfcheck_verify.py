#!/usr/bin/env python3
"""Prove that scripts/verify_run.py fails when the results are corrupted.

A verifier that has never been seen to fail is a decoration. This copies the
repository's data, schemas and results into a temporary directory, breaks one thing
at a time, runs verify_run.py --fast against the copy, and requires a non-zero exit
each time. An outside review showed two corruptions that used to pass: one wrong
answer flipped to gold with the summary adjusted to match, and a current-model
receipt file replaced with "{}". Both are cases here.

    python3 scripts/selfcheck_verify.py

No API, no network, no changes to the repository itself.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8", newline="\n")


def flip_pred_and_summary(root: Path) -> str:
    """One wrong Jev answer becomes right; summary accuracy and Wilson k move with it."""
    tid = "sms_spam"
    rec_path = root / "results/receipts" / f"{tid}.json"
    rec = load(rec_path)
    wrong = next(r for r in rec["jev"] if r["pred"] != r["gold"])
    wrong["pred"] = wrong["gold"]
    dump(rec_path, rec)
    summ_path = root / "results/summary.json"
    summ = load(summ_path)
    row = next(r for r in summ if r["task_id"] == tid)
    k = round(row["jev_acc"] * row["n"]) + 1
    row["jev_acc"] = k / row["n"]
    row["jev_wilson"]["k"] = k
    dump(summ_path, summ)
    return f"{tid}: flipped one wrong Jev pred to gold and raised the published accuracy"


def empty_modern_receipt(root: Path) -> str:
    p = root / "results/receipts/prompt_injection.modern.json"
    p.write_text("{}\n", encoding="utf-8")
    return "prompt_injection: current-model receipts replaced with {}"


def stale_calibration(root: Path) -> str:
    p = root / "results/calibration.json"
    c = load(p)
    c["news_topic"]["p_chosen"]["ece"] = 0.01
    dump(p, c)
    return "news_topic: ECE edited to 0.01 without touching the receipts"


def drop_receipt_row(root: Path) -> str:
    tid = "review_sentiment"
    p = root / "results/receipts" / f"{tid}.json"
    rec = load(p)
    rec["gpt4o_mini"].pop()
    dump(p, rec)
    return f"{tid}: one Mini receipt removed"


def invalid_label_uncounted(root: Path) -> str:
    p = root / "results/modern_baseline.json"
    m = load(p)
    row = next(r for r in m["tasks"] if r["task_id"] == "cfpb_queue_route")
    row["invalid_labels"] = 0
    dump(p, m)
    return "cfpb_queue_route: current-model invalid labels reported as 0"


def wrong_cost_curve(root: Path) -> str:
    p = root / "results/cost_curve.json"
    c = load(p)
    c["points"][-1]["mini_per_million"] = 420.55
    dump(p, c)
    return "cost curve: longest point priced without the cached-token rate"


CASES = [flip_pred_and_summary, empty_modern_receipt, stale_calibration,
         drop_receipt_row, invalid_label_uncounted, wrong_cost_curve]


def copy_tree(dst: Path) -> None:
    for rel in ("data", "schemas", "results", "scripts"):
        shutil.copytree(ROOT / rel, dst / rel, ignore=shutil.ignore_patterns("__pycache__"))


def run_verifier(root: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-X", "utf8", str(root / "scripts/verify_run.py"), "--fast"],
                          cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


def main() -> None:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="whichjudge-selfcheck-") as tmp:
        base = Path(tmp) / "clean"
        copy_tree(base)
        code, out = run_verifier(base)
        if code != 0:
            print(out[-2000:])
            raise SystemExit("the untouched copy does not pass verify_run.py --fast; fix that first")
        print("clean copy: PASS (as it should)")
        for case in CASES:
            root = Path(tmp) / case.__name__
            copy_tree(root)
            what = case(root)
            code, out = run_verifier(root)
            if code == 0:
                failures += 1
                print(f"NOT CAUGHT  {what}")
            else:
                line = next((l for l in out.splitlines()
                             if any(k in l for k in ("MISMATCH", "COVERAGE", "RECEIPTS", "RECOUNT", "FAIL"))),
                            "(exit non-zero)")
                print(f"caught      {what}\n            {line.strip()[:140]}")
    if failures:
        raise SystemExit(f"{failures} corruption(s) passed the verifier")
    print(f"\nSELF-CHECK PASSED: {len(CASES)} corruptions, all caught")


if __name__ == "__main__":
    main()
