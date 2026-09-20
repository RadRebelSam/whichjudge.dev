#!/usr/bin/env python3
"""Measure cost and latency against input length, and find where Jev overtakes Mini.

Jev bills a large fixed overhead per call (measured at roughly 270 input tokens for a
near-empty request), then your content on top. gpt-4o-mini bills almost nothing fixed
but charges 3.6x more per input token and charges for output, which Jev does not.

So neither is simply cheaper. There is a crossover, and this script finds it by
sending the same document to both models at a range of lengths and recording what each
one actually billed. It measures price and latency only. It says nothing about
accuracy, and the question is deliberately identical at every length so that length is
the only thing changing.

    python3 scripts/cost_curve.py            # full curve
    python3 scripts/cost_curve.py --dry-run  # build inputs, print sizes, call nothing

Writes results/cost_curve.json and results/receipts/cost_curve.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import hashlib
import urllib.error
import urllib.request

JEV_URL = "https://api.typesafe.ai/v1/systemone"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def canonical_bytes(obj) -> bytes:
    """Same canonical form run_eval.py hashes with, so receipts are comparable."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_obj(obj) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {e.code}: {body[:400]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last
        except Exception as e:  # noqa: BLE001 - retry transport errors
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise last


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"

JEV_MODEL = "jev-latest"
MINI_MODEL = "gpt-4o-mini"

# List prices, USD per million tokens. Change here if the vendors change them.
PRICES = {
    "jev": {"input": 0.042, "output": 0.0},
    "mini": {"input": 0.15, "output": 0.60},
}

# Target input sizes in tokens. Roughly 4 characters per token when building.
TARGETS = [0, 25, 50, 100, 200, 400, 800, 1600, 3200]
SAMPLES_PER_TARGET = 3

# One judgment, held constant at every length, so only length varies.
QUESTION_ID = "mentions_company"
JEV_QUESTIONS = {
    QUESTION_ID: {
        "type": "noul",
        "instructions": "Does this text name at least one company or organisation?",
    }
}
MINI_SYSTEM = (
    'Does this text name at least one company or organisation? '
    'Reply with JSON {"answer": true} or {"answer": false}. Only output JSON.'
)


def load_pool() -> list[str]:
    """Real sentences, so tokenisation behaves like real traffic."""
    pool: list[str] = []
    for task in ("news_topic", "banking_coarse_route", "review_sentiment"):
        path = DATA / f"{task}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            text = row.get("text")
            if text:
                pool.append(text.strip())
    if not pool:
        raise SystemExit(
            "No plain text available. These tasks must not be redacted; "
            "run scripts/rehydrate.py or use non-redacted tasks."
        )
    return pool


def build_input(pool: list[str], target_tokens: int, offset: int) -> str:
    """Concatenate real snippets until the target size is reached."""
    if target_tokens == 0:
        return "ok"
    target_chars = target_tokens * 4
    parts, size, i = [], 0, offset
    while size < target_chars:
        s = pool[i % len(pool)]
        parts.append(s)
        size += len(s) + 1
        i += 1
    return " ".join(parts)[:target_chars]


def call_jev(text: str, key: str) -> dict:
    request = {"state": text, "model": JEV_MODEL, "questions": JEV_QUESTIONS}
    t0 = time.perf_counter()
    raw = post_json(
        JEV_URL,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        request,
    )
    ms = (time.perf_counter() - t0) * 1000
    usage = raw.get("usage") or {}
    return {
        "latency_ms": ms,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "model_returned": raw.get("model"),
        "request": request,
        "response": raw,
        "request_sha256": sha256_obj(request),
        "response_sha256": sha256_obj(raw),
    }


def call_mini(text: str, key: str) -> dict:
    request = {
        "model": MINI_MODEL,
        "temperature": 0,
        "max_tokens": 20,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": MINI_SYSTEM},
            {"role": "user", "content": text},
        ],
    }
    t0 = time.perf_counter()
    raw = post_json(
        OPENAI_URL,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        request,
    )
    ms = (time.perf_counter() - t0) * 1000
    usage = raw.get("usage") or {}
    return {
        "latency_ms": ms,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "model_returned": raw.get("model"),
        "request": request,
        "response": raw,
        "request_sha256": sha256_obj(request),
        "response_sha256": sha256_obj(raw),
    }


