# Dataset attribution and redistribution status

`data/*.jsonl` contains 500 rows sampled from each public dataset below, with the
original text and the original gold label. Publishing this repo redistributes that
text, so each source has to be cleared on its own terms.

**Status column meaning**

Every row has now been checked against its upstream source. Three come back with no
licence declared at all, which is a finding rather than an oversight: see below.

| Task | Source | Upstream | Status |
|---|---|---|---|
| `cfpb_queue_route` | CFPB Consumer Complaint Database | text: [`BEE-spoke-data/consumer-finance-complaints`](https://huggingface.co/datasets/BEE-spoke-data/consumer-finance-complaints) (CC0); labels: [CFPB export](https://www.consumerfinance.gov/data-research/consumer-complaints/) | US federal government work, see note |
| `prompt_injection` | deepset prompt injections | [`deepset/prompt-injections`](https://huggingface.co/datasets/deepset/prompt-injections) | Apache-2.0, text redistributable |
| `civil_toxicity` | Civil Comments | [`google/civil_comments`](https://huggingface.co/datasets/google/civil_comments) test split | CC0, text redistributable |
| `sms_spam` | UCI SMS Spam Collection | [`ucirvine/sms_spam`](https://huggingface.co/datasets/ucirvine/sms_spam) | no licence upstream, text not redistributed |
| `review_sentiment` | SST-2 validation (Stanford Sentiment Treebank) | [`stanfordnlp/sst2`](https://huggingface.co/datasets/stanfordnlp/sst2) | no licence upstream, text not redistributed |
| `news_topic` | AG News test | [`fancyzhx/ag_news`](https://huggingface.co/datasets/fancyzhx/ag_news) | no licence upstream, text not redistributed |
| `banking_coarse_route` | BANKING77 (PolyAI) | [`PolyAI-LDN/task-specific-datasets`](https://github.com/PolyAI-LDN/task-specific-datasets) | CC BY 4.0, confirmed from the repo's LICENSE file |
| `message_emotion` | TweetEval emotion | [`cardiffnlp/tweet_eval`](https://huggingface.co/datasets/cardiffnlp/tweet_eval) | text not redistributed |
| `content_offensive` | TweetEval offensive | [`cardiffnlp/tweet_eval`](https://huggingface.co/datasets/cardiffnlp/tweet_eval) | text not redistributed |
| `content_hate` | TweetEval hate | [`cardiffnlp/tweet_eval`](https://huggingface.co/datasets/cardiffnlp/tweet_eval) | text not redistributed |
| `tweet_sentiment` | TweetEval sentiment | [`cardiffnlp/tweet_eval`](https://huggingface.co/datasets/cardiffnlp/tweet_eval) | text not redistributed |

## Nothing in this repo is redistributed without a clear right to

Seven of the eleven tasks ship the sample id, the gold label and a SHA-256 of the
text, never the text itself. `scripts/rehydrate.py` downloads the upstream split,
matches rows by hash and writes the text back locally, refusing to write anything if
a single hash disagrees.

```bash
python3 scripts/rehydrate.py      # all seven, or name one task
python3 scripts/verify_run.py     # now checks text and request hashes too
```

Two different reasons for the same treatment:

- **TweetEval** (`message_emotion`, `content_offensive`, `content_hate`,
  `tweet_sentiment`): platform terms for X/Twitter content have historically favoured
  sharing ids over text.
- **No declared licence** (`sms_spam`, `review_sentiment`, `news_topic`): all three
  dataset cards report `license: unknown`. They are benchmarks everyone
  redistributes, but redistribution as a norm is not a grant, so this repo does not
  rely on one.

The four that do ship their text are the ones with an explicit grant or public-domain
status: CFPB (US federal government work), Civil Comments (CC0), deepset
prompt-injections (Apache-2.0) and BANKING77 (CC BY 4.0, confirmed from the LICENSE
file in PolyAI's repo).

Without rehydrating, `verify_run.py` still recounts every published accuracy from the
receipts, because that needs only predictions and gold labels. It names the tasks
running in reduced mode rather than skipping them silently.

`scripts/redact_text.py` produces that state and is idempotent. It clears the text in
four places: the frozen samples, the Jev request's `state`, the chat arms' user
message, and the cost-curve inputs, which are built by concatenating real sentences
and so inherit those datasets' terms.

## CFPB: two sources on purpose


The Bureau's own bulk export carries no narratives, and its search API refuses scripted
clients, so the complaint text comes from a CC0 mirror on Hugging Face. The **gold
label never does**: `scripts/prepare_cfpb.py` joins every row's Product from the
Bureau's export on Complaint ID and discards any row where the mirror disagrees. On the
32,000-row candidate pool, 31,990 matched and **none disagreed**, which is the evidence
that the mirror is faithful.

US federal government works are generally not subject to domestic copyright, and the
Bureau publishes the database for reuse, but confirm the current terms of use before
launch. Personal details are redacted as `XXXX` by the Bureau before publication.

The label is selected by the person filing the complaint, not by an expert annotator,
and the product taxonomy has been renamed several times. The eight queues collapse that
history; the mapping is in `scripts/prepare_cfpb.py` and the meta file records it.

## Civil Comments is the clean-licence route

`civil_toxicity` is CC0, so its text ships in this repo with no redaction and no
rehydration step. It covers the same judgement as the TweetEval hate row, which is why
both are published: one shows what the verdict looks like on thin gold with an awkward
licence, the other on clean gold that can simply be handed to a reader.

The label is the fraction of crowd annotators who called a comment toxic, thresholded
at 0.5. That is a crowd majority, not an expert ruling, and 99 of the 500 rows sit
between 0.4 and 0.6, so a fifth of the set is genuinely contested. The meta file
records that count rather than hiding it.

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

Four of the eleven rows are tweet text. Platform terms for X/Twitter content have
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
