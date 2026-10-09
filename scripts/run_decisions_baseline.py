#!/usr/bin/env python3
"""Two more System One-style columns on the same frozen samples and the same rubric.

  decisions   OpenAI Decisions API, model gpt-6-luna   (POST /v1/decisions)
  clef        Cloudflare Workers AI @cf/cloudflare/clef (and clef-flash, labelled separately)

Both answer the same typed choice question Jev answers. The request is generated
from the same schema rubric Jev and the chat models get (the question's
instructions plus every label's criteria sentence), exactly as openai_prompt_from
does for the OpenAI column, so no column has a hand-tuned prompt.

Shape of this script: one engine, two thin entry points.

    python3 scripts/run_decisions_baseline.py                  # every task, hits the API
    python3 scripts/run_decisions_baseline.py sms_spam         # one task
    python3 scripts/run_decisions_baseline.py --dry 3          # 3 rows of the first task, writes nothing
    python3 scripts/run_decisions_baseline.py --recompute      # statistics only, no API calls
    python3 scripts/run_clef_baseline.py [--flash] [same flags]

Writes results/<column>_baseline.json and results/receipts/<task>.<column>.json.
Receipts are checkpointed per row to results/receipts/<task>.<column>.partial.jsonl
(gitignored) and resumed. Scoring is separate from calling, as in
run_modern_baseline.py, so a statistics fix costs a recompute, not another run.

Credentials come from the environment (a gitignored .env is read if present):
OPENAI_API_KEY for decisions; CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN for
clef. Keys are never written to receipts: only the request body is stored, and
the Cloudflare account id is replaced by a placeholder in the stored endpoint.
"""
from __future__ import annotations

import json
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_modern_baseline import (  # noqa: E402
    RECEIPTS, RESULTS, ROOT, SCHEMAS, dump, load, load_rows, mcnemar, sha256_obj,
    summary_row, wilson,
)

WORKERS = 8
PRICE_CHECKED = "2026-10-09"  # date the prices below were read off the vendor pages

# An explicit URL, never OPENAI_BASE_URL: that variable is overridden for chat completions.
DECISIONS_URL = "https://api.openai.com/v1/decisions"
CF_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

SPECS = {
    "decisions": {
        "label": "gpt-6-luna", "model": "gpt-6-luna", "price_in": 0.10,
        "endpoint": DECISIONS_URL, "env": ("OPENAI_API_KEY",),
        "price_url": "https://developers.openai.com/api/docs/pricing",
        "price_basis": "Standard tier, short context, input $0.10 per 1M tokens. The pricing page lists the model, not the Decisions API separately, so this applies that input price to the input tokens each call reports and charges nothing for output because every call reports 0 output tokens. No cached-input discount applied.",
        "why": ("OpenAI's Decisions API, a System One-style endpoint: typed questions in, "
                "probabilities back, no generated text. Same samples, same rubric as Jev."),
    },
    "clef": {
        "label": "clef", "model": "@cf/cloudflare/clef", "price_in": 0.24,
        "endpoint": CF_URL.format(account="<ACCOUNT_ID>", model="@cf/cloudflare/clef"),
        "env": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"),
        "price_url": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
        "price_basis": "Workers AI list price, $0.240 per 1M input tokens (21818 neurons per 1M). Output tokens are 0 on every call.",
        "why": ("Cloudflare Workers AI clef (27B), a Jev-shaped System One endpoint: the request "
                "body is the same {state, questions} Jev receives. Same samples, same schema."),
    },
    "clef-flash": {
        "label": "clef-flash", "model": "@cf/cloudflare/clef-flash", "price_in": 0.09,
        "endpoint": CF_URL.format(account="<ACCOUNT_ID>", model="@cf/cloudflare/clef-flash"),
        "env": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"),
        "price_url": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
        "price_basis": "Workers AI list price, $0.090 per 1M input tokens (8182 neurons per 1M). Output tokens are 0 on every call.",
        "why": ("Cloudflare Workers AI clef-flash, the smaller sibling of clef, run on the same "
                "samples and schema and reported separately."),
    },
}