def cost_per_million(vendor: str, in_tok: int, out_tok: int) -> float:
    p = PRICES[vendor]
    return (in_tok * p["input"] + out_tok * p["output"])


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def crossover(points: list[dict]):
    """First length where Jev stops being the more expensive of the two."""
    for a, b in zip(points, points[1:]):
        da = a["jev_per_million"] - a["mini_per_million"]
        db = b["jev_per_million"] - b["mini_per_million"]
        if da > 0 >= db:
            span = da - db
            frac = da / span if span else 0.0
            x = a["mean_content_tokens"] + frac * (b["mean_content_tokens"] - a["mean_content_tokens"])
            return {
                "content_tokens": round(x),
                "between": [a["target_tokens"], b["target_tokens"]],
                "note": "Linear interpolation between the two measured points either side.",
            }
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pool = load_pool()
    inputs = {t: [build_input(pool, t, i * 37) for i in range(SAMPLES_PER_TARGET)] for t in TARGETS}

    if args.dry_run:
        for t in TARGETS:
            print(f"target {t:>5} tokens -> {[len(s) for s in inputs[t]]} chars")
        print(f"\nWould make {len(TARGETS) * SAMPLES_PER_TARGET * 2} calls.")
        return

    jev_key = os.environ.get("TYPESAFE_API_KEY")
    mini_key = os.environ.get("OPENAI_API_KEY")
    if not jev_key or not mini_key:
        raise SystemExit("Set TYPESAFE_API_KEY and OPENAI_API_KEY (see .env.example)")

    started = datetime.now(timezone.utc).isoformat()
    points, receipts = [], []

    for t in TARGETS:
        jev_calls, mini_calls = [], []
        for text in inputs[t]:
            j = call_jev(text, jev_key)
            m = call_mini(text, mini_key)
            jev_calls.append(j)
            mini_calls.append(m)
            receipts.append({
                "target_tokens": t,
                "chars": len(text),
                "text_sha256": sha256_obj(text),
                "jev": j,
                "mini": m,
            })

        j_in = mean([c["input_tokens"] for c in jev_calls])
        j_out = mean([c["output_tokens"] for c in jev_calls])
        m_in = mean([c["input_tokens"] for c in mini_calls])
        m_out = mean([c["output_tokens"] for c in mini_calls])
        point = {
            "target_tokens": t,
            "mean_chars": round(mean([len(s) for s in inputs[t]])),
            "mean_content_tokens": round(m_in),
            "jev_input_tokens": round(j_in, 1),
            "jev_output_tokens": round(j_out, 1),
            "mini_input_tokens": round(m_in, 1),
            "mini_output_tokens": round(m_out, 1),
            "jev_per_million": round(cost_per_million("jev", j_in, j_out), 2),
            "mini_per_million": round(cost_per_million("mini", m_in, m_out), 2),
            "jev_p50_ms": round(sorted(c["latency_ms"] for c in jev_calls)[len(jev_calls) // 2]),
            "mini_p50_ms": round(sorted(c["latency_ms"] for c in mini_calls)[len(mini_calls) // 2]),
            "mini_cached_tokens": mini_calls[0].get("cached_tokens"),
        }
        point["cheaper"] = "jev" if point["jev_per_million"] < point["mini_per_million"] else "mini"
        points.append(point)
        print(
            f"{t:>5} target | jev {point['jev_input_tokens']:>7} tok "
            f"${point['jev_per_million']:>8} /M | mini {point['mini_input_tokens']:>7} tok "
            f"${point['mini_per_million']:>8} /M | cheaper: {point['cheaper']}"
        )

    floor = points[0]["jev_input_tokens"] - points[0]["mini_input_tokens"]
    out = {
        "run_id": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "what_this_measures": (
            "Billed tokens, list-price cost and latency against input length, for one "
            "fixed question. Not an accuracy measurement."
        ),
        "prices_usd_per_million": PRICES,
        "jev_model": points and None,
        "samples_per_point": SAMPLES_PER_TARGET,
        "question": {"jev": JEV_QUESTIONS, "mini_system": MINI_SYSTEM},
        "input_construction": (
            "Real sentences from the frozen samples, concatenated to hit each target "
            "length. Synthetic in length, real in vocabulary."
        ),
        "jev_fixed_overhead_tokens": round(points[0]["jev_input_tokens"]),
        "jev_overhead_vs_mini_tokens": round(floor, 1),
        "crossover": crossover(points),
        "points": points,
    }
    out["jev_model"] = receipts[0]["jev"]["model_returned"] if receipts else None

    RESULTS.mkdir(exist_ok=True)
    RECEIPTS.mkdir(exist_ok=True)
    (RESULTS / "cost_curve.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (RECEIPTS / "cost_curve.json").write_text(
        json.dumps({"run_id": started, "calls": receipts}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")

    print(f"\nJev fixed overhead: ~{out['jev_fixed_overhead_tokens']} input tokens per call")
    x = out["crossover"]
    if x:
        print(f"Crossover: Jev becomes the cheaper option above ~{x['content_tokens']} content tokens")
    else:
        print("No crossover inside the measured range")
    print("wrote results/cost_curve.json and results/receipts/cost_curve.json")


if __name__ == "__main__":
    main()
