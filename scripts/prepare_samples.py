#!/usr/bin/env python3
"""Build balanced eval samples from public datasets."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
RNG = 7
N = 500


def coarse_banking(cat: str) -> str:
    c = cat.lower()
    if any(k in c for k in ("card", "pin", "contactless", "visa", "mastercard")):
        return "cards"
    if any(k in c for k in ("top_up", "topup")):
        return "top_up"
    if any(k in c for k in ("cash", "atm", "withdrawal")):
        return "cash_atm"
    if any(k in c for k in ("transfer", "beneficiary", "receiving_money", "balance_not_updated")):
        return "transfers"
    if any(k in c for k in ("exchange", "fiat", "currency")):
        return "fx"
    if any(
        k in c
        for k in (
            "identity",
            "verify",
            "passcode",
            "personal_details",
            "age_limit",
            "terminate",
            "country_support",
            "lost_or_stolen_phone",
        )
    ):
        return "account"
    if any(k in c for k in ("charge", "fee", "refund", "declined", "reverted", "wrong_amount")):
        return "payments_fees"
    return "other"


def balanced(df: pd.DataFrame, label_col: str, n: int, seed: int = RNG,
             text_col: str = "text") -> pd.DataFrame:
    # Public corpora repeat messages (SMS spam has 18 in 500). One text should
    # weigh once, so exact duplicates are collapsed before any draw.
    if text_col in df.columns:
        df = df.drop_duplicates(subset=[text_col])
    labels = list(df[label_col].unique())
    per = max(1, n // len(labels))
    parts = []
    for lab in labels:
        g = df[df[label_col] == lab]
        parts.append(g.sample(n=min(per, len(g)), random_state=seed))
    # Keep the source index here. The top-up below removes the rows already chosen
    # by their original index; an earlier version reset the index first, so it
    # dropped rows 0..len(out) of the source instead and could draw a row twice.
    # The frozen offensive and emotion samples were built with that version and
    # carry 7 and 1 duplicated texts; see README, "What these numbers do not mean".
    out = pd.concat(parts)
    if len(out) > n:
        out = out.sample(n=n, random_state=seed)
    elif len(out) < n:
        extra = df.drop(out.index)
        need = n - len(out)
        if len(extra) >= need:
            out = pd.concat([out, extra.sample(n=need, random_state=seed)])
    assert out.index.is_unique, "top-up drew a row that was already in the sample"
    return out.reset_index(drop=True)


def dump(task_id: str, rows: list[dict], meta: dict) -> None:
    path = OUT / f"{task_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / f"{task_id}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(task_id, len(rows), "labels", meta.get("label_counts"))


# 1. Banking coarse routing
bank = pd.read_csv(RAW / "banking_test.csv")
bank["gold"] = bank["category"].map(coarse_banking)
b = balanced(bank, "gold", N)
dump(
    "banking_coarse_route",
    [{"id": i, "text": r.text, "gold": r.gold, "fine": r.category} for i, r in b.iterrows()],
    {
        "dataset": "PolyAI BANKING77 test",
        "n": len(b),
        "label_counts": b.gold.value_counts().to_dict(),
        "notes": "77 fine intents collapsed by keyword into 8 support queues.",
    },
)

# 2. AG News
ag = pd.read_parquet(RAW / "ag_news_test.parquet")
ag_map = {0: "world", 1: "sports", 2: "business", 3: "sci_tech"}
ag["gold"] = ag["label"].map(ag_map)
a = balanced(ag, "gold", N)
dump(
    "news_topic",
    [{"id": i, "text": r.text, "gold": r.gold} for i, r in a.iterrows()],
    {"dataset": "AG News test", "n": len(a), "label_counts": a.gold.value_counts().to_dict()},
)

# 3. Tweet sentiment
tw = pd.read_parquet(RAW / "tweet_sent_test.parquet")
sent_map = {0: "negative", 1: "neutral", 2: "positive"}
tw["gold"] = tw["label"].map(sent_map)
t = balanced(tw, "gold", N)
dump(
    "tweet_sentiment",
    [{"id": i, "text": r.text, "gold": r.gold} for i, r in t.iterrows()],
    {
        "dataset": "tweet_eval sentiment test",
        "n": len(t),
        "label_counts": t.gold.value_counts().to_dict(),
    },
)

# 4. SST-2
sst = pd.read_parquet(RAW / "sst2_validation.parquet")
sst["gold"] = sst["label"].map({0: "negative", 1: "positive"})
s = balanced(sst, "gold", N, text_col="sentence")
dump(
    "review_sentiment",
    [{"id": i, "text": r.sentence, "gold": r.gold} for i, r in s.iterrows()],
    {"dataset": "SST-2 validation", "n": len(s), "label_counts": s.gold.value_counts().to_dict()},
)

# 5. SMS spam
sms = pd.read_parquet(RAW / "sms_spam.parquet")
sms["gold"] = sms["label"].map({0: "ham", 1: "spam"})
m = balanced(sms, "gold", N, text_col="sms")
dump(
    "sms_spam",
    [{"id": i, "text": r.sms.strip(), "gold": r.gold} for i, r in m.iterrows()],
    {"dataset": "UCI SMS Spam", "n": len(m), "label_counts": m.gold.value_counts().to_dict()},
)

# 6. Offensive
off = pd.read_parquet(RAW / "tweet_off_test.parquet")
off["gold"] = off["label"].map({0: "not_offensive", 1: "offensive"})
o = balanced(off, "gold", N)
dump(
    "content_offensive",
    [{"id": i, "text": r.text, "gold": r.gold} for i, r in o.iterrows()],
    {
        "dataset": "tweet_eval offensive test",
        "n": len(o),
        "label_counts": o.gold.value_counts().to_dict(),
    },
)

# 7. Hate
hate = pd.read_parquet(RAW / "tweet_hate_test.parquet")
hate["gold"] = hate["label"].map({0: "not_hate", 1: "hate"})
h = balanced(hate, "gold", N)
dump(
    "content_hate",
    [{"id": i, "text": r.text, "gold": r.gold} for i, r in h.iterrows()],
    {"dataset": "tweet_eval hate test", "n": len(h), "label_counts": h.gold.value_counts().to_dict()},
)

# 8. Tweet emotion (anger, joy, optimism, sadness)
emo = pd.read_parquet(RAW / "tweet_emoji_test.parquet")
emo_map = {0: "anger", 1: "joy", 2: "optimism", 3: "sadness"}
emo["gold"] = emo["label"].map(emo_map)
e = balanced(emo, "gold", N)
dump(
    "message_emotion",
    [{"id": i, "text": r.text, "gold": r.gold} for i, r in e.iterrows()],
    {
        "dataset": "tweet_eval emotion test",
        "n": len(e),
        "label_counts": e.gold.value_counts().to_dict(),
    },
)
