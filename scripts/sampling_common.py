"""Shared by every prepare_*.py: keep the v2 draw away from the v1 rows.

data/previous_samples.json holds the SHA-256 of every text the v1 samples used
(git tag v1-config-comparison). A v2 sample must not repeat any of them, so the
normalized comparison is scored on rows no published prompt has seen.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIOUS = ROOT / "data" / "previous_samples.json"
SEED = 11  # v1 used 7


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def previous_hashes(task_id: str) -> set[str]:
    if not PREVIOUS.exists():
        return set()
    return set(json.loads(PREVIOUS.read_text(encoding="utf-8"))["tasks"].get(task_id, []))


def exclude_previous(df, text_col: str, task_id: str):
    """Drop rows whose text was in the v1 sample for this task."""
    prev = previous_hashes(task_id)
    if not prev:
        return df
    keep = ~df[text_col].astype(str).map(sha_text).isin(prev)
    print(f"  {task_id}: excluding {int((~keep).sum())} v1 rows from the pool")
    return df[keep]
