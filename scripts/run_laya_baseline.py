#!/usr/bin/env python3
"""Laya, a self-hosted System One-style model, on the same frozen samples.

Laya (convaiinnovations/laya, Apache 2.0) answers the same typed questions Jev
does: choice / score / noul over a state, one forward pass, probabilities and a
confidence back. It runs locally, so this column has no API bill and no network
latency; the latency recorded here is this machine's CPU or GPU and is stated as
such. It is the same schema questions Jev receives, byte for byte, so the two
System One models see identical task information.

    pip install laya
    python3 scripts/run_laya_baseline.py                 # every task, ~35 min on CPU
    python3 scripts/run_laya_baseline.py sms_spam        # one task
    python3 scripts/run_laya_baseline.py --recompute     # statistics only, no model

Writes results/receipts/<task>.laya.json (every input, question set, raw answer
and SHA-256) and results/laya_baseline.json. Receipts are checkpointed per row
to results/receipts/<task>.laya.partial.jsonl (gitignored) and resumed.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_modern_baseline import (  # noqa: E402
    DATA, RECEIPTS, RESULTS, SCHEMAS, dump, load, load_rows, mcnemar, sha256_obj,
    summary_row, wilson,
)

REPO = "convaiinnovations/laya"
CHECKPOINT = "root"  # English zero-shot checkpoint; multilingual and typed-decisions exist


def checkpoint_revision() -> str | None:
    """The HF commit the local snapshot was fetched from, so the column is pinned."""
    try:
        from huggingface_hub import scan_cache_dir
        for repo in scan_cache_dir().repos:
            if repo.repo_id == REPO:
                revs = sorted(repo.revisions, key=lambda r: r.last_modified, reverse=True)
                return revs[0].commit_hash if revs else None
    except Exception:  # noqa: BLE001 - provenance, not a hard requirement
        return None
    return None


def environment(device: str) -> dict:
    import torch
    return {
        "host": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "device": device,
        "cpu": platform.processor(),
        "note": ("Self-hosted. Latency is one forward pass on this machine, no network; it is "
                 "not comparable with the API columns, which include a round trip."),
    }


def parse(res: dict, key: str) -> tuple[str, float, float]:
    ans = res["answers"][key]
    choice = ans.get("choice")
    conf = float(ans.get("confidence") or 0)
    probs = ans.get("probabilities") or {}
    return str(choice), conf, float(probs.get(choice, 0) if choice else 0)


def score(task_id: str, calls: list[dict], revision: str | None) -> dict:
    """Statistics only. No model, no writes to the receipts."""
    summary = summary_row(task_id)
    rec = load(RECEIPTS / f"{task_id}.json")

    def arm_ok(key: str) -> list[bool]:
        by_id = {r["id"]: (r["pred"] == r["gold"]) for r in rec[key]}
        missing = [r["id"] for r in calls if r["id"] not in by_id]
        if missing:
            raise SystemExit(f"{task_id}: {key} receipts missing ids {missing[:5]}")
        return [by_id[r["id"]] for r in calls]

    jev_ok = arm_ok("jev")
    mini_ok = arm_ok("gpt4o_mini")
    for label, arm, want in (("jev", jev_ok, summary["jev_acc"]),
                             ("mini", mini_ok, summary["mini_acc"])):
        got = sum(arm) / len(arm)
        if abs(got - want) > 1e-9:
            raise SystemExit(f"{task_id}: recounted {label} {got:.4f} != published {want:.4f}")

    labels = set(load(SCHEMAS / f"{task_id}.json")["labels"])
    ok = [r["pred"] == r["gold"] for r in calls]
    lat = sorted(r["latency_ms"] for r in calls)
    in_tok = sum(r["input_tokens"] or 0 for r in calls)
    return {
        "task_id": task_id, "model": f"laya ({CHECKPOINT})", "revision": revision, "n": len(calls),
        "acc": sum(ok) / len(ok), "wilson": wilson(sum(ok), len(ok)),
        "p50_ms": lat[len(lat) // 2], "p95_ms": lat[int(len(lat) * 0.95)],
        "input_tokens": in_tok, "output_tokens": 0,
        "tokens_per_call": round(in_tok / len(calls), 1),
        "cost_usd": 0.0, "cost_note": "self-hosted: no API charge; compute not priced",
        "invalid_labels": sum(1 for r in calls if r["pred"] not in labels),
        "mean_confidence": sum(r["confidence"] for r in calls) / len(calls),
        "mcnemar_vs_jev": mcnemar(ok, jev_ok),
        "mcnemar_vs_mini": mcnemar(ok, mini_ok),
        "jev_acc": summary["jev_acc"], "mini_acc": summary["mini_acc"],
    }


def run_task(task_id: str, agent, device: str, revision: str | None) -> dict:
    schema = load(SCHEMAS / f"{task_id}.json")
    questions = schema["questions"]
    key = schema["question_key"]
    rows = load_rows(task_id)
    summary = summary_row(task_id)
    print(f"\n=== {task_id} n={len(rows)} laya/{CHECKPOINT} on {device} ===", flush=True)

    partial = RECEIPTS / f"{task_id}.laya.partial.jsonl"
    done: dict[int, dict] = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["id"]] = rec
        print(f"  resuming, {len(done)} of {len(rows)} already answered", flush=True)

    for i, row in enumerate(rows, 1):
        if row["id"] in done:
            continue
        request = {"state": row["text"], "questions": questions, "model": REPO,
                   "checkpoint": CHECKPOINT}
        t0 = time.perf_counter()
        res = agent.predict(row["text"], questions)
        ms = (time.perf_counter() - t0) * 1000
        pred, conf, p_chosen = parse(res, key)
        usage = res.get("usage") or {}
        rec = {
            "id": row["id"], "gold": row["gold"], "text": row["text"], "pred": pred,
            "confidence": conf, "p_chosen": p_chosen, "latency_ms": ms,
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens", 0),
            "model_returned": res.get("model"),
            "request": request, "response": res,
            "request_sha256": sha256_obj(request), "response_sha256": sha256_obj(res),
            "utc": datetime.now(timezone.utc).isoformat(),
        }
        with partial.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        done[row["id"]] = rec
        if i % 50 == 0 or i == len(rows):
            print(f"  {i}/{len(rows)}  acc so far {sum(r['pred'] == r['gold'] for r in done.values()) / len(done):.3f}", flush=True)

    calls = sorted(done.values(), key=lambda r: r["id"])
    dump(RECEIPTS / f"{task_id}.laya.json", {
        "task_id": task_id, "model": f"laya ({CHECKPOINT})", "repo": REPO, "revision": revision,
        "n": len(calls),
        "samples_sha256": summary["samples_sha256"], "schema_sha256": summary["schema_sha256"],
        "environment": environment(device),
        "calls": calls,
    }, indent=None)
    partial.unlink()
    return score(task_id, calls, revision)


def recompute(task_id: str) -> dict:
    rec = load(RECEIPTS / f"{task_id}.laya.json")
    return score(task_id, rec["calls"], rec.get("revision"))


def main() -> None:
    only_recompute = "--recompute" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [r["task_id"] for r in load(RESULTS / "summary.json")]

    path = RESULTS / "laya_baseline.json"
    prev = {}
    top = {}
    if path.exists():
        top = load(path)
        prev = {r["task_id"]: r for r in top.get("tasks", [])}

    agent, device, revision = None, None, None
    if not only_recompute:
        import laya
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.perf_counter()
        agent = laya.load(REPO)
        revision = checkpoint_revision()
        print(f"loaded {REPO} ({CHECKPOINT}) rev {revision} on {device} in {time.perf_counter() - t0:.1f}s")
    started = datetime.now(timezone.utc).isoformat()

    for tid in ids:
        prev[tid] = recompute(tid) if only_recompute else run_task(tid, agent, device, revision)
        r = prev[tid]
        print(f"  {tid:24} acc {r['acc']:.3f}  (jev {r['jev_acc']:.3f}, mini {r['mini_acc']:.3f})  "
              f"vs jev: {r['mcnemar_vs_jev']['winner']:>3}  vs mini: {r['mcnemar_vs_mini']['winner']:>3}  "
              f"p50 {r['p50_ms']:.0f}ms")

    if only_recompute and top:
        provenance = {k: top[k] for k in ("run_id", "finished_utc", "environment") if k in top}
        provenance["recomputed_utc"] = datetime.now(timezone.utc).isoformat()
    else:
        provenance = {"run_id": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                      "environment": environment(device)}
    order = [r["task_id"] for r in load(RESULTS / "summary.json")]
    dump(path, {
        **provenance,
        "model": f"laya ({CHECKPOINT})", "repo": REPO, "revision": revision or top.get("revision"),
        "licence": "Apache-2.0",
        "why": ("A second System One-style model, self-hosted and open-weight, on the same "
                "samples and the same schema questions as Jev. Same task information, no API."),
        "tasks": [prev[t] for t in order if t in prev],
    })
    print("\nwrote results/laya_baseline.json")


if __name__ == "__main__":
    main()
