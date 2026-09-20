#!/usr/bin/env python3
"""Recompute calibration (ECE, MCE, reliability bins) from the stored receipts.

The quit line only means something if Jev's confidence is honest: when it says 0.9,
it should be right about 90% of the time. Expected calibration error is the
traffic-weighted gap between confidence and accuracy, so low ECE means a threshold
can be trusted and high ECE means it cannot.

This reads results/receipts/<task>.json and writes results/calibration.json. No API
calls, no network. Run it after every scripts/run_eval.py, or the published ECE
describes an older run.

    python3 scripts/calibrate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"

BINS = 10  # fixed-width bins of 0.1 across [0, 1]


def reliability(pairs: list[tuple[float, bool]]) -> dict:
    """pairs: (confidence in the chosen answer, was that answer correct)."""
    n = len(pairs)
    bins = []
    ece = 0.0
    mce = 0.0
    for i in range(BINS):
        lo = i / BINS
        hi = (i + 1) / BINS
        # last bin closes on the right so confidence 1.0 is counted
        hits = [p for p in pairs if (lo <= p[0] < hi) or (i == BINS - 1 and p[0] == 1.0)]
        if hits:
            conf = sum(p[0] for p in hits) / len(hits)
            acc = sum(1 for p in hits if p[1]) / len(hits)
            gap = abs(conf - acc)
            ece += (len(hits) / n) * gap
            mce = max(mce, gap)
        else:
            conf = None
            acc = None
        bins.append({
            "lo": round(lo, 1),
            "hi": round(hi, 1),
            "n": len(hits),
            "conf": conf,
            "acc": acc,
        })
    return {"ece": ece, "mce": mce, "n": n, "bins": bins}


def main() -> None:
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    out = {}
    for row in summary:
        tid = row["task_id"]
        rec = json.loads((RECEIPTS / f"{tid}.json").read_text(encoding="utf-8"))
        pairs = []
        for r in rec["jev"]:
            p = r.get("p_chosen")
            if p is None:
                p = r.get("confidence")
            if p is None:
                raise SystemExit(f"{tid}: receipt {r['id']} has no p_chosen or confidence")
            pairs.append((float(p), r["pred"] == r["gold"]))
        out[tid] = {"p_chosen": reliability(pairs)}
        rel = out[tid]["p_chosen"]
        occupied = sum(1 for b in rel["bins"] if b["n"])
        print(f"{tid:24} ECE {rel['ece']:.3f}  MCE {rel['mce']:.3f}  bins used {occupied}/{BINS}")

    (RESULTS / "calibration.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("\nwrote results/calibration.json")
    print("High ECE means the confidence number cannot carry a quit line on that task.")


if __name__ == "__main__":
    main()
