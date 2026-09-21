#!/usr/bin/env python3
"""Check frozen samples, schemas, receipts, and every published statistic.

Does not call APIs. Exit 0 if everything in results/ follows from the receipts:
accuracy is recounted, and the intervals, paired tests, costs, latencies, gates,
calibration, error profile, TF-IDF column, current-model column and cost curve are
recomputed and compared. The last lines say exactly what was and was not covered.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

try:  # Windows consoles default to a legacy codepage; the report is UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - older interpreters / redirected streams
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMAS = ROOT / "schemas"
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fail(msg: str) -> None:
    print("FAIL", msg)
    raise SystemExit(1)


def main() -> None:
    errors = 0
    summary = load(RESULTS / "summary.json")
    manifest = load(RESULTS / "manifest.json")

    print("run", manifest.get("run_id"))
    print("seed", manifest.get("seed"), "n", manifest.get("n_per_task"))
    print(manifest.get("caveat", ""))
    print()

    patches = {}
    patch_path = RESULTS / "code_patches.json"
    if patch_path.exists():
        patches = {p["path"]: p for p in load(patch_path)["patches"]}

    patched = []
    skipped_text = []
    for rel, expected in (manifest.get("file_sha256") or {}).items():
        path = ROOT / rel
        if not path.exists():
            print("MISSING", rel)
            errors += 1
            continue
        got = sha256_file(path)
        if got == expected:
            print("ok file", rel)
            continue
        # data/ and schemas/ define the frozen run: any drift is fatal.
        # scripts/ may be patched after the run, but only changes recorded in
        # results/code_patches.json are accepted, and they are reported.
        entry = patches.get(rel)
        if entry and entry["run_sha256"] == expected and entry["current_sha256"] == got:
            print("patched file", rel, "-", entry["reason"])
            patched.append(rel)
        else:
            print("HASH MISMATCH", rel)
            errors += 1

    for row in summary:
        tid = row["task_id"]
        samples = DATA / f"{tid}.jsonl"
        schema = SCHEMAS / f"{tid}.json"
        task = RESULTS / f"{tid}.json"
        rec_path = RECEIPTS / f"{tid}.json"
        for p in (samples, schema, task, rec_path):
            if not p.exists():
                print("MISSING", p)
                errors += 1

        gold = {}
        with samples.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                gold[r["id"]] = r

        # Tasks carrying third-party text ship hashes instead of the text itself.
        # scripts/rehydrate.py restores it into data/<task>.text.jsonl; without that
        # file the text-dependent checks cannot run and are reported as skipped.
        sidecar = DATA / f"{tid}.text.jsonl"
        if sidecar.exists():
            with sidecar.open(encoding="utf-8") as f:
                for line in f:
                    restored = json.loads(line)
                    if restored["id"] in gold:
                        gold[restored["id"]]["text"] = restored["text"]
        rec = load(rec_path)
        # Redaction is a property of the receipts, not of the gold file: after
        # scripts/redact_text.py the request envelope no longer holds the text, so
        # its hash cannot be recomputed even once the text is rehydrated.
        redacted = bool(rec.get("text_redacted"))
        rehydrated = all("text" in g for g in gold.values())
        if redacted:
            skipped_text.append(f"{tid}{' (rehydrated)' if rehydrated else ''}")
        if rec["n"] != len(gold) or rec["n"] != row["n"]:
            print("N MISMATCH", tid, rec["n"], row["n"], len(gold))
            errors += 1

        if rec.get("samples_sha256") != sha256_file(samples):
            print("SAMPLES HASH vs receipts", tid)
            errors += 1
        if rec.get("schema_sha256") != sha256_file(schema):
            print("SCHEMA HASH vs receipts", tid)
            errors += 1

        jev_ok = 0
        for r in rec["jev"]:
            g = gold[r["id"]]
            if r["gold"] != g["gold"]:
                print("GOLD DRIFT", tid, "jev", r["id"])
                errors += 1
            if not redacted:
                if r["text"] != g["text"]:
                    print("SAMPLE DRIFT", tid, "jev", r["id"])
                    errors += 1
                if sha256_bytes(canonical_bytes(r["request"])) != r["request_sha256"]:
                    print("REQUEST HASH", tid, "jev", r["id"])
                    errors += 1
            elif rehydrated:
                # The text is back: prove it is byte-identical to what was sent.
                if sha256_bytes(g["text"].encode("utf-8")) != r.get("text_sha256"):
                    print("REHYDRATED TEXT HASH", tid, "jev", r["id"])
                    errors += 1
            if sha256_bytes(canonical_bytes(r["response"])) != r["response_sha256"]:
                print("RESPONSE HASH", tid, "jev", r["id"])
                errors += 1
            if not redacted and r["request"].get("state") != r["text"]:
                print("STATE != TEXT", tid, "jev", r["id"])
                errors += 1
            if r["pred"] == r["gold"]:
                jev_ok += 1
        mini_ok = 0
        for r in rec["gpt4o_mini"]:
            g = gold[r["id"]]
            if r["gold"] != g["gold"]:
                print("GOLD DRIFT", tid, "mini", r["id"])
                errors += 1
            if not redacted:
                if r["text"] != g["text"]:
                    print("SAMPLE DRIFT", tid, "mini", r["id"])
                    errors += 1
                if sha256_bytes(canonical_bytes(r["request"])) != r["request_sha256"]:
                    print("REQUEST HASH", tid, "mini", r["id"])
                    errors += 1
            elif rehydrated:
                # The text is back: prove it is byte-identical to what was sent.
                if sha256_bytes(g["text"].encode("utf-8")) != r.get("text_sha256"):
                    print("REHYDRATED TEXT HASH", tid, "mini", r["id"])
                    errors += 1
            if sha256_bytes(canonical_bytes(r["response"])) != r["response_sha256"]:
                print("RESPONSE HASH", tid, "mini", r["id"])
                errors += 1
            if r["pred"] == r["gold"]:
                mini_ok += 1

        n = rec["n"]
        jev_acc = jev_ok / n
        mini_acc = mini_ok / n
        if abs(jev_acc - row["jev_acc"]) > 1e-9:
            print("ACC RECOUNT JEV", tid, jev_acc, row["jev_acc"])
            errors += 1
        if abs(mini_acc - row["mini_acc"]) > 1e-9:
            print("ACC RECOUNT MINI", tid, mini_acc, row["mini_acc"])
            errors += 1
        print(
            f"ok {tid:24} recounted jev {jev_acc:.3f} mini {mini_acc:.3f} "
            f"receipts {n}×2"
        )

    print()
    fast = "--fast" in sys.argv
    derived = check_derived(summary, fast=fast)
    errors += derived.errors
    if errors:
        fail(f"{errors} check(s) failed")
    print("\nALL CHECKS PASSED")
    if patched:
        print(
            f"{len(patched)} script(s) changed since the run "
            "(documented in results/code_patches.json): " + ", ".join(patched)
        )
        print("Receipts and gold labels are byte-identical to the run.")
    if skipped_text:
        print(
            f"{len(skipped_text)} task(s) ship hashed text instead of the text itself: "
            + ", ".join(skipped_text)
        )
        print("Accuracy above was still recounted from the receipts. To also check the "
              "text and request hashes, run scripts/rehydrate.py first.")
    print("\nRECOMPUTED FROM RECEIPTS AND COMPARED WITH results/:")
    for line in derived.checked:
        print("  " + line)
    print("NOT RECOMPUTED HERE:")
    if derived.skipped_cv:
        print("  the cross-validated gate slice (skipped by --fast; CI runs without it)")
    print("  Holm adjustment, verdict mapping and every rendered number: scripts/build_site.py --check")
    print("  TF-IDF training itself (needs the raw corpora): scripts/run_tfidf_baseline.py")
    print("  that either API produced these responses: only a re-run can; see the manifest caveat")


# ---------------------------------------------------------------------------
# Everything below recomputes derived numbers. The checks above prove the
# receipts are what the run wrote and that accuracy recounts; these prove that
# every other published statistic follows from those receipts. A wrong Wilson
# bound, McNemar p, cost, gate, ECE, TF-IDF or current-model result used to
# pass CI untouched. Now it fails here.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(ROOT / "scripts"))

JEV_INPUT_USD_PER_M = 0.042
MINI_INPUT_USD_PER_M = 0.15
MINI_OUTPUT_USD_PER_M = 0.60
GATES = (0.5, 0.6, 0.7, 0.8, 0.9)
BINS = 10


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / den
    margin = z * math.sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n)) / den
    return max(0.0, centre - margin), min(1.0, centre + margin)


def mcnemar(a_ok: list[bool], b_ok: list[bool]) -> tuple[int, int, float]:
    """(a-only-correct, b-only-correct, p) with continuity correction, chi2(1)."""
    a_only = sum(1 for x, y in zip(a_ok, b_ok) if x and not y)
    b_only = sum(1 for x, y in zip(a_ok, b_ok) if y and not x)
    disc = a_only + b_only
    if disc == 0:
        return 0, 0, 1.0
    chi2 = (abs(a_only - b_only) - 1) ** 2 / disc
    return a_only, b_only, math.erfc(math.sqrt(chi2 / 2.0))


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))]


def score_of(r: dict) -> float:
    p = r.get("p_chosen")
    return float(p if p is not None else r["confidence"])


def gate_table(rows: list[dict], score) -> dict:
    out = {}
    for g in GATES:
        kept = [r for r in rows if score(r) >= g]
        out[str(g)] = {
            "coverage": len(kept) / len(rows),
            "accuracy": (sum(r["pred"] == r["gold"] for r in kept) / len(kept)) if kept else None,
        }
    return out


def pick_gate(rows: list[dict]):
    best = None
    for g in GATES:
        kept = [r for r in rows if score_of(r) >= g]
        if not kept or len(kept) / len(rows) < 0.5:
            continue
        acc = sum(r["pred"] == r["gold"] for r in kept) / len(kept)
        if best is None or acc > best[1]:
            best = (g, acc)
    return best


def reliability(rows: list[dict]) -> dict:
    pairs = [(score_of(r), r["pred"] == r["gold"]) for r in rows]
    n = len(pairs)
    ece = mce = 0.0
    bins = []
    for i in range(BINS):
        lo, hi = i / BINS, (i + 1) / BINS
        hits = [p for p in pairs if (lo <= p[0] < hi) or (i == BINS - 1 and p[0] == 1.0)]
        if hits:
            conf = sum(p[0] for p in hits) / len(hits)
            acc = sum(1 for p in hits if p[1]) / len(hits)
            gap = abs(conf - acc)
            ece += (len(hits) / n) * gap
            mce = max(mce, gap)
            bins.append((len(hits), conf, acc))
        else:
            bins.append((0, None, None))
    return {"ece": ece, "mce": mce, "bins": bins}


def per_class(rows: list[dict]) -> dict:
    classes = sorted({r["gold"] for r in rows})
    out = {}
    for cls in classes:
        actual = [r for r in rows if r["gold"] == cls]
        caught = [r for r in actual if r["pred"] == cls]
        others = [r for r in rows if r["gold"] != cls]
        fp = [r for r in others if r["pred"] == cls]
        out[cls] = {
            "n": len(actual),
            "recall": round(len(caught) / len(actual), 4) if actual else None,
            "missed": len(actual) - len(caught),
            "missed_rate": round(1 - len(caught) / len(actual), 4) if actual else None,
            "false_positives": len(fp),
            "false_positive_rate": round(len(fp) / len(others), 4) if others else None,
        }
    return out


def recall_at_gate(rows: list[dict]) -> dict:
    classes = sorted({r["gold"] for r in rows})
    out = {}
    for g in GATES:
        per = {}
        for cls in classes:
            covered = [r for r in rows if r["gold"] == cls and score_of(r) >= g]
            caught = [r for r in covered if r["pred"] == cls]
            per[cls] = {"covered": len(covered),
                        "recall_on_covered": round(len(caught) / len(covered), 4) if covered else None}
        out[str(g)] = per
    return out


def reparse_jev(response: dict, key: str) -> tuple[str, float, float]:
    """The same reading of a Jev reply that run_eval.py makes, done again here."""
    ans = response["answers"][key]
    choice = ans.get("choice")
    conf = float(ans.get("confidence") or 0)
    probs = ans.get("probabilities") or {}
    return str(choice), conf, float(probs.get(choice, 0) if choice else 0)


def reparse_mini(response: dict, labels: list[str]) -> str:
    content = response["choices"][0]["message"]["content"]
    try:
        label = str(json.loads(content).get("label", "")).strip()
    except Exception:  # noqa: BLE001 - a malformed reply is a wrong answer
        label = ""
    if label not in labels:
        low = content.lower()
        label = next((l for l in labels if l.lower() in low), "INVALID")
    return label


def reparse_modern(response: dict) -> tuple[str | None, str]:
    content = (response["choices"][0]["message"]["content"] or "").strip()
    try:
        return json.loads(content).get("label"), content
    except Exception:  # noqa: BLE001
        return None, content


def close(a, b, tol=1e-9) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


class Derived:
    """Collects mismatches so one run reports everything, not the first failure."""

    def __init__(self):
        self.errors = 0
        self.checked: list[str] = []
        self.skipped_cv = False

    def expect(self, where: str, got, want, tol=1e-9) -> None:
        ok = close(got, want, tol) if isinstance(want, (int, float)) or want is None else got == want
        if not ok:
            print(f"DERIVED MISMATCH {where}: recomputed {got!r}, published {want!r}")
            self.errors += 1


def check_derived(summary: list[dict], fast: bool = False) -> Derived:
    d = Derived()
    calib = load(RESULTS / "calibration.json")
    gates = load(RESULTS / "gates.json")
    profile = load(RESULTS / "error_profile.json")
    tfidf_full = {r["task_id"]: r for r in load(RESULTS / "tfidf_baseline.json")}
    tfidf_slim = {r["task_id"]: r for r in load(RESULTS / "tfidf_baseline_summary.json")}
    modern_path = RESULTS / "modern_baseline.json"
    modern = {r["task_id"]: r for r in load(modern_path)["tasks"]} if modern_path.exists() else {}
    laya_path = RESULTS / "laya_baseline.json"
    laya = {r["task_id"]: r for r in load(laya_path)["tasks"]} if laya_path.exists() else {}

    from calibrate import cross_validated_slice  # same seeded splits as the producer

    for row in summary:
        tid = row["task_id"]
        rec = load(RECEIPTS / f"{tid}.json")
        jev, mini = rec["jev"], rec["gpt4o_mini"]
        n = len(jev)
        schema = load(SCHEMAS / f"{tid}.json")
        sample_ids = []
        with (DATA / f"{tid}.jsonl").open(encoding="utf-8") as f:
            sample_ids = [json.loads(line)["id"] for line in f if line.strip()]

        # Every arm must answer every frozen sample exactly once. A dropped or
        # doubled row changes n, the pairing and every statistic downstream.
        def coverage(arm_name: str, rows_: list[dict]) -> None:
            ids = [r["id"] for r in rows_]
            if sorted(ids) != sorted(sample_ids) or len(set(ids)) != len(ids):
                print(f"ID COVERAGE {tid} {arm_name}: {len(ids)} receipts for {len(sample_ids)} samples")
                d.errors += 1

        coverage("jev", jev)
        coverage("mini", mini)

        # The stored pred is what every number is counted from. Read the raw
        # response again and require it to say the same thing, so an edited pred
        # with an untouched response (and hash) cannot pass. This is the gap an
        # outside review demonstrated by flipping one wrong answer to gold.
        for r in jev:
            pred, conf, p_chosen = reparse_jev(r["response"], schema["question_key"])
            d.expect(f"{tid} jev[{r['id']}].pred reparsed", pred, r["pred"])
            d.expect(f"{tid} jev[{r['id']}].confidence reparsed", conf, r.get("confidence"))
            d.expect(f"{tid} jev[{r['id']}].p_chosen reparsed", p_chosen, r.get("p_chosen"))
            d.expect(f"{tid} jev[{r['id']}].model_returned", r["response"].get("model"), r.get("model_returned"))
        for r in mini:
            d.expect(f"{tid} mini[{r['id']}].model_returned", r["response"].get("model"), r.get("model_returned"))
            d.expect(f"{tid} mini[{r['id']}].pred reparsed",
                     reparse_mini(r["response"], schema["labels"]), r["pred"])

        jev_ok = [r["pred"] == r["gold"] for r in jev]
        mini_by = {r["id"]: r["pred"] == r["gold"] for r in mini}
        mini_ok = [mini_by[r["id"]] for r in jev]

        # summary.json: intervals, paired test, latency, cost, confidence, gates
        lo, hi = wilson(sum(jev_ok), n)
        d.expect(f"{tid} jev_wilson.lo", lo, row["jev_wilson"]["lo"])
        d.expect(f"{tid} jev_wilson.hi", hi, row["jev_wilson"]["hi"])
        lo, hi = wilson(sum(mini_ok), n)
        d.expect(f"{tid} mini_wilson.lo", lo, row["mini_wilson"]["lo"])
        d.expect(f"{tid} mini_wilson.hi", hi, row["mini_wilson"]["hi"])
        b, c, p = mcnemar(jev_ok, mini_ok)
        d.expect(f"{tid} mcnemar.jev_only_correct", b, row["mcnemar"]["jev_only_correct"])
        d.expect(f"{tid} mcnemar.mini_only_correct", c, row["mcnemar"]["mini_only_correct"])
        d.expect(f"{tid} mcnemar.p_value", p, row["mcnemar"]["p_value"], 1e-12)
        winner = "jev" if b > c and p < 0.05 else ("mini" if c > b and p < 0.05 else "ns")
        d.expect(f"{tid} mcnemar.winner", winner, row["mcnemar"]["winner"])
        for arm, key, rows_ in (("jev", "jev", jev), ("mini", "mini", mini)):
            lat = [r["latency_ms"] for r in rows_]
            d.expect(f"{tid} {arm}_p50_ms", percentile(lat, 0.5), row[f"{key}_p50_ms"])
            d.expect(f"{tid} {arm}_p95_ms", percentile(lat, 0.95), row[f"{key}_p95_ms"])
        jev_in = sum(r["input_tokens"] or 0 for r in jev)
        mini_in = sum(r["input_tokens"] or 0 for r in mini)
        mini_out = sum(r["output_tokens"] or 0 for r in mini)
        d.expect(f"{tid} jev_cost", jev_in / 1e6 * JEV_INPUT_USD_PER_M, row["jev_cost"], 1e-12)
        d.expect(f"{tid} mini_cost", mini_in / 1e6 * MINI_INPUT_USD_PER_M
                 + mini_out / 1e6 * MINI_OUTPUT_USD_PER_M, row["mini_cost"], 1e-12)
        confs = [r["confidence"] for r in jev if r.get("confidence") is not None]
        d.expect(f"{tid} jev_mean_conf", sum(confs) / len(confs), row["jev_mean_conf"])
        if "jev_gates" in row:
            # One gate table only, on p_chosen, in results/gates.json.
            print(f"LEGACY GATES {tid}: summary.json still carries confidence-thresholded jev_gates")
            d.errors += 1

        # calibration.json
        rel = reliability(jev)
        pub = calib[tid]["p_chosen"]
        d.expect(f"{tid} ece", rel["ece"], pub["ece"])
        d.expect(f"{tid} mce", rel["mce"], pub["mce"])
        d.expect(f"{tid} calibration.n", n, pub["n"])
        for i, (cnt, conf, acc) in enumerate(rel["bins"]):
            d.expect(f"{tid} bin[{i}].n", cnt, pub["bins"][i]["n"])
            d.expect(f"{tid} bin[{i}].conf", conf, pub["bins"][i]["conf"])
            d.expect(f"{tid} bin[{i}].acc", acc, pub["bins"][i]["acc"])

        # gates.json (p_chosen)
        g_pub = gates[tid]
        d.expect(f"{tid} gates.score", "p_chosen", g_pub["score"])
        for g, v in gate_table(jev, score_of).items():
            d.expect(f"{tid} gates[{g}].coverage", round(v["coverage"], 4), g_pub["gates"][g]["coverage"])
            d.expect(f"{tid} gates[{g}].accuracy",
                     round(v["accuracy"], 4) if v["accuracy"] is not None else None,
                     g_pub["gates"][g]["accuracy"])
        chosen = pick_gate(jev)
        d.expect(f"{tid} gates.in_sample.gate", chosen[0] if chosen else None,
                 (g_pub["in_sample"] or {}).get("gate"))
        d.expect(f"{tid} gates.in_sample.accuracy", round(chosen[1], 4) if chosen else None,
                 (g_pub["in_sample"] or {}).get("accuracy"))
        if fast:
            d.skipped_cv = True
        else:
            cv = cross_validated_slice(jev)
            for key in ("accuracy_mean", "accuracy_lo", "accuracy_hi", "gate_chosen_most",
                        "coverage_mean", "halves_below_min_coverage", "halves"):
                d.expect(f"{tid} gates.cross_validated.{key}", cv[key], g_pub["cross_validated"].get(key))

        # error_profile.json
        for arm, rows_ in (("jev", jev), ("mini", mini)):
            d.expect(f"{tid} error_profile.{arm}.per_class", per_class(rows_), profile[tid][arm]["per_class"])
        d.expect(f"{tid} error_profile.jev.recall_at_gate", recall_at_gate(jev),
                 profile[tid]["jev"]["recall_at_gate"])

        # TF-IDF column: predictions stored per row, recount and re-test them
        tf = tfidf_full[tid]
        gold = {r["id"]: r["gold"] for r in jev}
        tf_ok = []
        for pr in tf["preds"]:
            if gold[pr["id"]] != pr["gold"]:
                print("GOLD DRIFT", tid, "tfidf", pr["id"])
                d.errors += 1
            tf_ok.append(pr["pred"] == pr["gold"])
        d.expect(f"{tid} tfidf.n", len(tf_ok), tf["n"])
        d.expect(f"{tid} tfidf.acc", sum(tf_ok) / len(tf_ok), tf["acc"])
        lo, hi = wilson(sum(tf_ok), len(tf_ok))
        d.expect(f"{tid} tfidf.wilson.lo", lo, tf["wilson"]["lo"])
        d.expect(f"{tid} tfidf.wilson.hi", hi, tf["wilson"]["hi"])
        j_al = [dict(zip([r["id"] for r in jev], jev_ok))[pr["id"]] for pr in tf["preds"]]
        m_al = [mini_by[pr["id"]] for pr in tf["preds"]]
        for key, other in (("mcnemar_vs_jev", j_al), ("mcnemar_vs_mini", m_al)):
            a, b_, p = mcnemar(tf_ok, other)
            d.expect(f"{tid} tfidf.{key}.a_only_correct", a, tf[key]["a_only_correct"])
            d.expect(f"{tid} tfidf.{key}.b_only_correct", b_, tf[key]["b_only_correct"])
            d.expect(f"{tid} tfidf.{key}.p_value", p, tf[key]["p_value"], 1e-12)
        slim = tfidf_slim[tid]
        for key in ("acc", "wilson", "mcnemar_vs_jev", "mcnemar_vs_mini", "train_n",
                    "predict_mean_ms_per_row_batched"):
            d.expect(f"{tid} tfidf_summary.{key}", tf[key], slim[key])

        # current-model column
        if tid in modern:
            md = modern[tid]
            mpath = RECEIPTS / f"{tid}.modern.json"
            mrec = load(mpath) if mpath.exists() else None
            if not isinstance(mrec, dict) or not isinstance(mrec.get("calls"), list) or not mrec["calls"]:
                # An empty or missing receipt file used to pass every check while
                # the column it backs stayed on the site.
                print(f"MODERN RECEIPTS {tid}: missing or malformed {mpath.name}")
                d.errors += 1
                continue
            calls = mrec["calls"]
            coverage("modern", calls)
            d.expect(f"{tid} modern.model", md["model"], mrec.get("model"))
            invalid = 0
            for r in calls:
                if sha256_bytes(canonical_bytes(r["response"])) != r["response_sha256"]:
                    print("RESPONSE HASH", tid, "modern", r["id"])
                    d.errors += 1
                if gold[r["id"]] != r["gold"]:
                    print("GOLD DRIFT", tid, "modern", r["id"])
                    d.errors += 1
                label, content = reparse_modern(r["response"])
                # Two writer generations: the first kept an out-of-schema label as
                # written, later ones prefixed it. Either must match the raw reply.
                accepted = {label, f"__unparsed__:{content[:40]}"}
                if r["pred"] not in accepted:
                    print(f"DERIVED MISMATCH {tid} modern[{r['id']}].pred reparsed: "
                          f"raw says {label!r}, stored {r['pred']!r}")
                    d.errors += 1
                if r["pred"] not in schema["labels"]:
                    invalid += 1
            d.expect(f"{tid} modern.invalid_labels", invalid, md.get("invalid_labels"))
            m_ok = [r["pred"] == r["gold"] for r in calls]
            d.expect(f"{tid} modern.n", len(m_ok), md["n"])
            d.expect(f"{tid} modern.acc", sum(m_ok) / len(m_ok), md["acc"])
            lo, hi = wilson(sum(m_ok), len(m_ok))
            d.expect(f"{tid} modern.wilson.lo", lo, md["wilson"]["lo"])
            d.expect(f"{tid} modern.wilson.hi", hi, md["wilson"]["hi"])
            lat = sorted(r["latency_ms"] for r in calls)
            d.expect(f"{tid} modern.p50_ms", lat[len(lat) // 2], md["p50_ms"])
            d.expect(f"{tid} modern.p95_ms", lat[int(len(lat) * 0.95)], md["p95_ms"])
            in_tok = sum(r["input_tokens"] or 0 for r in calls)
            out_tok = sum(r["output_tokens"] or 0 for r in calls)
            d.expect(f"{tid} modern.tokens_per_call", round((in_tok + out_tok) / len(calls), 1),
                     md["tokens_per_call"])
            jev_by = dict(zip([r["id"] for r in jev], jev_ok))
            j_al = [jev_by[r["id"]] for r in calls]
            m_al = [mini_by[r["id"]] for r in calls]
            for key, other in (("mcnemar_vs_jev", j_al), ("mcnemar_vs_mini", m_al)):
                a, b_, p = mcnemar(m_ok, other)
                d.expect(f"{tid} modern.{key}.a_only_correct", a, md[key]["a_only_correct"])
                d.expect(f"{tid} modern.{key}.b_only_correct", b_, md[key]["b_only_correct"])
                d.expect(f"{tid} modern.{key}.p_value", p, md[key]["p_value"], 1e-12)
            # The per-class profile of this arm was once computed from an older
            # run's receipts and published; it is now checked like the other arms.
            if profile[tid].get("modern"):
                d.expect(f"{tid} error_profile.modern.per_class", per_class(calls), profile[tid]["modern"]["per_class"])
            else:
                print(f"DERIVED MISMATCH {tid} error_profile.modern: missing")
                d.errors += 1

        # self-hosted System One column: same reading as the Jev arm
        if tid in laya:
            ld = laya[tid]
            lpath = RECEIPTS / f"{tid}.laya.json"
            lrec = load(lpath) if lpath.exists() else None
            if not isinstance(lrec, dict) or not isinstance(lrec.get("calls"), list) or not lrec["calls"]:
                print(f"LAYA RECEIPTS {tid}: missing or malformed {lpath.name}")
                d.errors += 1
                continue
            lcalls = lrec["calls"]
            coverage("laya", lcalls)
            d.expect(f"{tid} laya.model", ld["model"], lrec.get("model"))
            l_invalid = 0
            for r in lcalls:
                if sha256_bytes(canonical_bytes(r["response"])) != r["response_sha256"]:
                    print("RESPONSE HASH", tid, "laya", r["id"])
                    d.errors += 1
                if gold[r["id"]] != r["gold"]:
                    print("GOLD DRIFT", tid, "laya", r["id"])
                    d.errors += 1
                pred, conf, p_chosen = reparse_jev(r["response"], schema["question_key"])
                d.expect(f"{tid} laya[{r['id']}].pred reparsed", pred, r["pred"])
                d.expect(f"{tid} laya[{r['id']}].confidence reparsed", conf, r.get("confidence"))
                d.expect(f"{tid} laya[{r['id']}].p_chosen reparsed", p_chosen, r.get("p_chosen"))
                if r["pred"] not in schema["labels"]:
                    l_invalid += 1
            d.expect(f"{tid} laya.invalid_labels", l_invalid, ld.get("invalid_labels"))
            l_ok = [r["pred"] == r["gold"] for r in lcalls]
            d.expect(f"{tid} laya.n", len(l_ok), ld["n"])
            d.expect(f"{tid} laya.acc", sum(l_ok) / len(l_ok), ld["acc"])
            lo, hi = wilson(sum(l_ok), len(l_ok))
            d.expect(f"{tid} laya.wilson.lo", lo, ld["wilson"]["lo"])
            d.expect(f"{tid} laya.wilson.hi", hi, ld["wilson"]["hi"])
            lat = sorted(r["latency_ms"] for r in lcalls)
            d.expect(f"{tid} laya.p50_ms", lat[len(lat) // 2], ld["p50_ms"])
            d.expect(f"{tid} laya.p95_ms", lat[int(len(lat) * 0.95)], ld["p95_ms"])
            jev_by = dict(zip([r["id"] for r in jev], jev_ok))
            j_al = [jev_by[r["id"]] for r in lcalls]
            m_al = [mini_by[r["id"]] for r in lcalls]
            for key, other in (("mcnemar_vs_jev", j_al), ("mcnemar_vs_mini", m_al)):
                a, b_, p = mcnemar(l_ok, other)
                d.expect(f"{tid} laya.{key}.a_only_correct", a, ld[key]["a_only_correct"])
                d.expect(f"{tid} laya.{key}.b_only_correct", b_, ld[key]["b_only_correct"])
                d.expect(f"{tid} laya.{key}.p_value", p, ld[key]["p_value"], 1e-12)
            if calib[tid].get("laya"):
                rel = reliability(lcalls)
                d.expect(f"{tid} laya.ece", rel["ece"], calib[tid]["laya"]["ece"])
                d.expect(f"{tid} laya.mce", rel["mce"], calib[tid]["laya"]["mce"])
            if profile[tid].get("laya"):
                d.expect(f"{tid} error_profile.laya.per_class", per_class(lcalls), profile[tid]["laya"]["per_class"])

        # the same text twice in one sample, reported so nobody has to find it
        seen, dup = set(), 0
        for r in jev:
            key = r.get("text_sha256") or r.get("text")
            dup += key in seen
            seen.add(key)
        if dup:
            print(f"note {tid}: {dup} row(s) repeat a text already in the sample")

    # cost curve: re-aggregate every point from the per-call receipts
    curve_path = RESULTS / "cost_curve.json"
    if curve_path.exists():
        from cost_curve import points_from_calls, crossover
        pub = load(curve_path)
        calls = load(RECEIPTS / "cost_curve.json")["calls"]
        for r in calls:
            for arm in ("jev", "mini"):
                if sha256_bytes(canonical_bytes(r[arm]["response"])) != r[arm]["response_sha256"]:
                    print("RESPONSE HASH cost_curve", arm, r["target_tokens"])
                    d.errors += 1
        points = points_from_calls(calls)
        d.expect("cost_curve.points", len(points), len(pub["points"]))
        for got, want in zip(points, pub["points"]):
            for key in got:
                d.expect(f"cost_curve[{got['target_tokens']}].{key}", got[key], want.get(key))
        d.expect("cost_curve.crossover", crossover(points), pub["crossover"])
        d.expect("cost_curve.mini_overhead_tokens", points[0]["mini_input_tokens"], pub["mini_overhead_tokens"])
        d.expect("cost_curve.jev_fixed_overhead_tokens", round(points[0]["jev_input_tokens"]),
                 pub["jev_fixed_overhead_tokens"])

    d.checked = [
        "every arm answers every frozen sample id exactly once",
        "each stored pred, confidence and p_chosen re-read from the raw response (all three arms)",
        "out-of-schema labels in the current-model column counted against the schema",
        "accuracy, Wilson 95% CI, McNemar (b, c, p, winner), latency p50/p95, list-price cost,",
        "mean confidence (results/summary.json), and no second gate table there",
        "ECE, MCE and reliability bins on p_chosen (results/calibration.json)",
        "p_chosen gate table, in-sample pick and cross-validated slice (results/gates.json;",
        "the split sequence is imported from calibrate.py, everything else is reimplemented here)",
        "per-class recall, misses, false positives and recall at gate (results/error_profile.json)",
        "TF-IDF accuracy, Wilson, McNemar vs both arms from its stored per-row predictions",
        "current-model accuracy, Wilson, latency, tokens per call, McNemar vs both arms, response hashes",
        "Laya accuracy, Wilson, latency, McNemar vs both arms, ECE, error profile, response hashes, reparsed preds",
        "cost-curve points, crossover and overheads re-aggregated from per-call receipts",
    ]
    return d


if __name__ == "__main__":
    main()
