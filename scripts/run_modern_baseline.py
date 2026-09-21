#!/usr/bin/env python3
"""Third column: a current small model, so the board is not Jev against 2024.

The standing objection to this bench is fair: gpt-4o-mini-2024-07-18 is two years
old, and beating it says little. This runs the same frozen samples and the same
prompts through a current-generation small model and reports it alongside, with
McNemar against both Jev and 4o-mini.

Additive on purpose. It does not touch run_eval.py, results/summary.json or the
existing receipts, so the chain that verify_run.py checks is unchanged. Same shape
as scripts/run_tfidf_baseline.py.

    python3 scripts/run_modern_baseline.py              # all tasks, hits the API
    python3 scripts/run_modern_baseline.py sms_spam     # one task
    python3 scripts/run_modern_baseline.py --recompute  # stats only, no API calls

Writes results/modern_baseline.json and results/receipts/<task>.modern.json.

Scoring is deliberately separated from calling, so a mistake in the statistics
costs a recompute rather than another 5,500 requests.

Pricing is not hardcoded. Token counts are always recorded; cost is only computed
if PRICES below is filled in from the vendor's own page. An invented price would be
worse than no price on a site that argues about cost.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMAS = ROOT / "schemas"
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.4-mini-2026-03-17"
MAX_COMPLETION_TOKENS = 2000  # this family rejects max_tokens and has no temperature
WORKERS = 8

# USD per million tokens. Leave as None unless you have checked the vendor's page.
PRICES = {"input": None, "output": None}


def sha256_obj(obj) -> str:
    canon = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj, indent=2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def summary_row(task_id: str) -> dict:
    return {r["task_id"]: r for r in load(RESULTS / "summary.json")}[task_id]


def post(payload: dict, key: str, log: list | None = None) -> dict:
    """POST with retries; every attempt is appended to `log` for the receipt."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_URL, data=data, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    last = None
    for attempt in range(5):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = json.loads(resp.read().decode())
            if log is not None:
                log.append({"attempt": attempt + 1, "status": "ok",
                            "ms": round((time.perf_counter() - t0) * 1000)})
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {e.code}: {body[:300]}")
            if log is not None:
                log.append({"attempt": attempt + 1, "status": f"HTTP {e.code}",
                            "ms": round((time.perf_counter() - t0) * 1000)})
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            raise last
        except Exception as e:  # noqa: BLE001
            last = e
            if log is not None:
                log.append({"attempt": attempt + 1, "status": type(e).__name__,
                            "ms": round((time.perf_counter() - t0) * 1000)})
            time.sleep(1.5 * (attempt + 1))
    raise last


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n <= 0:
        return {"k": 0, "n": 0, "p": 0.0, "lo": 0.0, "hi": 0.0}
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / den
    margin = z * math.sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n)) / den
    return {"k": k, "n": n, "p": p, "lo": max(0.0, centre - margin),
            "hi": min(1.0, centre + margin)}


def mcnemar(a_ok: list[bool], b_ok: list[bool]) -> dict:
    """a = this model, b = the comparison arm."""
    a_only = sum(1 for x, y in zip(a_ok, b_ok) if x and not y)
    b_only = sum(1 for x, y in zip(a_ok, b_ok) if y and not x)
    disc = a_only + b_only
    if disc == 0:
        return {"a_only_correct": 0, "b_only_correct": 0, "discordant": 0,
                "p_value": 1.0, "winner": "ns"}
    chi2 = (abs(a_only - b_only) - 1) ** 2 / disc
    p = math.erfc(math.sqrt(max(chi2, 0.0) / 2.0))
    winner = "ns" if p >= 0.05 else ("a" if a_only > b_only else "b")
    return {"a_only_correct": a_only, "b_only_correct": b_only, "discordant": disc,
            "chi2_cc": chi2, "p_value": p, "winner": winner}


