#!/usr/bin/env python3
"""Recompute calibration (ECE, MCE, reliability bins) from the stored receipts.

Expected calibration error is the traffic-weighted gap between confidence and
accuracy: low ECE means the number may be read as a probability. It does not by
itself say a threshold is safe, and high ECE does not say one is useless; whether
a cutoff works is answered by the gate tables, the per-class recall at each gate in
error_profile.json and the held-out split below, not by ECE.

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
GATES = (0.5, 0.6, 0.7, 0.8, 0.9)
MIN_COVERAGE = 0.5
SPLITS = 400  # random half splits for the cross-validated auto slice
SEED = 7


def score_of(r: dict) -> float:
    """The one score used for calibration AND gating.

    Gates used to threshold on Jev's 'confidence' while ECE was computed on
    'p_chosen'. They differ on hundreds of rows, so the page compared a gate
    built on one number against calibration of another. p_chosen is the
    probability of the answer actually returned, which is what both need.
    """
    p = r.get("p_chosen")
    if p is None:
        p = r.get("confidence")
    if p is None:
        raise SystemExit(f"receipt {r.get('id')} has no p_chosen or confidence")
    return float(p)


def gate_table(rows: list[dict]) -> dict:
    out = {}
    n = len(rows)
    for g in GATES:
        kept = [r for r in rows if score_of(r) >= g]
        out[f"{g}"] = {
            "coverage": round(len(kept) / n, 4) if n else 0.0,
            "accuracy": round(sum(r["pred"] == r["gold"] for r in kept) / len(kept), 4)
                        if kept else None,
        }
    return out


def pick_gate(rows: list[dict]):
    """Strongest gate that still automates at least half the traffic."""
    best = None
    for g in GATES:
        kept = [r for r in rows if score_of(r) >= g]
        if not kept or len(kept) / len(rows) < MIN_COVERAGE:
            continue
        acc = sum(r["pred"] == r["gold"] for r in kept) / len(kept)
        if best is None or acc > best[1]:
            best = (g, acc)
    return best


def cross_validated_slice(rows: list[dict]) -> dict:
    """Choose the gate on one half, score it on the other.

    Picking the gate and reporting its accuracy on the same 500 rows flatters the
    number: whichever gate happened to score well on this sample wins. Repeated
    random half splits give an honest estimate and the size of that optimism.
    """
    import random
    rng = random.Random(SEED)
    outs, gates, covs = [], [], []
    for _ in range(SPLITS):
        idx = list(range(len(rows)))
        rng.shuffle(idx)
        half = len(idx) // 2
        for a, b in ((idx[:half], idx[half:]), (idx[half:], idx[:half])):
            pick_rows = [rows[i] for i in a]
            eval_rows = [rows[i] for i in b]
            chosen = pick_gate(pick_rows)
            if chosen is None:
                continue
            g = chosen[0]
            kept = [r for r in eval_rows if score_of(r) >= g]
            if not kept:
                continue
            outs.append(sum(r["pred"] == r["gold"] for r in kept) / len(kept))
            covs.append(len(kept) / len(eval_rows))
            gates.append(g)
    order = sorted(range(len(outs)), key=lambda i: outs[i])
    k = len(outs)
    return {
        "method": f"{SPLITS} random half splits, gate chosen on one half and scored on the other",
        "accuracy_mean": round(sum(outs) / k, 4) if k else None,
        "accuracy_lo": round(outs[order[int(0.025 * k)]], 4) if k else None,
        "accuracy_hi": round(outs[order[int(0.975 * k) - 1]], 4) if k else None,
        # The 50% coverage rule is applied on the half that picks the gate; the
        # scoring half can land below it. Reported, not hidden.
        "coverage_mean": round(sum(covs) / k, 4) if k else None,
        "halves_below_min_coverage": sum(1 for c in covs if c < MIN_COVERAGE),
        "halves": k,
        "gate_chosen_most": max(set(gates), key=gates.count) if gates else None,
        "note": ("accuracy_lo and accuracy_hi are the 2.5th and 97.5th percentiles of "
                 "scores across overlapping half splits: split variability, not a "
                 "confidence interval for one fixed policy."),
    }


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


def error_profile(rec: dict, key: str) -> dict:
    """Per-class recall, and for Jev, recall at each confidence gate.

    Accuracy hides which way a model is wrong. On a security gate that is the whole
    story: a screen can look 80% accurate while letting 4 injections in 10 through.
    """
    rows = rec[key]
    classes = sorted({r["gold"] for r in rows})
    per_class = {}
    for cls in classes:
        actual = [r for r in rows if r["gold"] == cls]
        caught = [r for r in actual if r["pred"] == cls]
        others = [r for r in rows if r["gold"] != cls]
        false_pos = [r for r in others if r["pred"] == cls]
        per_class[cls] = {
            "n": len(actual),
            "recall": round(len(caught) / len(actual), 4) if actual else None,
            "missed": len(actual) - len(caught),
            "missed_rate": round(1 - len(caught) / len(actual), 4) if actual else None,
            "false_positives": len(false_pos),
            "false_positive_rate": round(len(false_pos) / len(others), 4) if others else None,
        }

    gates = {}
    if key == "jev":
        for g in (0.5, 0.6, 0.7, 0.8, 0.9):
            per_gate = {}
            for cls in classes:
                covered = [r for r in rows if r["gold"] == cls and score_of(r) >= g]
                caught = [r for r in covered if r["pred"] == cls]
                per_gate[cls] = {
                    "covered": len(covered),
                    "recall_on_covered": round(len(caught) / len(covered), 4) if covered else None,
                }
            gates[f"{g}"] = per_gate
    return {"per_class": per_class, "recall_at_gate": gates}


def main() -> None:
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    out = {}
    errors = {}
    gates_out = {}
    for row in summary:
        tid = row["task_id"]
        rec = json.loads((RECEIPTS / f"{tid}.json").read_text(encoding="utf-8"))
        pairs = [(score_of(r), r["pred"] == r["gold"]) for r in rec["jev"]]
        out[tid] = {"p_chosen": reliability(pairs)}
        chosen = pick_gate(rec["jev"])
        gates_out[tid] = {
            "score": "p_chosen",
            "gates": gate_table(rec["jev"]),
            "in_sample": ({"gate": chosen[0], "accuracy": round(chosen[1], 4)}
                          if chosen else None),
            "cross_validated": cross_validated_slice(rec["jev"]),
        }
        errors[tid] = {"jev": error_profile(rec, "jev"),
                       "mini": error_profile(rec, "gpt4o_mini")}
        # the current-model column, when scripts/run_modern_baseline.py has run
        modern_path = RECEIPTS / f"{tid}.modern.json"
        if modern_path.exists():
            md = json.loads(modern_path.read_text(encoding="utf-8"))
            errors[tid]["modern"] = error_profile({"calls": md["calls"]}, "calls")
        # Laya returns p_chosen like Jev, so it gets the same calibration measure.
        laya_path = RECEIPTS / f"{tid}.laya.json"
        if laya_path.exists():
            ld = json.loads(laya_path.read_text(encoding="utf-8"))
            errors[tid]["laya"] = error_profile({"calls": ld["calls"]}, "calls")
            out[tid]["laya"] = reliability([(score_of(r), r["pred"] == r["gold"]) for r in ld["calls"]])
        rel = out[tid]["p_chosen"]
        occupied = sum(1 for b in rel["bins"] if b["n"])
        print(f"{tid:24} ECE {rel['ece']:.3f}  MCE {rel['mce']:.3f}  bins used {occupied}/{BINS}")

    (RESULTS / "calibration.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (RESULTS / "gates.json").write_text(
        json.dumps(gates_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (RESULTS / "error_profile.json").write_text(
        json.dumps(errors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("\nwrote results/calibration.json, results/error_profile.json and results/gates.json")
    print("High ECE means the confidence must not be quoted as a probability on that task;")
    print("whether a threshold helps is in gates.json and error_profile.json, per class.")


if __name__ == "__main__":
    main()
