#!/usr/bin/env python3
"""TF-IDF + logistic regression on the frozen n=500 eval texts.

Train on leftover labeled rows (or official train split) so eval texts
never appear in training. Writes results/tfidf_baseline.json.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


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


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n <= 0:
        return {"k": 0, "n": 0, "p": 0.0, "lo": 0.0, "hi": 0.0}
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / den
    margin = z * math.sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n)) / den
    return {
        "k": k,
        "n": n,
        "p": p,
        "lo": max(0.0, center - margin),
        "hi": min(1.0, center + margin),
    }


def mcnemar(a_ok: list[bool], b_ok: list[bool]) -> dict:
    b = c = 0
    for x, y in zip(a_ok, b_ok):
        if x and not y:
            b += 1
        elif y and not x:
            c += 1
    n_disc = b + c
    if n_disc == 0:
        pval, chi2 = 1.0, 0.0
    else:
        chi2 = (abs(b - c) - 1) ** 2 / n_disc
        pval = math.erfc(math.sqrt(chi2 / 2.0))
    return {
        "a_only_correct": b,
        "b_only_correct": c,
        "discordant": n_disc,
        "p_value": pval,
        "winner": "a" if b > c and pval < 0.05 else ("b" if c > b and pval < 0.05 else "ns"),
    }


def load_eval(task_id: str) -> list[dict]:
    rows = []
    with (DATA / f"{task_id}.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    # Redacted tasks ship hashes instead of text; scripts/rehydrate.py puts the
    # text back in a sidecar. Without it this baseline cannot train or score.
    sidecar = DATA / f"{task_id}.text.jsonl"
    if sidecar.exists():
        texts = {}
        with sidecar.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                texts[r["id"]] = r["text"]
        for row in rows:
            row.setdefault("text", texts.get(row["id"]))
    if any(r.get("text") is None for r in rows):
        raise SystemExit(
            f"{task_id}: text is redacted and no sidecar found. "
            f"Run scripts/rehydrate.py first."
        )
    return rows


def leftover(df: pd.DataFrame, text_col: str, eval_texts: set[str]) -> pd.DataFrame:
    return df[~df[text_col].astype(str).isin(eval_texts)].copy()


def fit_predict(train_texts, train_y, test_texts):
    pipe = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=50000,
                    sublinear_tf=True,
                ),
            ),
            (
                # One-vs-rest around liblinear. sklearn used to apply OvR implicitly
                # for multiclass; 1.7+ refuses and asks for the wrapper. Wrapping
                # keeps the original scheme instead of silently switching solver.
                "lr",
                OneVsRestClassifier(
                    LogisticRegression(
                        max_iter=400,
                        C=2.0,
                        class_weight="balanced",
                        solver="liblinear",
                    )
                ),
            ),
        ]
    )
    t0 = time.perf_counter()
    pipe.fit(train_texts, train_y)
    fit_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    preds = pipe.predict(test_texts)
    pred_ms = (time.perf_counter() - t1) * 1000
    # One batched predict() over the whole test set, divided by its size. That is a
    # mean per row for batched inference, not a median of per-row timings, and it
    # was once published under the name p50. The key says what it is now.
    mean_ms = pred_ms / max(1, len(test_texts))
    return list(preds), fit_ms, pred_ms, mean_ms, len(train_texts)


def pack(task_id, eval_rows, preds, train_n, fit_ms, pred_ms, mean_ms, train_note, jev, mini):
    gold = [r["gold"] for r in eval_rows]
    n = len(gold)
    ok = [p == g for p, g in zip(preds, gold)]
    acc = sum(ok) / n
    jev_ok = [r["pred"] == r["gold"] for r in jev]
    mini_ok = [r["pred"] == r["gold"] for r in mini]
    # align by id
    jev_by = {r["id"]: r["pred"] == r["gold"] for r in jev}
    mini_by = {r["id"]: r["pred"] == r["gold"] for r in mini}
    tf_ok = []
    j_ok = []
    m_ok = []
    for r, p in zip(eval_rows, preds):
        tf_ok.append(p == r["gold"])
        j_ok.append(jev_by[r["id"]])
        m_ok.append(mini_by[r["id"]])
    return {
        "task_id": task_id,
        "n": n,
        "train_n": train_n,
        "train_note": train_note,
        "acc": acc,
        "wilson": wilson(sum(tf_ok), n),
        "fit_ms": fit_ms,
        "predict_total_ms": pred_ms,
        "predict_mean_ms_per_row_batched": mean_ms,
        "mcnemar_vs_jev": mcnemar(tf_ok, j_ok),
        "mcnemar_vs_mini": mcnemar(tf_ok, m_ok),
        "preds": [{"id": r["id"], "gold": r["gold"], "pred": str(p)} for r, p in zip(eval_rows, preds)],
    }


def run_one(task_id, train_df, text_col, note):
    ev = load_eval(task_id)
    eval_texts = {r["text"] for r in ev}
    train_df = leftover(train_df, text_col, eval_texts)
    preds, fit_ms, pred_ms, mean_ms, tn = fit_predict(
        train_df[text_col].astype(str).tolist(),
        train_df["gold"].tolist(),
        [r["text"] for r in ev],
    )
    d = json.loads((RESULTS / f"{task_id}.json").read_text(encoding="utf-8"))
    return pack(task_id, ev, preds, tn, fit_ms, pred_ms, mean_ms, note, d["jev_preds"], d["gpt4o_mini_preds"])


def cfpb_train() -> pd.DataFrame:
    """CFPB complaints the frozen 500 never used, mapped to the same eight queues."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_cfpb import MIRROR_PARQUET, PRODUCT_TO_QUEUE, MIN_CHARS, MAX_CHARS

    df = pd.read_parquet(MIRROR_PARQUET,
                         columns=["Complaint ID", "Product", "Consumer complaint narrative"])
    df = df.rename(columns={"Consumer complaint narrative": "text"})
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len().between(MIN_CHARS, MAX_CHARS)]
    df["gold"] = df["Product"].map(PRODUCT_TO_QUEUE)
    df = df[df["gold"].notna()]
    # Cap per class so the classical baseline is not just predicting the majority
    # queue: credit reporting alone is over half the database.
    parts = [g.sample(n=min(8000, len(g)), random_state=7) for _, g in df.groupby("gold")]
    return pd.concat(parts, ignore_index=True)


