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


def check_shell_meta_matches_generated() -> None:
    """The shell HTML is what crawlers and link previews read.

    It once advertised '8 classification decisions' while data.js said eleven,
    because the description was hand-written in copy.json instead of derived.
    """
    tasks = tasks_from_data_js()
    src = (SITE / "data.js").read_text(encoding="utf-8")
    site = json.loads(src.split("const SITE = ", 1)[1].split(";\n\nconst ", 1)[0])
    generated = site.get("description")
    shell = (SITE / "index.html").read_text(encoding="utf-8")
    for attr in ('name="description"', 'property="og:description"'):
        m = re.search(attr + r' content="([^"]*)"', shell)
        if not m:
            fail(f"index.html has no {attr}")
        elif m.group(1) != generated:
            fail(f"index.html {attr} does not match the generated SITE.description")
    for bad in re.findall(r"\b(\d+) (?:classification )?decisions\b", shell):
        if int(bad) != len(tasks):
            fail(f"index.html advertises {bad} decisions, but there are {len(tasks)}")


def check_prose_rates_match_error_profile() -> None:
    """Recall and miss rates quoted in prose must exist in error_profile.json.

    build_site.py enforces this at build time. Repeating it here means CI still
    catches it if the generated site is committed by another route.
    """
    errors = load(RESULTS / "error_profile.json")
    copy = load(SITE / "copy.json")
    for t in copy["tasks"]:
        prof = errors.get(t["id"], {})
        known = set()
        for arm in prof.values():
            for stats in arm.get("per_class", {}).values():
                for f_ in ("recall", "missed_rate", "false_positive_rate"):
                    if stats.get(f_) is not None:
                        known.add(round(stats[f_] * 100, 1))
            for gate in arm.get("recall_at_gate", {}).values():
                for stats in gate.values():
                    if stats.get("recall_on_covered") is not None:
                        known.add(round(stats["recall_on_covered"] * 100, 1))
        blob = " ".join(str(t.get(f_) or "") for f_ in ("why", "gate", "rowNote"))
        for phrase in re.findall(r"[Mm]isses (\d+\.?\d*)%|catches (\d+\.?\d*)%|"
                                 r"recall (?:from |of )?(\d+\.?\d*)%", blob):
            for raw in filter(None, phrase):
                if float(raw) not in known:
                    fail(f"{t['id']}: prose claims {raw}% recall/miss with no match "
                         f"in error_profile.json")


def check_units_in_decision_tables() -> None:
    """A cost column must not carry a token count.

    The current-model row put '334.5 tok/call' under '$/1M decisions'.
    """
    for t in tasks_from_data_js():
        page = SITE / "decision" / f"{t['id'].replace('_', '-')}.html"
        if not page.exists():
            continue
        html_src = page.read_text(encoding="utf-8")
        headers = re.findall(r"<th>([^<]*)</th>", html_src)
        cells = re.findall(r"<tr>(.*?)</tr>", html_src, re.S)
        cost_idx = next((i for i, h in enumerate(headers) if "cost" in h.lower()
                         or "$" in h), None)
        if cost_idx is None:
            continue
        for row in cells:
            tds = re.findall(r"<td>(.*?)</td>", row, re.S)
            if len(tds) <= cost_idx:
                continue
            cell = tds[cost_idx]
            if "tok" in cell and "$" not in cell and "unpriced" not in cell:
                fail(f"{page.name}: token count in the cost column ({cell.strip()!r})")


def check_titles_name_every_column() -> None:
    """A title must not list three models when the table shows four."""
    for t in tasks_from_data_js():
        page = SITE / "decision" / f"{t['id'].replace('_', '-')}.html"
        if not page.exists():
            continue
        html_src = page.read_text(encoding="utf-8")
        title = re.search(r"<title>([^<]*)</title>", html_src)
        if not title:
            continue
        rows = len(re.findall(r"<tr><td>", html_src))
        named = len(re.findall(r"\bvs\b", title.group(1)))
        if named and named + 1 < rows and not re.search(r"\d+ other models", title.group(1)):
            fail(f"{page.name}: title names {named + 1} models but the table shows {rows}")


def check_attribution_is_self_consistent() -> None:
    """The opening paragraph once said the opposite of paragraph seven."""
    text = (ROOT / "ATTRIBUTION.md").read_text(encoding="utf-8")
    head = text[:text.index("| Task |")] if "| Task |" in text else text[:1200]
    claims_text = re.search(r"with the\s+original text", head)
    says_hashed = "ship the hash" in head or "SHA-256 of it" in head
    if claims_text and says_hashed:
        fail("ATTRIBUTION.md opening both claims raw text and hashed text")
    if claims_text and not says_hashed:
        fail("ATTRIBUTION.md opening says data/*.jsonl holds the original text, "
             "but rows are redacted further down")


def main() -> None:
    check_no_leaked_text()
    check_shell_meta_matches_generated()
    check_prose_rates_match_error_profile()
    check_units_in_decision_tables()
    check_titles_name_every_column()
    check_attribution_is_self_consistent()
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