def load_rows(task_id: str) -> list[dict]:
    rows = [json.loads(l) for l in (DATA / f"{task_id}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    sidecar = DATA / f"{task_id}.text.jsonl"
    if sidecar.exists():
        texts = {json.loads(l)["id"]: json.loads(l)["text"]
                 for l in sidecar.read_text(encoding="utf-8").splitlines() if l.strip()}
        for r in rows:
            r.setdefault("text", texts.get(r["id"]))
    if any(r.get("text") is None for r in rows):
        raise SystemExit(f"{task_id}: text redacted, run scripts/rehydrate.py first")
    return rows


def score(task_id: str, calls: list[dict]) -> dict:
    """Statistics only. No API, no writes to the receipts."""
    summary = summary_row(task_id)

    # Align on sample id, never on array position. results/<task>.json stores full
    # record objects rather than label strings, so zipping those against labels
    # compares dict to str, is always false, and hands this model a win on every
    # row. Read the receipts and key by id, then check the recount against the
    # published accuracy so a misalignment cannot pass silently again.
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
            raise SystemExit(
                f"{task_id}: recounted {label} {got:.4f} != published {want:.4f}")

    ok = [r["pred"] == r["gold"] for r in calls]
    lat = sorted(r["latency_ms"] for r in calls)
    in_tok = sum(r["input_tokens"] or 0 for r in calls)
    out_tok = sum(r["output_tokens"] or 0 for r in calls)
    unparsed = sum(1 for r in calls if str(r["pred"]).startswith("__unparsed__"))
    # A reply that parses but names a label outside the schema ("auto_loans" for
    # a queue that is called "loans") is wrong, and it is counted wrong in the
    # accuracy above. It was not counted as invalid: the first receipts kept the
    # literal value and only later runs prefixed it, so unparsed_replies read 0
    # while seven such labels sat in the receipts. Count against the schema.
    labels = set(load(SCHEMAS / f"{task_id}.json")["labels"])
    invalid = sorted({str(r["pred"]) for r in calls if r["pred"] not in labels})
    invalid_n = sum(1 for r in calls if r["pred"] not in labels)

    cost = None
    if PRICES["input"] is not None and PRICES["output"] is not None:
        cost = in_tok / 1e6 * PRICES["input"] + out_tok / 1e6 * PRICES["output"]

    acc = sum(ok) / len(ok)
    res = {
        "task_id": task_id, "model": MODEL, "n": len(calls),
        "acc": acc, "wilson": wilson(sum(ok), len(ok)),
        "p50_ms": lat[len(lat) // 2], "p95_ms": lat[int(len(lat) * 0.95)],
        "input_tokens": in_tok, "output_tokens": out_tok,
        "tokens_per_call": round((in_tok + out_tok) / len(calls), 1),
        "cost_usd": cost,
        "unparsed_replies": unparsed,
        "invalid_labels": invalid_n,
        "invalid_label_values": invalid,
        "mcnemar_vs_jev": mcnemar(ok, jev_ok),
        "mcnemar_vs_mini": mcnemar(ok, mini_ok),
        "jev_acc": summary["jev_acc"], "mini_acc": summary["mini_acc"],
    }

    def verdict(m: dict, other: str) -> str:
        if m["p_value"] >= 0.05:
            return "ns"
        return "modern" if m["winner"] == "a" else other

    print(f"  {task_id:24} acc {acc:.3f}  (jev {summary['jev_acc']:.3f}, "
          f"mini {summary['mini_acc']:.3f})  vs jev: {verdict(res['mcnemar_vs_jev'], 'jev'):>6}  "
          f"vs mini: {verdict(res['mcnemar_vs_mini'], 'mini'):>6}  "
          f"{res['tokens_per_call']:.0f} tok/call")
    return res


def run_task(task_id: str, key: str) -> dict:
    schema = load(SCHEMAS / f"{task_id}.json")
    prompt = schema["openai_prompt"]
    labels = schema["labels"]
    rows = load_rows(task_id)
    summary = summary_row(task_id)
    print(f"\n=== {task_id} n={len(rows)} model={MODEL} ===", flush=True)

    def one(row: dict) -> dict:
        request = {
            "model": MODEL,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": row["text"]}],
        }
        attempts: list = []
        t0 = time.perf_counter()
        raw = post(request, key, log=attempts)
        ms = (time.perf_counter() - t0) * 1000
        content = (raw["choices"][0]["message"]["content"] or "").strip()
        try:
            pred = json.loads(content).get("label")
        except Exception:  # noqa: BLE001 - a malformed reply is a wrong answer
            pred = None
        if pred not in labels:
            pred = f"__unparsed__:{content[:40]}"
        usage = raw.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return {
            "id": row["id"], "gold": row["gold"], "pred": pred,
            "latency_ms": ms,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "model_returned": raw.get("model"),
            "request": request, "response": raw,
            "request_sha256": sha256_obj(request), "response_sha256": sha256_obj(raw),
            "attempts": attempts,
        }

    # Checkpoint each receipt as it lands (results/receipts/<task>.modern.partial.jsonl,
    # gitignored); a rerun skips answered ids and the file goes once all are in.
    partial = RECEIPTS / f"{task_id}.modern.partial.jsonl"
    done: dict[int, dict] = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["id"]] = rec
        print(f"  resuming, {len(done)} of {len(rows)} already answered", flush=True)
    todo = [r for r in rows if r["id"] not in done]
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(one, row) for row in todo]
        for i, fut in enumerate(as_completed(futs), len(done) + 1):
            rec = fut.result()
            with lock:
                with partial.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done[rec["id"]] = rec
            if i % 50 == 0 or i == len(rows):
                print(f"  {i}/{len(rows)}", flush=True)
    calls = [done[r["id"]] for r in rows]
    calls.sort(key=lambda r: r["id"])
    partial.unlink()

    dump(RECEIPTS / f"{task_id}.modern.json", {
        "task_id": task_id, "model": MODEL, "n": len(calls),
        "samples_sha256": summary["samples_sha256"],
        "schema_sha256": summary["schema_sha256"],
        "calls": calls,
    }, indent=None)
    return score(task_id, calls)


def recompute(task_id: str) -> dict:
    """Rebuild the statistics from stored receipts. No API calls."""
    rec = load(RECEIPTS / f"{task_id}.modern.json")
    return score(task_id, rec["calls"])


def main() -> None:
    only_recompute = "--recompute" in sys.argv
    key = os.environ.get("OPENAI_API_KEY")
    if not key and not only_recompute:
        raise SystemExit("set OPENAI_API_KEY (see .env.example)")

    started = datetime.now(timezone.utc).isoformat()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or [r["task_id"] for r in load(RESULTS / "summary.json")]

    path = RESULTS / "modern_baseline.json"
    prev = {}
    if path.exists():
        prev = {r["task_id"]: r for r in load(path).get("tasks", [])}

    for tid in ids:
        prev[tid] = recompute(tid) if only_recompute else run_task(tid, key)

    order = [r["task_id"] for r in load(RESULTS / "summary.json")]
    # --recompute changes statistics, not measurements: keep the run's own id,
    # finish time and client environment, and stamp the recomputation separately.
    top = load(path) if path.exists() else {}
    if only_recompute and top:
        provenance = {k: top[k] for k in ("run_id", "finished_utc", "latency_environment") if k in top}
        provenance["recomputed_utc"] = datetime.now(timezone.utc).isoformat()
    else:
        provenance = {
            "run_id": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "latency_environment": {
                "host": platform.platform(),
                "measured_from": os.environ.get("WHICHJUDGE_REGION", "unset"),
                "note": "Wall clock from this client, including network round trip.",
            },
        }
    dump(path, {
        **provenance,
        "model": MODEL,
        "why": ("A current small model, so the board is not Jev against a 2024 baseline. "
                "Same frozen samples and same prompts as the main run."),
        "prices_usd_per_million": PRICES,
        "pricing_note": ("Left unset on purpose. Token counts are measured; cost is only "
                         "computed when a real published price is filled in."),
        "tasks": [prev[t] for t in order if t in prev],
    })
    print("\nwrote results/modern_baseline.json")


if __name__ == "__main__":
    main()
