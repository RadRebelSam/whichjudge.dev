#!/usr/bin/env python3
"""Cross-checks that build_site.py --check cannot catch, run in CI.

--check only proves the site matches what build_site.py would generate today. It
says nothing about whether the published files leak text the repo may not
redistribute, whether a number hand-written in app.js still agrees with results/,
or whether the prose cites a model that has no column.

Every failure here has actually happened in this repo, which is why each one is a
check rather than a habit.

    python3 scripts/audit_site.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RECEIPTS = RESULTS / "receipts"
SITE = ROOT / "site"

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tasks_from_data_js() -> list[dict]:
    src = (SITE / "data.js").read_text(encoding="utf-8")
    return json.loads(src.split("const TASKS = ", 1)[1].rstrip().rstrip(";"))


def check_no_leaked_text() -> None:
    """Redacted tasks must not ship their text in any published file.

    The first redaction cleared the Jev request's state and the row's text but
    missed the chat arms, where the input lives in the user message. 3500 strings
    stayed published until a scan found them.
    """
    redacted = [t["id"] for t in tasks_from_data_js()
                if not any("text" in json.loads(l)
                           for l in (DATA / f"{t['id']}.jsonl").read_text(
                               encoding="utf-8").splitlines() if l.strip())]
    notes.append(f"{len(redacted)} task(s) ship hashed text")

    def strings_in(call: dict) -> int:
        hits = 1 if call.get("text") else 0
        req = call.get("request") or {}
        if isinstance(req, dict):
            if req.get("state"):
                hits += 1
            for m in req.get("messages") or []:
                if m.get("role") == "user" and m.get("content"):
                    hits += 1
        return hits

    for tid in redacted:
        for rel in (f"results/receipts/{tid}.json",
                    f"results/receipts/{tid}.modern.json",
                    f"site/receipts/{tid}.json"):
            path = ROOT / rel
            if not path.exists():
                continue
            rec = load(path)
            hits = sum(strings_in(c)
                       for arm in ("jev", "gpt4o_mini", "calls")
                       for c in (rec.get(arm) or []))
            if hits:
                fail(f"{rel} still publishes {hits} text string(s) for a redacted task")
        samples = DATA / f"{tid}.jsonl"
        if any("text" in json.loads(l) for l in samples.read_text(
                encoding="utf-8").splitlines() if l.strip()):
            fail(f"data/{tid}.jsonl still contains raw text")

    curve = RECEIPTS / "cost_curve.json"
    if curve.exists():
        rec = load(curve)
        hits = 0
        for call in rec.get("calls", []):
            for arm in ("jev", "mini"):
                req = (call.get(arm) or {}).get("request") or {}
                if req.get("state"):
                    hits += 1
                for m in req.get("messages") or []:
                    if m.get("role") == "user" and m.get("content"):
                        hits += 1
        if hits:
            fail(f"results/receipts/cost_curve.json publishes {hits} input string(s); "
                 "its inputs are built from the frozen samples and inherit their terms")


def check_numbers_in_app_js() -> None:
    """Any percentage or ECE hand-written in app.js must exist in results/.

    The first screen carried ECE 0.013 and 0.019 from the n=48 run, and the proof
    layer claimed 'Mini +12 pts' when the measured gap was 7.8, for days.
    """
    calib = load(RESULTS / "calibration.json")
    tasks = tasks_from_data_js()
    allowed_ece = {round(v["p_chosen"]["ece"], 3) for v in calib.values()}
    src = (SITE / "app.js").read_text(encoding="utf-8")

    # strip template expressions: those are derived, not hand-written
    literal = re.sub(r"\$\{[^}]*\}", "", src)

    for raw in set(re.findall(r"\b0\.0\d\d\b", literal)):
        if float(raw) not in allowed_ece:
            fail(f"app.js hardcodes {raw}, which is not an ECE in calibration.json")

    known_pct = set()
    for t in tasks:
        for v in (t["jev"]["acc"], t["mini"]["acc"], t["tfidf"]["acc"]):
            known_pct.add(round(v * 100, 1))
        for g in t["gates"].values():
            known_pct.add(round(g["acc"] * 100, 1))
            known_pct.add(round(g["cov"] * 100, 1))
        if t.get("modern"):
            known_pct.add(round(t["modern"]["acc"] * 100, 1))
    for raw in set(re.findall(r"(\d{2}\.\d)\s*%", literal)):
        if float(raw) not in known_pct:
            fail(f"app.js hardcodes {raw}% with no matching measurement in results/")
    for raw in set(re.findall(r"\+(\d+)\s*pts?\b", literal)):
        fail(f"app.js hardcodes a '+{raw}pt' gap; derive it from the data instead")


def check_models_named_have_columns() -> None:
    """Prose must not cite a model the tables do not show."""
    tasks = tasks_from_data_js()
    shown = {"jev", "gpt-4o-mini", "4o-mini", "tf-idf", "tfidf"}
    modern = next((t["modern"]["model"] for t in tasks if t.get("modern")), None)
    if modern:
        shown |= {modern.lower(), modern.split("-2026")[0].lower(), "5.4-mini"}
    copy = load(SITE / "copy.json")
    blob = json.dumps(copy, ensure_ascii=False).lower()
    for m in re.findall(r"gpt-[0-9][\w.\-]*|claude-[\w.\-]+|haiku|gemini[\w.\-]*", blob):
        if not any(m.startswith(s) or s.startswith(m) for s in shown):
            fail(f"copy.json cites model '{m}' which has no column in the tables")
    if modern and not re.search(re.escape("5.4-mini"), (SITE / "app.js").read_text(encoding="utf-8")):
        fail("a current-model column exists in results/ but the table does not show it")
    for t in tasks:
        page = SITE / "decision" / f"{t['id'].replace('_', '-')}.html"
        if t.get("modern") and page.exists():
            if t["modern"]["model"] not in page.read_text(encoding="utf-8"):
                fail(f"{page.name} omits the {t['modern']['model']} row")


def check_verdicts() -> None:
    """A badge may not crown a winner McNemar refused to give."""
    for t in tasks_from_data_js():
        if t["ns"] and t["verdict"] in ("replace", "dont"):
            fail(f"{t['id']}: verdict={t['verdict']} but the comparison is ns")


def check_task_counts() -> None:
    """Docs drift behind the number of rows; the count is measurable."""
    n = len(tasks_from_data_js())
    for rel in ("README.md", "ATTRIBUTION.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for bad in re.findall(r"(?:four|all|the) of the (?:eight|8) tasks", text, re.I):
            fail(f"{rel} still says '{bad}' with {n} rows")
        for bad in re.findall(r"\ball 8 tasks\b|\b8-task\b", text, re.I):
            fail(f"{rel} still says '{bad}' with {n} rows")
    dupes = [h for h in re.findall(r"^## .+$", (ROOT / "ATTRIBUTION.md").read_text(
        encoding="utf-8"), re.M)]
    for h in set(dupes):
        if dupes.count(h) > 1:
            fail(f"ATTRIBUTION.md repeats heading {h!r} {dupes.count(h)} times")


def main() -> None:
    check_no_leaked_text()
    check_numbers_in_app_js()
    check_models_named_have_columns()
    check_verdicts()
    check_task_counts()

    for n in notes:
        print("note:", n)
    if failures:
        print()
        for f in failures:
            print("FAIL", f)
        raise SystemExit(f"\n{len(failures)} audit check(s) failed")
    print("\nAUDIT PASSED")
    print("No leaked text, no hardcoded numbers that results/ cannot back, "
          "no cited model without a column, no verdict past a failed test.")


if __name__ == "__main__":
    main()
