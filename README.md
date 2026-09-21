# whichjudge.dev

Replacement matrix for cheap **judge / decision** models.

Rows are decisions you already pay an LLM to make (spam gate, ticket route, hate screen).
Columns are models: **Jev `jev-1.13.0`**, **`gpt-4o-mini-2024-07-18`**, **`gpt-5.4-mini-2026-03-17`** and a TF-IDF + logistic regression baseline.
The next System One-style model is another column, not another site.

<!-- generated:ece-line -->
**Calibration (ECE on p_chosen, 10 bins, `scripts/calibrate.py`):** review polarity 0.015, sms spam gate 0.016, comment toxicity gate 0.075, message emotion 0.083, news topic 0.096, consumer complaint routing 0.100, offensive language screen 0.110, prompt-injection screen 0.134, social sentiment (3-way) 0.141, hate-speech screen 0.187, banking queue routing 0.213. A quit line is only honest where ECE is low. Do not auto-route on the high ones.
<!-- /generated:ece-line -->

Domain: [whichjudge.dev](https://whichjudge.dev). **Judge = in-loop decision**, not “grade this agent.” Do not rename. Eyebrow: “which model for this decision.” Contact: contact@radrebeldeveloper.com

Everything needed to reproduce the table is in this repo: the frozen samples, the schemas, every per-call receipt, and the scripts that recount and re-run them.

---

## What you have in this folder

```
whichjudge/
  README.md                 this file
  ATTRIBUTION.md            dataset sources + redistribution status (read before launch)
  requirements.txt
  .env.example
  .gitignore
  .github/workflows/
    pages.yml               verify receipts, check site is generated, deploy to Pages
  scripts/
    download_raw.py         optional: re-fetch public datasets
    prepare_samples.py      build the academic data/*.jsonl (seed=7, n=500)
    run_eval.py             Jev vs gpt-4o-mini; writes hashed receipts
    verify_run.py           recompute every published statistic from receipts (no API)
    run_tfidf_baseline.py   TF-IDF + LR on leftover official train
    prepare_cfpb.py         freeze 500 CFPB complaints, labels joined from the Bureau
    prepare_civil.py        freeze 500 Civil Comments (CC0) for the toxicity row
    prepare_injection.py    freeze 300 prompt-injection rows (n is capped by the source)
    run_modern_baseline.py  same samples through a current small model (--recompute)
    calibrate.py            ECE + reliability bins from receipts (no API)
    cost_curve.py           cost and latency vs input length; finds the crossover
    redact_text.py          strip third-party text to hashes before publishing
    rehydrate.py            restore that text from upstream, hash-checked
    build_site.py           GENERATE site from results/ (--check gates CI)
    audit_site.py           CI cross-checks --check cannot make
  data/                     FROZEN samples + meta (n=500, injection n=300)
  schemas/                  frozen questions + Mini prompts
  results/                  summary, calibration.json, tfidf_*.json
  results/code_patches.json scripts changed after the run, with before/after hashes
  results/receipts/         full request/response JSON + hashes
  site/                     STATIC HOST THIS
    copy.json               editorial text only, no numbers
    data.js                 GENERATED from results/
    decision/*.html         GENERATED, one crawlable page per decision
    sitemap.xml robots.txt  GENERATED
```

`ATTRIBUTION.md` records what each row may and may not redistribute. Seven of the
eleven ship a SHA-256 of the text rather than the text; `scripts/rehydrate.py`
restores them.

`data/*.jsonl` is the source of truth for which 500 examples.
`results/*.json` is each task's parsed predictions; rows were added over several runs.
`site/` is the comparison page. Open `site/index.html` locally or dump the three files on any static host (Vercel / Cloudflare Pages / GitHub Pages) pointed at whichjudge.dev.

---

## Reproduce the table

Python 3.10+. No GPU.

```bash
cd whichjudge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# put real keys in .env, then:
set -a && source .env && set +a

# Frozen samples are already in data/. Skip prepare unless you change seed/N.
python3 scripts/run_eval.py                 # every task
python3 scripts/run_eval.py sms_spam        # one task
```

Jev: `POST https://api.typesafe.ai/v1/systemone` with `model: jev-latest` (resolved to `jev-1.13.0` on 2026-09-20).
Mini: `POST https://api.openai.com/v1/chat/completions`, `temperature: 0`, `response_format: json_object`.

A full run of the two main arms across every task is about **$0.12**. The current-model column adds roughly the same again. Output tokens on Jev are free; Mini is $0.15 / $0.60 per million in/out.

### Rebuild samples (optional)

```bash
python3 scripts/download_raw.py
python3 scripts/prepare_samples.py
```

Sampling: `random_state=7`, `N=500`, balanced across labels.
BANKING77 is collapsed from 77 fine intents → 8 queues by keyword (see `coarse_banking()`). That gold is noisy; the Mix verdict on that row is not a production bake-off.

---

<!-- generated:main-table -->
## Results, seed 7, n=500 per task except prompt-injection screen (n=300)

Wilson 95% CI. McNemar on paired errors, Holm-corrected across the 11 Jev-vs-Mini
tests. `ns` = Holm p >= 0.05, meaning the accuracy gap is noise and neither model should
be crowned. 2 row(s) clear the raw 0.05 and not the corrected one: offensive language screen, news topic.

| Decision | n | Jev | Mini | McNemar | ECE | Verdict |
|---|---|---|---|---|---|---|
| Prompt-injection screen | 300 | 80.0% [75.1%-84.1%] | 81.0% | ns raw p=0.719, Holm p=1 | 0.134 | ns, Neither |
| Consumer complaint routing | 500 | 82.8% [79.2%-85.9%] | 81.0% | ns raw p=0.253, Holm p=1 | 0.100 | ns |
| Comment toxicity gate | 500 | 78.0% [74.2%-81.4%] | 77.0% | ns raw p=0.688, Holm p=1 | 0.075 | ns |
| SMS spam gate | 500 | 96.4% [94.4%-97.7%] | 96.4% | ns raw p=0.773, Holm p=1 | 0.016 | ns |
| Review polarity | 500 | 97.0% [95.1%-98.2%] | 96.4% | ns raw p=0.546, Holm p=1 | 0.015 | ns |
| Message emotion | 500 | 79.8% [76.1%-83.1%] | 75.0% | jev raw p=0.00528, Holm p=0.0476 | 0.083 | Replace |
| Offensive language screen | 500 | 76.6% [72.7%-80.1%] | 70.8% | ns raw p=0.00787, Holm p=0.063 | 0.110 | ns |
| Social sentiment (3-way) | 500 | 73.8% [69.8%-77.5%] | 72.6% | ns raw p=0.576, Holm p=1 | 0.141 | ns |
| News topic | 500 | 85.6% [82.3%-88.4%] | 82.6% | ns raw p=0.00933, Holm p=0.0653 | 0.096 | ns |
| Banking queue routing | 500 | 71.8% [67.7%-75.6%] | 64.4% | jev raw p=3.23e-05, Holm p=0.000355 | 0.213 | Replace |
| Hate-speech screen | 500 | 66.2% [61.9%-70.2%] | 74.0% | mini raw p=0.00258, Holm p=0.0258 | 0.187 | Don't |
<!-- /generated:main-table -->

## Is Jev only beating a 2024 baseline?

<!-- generated:modern-table -->
Fair objection, so here is a current small model on the same frozen samples with the
same prompts (`scripts/run_modern_baseline.py`, model `gpt-5.4-mini-2026-03-17`). Both `vs` columns are
Holm-corrected within their own family of 11 tests:

| Decision | Jev | 4o-mini (2024) | gpt-5.4-mini (2026) | vs Jev | vs 4o-mini |
|---|---|---|---|---|---|
| Prompt-injection screen | 80.0% | 81.0% | 86.0% | **gpt-5.4-mini** | ns |
| Consumer complaint routing | 82.8% | 81.0% | 78.6% | ns | ns |
| Comment toxicity gate | 78.0% | 77.0% | 76.6% | ns | ns |
| SMS spam gate | 96.4% | 96.4% | 94.6% | ns | ns |
| Review polarity | 97.0% | 96.4% | 94.8% | ns | ns |
| Message emotion | 79.8% | 75.0% | 77.6% | ns | ns |
| Offensive language screen | 76.6% | 70.8% | 74.2% | ns | ns |
| Social sentiment (3-way) | 73.8% | 72.6% | 74.4% | ns | ns |
| News topic | 85.6% | 82.6% | 80.4% | Jev | ns |
| Banking queue routing | 71.8% | 64.4% | 70.8% | ns | **gpt-5.4-mini** |
| Hate-speech screen | 66.2% | 74.0% | 71.0% | ns | ns |

**Jev 1 win, 9 ties, 1 loss** against a model two years newer. 2 row(s) that beat it at the raw 0.05 (consumer complaint routing, review polarity) do not survive the correction.
The loss is prompt injection, and it matters: the 2026 model catches
72.0% of injections against Jev's
60.0%, at 0.0% and 0.0% false positives.
It is genuinely better there and still misses 28.0%, so the Neither verdict
on that row stands for all three.
<!-- /generated:modern-table -->

Token cost per call is recorded; price is left unset rather than guessed, because a
made-up price on a site that argues about cost would be worse than no price.

This column is additive. It does not touch `run_eval.py`, `results/summary.json` or the
existing receipts. `verify_run.py` recounts it from `results/receipts/<task>.modern.json`
like every other column. Statistics are separated from the calls, so `--recompute`
rebuilds them from stored receipts for free.

### Calibration and gating are different questions

ECE says whether the confidence can be read as a probability. It does **not** say
whether thresholding helps, because gating only needs the model to rank its own
answers correctly. A badly calibrated task can still gate well, and the two lowest-ECE
rows here gain the least because they have no headroom left.

The auto slice below is the strongest gate that still leaves at least half the traffic
automated, selected by that rule from the measured gates rather than chosen by hand.

<!-- generated:gate-table -->
| Decision | Gold | ECE | Auto slice (gate) | Lift vs ungated | Cross-validated |
|---|---|---|---|---|---|
| Prompt-injection screen | academic | 0.134 | 87.4% on 79.3% (>=0.9) | +7.4pt | 87.3% |
| Consumer complaint routing | live system | 0.100 | 91.2% on 77.4% (>=0.9) | +8.4pt | 91.2% |
| Comment toxicity gate | real text | 0.075 | 91.0% on 53.4% (>=0.9) | +13.0pt | 90.9% |
| SMS spam gate | academic | 0.016 | 98.8% on 85.2% (>=0.9) | +2.4pt | 98.7% |
| Review polarity | academic | 0.015 | 98.5% on 94.2% (>=0.8) | +1.5pt | 98.3% |
| Message emotion | academic | 0.083 | 90.3% on 66.2% (>=0.9) | +10.5pt | 90.3% |
| Offensive language screen | academic | 0.110 | 86.7% on 60.2% (>=0.9) | +10.1pt | 86.7% |
| Social sentiment (3-way) | academic | 0.141 | 81.6% on 65.2% (>=0.9) | +7.8pt | 81.1% |
| News topic | academic | 0.096 | 92.9% on 84.4% (>=0.9) | +7.3pt | 92.9% |
| Banking queue routing | academic | 0.213 | 80.1% on 78.4% (>=0.9) | +8.3pt | 80.1% |
| Hate-speech screen | academic | 0.187 | 70.7% on 64.2% (>=0.8) | +4.5pt | 71.1% |

Gating beats not gating on **11 of 11 rows**. The last column chooses the gate on one random half and scores it on the other, 400 splits; the optimism of picking and scoring on the same rows is at most 0.5pt here. What a high ECE costs you is the right to quote the confidence number as a probability, not the right to threshold on it.
<!-- /generated:gate-table -->

### Accuracy is the wrong number for a security gate

<!-- generated:injection-classes -->
The prompt-injection row looks fine on accuracy: Jev 80.0%,
Mini 81.0%, tied at raw p=0.719.
Split it by class and the picture changes:

|  | Jev | 4o-mini |
|---|---|---|
| Injections caught | 60.0% | 62.7% |
| Injections missed | 60 of 150 | 56 of 150 |
| Legitimate text wrongly blocked | 0.0% | 0.7% |

Both models are biased hard toward letting text through. They almost never block a
legitimate request, and they miss roughly 4 injections in ten.

The quit line does not rescue it either. Raising Jev's threshold from 0.5 to 0.9 moves
injection recall from 60.0% to only
66.3% on the 89 injections it still covers, while coverage falls, so the misses
move to a human rather than disappearing. That is a documented exception to this site's
own headline, and it stays on the page.
<!-- /generated:injection-classes -->

`results/error_profile.json` carries per-class recall and recall-at-gate for every row,
and the build refuses to publish a sentence quoting a rate it cannot find there.

### The Don't verdict does not survive a change of gold

Two rows, one decision, different labels:

<!-- generated:hate-vs-civil -->
|  | TweetEval hate | Civil Comments (CC0) |
|---|---|---|
| Jev | 66.2% | 78.0% |
| 4o-mini | 74.0% | 77.0% |
| McNemar | Mini wins, Holm p=0.0258 | ns, Holm p=1 |
| ECE | 0.187 | 0.075 |

On TweetEval, Mini wins by 7.8 points and Jev's
confidence is too badly calibrated to gate on. On CC0 gold for the same judgement the
models tie and the confidence becomes usable. So the Don't was mostly a fact about that
dataset. Both rows stay up: deleting the inconvenient one would be the opposite of the
point.
<!-- /generated:hate-vs-civil -->

<!-- generated:cfpb-cost -->
**Consumer complaint routing is the only production decision here.** The CFPB runs it
live, the consumer writes the narrative and picks the product, and the complaint is
routed to the company on that basis. Its narratives are the longest on the board and clear the
cost crossover: at about 1,157 characters per narrative, roughly 289 tokens, Jev costs
$33.89 per million decisions against $53.21
for 4o-mini. Text comes from a CC0 mirror; the gold label is joined from the Bureau's
own export on Complaint ID, and 31,990 of 32,000 candidate rows agreed with zero
disagreements. Product is chosen by the person filing, not an expert annotator.
<!-- /generated:cfpb-cost -->

<!-- generated:tfidf-table -->
**TF-IDF + logistic regression** on the official train leftover, never touching the
frozen samples (`scripts/run_tfidf_baseline.py`). Both columns Holm-corrected within
their family of 11:

| Decision | TF-IDF | vs Jev | vs Mini |
|---|---|---|---|
| Prompt-injection screen | 85.7% | ns | ns |
| Consumer complaint routing | 86.8% | ns | TF-IDF wins |
| Comment toxicity gate | 82.8% | ns | ns |
| SMS spam gate | 96.4% | ns | ns |
| Review polarity | 82.6% | Jev wins | Mini wins |
| Message emotion | 64.2% | Jev wins | Mini wins |
| Offensive language screen | 73.8% | ns | ns |
| Social sentiment (3-way) | 63.8% | Jev wins | Mini wins |
| News topic | 90.8% | TF-IDF wins | TF-IDF wins |
| Banking queue routing | 93.2% | TF-IDF wins | TF-IDF wins |
| Hate-speech screen | 54.0% | Jev wins | Mini wins |

If you have labels, skip both APIs on news topic, banking queue routing. Predicts in microseconds for $0.
<!-- /generated:tfidf-table -->

**Calibration** is measured by `scripts/calibrate.py`. The two highest-ECE rows in the
table above are the ones not to auto-route on confidence.

## Cost depends on input length, and that is the whole story

<!-- generated:cost-curve -->
Jev bills about **278 input tokens before your content**,
then charges 3.6x less per token than 4o-mini and nothing for output. So the question
is not which model is cheaper, it is how long your input is
(`scripts/cost_curve.py`, 3 calls per point, same document to both):

| Content tokens | Mini prompt tokens | of which cached | Jev $/1M | 4o-mini $/1M | Cheaper |
|---|---|---|---|---|---|
| 0 | 41 | 0 | $11.68 | $9.15 | mini |
| 23 | 64 | 0 | $12.73 | $12.65 | mini |
| 46 | 87 | 0 | $13.69 | $16.1 | jev |
| 87 | 128 | 0 | $15.57 | $22.2 | jev |
| 174 | 215 | 0 | $19.52 | $35.3 | jev |
| 336 | 377 | 0 | $26.77 | $59.55 | jev |
| 685 | 726 | 0 | $42.14 | $111.9 | jev |
| 1361 | 1402 | 0 | $72.45 | $213.35 | jev |
| 2743 | 2784 | 1323 | $133.97 | $321.35 | jev |

Crossover: Jev becomes the cheaper option above roughly **24 tokens of actual input**, about 96 characters. That is after removing the ~41-token system prompt 4o-mini adds to every call; an earlier version of this page counted that prompt as content and reported 65. Mini prompt tokens the API reports as cached are priced at the cached rate ($0.075/M); only the longest point had any. Measured on the rows themselves, Jev is the cheaper API on **4 of 11**: prompt-injection screen, consumer complaint routing, comment toxicity gate, news topic. The short-text rows go to Mini. Receipts in `results/receipts/cost_curve.json`.
<!-- /generated:cost-curve -->

<!-- generated:latency -->
**Latency** p50 was 807ms Jev against
1057ms Mini on SMS in this run, including client
round-trip.
<!-- /generated:latency -->
An earlier run from a different network measured 193ms against 518ms. The
ratio moves with where you measure from, so `results/manifest.json` records the
machine and `WHICHJUDGE_REGION`. Treat any latency claim, including this one, as
local to its client.

## What these numbers do not mean

Read the table with these limits in mind. Each was raised by an outside review; the ones
that could be measured have been. This list, like every table above, is generated from
`results/` by `scripts/build_site.py`, and `--check` fails in CI when it drifts.

<!-- generated:limits -->
- **Balanced samples, not production mix.** Every task is sampled with equal counts per
  label. That makes accuracy comparable across models but it is not the share of each
  label in real traffic, so a gate's coverage and accuracy here will not be the ones you
  see in production. A spam gate at 50% spam behaves differently from one at 3%.
- **Some frozen rows repeat a text.** Rows whose text already appears earlier in the same
  sample: consumer complaint routing 1, offensive language screen 11, message emotion 1, sms spam gate 18. SMS spam and CFPB duplicates are in the source data. 7 of the offensive rows and 1 of the emotion rows
  were drawn twice by a top-up bug in `prepare_samples.py` (it dropped the wrong index
  before refilling an unbalanced label; fixed, see `results/code_patches.json`). The
  frozen samples and receipts are kept as run; a re-run on a corrected sample would move
  those two rows by at most 1.4pt and 0.2pt.
- **The auto-slice gate is chosen and scored on the same rows.** That flatters it in
  principle. Measured: choosing the gate on one half and scoring it on the other, over
  400 random splits, moves the result by at most 0.5pt on any row, because there
  are only five candidate gates and the pick is stable. `results/gates.json` carries both
  numbers.
- **11 comparisons at once.** Significance is Holm-corrected within each comparison
  family. 2 row(s) that looked like wins for Jev over 4o-mini (offensive language screen, news topic) do not survive the correction and are shown as ties.
- **Gating and calibration use one score.** An earlier version thresholded on Jev's
  `confidence` while computing ECE on `p_chosen`; they differ on hundreds of rows.
  Both now use `p_chosen`.
- **Rows come from 4 invocations of `run_eval.py`.** Tasks were added one at a
  time, so the table is not one run. Each row's receipts carry their own timestamps and the
  site shows which invocation a row came from.
- **Public gold.** Nine of eleven rows are academic benchmarks. Only CFPB routing uses
  a live system's own labels, and those are chosen by the person filing, not an expert.
<!-- /generated:limits -->

## Provenance - four layers

1. **Frozen inputs.** `data/*.jsonl` (seed=7, n=500 per task except prompt injection at n=300) and `schemas/*.json`. SHA-256 in `results/manifest.json`. Seven of the eleven tasks ship a SHA-256 of each text instead of the text, because their terms either favour sharing ids or declare no licence at all; `scripts/rehydrate.py` restores and re-checks it. See `ATTRIBUTION.md`.
2. **Per-call receipts.** `results/receipts/<task>.json` (full JSON). `site/receipts/` is a slimmer copy for the UI. Open a row, then open that task's receipts.
3. **Don't stays on the homepage.** Hate-speech: Mini wins by 7.8 points, and the row is kept in full view.
4. **Re-run / recount.** No API: `python3 scripts/verify_run.py` (must print ALL CHECKS PASSED).
   It recomputes accuracy, Wilson intervals, McNemar, costs, latency percentiles, the
   confidence gates, ECE and reliability bins, the p_chosen gates and their
   cross-validation, the per-class error profile, the TF-IDF and current-model columns
   and the cost curve from the receipts, and prints what it did not recompute.
   Scripts patched after the run are listed in `results/code_patches.json` with their
   before and after hashes, and the verifier prints them. `data/`, `schemas/` and
   `results/receipts/` are never in that list: any drift there is a hard failure. Independent bake-off: `python3 scripts/run_eval.py` with your keys, then diff `results/summary.json`.

APIs do not cryptographically sign responses. Receipts stop silent edits of the summary table. They do not prove a third party issued the JSON - only a re-run does.

Eleven rows, of which one rests on a live system's own labels and one on real
user text with research labels. The other nine are academic benchmarks. That is
stated per row on the site, and it is still not a procurement study.

---

## Full pipeline, in order

```bash
python3 scripts/run_eval.py          # hits both APIs, writes receipts     (~$0.12)
python3 scripts/calibrate.py         # ECE + per-class error profile        (no API)
python3 scripts/run_tfidf_baseline.py  # classical baseline                (no API)
python3 scripts/run_modern_baseline.py # current small model column         (~$0.30)
python3 scripts/cost_curve.py        # cost vs length                      (~$0.01)
python3 scripts/redact_text.py       # strip tweet text before committing  (no API)
python3 scripts/build_site.py        # regenerate site and README numbers  (no API)
python3 scripts/verify_run.py        # recompute everything; ALL CHECKS PASSED (no API)
python3 scripts/audit_site.py        # leaks, stale numbers, uncited columns (no API)
```

Set `WHICHJUDGE_REGION` before `run_eval.py` so the latency numbers are attributable.

To check the text-dependent hashes on the seven redacted tasks, run
`python3 scripts/rehydrate.py` first: it re-downloads the upstream split, matches rows
by hash, and refuses to write anything if the revision has moved.

## Ship the site

`site/` is static. No build step.

```bash
# local
python3 -m http.server 8080 --directory site

# GitHub Pages / Cloudflare Pages / Vercel: set root to site/
```

Numbers are **generated**, never copied. `site/data.js`, the per-decision pages,
`sitemap.xml`, `robots.txt` and every table in this README come from
`scripts/build_site.py`:

```bash
python3 scripts/build_site.py           # regenerate after any re-run
python3 scripts/build_site.py --check   # CI gate: fails if the site drifts from results/
```

Editorial wording lives in `site/copy.json`. Measurements live in `results/`. The
build also refuses to run if `copy.json` claims a verdict is `ns` when McNemar
disagrees.

Deployment is GitHub Pages from this repo. CI will not publish a site whose table
fails `verify_run.py` or drifts from `results/`.

---