def civil_train() -> pd.DataFrame:
    """Civil Comments train split, balanced, never touching the frozen test rows."""
    import sys
    import urllib.request
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_civil import TOXIC_AT, MIN_CHARS, MAX_CHARS

    local = RAW / "civil_comments_train.parquet"
    if not local.exists():
        url = ("https://huggingface.co/datasets/google/civil_comments/resolve/main/"
               "data/train-00000-of-00002.parquet")
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, local)
    df = pd.read_parquet(local, columns=["text", "toxicity"])
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len().between(MIN_CHARS, MAX_CHARS)]
    df["gold"] = (df["toxicity"] >= TOXIC_AT).map({True: "toxic", False: "not_toxic"})
    n = min(30000, int(df["gold"].value_counts().min()))
    parts = [g.sample(n=n, random_state=7) for _, g in df.groupby("gold")]
    return pd.concat(parts, ignore_index=True)


def injection_train() -> pd.DataFrame:
    """The 361 deepset rows the frozen 300 did not take."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_injection import load_all, LABELS

    df = load_all()
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() >= 10].drop_duplicates(subset=["text"])
    df["gold"] = df["label"].map(LABELS)
    return df.reset_index(drop=True)


def main():
    out = []

    out.append(run_one("prompt_injection", injection_train(), "text",
                       "deepset rows outside the frozen 300"))

    out.append(run_one("civil_toxicity", civil_train(), "text",
                       "Civil Comments official train, balanced"))

    out.append(run_one("cfpb_queue_route", cfpb_train(), "text",
                       "CFPB complaints outside the frozen 500, capped at 8000 per queue"))

    bank_tr = pd.read_csv(RAW / "banking_train.csv")
    bank_tr["gold"] = bank_tr["category"].map(coarse_banking)
    out.append(run_one("banking_coarse_route", bank_tr, "text", "BANKING77 official train"))

    sms = pd.read_parquet(RAW / "sms_spam.parquet")
    sms["text"] = sms["sms"].astype(str).str.strip()
    sms["gold"] = sms["label"].map({0: "ham", 1: "spam"})
    out.append(run_one("sms_spam", sms, "text", "UCI SMS leftover after frozen eval (no official train split)"))

    sst = pd.read_parquet(RAW / "sst2_train.parquet")
    sst["text"] = sst["sentence"]
    sst["gold"] = sst["label"].map({0: "negative", 1: "positive"})
    out.append(run_one("review_sentiment", sst, "text", "SST-2 official train"))

    ag = pd.read_parquet(RAW / "ag_news_train.parquet")
    ag["gold"] = ag["label"].map({0: "world", 1: "sports", 2: "business", 3: "sci_tech"})
    out.append(run_one("news_topic", ag, "text", "AG News official train"))

    tw = pd.read_parquet(RAW / "tweet_sent_train.parquet")
    tw["gold"] = tw["label"].map({0: "negative", 1: "neutral", 2: "positive"})
    out.append(run_one("tweet_sentiment", tw, "text", "tweet_eval sentiment official train"))

    off = pd.read_parquet(RAW / "tweet_off_train.parquet")
    off["gold"] = off["label"].map({0: "not_offensive", 1: "offensive"})
    out.append(run_one("content_offensive", off, "text", "tweet_eval offensive official train"))

    hate = pd.read_parquet(RAW / "tweet_hate_train.parquet")
    hate["gold"] = hate["label"].map({0: "not_hate", 1: "hate"})
    out.append(run_one("content_hate", hate, "text", "tweet_eval hate official train"))

    emo = pd.read_parquet(RAW / "tweet_emo_train.parquet")
    emo["gold"] = emo["label"].map({0: "anger", 1: "joy", 2: "optimism", 3: "sadness"})
    out.append(run_one("message_emotion", emo, "text", "tweet_eval emotion official train"))

    slim = []
    for r in out:
        slim.append({k: r[k] for k in r if k != "preds"})
        print(
            f"{r['task_id']:24} tfidf {r['acc']:.3f} [{r['wilson']['lo']:.3f},{r['wilson']['hi']:.3f}] "
            f"train_n={r['train_n']} mean/row={r['predict_mean_ms_per_row_batched']*1000:.2f}us batched  "
            f"vs_jev={r['mcnemar_vs_jev']['winner']} p={r['mcnemar_vs_jev']['p_value']:.3g}  "
            f"vs_mini={r['mcnemar_vs_mini']['winner']} p={r['mcnemar_vs_mini']['p_value']:.3g}"
        )
    (RESULTS / "tfidf_baseline.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (RESULTS / "tfidf_baseline_summary.json").write_text(json.dumps(slim, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
