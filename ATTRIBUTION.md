# Dataset attribution and redistribution status

`data/*.jsonl` contains 500 rows sampled from each public dataset below, with the
original text and the original gold label. Publishing this repo redistributes that
text, so each source has to be cleared on its own terms.

**Status column meaning**

- `verify` - the licence has not been confirmed against the dataset card yet. Do this
  before the repo is advertised publicly.
- `risk` - there is a known redistribution restriction to resolve, not just a citation
  to add.

| Task | Source | Upstream | Status |
|---|---|---|---|
| `sms_spam` | UCI SMS Spam Collection | `ucirvine/sms_spam` | verify |
| `review_sentiment` | SST-2 validation (Stanford Sentiment Treebank) | `stanfordnlp/sst2` | verify |
| `news_topic` | AG News test | `fancyzhx/ag_news` | verify |
| `banking_coarse_route` | BANKING77 (PolyAI) | `PolyAI-LDN/task-specific-datasets` | verify |
| `message_emotion` | TweetEval emotion | `cardiffnlp/tweet_eval` | text not redistributed |
| `content_offensive` | TweetEval offensive | `cardiffnlp/tweet_eval` | text not redistributed |
| `content_hate` | TweetEval hate | `cardiffnlp/tweet_eval` | text not redistributed |
| `tweet_sentiment` | TweetEval sentiment | `cardiffnlp/tweet_eval` | text not redistributed |

## How the TweetEval question is handled

**Resolved by not shipping the text.** For the four tweet tasks, `data/*.jsonl`
contains the sample id, the gold label and a SHA-256 of the text. The text itself is
never committed. Anyone who wants the full check runs:

```bash
python3 scripts/rehydrate.py     # re-downloads upstream, verifies every hash
python3 scripts/verify_run.py    # now checks text and request hashes too
```

Without rehydrating, `verify_run.py` still recounts every published accuracy from the
receipts, because that only needs predictions and gold labels. It prints exactly which
tasks are running in the reduced mode rather than quietly skipping them.

`scripts/redact_text.py` is what produces that state after a run, and it is idempotent.

### Why, stated plainly

Four of the eight tasks are tweet text. Platform terms for X/Twitter content have
historically allowed sharing **tweet IDs** rather than **tweet text**, which is why
many research corpora ship IDs plus a rehydration script. TweetEval itself
distributes text, but that does not automatically transfer the right to redistribute
it from this repo.

This repo takes option 2: ship what verification needs, not the text. It keeps the
proof story and removes the clearance question, at the cost of one extra script for
anyone who wants the byte-level check.

The alternatives, for the record, were to confirm the licence and ship the text
anyway, or to drop the four tweet tasks and throw away real measurements.

## What this repo is not

This is an independent bench. It is not affiliated with TypeSafe AI, OpenAI, or any
dataset author. Model names and dataset names are used for identification only.

## Code

MIT, see `LICENSE`. That covers `scripts/` and `site/` only. The datasets keep their
own terms.
