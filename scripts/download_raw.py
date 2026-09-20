#!/usr/bin/env python3
"""Download the public datasets used to build data/*.jsonl.

Raw files land in raw/. You do not need them to re-run the eval —
the frozen 48-row samples are already in data/. Use this only if you
want to rebuild the samples with a different seed or N.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

FILES = {
    "banking_test.csv": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv",
    "banking_train.csv": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv",
    "ag_news_test.parquet": "https://huggingface.co/datasets/fancyzhx/ag_news/resolve/main/data/test-00000-of-00001.parquet",
    "tweet_sent_test.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/sentiment/test-00000-of-00001.parquet",
    "sms_spam.parquet": "https://huggingface.co/datasets/ucirvine/sms_spam/resolve/main/plain_text/train-00000-of-00001.parquet",
    "sst2_validation.parquet": "https://huggingface.co/datasets/stanfordnlp/sst2/resolve/main/data/validation-00000-of-00001.parquet",
    "tweet_off_test.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/offensive/test-00000-of-00001.parquet",
    "tweet_hate_test.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/hate/test-00000-of-00001.parquet",
    "tweet_emoji_test.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/emotion/test-00000-of-00001.parquet",
    # Train splits. scripts/run_tfidf_baseline.py fits on these; the frozen eval rows
    # come from the test splits above, so the baseline never trains on what it scores.
    "ag_news_train.parquet": "https://huggingface.co/datasets/fancyzhx/ag_news/resolve/main/data/train-00000-of-00001.parquet",
    "sst2_train.parquet": "https://huggingface.co/datasets/stanfordnlp/sst2/resolve/main/data/train-00000-of-00001.parquet",
    "tweet_sent_train.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/sentiment/train-00000-of-00001.parquet",
    "tweet_off_train.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/offensive/train-00000-of-00001.parquet",
    "tweet_hate_train.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/hate/train-00000-of-00001.parquet",
    "tweet_emo_train.parquet": "https://huggingface.co/datasets/cardiffnlp/tweet_eval/resolve/main/emotion/train-00000-of-00001.parquet",
}


def main() -> None:
    for name, url in FILES.items():
        dest = RAW / name
        print(f"GET {url}")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
