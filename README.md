# whichjudge.dev

Replacement matrix for cheap **judge / decision** models.

Rows are decisions you already pay an LLM to make (spam gate, ticket route, hate screen).
Columns are models. First bake-off: **Jev `jev-1.13.0`** vs **`gpt-4o-mini`**.
The next System One–style model is another column, not another site.

**Calibration (ECE on p_chosen, 10 bins, n=500):** SMS 0.013, reviews 0.019, emotion 0.084, news 0.091, offensive 0.113, sentiment 0.146, hate 0.188, banking 0.215. Quit line ≥0.7 is honest on SMS/reviews; banking's 0.9-bin is 99% confident and 80% accurate — do not auto-route there.

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
    prepare_samples.py      build data/*.jsonl (seed=7, n=500)
    run_eval.py             Jev vs gpt-4o-mini; writes hashed receipts
    verify_run.py           recount accuracy; check SHA-256 (no API)
    run_tfidf_baseline.py   TF-IDF + LR on leftover official train
    calibrate.py            ECE + reliability bins from receipts (no API)
    cost_curve.py           cost and latency vs input length; finds the crossover
    redact_text.py          strip third-party text to hashes before publishing
    rehydrate.py            restore that text from upstream, hash-checked
    build_site.py           GENERATE site from results/ (--check gates CI)
  data/                     FROZEN n=500 samples + meta
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

Before any public launch, read `ATTRIBUTION.md`: four of the eight tasks are tweet
text, and redistributing that from this repo is not automatically cleared.

`data/*.jsonl` is the source of truth for which 500 examples.
`results/*.json` is the first run’s parsed predictions.
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
python3 scripts/run_eval.py                 # all 8 tasks
python3 scripts/run_eval.py sms_spam        # one task
```

Jev: `POST https://api.typesafe.ai/v1/systemone` with `model: jev-latest` (resolved to `jev-1.13.0` on 2026-09-20).
Mini: `POST https://api.openai.com/v1/chat/completions`, `temperature: 0`, `response_format: json_object`.

Cost of an 8-task n=500 run is about **$0.12** total (Jev ~$0.006, Mini ~$0.005). Output tokens on Jev are free; Mini is $0.15 / $0.60 per million in/out.

### Rebuild samples (optional)

```bash
python3 scripts/download_raw.py
python3 scripts/prepare_samples.py
```

Sampling: `random_state=7`, `N=500`, balanced across labels.
BANKING77 is collapsed from 77 fine intents → 8 queues by keyword (see `coarse_banking()`). That gold is noisy; the Mix verdict on that row is not a production bake-off.

---

## Results, n=500 per task, seed 7

Wilson 95% CI. McNemar on paired errors. `ns` = p >= 0.05, meaning the accuracy gap
is noise and neither model should be crowned.

| Decision | n | Jev | Mini | McNemar | ECE | Verdict |
|---|---|---|---|---|---|---|
| SMS spam gate | 500 | 96.4% [94.4%-97.7%] | 96.4% | ns p=0.773 | 0.016 | ns |
| Review polarity | 500 | 97.0% [95.1%-98.2%] | 96.4% | ns p=0.546 | 0.015 | ns |
| Message emotion | 500 | 79.8% [76.1%-83.1%] | 75.0% | jev p=0.00528 | 0.083 | Replace |
| Offensive language screen | 500 | 76.6% [72.7%-80.1%] | 70.8% | jev p=0.00787 | 0.110 | Replace |
| Social sentiment (3-way) | 500 | 73.8% [69.8%-77.5%] | 72.6% | ns p=0.576 | 0.141 | ns |
| News topic | 500 | 85.6% [82.3%-88.4%] | 82.6% | jev p=0.00933 | 0.096 | Replace |
| Banking queue routing | 500 | 71.8% [67.7%-75.6%] | 64.4% | jev p=3.23e-05 | 0.213 | Replace |
| Hate-speech screen | 500 | 66.2% [61.9%-70.2%] | 74.0% | mini p=0.00258 | 0.187 | Don't |

**TF-IDF + logistic regression** on the official train leftover, never touching the
frozen 500 (`scripts/run_tfidf_baseline.py`):

| Decision | TF-IDF | vs Jev | vs Mini |
|---|---|---|---|
| SMS spam gate | 96.4% | ns | ns |
| Review polarity | 82.6% | Jev wins | Mini wins |
| Message emotion | 64.2% | Jev wins | Mini wins |
| Offensive language screen | 73.8% | ns | ns |
| Social sentiment (3-way) | 63.8% | Jev wins | Mini wins |
| News topic | 90.8% | TF-IDF wins | TF-IDF wins |
| Banking queue routing | 93.2% | TF-IDF wins | TF-IDF wins |
| Hate-speech screen | 54.0% | Jev wins | Mini wins |

If you have labels, skip both APIs on banking routing and news topic. Predicts in
microseconds for $0.

**Calibration** decides whether a confidence threshold means anything
(`scripts/calibrate.py`). Low ECE tasks can carry a quit line; high ECE tasks cannot.
Banking is 0.213 and hate is
0.187: do not auto-route on confidence there.

## Cost depends on input length, and that is the whole story

Jev bills about **278 input tokens before your content**,
then charges 3.6x less per token than 4o-mini and nothing for output. So the question
is not which model is cheaper, it is how long your input is
(`scripts/cost_curve.py`, 3 calls per point, same document to both):

| Content tokens | Jev $/1M | 4o-mini $/1M | Cheaper |
|---|---|---|---|
| 41 | $11.68 | $9.15 | mini |
| 64 | $12.73 | $12.65 | mini |
| 87 | $13.69 | $16.1 | jev |
| 128 | $15.57 | $22.2 | jev |
| 215 | $19.52 | $35.3 | jev |
| 377 | $26.77 | $59.55 | jev |
| 726 | $42.14 | $111.9 | jev |
| 1402 | $72.45 | $213.35 | jev |
| 2784 | $133.97 | $420.55 | jev |

Crossover: Jev becomes the cheaper option above roughly
**65 tokens** of content, about
260 characters. Every task in the table above sits
below that line, which is why Jev looks expensive on this board and would not on
document-length work. Measured, not modelled; receipts in
`results/receipts/cost_curve.json`.

**Latency** p50 was 807ms Jev against
1057ms Mini on SMS in this run, including client
round-trip. An earlier run from a different network measured 193ms against 518ms. The
ratio moves with where you measure from, so `results/manifest.json` records the
machine and `WHICHJUDGE_REGION`. Treat any latency claim, including this one, as
local to its client.

## Provenance — four layers

1. **Frozen inputs.** `data/*.jsonl` (seed=7, n=500) and `schemas/*.json`. SHA-256 in `results/manifest.json`. The four TweetEval tasks ship a SHA-256 of each text instead of the text; `scripts/rehydrate.py` restores and re-checks it. See `ATTRIBUTION.md`.
2. **Per-call receipts.** `results/receipts/<task>.json` (full JSON). `site/receipts/` is a slimmer copy for the UI. Open a row → Open 500 receipts.
3. **Don't stays on the homepage.** Hate-speech: Mini wins by 7.8 points, and the row is kept in full view.
4. **Re-run / recount.** No API: `python3 scripts/verify_run.py` (must print ALL CHECKS PASSED).
   Scripts patched after the run are listed in `results/code_patches.json` with their
   before and after hashes, and the verifier prints them. `data/`, `schemas/` and
   `results/receipts/` are never in that list: any drift there is a hard failure. Independent bake-off: `python3 scripts/run_eval.py` with your keys, then diff `results/summary.json`.

APIs do not cryptographically sign responses. Receipts stop silent edits of the summary table. They do not prove a third party issued the JSON — only a re-run does.

n=500 on public academic gold is still not a procurement study.

---

## Full pipeline, in order

```bash
python3 scripts/run_eval.py          # hits both APIs, writes receipts     (~$0.12)
python3 scripts/calibrate.py         # ECE from those receipts             (no API)
python3 scripts/run_tfidf_baseline.py  # classical baseline                (no API)
python3 scripts/cost_curve.py        # cost vs length                      (~$0.01)
python3 scripts/redact_text.py       # strip tweet text before committing  (no API)
python3 scripts/build_site.py        # regenerate every published number   (no API)
python3 scripts/verify_run.py        # must print ALL CHECKS PASSED        (no API)
```

Set `WHICHJUDGE_REGION` before `run_eval.py` so the latency numbers are attributable.

To check the text-dependent hashes on the four redacted tasks, run
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
`sitemap.xml` and `robots.txt` all come from `scripts/build_site.py`:

```bash
python3 scripts/build_site.py           # regenerate after any re-run
python3 scripts/build_site.py --check   # CI gate: fails if the site drifts from results/
```

Editorial wording lives in `site/copy.json`. Measurements live in `results/`. The
build also refuses to run if `copy.json` claims a verdict is `ns` when McNemar
disagrees.

Deployment is GitHub Pages from this repo. CI will not publish a site whose table
fails `verify_run.py` or drifts from `results/`.
