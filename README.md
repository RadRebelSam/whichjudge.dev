# whichjudge.dev

Replacement matrix for cheap **judge / decision** models.

Rows are decisions you already pay an LLM to make (spam gate, ticket route, hate screen).
Columns are models: **Jev `jev-1.13.0`**, **`gpt-4o-mini-2024-07-18`**, **`gpt-5.4-mini-2026-03-17`** and a TF-IDF + logistic regression baseline.
The next System One-style model is another column, not another site.

<!-- generated:ece-line -->
**Calibration (ECE on p_chosen, 10 bins, `scripts/calibrate.py`):** sms spam gate 0.015, review polarity 0.030, news topic 0.068, consumer complaint routing 0.094, message emotion 0.100, comment toxicity gate 0.101, prompt-injection screen 0.137, offensive language screen 0.151, social sentiment (3-way) 0.157, hate-speech screen 0.196, banking queue routing 0.232. Low ECE means the number may be quoted as a probability. Whether a threshold is safe is a separate question, answered per class in the gate tables below, not by ECE.
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
    prepare_samples.py      build the academic data/*.jsonl (seed=11, n=500, v1 rows excluded)
    sampling_common.py      the v1-exclusion rule every preparer applies
    run_eval.py             Jev vs gpt-4o-mini; writes hashed receipts
    verify_run.py           re-read every raw response, recompute every statistic (no API)
    selfcheck_verify.py     corrupt a copy six ways; verify_run.py must fail each time
    smoke_site.py           headless browser: overflow at 390px, axe violations, dialog focus
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
  data/                     FROZEN v2 samples + meta (n=500, injection n=200)
  data/previous_samples.json  hashes of every v1 text, excluded from the v2 draw
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

## Two runs: v1 and the normalized v2

The first published run (git tag `v1-config-comparison`, commit `8542e66`) gave Jev a
criteria sentence per label and gave the OpenAI models the label names only. An outside
review pointed out that this compares two amounts of task information, not two models.
Everything below is the v2 run: both prompt formats generated from one rubric per task
(`openai_prompt_from()` in `scripts/run_eval.py`), scored on fresh samples that exclude
every v1 row. The v1 numbers, receipts and site are intact at that tag.

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
python3 scripts/rehydrate.py                # seven tasks ship hashes; this restores their text
python3 scripts/run_eval.py                 # every task (preflights all text before any call)
python3 scripts/run_eval.py sms_spam        # one task
```

Jev: `POST https://api.typesafe.ai/v1/systemone` with `model: jev-latest` (resolved to `jev-1.13.0` on 2026-09-20).
Mini: `POST https://api.openai.com/v1/chat/completions`, `temperature: 0`, `response_format: json_object`.

A full run of the two main arms across every task was **$0.24** at list price for v2 (the
normalized prompt makes every Mini call longer). The current-model column used about
0.87M tokens; its price is left unset. Output tokens on Jev are free; Mini is $0.15 / $0.60
per million in/out.

### Rebuild samples (optional)

```bash
python3 scripts/download_raw.py
python3 scripts/prepare_samples.py
```

Sampling: `random_state=11`, `N=500`, balanced across labels, exact duplicate texts
collapsed, and every text the v1 samples used excluded (`data/previous_samples.json`).
BANKING77 is collapsed from 77 fine intents → 8 queues by keyword (see `coarse_banking()`). That gold is noisy; the Mix verdict on that row is not a production bake-off.

---

<!-- generated:main-table -->
## Results, seed 11, n=500 per task except prompt-injection screen (n=200), review polarity (n=356)

Wilson 95% CI. McNemar on paired errors, Holm-corrected across the 11 Jev-vs-Mini
tests. `ns` = Holm p >= 0.05: insufficient evidence of a difference at this n. It does not
say the two are equal, only that neither may be crowned on this sample. No row changes verdict under the correction.

| Decision | n | Jev | Mini | McNemar | ECE | Verdict |
|---|---|---|---|---|---|---|
| Prompt-injection screen | 200 | 80.5% [74.5%-85.4%] | 74.5% | jev raw p=0.00596, Holm p=0.0358 | 0.137 | Neither |
| Consumer complaint routing | 500 | 83.8% [80.3%-86.8%] | 77.4% | jev raw p=1.72e-05, Holm p=0.000189 | 0.094 | Replace |
| Comment toxicity gate | 500 | 76.8% [72.9%-80.3%] | 72.4% | jev raw p=0.00501, Holm p=0.0351 | 0.101 | Replace |
| SMS spam gate | 500 | 95.4% [93.2%-96.9%] | 94.6% | ns raw p=0.48, Holm p=1 | 0.015 | ns |
| Review polarity | 356 | 96.3% [93.9%-97.9%] | 95.5% | ns raw p=0.546, Holm p=1 | 0.030 | ns |
| Message emotion | 500 | 78.2% [74.4%-81.6%] | 76.2% | ns raw p=0.229, Holm p=1 | 0.100 | ns |
| Offensive language screen | 500 | 72.6% [68.5%-76.3%] | 72.2% | ns raw p=0.901, Holm p=1 | 0.151 | ns |
| Social sentiment (3-way) | 500 | 73.2% [69.2%-76.9%] | 71.4% | ns raw p=0.349, Holm p=1 | 0.157 | ns |
| News topic | 500 | 89.8% [86.8%-92.2%] | 86.0% | jev raw p=0.00308, Holm p=0.0247 | 0.068 | Replace |
| Banking queue routing | 500 | 70.2% [66.0%-74.0%] | 66.4% | jev raw p=0.00235, Holm p=0.0211 | 0.232 | Replace |
| Hate-speech screen | 500 | 65.6% [61.3%-69.6%] | 72.4% | mini raw p=0.000187, Holm p=0.00187 | 0.196 | Don't |
<!-- /generated:main-table -->

## Is Jev only beating a 2024 baseline?

<!-- generated:modern-table -->
Fair objection, so here is a current small model on the same frozen samples with the
same prompts (`scripts/run_modern_baseline.py`, model `gpt-5.4-mini-2026-03-17`). Both `vs` columns are
Holm-corrected within their own family of 11 tests:

| Decision | Jev | 4o-mini (2024) | gpt-5.4-mini (2026) | vs Jev | vs 4o-mini |
|---|---|---|---|---|---|
| Prompt-injection screen | 80.5% | 74.5% | 80.0% | ns | ns |
| Consumer complaint routing | 83.8% | 77.4% | 83.8% | ns | **gpt-5.4-mini** |
| Comment toxicity gate | 76.8% | 72.4% | 75.6% | ns | ns |
| SMS spam gate | 95.4% | 94.6% | 93.0% | ns | ns |
| Review polarity | 96.3% | 95.5% | 97.2% | ns | ns |
| Message emotion | 78.2% | 76.2% | 76.2% | ns | ns |
| Offensive language screen | 72.6% | 72.2% | 73.6% | ns | ns |
| Social sentiment (3-way) | 73.2% | 71.4% | 71.0% | ns | ns |
| News topic | 89.8% | 86.0% | 86.8% | ns | ns |
| Banking queue routing | 70.2% | 66.4% | 72.4% | ns | **gpt-5.4-mini** |
| Hate-speech screen | 65.6% | 72.4% | 64.2% | ns | 4o-mini |

**Jev 0 wins, 11 ties, 0 losses** against a model two years newer. 3 row(s) that beat it at the raw 0.05 (sms spam gate, news topic, banking queue routing) do not survive the correction.

Out-of-schema labels, counted as wrong and reported as such: message emotion 2 (fear, sarcasm).
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
| Decision | Gold | ECE | Auto slice (gate) | Lift vs ungated | Held-out acc on coverage | Halves under 50% |
|---|---|---|---|---|---|---|
| Prompt-injection screen | academic | 0.137 | 86.3% on 84.0% (>=0.9) | +5.8pt | 86.0% on 84.7% | 0/800 |
| Consumer complaint routing | live system | 0.094 | 92.1% on 78.6% (>=0.9) | +8.3pt | 92.1% on 78.6% | 0/800 |
| Comment toxicity gate | real text | 0.101 | 86.7% on 58.8% (>=0.9) | +9.9pt | 86.7% on 58.9% | 0/800 |
| SMS spam gate | academic | 0.015 | 98.6% on 86.0% (>=0.9) | +3.2pt | 98.4% on 86.8% | 0/800 |
| Review polarity | academic | 0.030 | 97.9% on 93.3% (>=0.8) | +1.5pt | 97.6% on 95.5% | 0/800 |
| Message emotion | academic | 0.100 | 88.8% on 64.2% (>=0.9) | +10.6pt | 88.8% on 64.2% | 0/800 |
| Offensive language screen | academic | 0.151 | 81.4% on 59.0% (>=0.9) | +8.8pt | 81.1% on 59.8% | 0/800 |
| Social sentiment (3-way) | academic | 0.157 | 79.8% on 61.4% (>=0.9) | +6.6pt | 79.3% on 64.0% | 0/800 |
| News topic | academic | 0.068 | 94.0% on 87.4% (>=0.9) | +4.2pt | 94.0% on 87.4% | 0/800 |
| Banking queue routing | academic | 0.232 | 79.0% on 80.2% (>=0.9) | +8.8pt | 79.0% on 80.2% | 0/800 |
| Hate-speech screen | academic | 0.196 | 78.9% on 53.0% (>=0.9) | +13.3pt | 78.6% on 54.2% | 58/800 |

Gating beats not gating on **11 of 11 rows** on this balanced sample; coverage here is benchmark coverage, not a forecast of production traffic. The held-out column chooses the gate on one random half and scores it on the other, 400 splits; the optimism of picking and scoring on the same rows is at most 0.5pt here. The 50% coverage rule is applied on the picking half, and the last column counts scoring halves that fell under it (most on hate-speech screen). Accepted-slice accuracy is one number; what a gate does to each class is in `results/error_profile.json` and, for the security row, in the next section.
<!-- /generated:gate-table -->

### Accuracy is the wrong number for a security gate

<!-- generated:injection-classes -->
The prompt-injection row looks fine on accuracy: Jev 80.5%,
Mini 74.5%, tied at raw p=0.00596.
Split it by class and the picture changes:

|  | Jev | 4o-mini |
|---|---|---|
| Injections caught | 61.0% | 49.0% |
| Injections missed | 39 of 100 | 51 of 100 |
| Legitimate text wrongly blocked | 0.0% | 0.0% |

Both models are biased hard toward letting text through. They almost never block a
legitimate request, and they miss roughly 4 injections in ten.

The quit line does not rescue it either. Raising Jev's threshold from 0.5 to 0.9 moves
injection recall from 61.0% to only
66.2% on the 68 injections it still covers, while coverage falls, so the misses
move to a human rather than disappearing. That is a documented exception to this site's
own headline, and it stays on the page.

In counts, at p_chosen >= 0.9: 168 of 200 rows are handled automatically; 23 of them are injections passed as legitimate, 23.0% of all 100 attacks in the sample; and 32 attacks fall below the threshold to whatever fallback the operator supplies. Accepted-slice accuracy does not show any of that.
<!-- /generated:injection-classes -->

`results/error_profile.json` carries per-class recall and recall-at-gate for every row,
and the build refuses to publish a sentence quoting a rate it cannot find there.

### Hate speech and toxicity: neighbouring tasks, different rankings

Two rows, related judgements, different task definitions and datasets:

<!-- generated:hate-vs-civil -->
|  | TweetEval hate | Civil Comments (CC0) |
|---|---|---|
| Jev | 65.6% | 76.8% |
| 4o-mini | 72.4% | 72.4% |
| McNemar | Mini wins, Holm p=0.00187 | Jev wins, Holm p=0.0351 |
| ECE | 0.196 | 0.101 |

On TweetEval, Mini wins by 6.8 points and Jev's
confidence is too badly calibrated to quote. On Civil Comments the models tie and the
confidence becomes usable. These are not the same decision with different labels: the
hate row asks for hate speech aimed at a protected group in tweets, the toxicity row asks
for rudeness or disrespect in comments, with different inputs, populations and prompts.
What the pair shows is that the ranking depends on the task and the dataset. It does not
show that the hate loss was label noise; isolating that would take the same examples
re-annotated under one rubric. Both rows stay up.
<!-- /generated:hate-vs-civil -->

<!-- generated:cfpb-cost -->
**Consumer complaint routing is the only production decision here.** The CFPB runs it
live, the consumer writes the narrative and picks the product, and the complaint is
routed to the company on that basis. Its narratives are the longest on the board and clear the
cost crossover: at about 1,113 characters per narrative, roughly 278 tokens, Jev costs
$33.42 per million decisions against $78.59
for 4o-mini. Text comes from a CC0 mirror; the gold label is joined from the Bureau's
own export on Complaint ID: 31,982 candidate rows agreed, 0 disagreed, 18 were not found. Product is chosen by the person filing, not an expert annotator.
<!-- /generated:cfpb-cost -->

<!-- generated:tfidf-table -->
**TF-IDF + logistic regression** on the official train leftover, never touching the
frozen samples (`scripts/run_tfidf_baseline.py`). Both columns Holm-corrected within
their family of 11:

| Decision | TF-IDF | vs Jev | vs Mini |
|---|---|---|---|
| Prompt-injection screen | 90.5% | TF-IDF wins | TF-IDF wins |
| Consumer complaint routing | 85.6% | ns | TF-IDF wins |
| Comment toxicity gate | 85.2% | TF-IDF wins | TF-IDF wins |
| SMS spam gate | 96.0% | ns | ns |
| Review polarity | 84.8% | Jev wins | Mini wins |
| Message emotion | 60.0% | Jev wins | Mini wins |
| Offensive language screen | 69.4% | ns | ns |
| Social sentiment (3-way) | 60.2% | Jev wins | Mini wins |
| News topic | 93.8% | TF-IDF wins | TF-IDF wins |
| Banking queue routing | 94.2% | TF-IDF wins | TF-IDF wins |
| Hate-speech screen | 53.4% | Jev wins | Mini wins |

If you have labels, skip both APIs on prompt-injection screen, comment toxicity gate, news topic, banking queue routing. Predicts in microseconds for $0.
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

Crossover: Jev becomes the cheaper option above roughly **24 tokens of actual input**, about 96 characters. That is after removing the ~41-token system prompt 4o-mini adds to every call; an earlier version of this page counted that prompt as content and reported 65. Mini prompt tokens the API reports as cached are priced at the cached rate ($0.075/M); only the longest point had any. Measured on the rows themselves, Jev is the cheaper API on **11 of 11**: prompt-injection screen, consumer complaint routing, comment toxicity gate, sms spam gate, review polarity, message emotion, offensive language screen, social sentiment (3-way), news topic, banking queue routing, hate-speech screen. Every row clears the crossover now: the normalized prompt gives Mini the label criteria Jev already carried, which lengthens Mini's input on every task. Receipts in `results/receipts/cost_curve.json`.
<!-- /generated:cost-curve -->

<!-- generated:latency -->
**Latency** p50 was 716ms Jev against
987ms Mini on SMS in this run, including client
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
- **No frozen row repeats a text.** Exact duplicates are collapsed before the draw and every
  v1 row is excluded, so each sample here is unique texts only. The v1 samples at tag
  `v1-config-comparison` carried source duplicates and 8 rows from a top-up bug since fixed.
- **The auto-slice gate is chosen and scored on the same rows.** That flatters it in
  principle. Measured: choosing the gate on one half and scoring it on the other, over
  400 random splits, moves the result by at most 0.5pt on any row, because there
  are only five candidate gates and the pick is stable. `results/gates.json` carries both
  numbers.
- **11 comparisons at once.** Significance is Holm-corrected within each comparison
  family. 
- **Gating and calibration use one score.** An earlier version thresholded on Jev's
  `confidence` while computing ECE on `p_chosen`; they differ on hundreds of rows.
  Both now use `p_chosen`.
- **Rows come from 1 invocations of `run_eval.py`.** Tasks were added one at a
  time, so the table is not one run. Each row's receipts carry their own timestamps and the
  site shows which invocation a row came from.
- **The two prompt formats do not carry the same information.** Jev's choice questions
  include a criteria sentence per label; the OpenAI prompt, reused for the 2026 model,
  lists the label names only. On routing rows that tells Jev which odd intents belong to
  `account` and Mini nothing. So this is a comparison of configurations, not of models
  alone, and the receipts cannot say how much of any gap the prompt difference caused.
  A normalized rerun would generate both formats from one rubric on a fresh sample.
- **Reruns checkpoint per row and log every attempt.** A request that exhausts its
  retries costs one request, not the task; the retry log of each call goes into its
  receipt. Receipts written before this change carry no attempt log. Published counts
  are complete: every arm answers every id exactly once, checked by `verify_run.py`.
- **Public gold.** Nine of eleven rows are academic benchmarks. Only CFPB routing uses
  a live system's own labels, and those are chosen by the person filing, not an expert.
<!-- /generated:limits -->

## Provenance - four layers

1. **Frozen inputs.** `data/*.jsonl` (seed=11, n=500 per task except prompt injection at n=200, every v1 row excluded) and `schemas/*.json`. SHA-256 in `results/manifest.json`. Seven of the eleven tasks ship a SHA-256 of each text instead of the text, because their terms either favour sharing ids or declare no licence at all; `scripts/rehydrate.py` restores and re-checks it. See `ATTRIBUTION.md`.
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
python3 scripts/selfcheck_verify.py  # prove the verifier fails on corrupted results (no API)
python3 scripts/smoke_site.py        # headless browser: 390px overflow, axe, dialog focus
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
