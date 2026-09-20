#!/usr/bin/env python3
"""Check frozen samples, schemas, receipts, and recounted accuracy.

Does not call APIs. Exit 0 if the published table matches the receipts.
"""
from __future__ import annotations

import hashlib
import json
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
    print("This proves the table matches frozen samples + stored receipts.")
    print("It does not prove a third party ran the APIs. Re-run scripts/run_eval.py for that.")


if __name__ == "__main__":
    main()