def load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def post(url: str, headers: dict, payload: dict, log: list) -> dict:
    """POST with retries; every attempt is appended to `log` for the receipt."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    last = None
    for attempt in range(8):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode())
            log.append({"attempt": attempt + 1, "status": "ok",
                        "ms": round((time.perf_counter() - t0) * 1000)})
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {e.code}: {body[:300]}")
            log.append({"attempt": attempt + 1, "status": f"HTTP {e.code}",
                        "ms": round((time.perf_counter() - t0) * 1000)})
            if e.code == 429 and "daily free allocation" in body:
                raise last  # quota exhausted: retrying cannot help
            if e.code in (429, 500, 502, 503, 504, 529):  # 529: Workers AI "inference failed", transient
                time.sleep(min(30.0, 2.0 * (attempt + 1) ** 1.5))
                continue
            raise last
        except Exception as e:  # noqa: BLE001
            last = e
            log.append({"attempt": attempt + 1, "status": type(e).__name__,
                        "ms": round((time.perf_counter() - t0) * 1000)})
            time.sleep(1.5 * (attempt + 1))
    raise last


# ---- request builders: one rubric, two wire formats ------------------------------------------

def decisions_body(schema: dict, text: str, model: str) -> dict:
    key = schema["question_key"]
    q = schema["questions"][key]
    return {"model": model, "input": text, "questions": [{
        "type": "choice", "name": key, "instructions": q["instructions"],
        "choices": [{"value": lab, "description": q["criteria"][lab]} for lab in schema["labels"]],
    }]}


def clef_body(schema: dict, text: str, model: str) -> dict:
    # Byte for byte what Jev receives (minus the model field, which is in the URL).
    return {"state": text, "questions": schema["questions"]}


def parse_decisions(resp: dict, key: str) -> tuple[str, float, float]:
    ans = next(a for a in resp["answers"] if a.get("name") == key)
    choice = ans.get("choice")
    probs = {p["value"]: p["probability"] for p in ans.get("probabilities") or []}
    return str(choice), float(ans.get("confidence") or 0), float(probs.get(choice, 0) if choice else 0)


def parse_clef(resp: dict, key: str) -> tuple[str, float, float]:
    ans = resp["answers"][key]
    choice = ans.get("choice")
    probs = ans.get("probabilities") or {}
    return str(choice), float(ans.get("confidence") or 0), float(probs.get(choice, 0) if choice else 0)


def unwrap_clef(raw: dict) -> dict:
    if raw.get("success") is False or "result" not in raw:
        raise RuntimeError(f"clef error: {json.dumps(raw.get('errors'))[:300]}")
    return raw["result"]


def prepare(col: str):
    """(url, headers, body_fn, unwrap_fn, parse_fn) for a column; reads credentials from env."""
    spec = SPECS[col]
    missing = [e for e in spec["env"] if not os.environ.get(e)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} (never print it)")
    if col == "decisions":
        h = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"}
        return DECISIONS_URL, h, decisions_body, lambda raw: raw, parse_decisions
    h = {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}", "Content-Type": "application/json"}
    url = CF_URL.format(account=os.environ["CLOUDFLARE_ACCOUNT_ID"], model=spec["model"])
    return url, h, clef_body, unwrap_clef, parse_clef


# ---- scoring (no API, no writes to receipts) -------------------------------------------------

def score(col: str, task_id: str, calls: list[dict]) -> dict:
    spec = SPECS[col]
    summary = summary_row(task_id)
    rec = load(RECEIPTS / f"{task_id}.json")

    def arm_ok(key: str) -> list[bool]:
        by_id = {r["id"]: (r["pred"] == r["gold"]) for r in rec[key]}
        missing = [r["id"] for r in calls if r["id"] not in by_id]
        if missing:
            raise SystemExit(f"{task_id}: {key} receipts missing ids {missing[:5]}")
        return [by_id[r["id"]] for r in calls]

    jev_ok, mini_ok = arm_ok("jev"), arm_ok("gpt4o_mini")
    for label, arm, want in (("jev", jev_ok, summary["jev_acc"]), ("mini", mini_ok, summary["mini_acc"])):
        got = sum(arm) / len(arm)
        if abs(got - want) > 1e-9:
            raise SystemExit(f"{task_id}: recounted {label} {got:.4f} != published {want:.4f}")

    labels = set(load(SCHEMAS / f"{task_id}.json")["labels"])
    ok = [r["pred"] == r["gold"] for r in calls]
    lat = sorted(r["latency_ms"] for r in calls)
    in_tok = sum(r["input_tokens"] or 0 for r in calls)
    out_tok = sum(r["output_tokens"] or 0 for r in calls)
    return {
        "task_id": task_id, "model": spec["model"], "n": len(calls),
        "acc": sum(ok) / len(ok), "wilson": wilson(sum(ok), len(ok)),
        "p50_ms": lat[len(lat) // 2], "p95_ms": lat[int(len(lat) * 0.95)],
        "input_tokens": in_tok, "output_tokens": out_tok,
        "tokens_per_call": round((in_tok + out_tok) / len(calls), 1),
        "cost_usd": in_tok / 1e6 * spec["price_in"],
        "invalid_labels": sum(1 for r in calls if r["pred"] not in labels),
        "mean_confidence": sum(r["confidence"] for r in calls) / len(calls),
        "mcnemar_vs_jev": mcnemar(ok, jev_ok),
        "mcnemar_vs_mini": mcnemar(ok, mini_ok),
        "jev_acc": summary["jev_acc"], "mini_acc": summary["mini_acc"],
    }


# ---- running ---------------------------------------------------------------------------------

def one_call(col: str, row: dict, schema: dict, ctx) -> dict:
    url, headers, body_fn, unwrap, parse = ctx
    spec = SPECS[col]
    request = body_fn(schema, row["text"], spec["model"])
    attempts: list = []
    t0 = time.perf_counter()
    raw = post(url, headers, request, attempts)
    ms = (time.perf_counter() - t0) * 1000
    resp = unwrap(raw)
    pred, conf, p_chosen = parse(resp, schema["question_key"])
    usage = resp.get("usage") or {}
    return {
        "id": row["id"], "gold": row["gold"], "text": row["text"], "pred": pred,
        "confidence": conf, "p_chosen": p_chosen, "latency_ms": ms,
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens", 0),
        "model_returned": resp.get("model"), "endpoint": spec["endpoint"],
        "request": request, "response": resp,
        "request_sha256": sha256_obj(request), "response_sha256": sha256_obj(resp),
        "utc": datetime.now(timezone.utc).isoformat(), "attempts": attempts,
    }


def run_task(col: str, task_id: str, ctx) -> dict:
    spec = SPECS[col]
    schema = load(SCHEMAS / f"{task_id}.json")
    rows = load_rows(task_id)
    summary = summary_row(task_id)
    print(f"\n=== {task_id} n={len(rows)} model={spec['model']} ===", flush=True)

    partial = RECEIPTS / f"{task_id}.{col}.partial.jsonl"
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
        futs = [pool.submit(one_call, col, row, schema, ctx) for row in todo]
        for i, fut in enumerate(as_completed(futs), len(done) + 1):
            rec = fut.result()
            with lock:
                with partial.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done[rec["id"]] = rec
            if i % 50 == 0 or i == len(rows):
                print(f"  {i}/{len(rows)}", flush=True)
    calls = sorted((done[r["id"]] for r in rows), key=lambda r: r["id"])
    dump(RECEIPTS / f"{task_id}.{col}.json", {
        "task_id": task_id, "model": spec["model"], "n": len(calls), "endpoint": spec["endpoint"],
        "samples_sha256": summary["samples_sha256"], "schema_sha256": summary["schema_sha256"],
        "calls": calls,
    }, indent=None)
    partial.unlink()
    return score(col, task_id, calls)


def dry(col: str, ids: list[str], n: int, ctx) -> None:
    """A few rows, nothing written: shows the wire format and the cost of a full run."""
    task_id = ids[0]
    schema = load(SCHEMAS / f"{task_id}.json")
    rows = load_rows(task_id)[:n]
    in_tok = 0
    for i, row in enumerate(rows):
        rec = one_call(col, row, schema, ctx)
        in_tok += rec["input_tokens"] or 0
        print(f"  id {rec['id']}: gold {rec['gold']} pred {rec['pred']} conf {rec['confidence']:.3f} "
              f"p {rec['p_chosen']:.3f} in {rec['input_tokens']} out {rec['output_tokens']} "
              f"{rec['latency_ms']:.0f}ms returned {rec['model_returned']}")
        if i == 0:
            print("  request :", json.dumps(rec["request"], ensure_ascii=False)[:600])
            print("  response:", json.dumps(rec["response"], ensure_ascii=False)[:600])
    spec = SPECS[col]
    print(f"  {len(rows)} rows, {in_tok} input tokens, ${in_tok / 1e6 * spec['price_in']:.6f}; nothing written")


def main(col: str) -> None:
    load_dotenv()
    argv = sys.argv[1:]
    only_recompute = "--recompute" in argv
    dry_n = None
    if "--dry" in argv:
        i = argv.index("--dry")
        dry_n = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    order = [r["task_id"] for r in load(RESULTS / "summary.json")]
    ids = args or order
    spec = SPECS[col]

    if dry_n is not None:
        dry(col, ids, dry_n, prepare(col))
        return

    ctx = None if only_recompute else prepare(col)
    started = datetime.now(timezone.utc).isoformat()
    path = RESULTS / f"{col}_baseline.json"
    top = load(path) if path.exists() else {}
    prev = {r["task_id"]: r for r in top.get("tasks", [])}

    for tid in ids:
        prev[tid] = (score(col, tid, load(RECEIPTS / f"{tid}.{col}.json")["calls"])
                     if only_recompute else run_task(col, tid, ctx))
        r = prev[tid]
        print(f"  {tid:24} acc {r['acc']:.3f}  (jev {r['jev_acc']:.3f}, mini {r['mini_acc']:.3f})  "
              f"vs jev: {r['mcnemar_vs_jev']['winner']:>3}  vs mini: {r['mcnemar_vs_mini']['winner']:>3}  "
              f"p50 {r['p50_ms']:.0f}ms  ${r['cost_usd']:.5f}")

    # --recompute changes statistics, not measurements: keep the run's own provenance.
    if only_recompute and top:
        provenance = {k: top[k] for k in ("run_id", "finished_utc", "latency_environment") if k in top}
        provenance["recomputed_utc"] = datetime.now(timezone.utc).isoformat()
    else:
        provenance = {
            "run_id": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "latency_environment": {
                "host": platform.platform(),
                "measured_from": os.environ.get("WHICHJUDGE_REGION", "unset"),
                "note": "Wall clock from this client, including network round trip.",
            },
        }
    tasks = [prev[t] for t in order if t in prev]
    dump(path, {
        **provenance, "column": col, "model": spec["model"], "endpoint": spec["endpoint"],
        "why": spec["why"],
        "prices_usd_per_million": {"input": spec["price_in"], "output": 0.0},
        "price_source_url": spec["price_url"], "price_checked": PRICE_CHECKED,
        "pricing_note": (f"Read off the vendor's own pricing page on {PRICE_CHECKED}: " + spec["price_basis"]),
        "total_cost_usd": sum(t["cost_usd"] for t in tasks),
        "tasks": tasks,
    })
    print(f"\nwrote results/{col}_baseline.json")


if __name__ == "__main__":
    main("decisions")
