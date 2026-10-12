# New columns: OpenAI Decisions (gpt-6-luna) and Cloudflare clef

Status (2026-10-08): Decisions and clef are measured, verified AND rendered locally in site/, README.md and copy.json by build_site.py. Nothing is committed, pushed or deployed. clef-flash is not run (Cloudflare free quota); when results/clef-flash_baseline.json exists, build_site.py renders it with no code change.
Vendor prices were read off the vendor pages on 2026-10-08 (sources recorded in the result files and shown on the site).
Regenerate these tables any time with `python3 scripts/build_site.py --new-columns` (Holm per comparison family of 11, same `holm()` as the other columns).

## What was added

- scripts/run_decisions_baseline.py: shared engine plus the Decisions entry point.
- scripts/run_clef_baseline.py: thin entry point (`--flash` selects clef-flash).
- Requests are generated from the same schema rubric Jev gets (instructions plus every label's criteria). Decisions: one `choice` question. clef: the exact `{state, questions}` body Jev receives.
- Outputs: results/decisions_baseline.json, results/clef_baseline.json, results/receipts/<task>.decisions.json and <task>.clef.json. Checkpoints go to `*.partial.jsonl` (already gitignored).
- calibrate.py now writes ECE and error profile for the new columns (existing entries byte-identical). verify_run.py, selfcheck_verify.py (4 new corruptions) and audit_site.py cover them. build_site.py reads calibration and error_profile through `published_view()` so the site and its fingerprint are unchanged until you publish.
- results/code_patches.json: verify_run.py entry updated (it is a manifest-tracked file).
- Note: the bench has 11 tasks, not 8.

## Cost of the full runs

Decisions $0.1115 (0.10 USD per M input, output not billed). clef $0.3104 (0.24 USD per M input). Prices were supplied to me and stored in the result files with a note; re-check the vendor pages before publishing a cost.

## Headline (n per task as in the bench; Holm-corrected McNemar)

Decisions vs Jev: 0 wins, 9 ties, 2 losses (prompt_injection 72.0 vs 80.5, content_hate 57.6 vs 65.6). Vs 4o-mini: wins cfpb (83.0 vs 77.4), loses content_hate.
clef vs Jev: 2 wins (civil_toxicity 86.0 vs 76.8, banking 76.2 vs 70.2), 8 ties, 1 loss (tweet_sentiment 63.2 vs 73.2). Vs 4o-mini: wins civil, cfpb, banking, news; loses tweet and content_hate.

### decisions (gpt-6-luna), total $0.1115

| task | n | decisions | Jev | 4o-mini | vs Jev (Holm) | vs 4o-mini (Holm) | ECE | p50 ms |
|---|---|---|---|---|---|---|---|---|
| prompt_injection | 200 | 72.0% | 80.5% | 74.5% | Jev | ns | 0.245 | 814 |
| civil_toxicity | 500 | 72.6% | 76.8% | 72.4% | ns | ns | 0.169 | 903 |
| cfpb_queue_route | 500 | 83.0% | 83.8% | 77.4% | ns | decisions | 0.112 | 802 |
| banking_coarse_route | 500 | 70.2% | 70.2% | 66.4% | ns | ns | 0.104 | 1316 |
| news_topic | 500 | 88.4% | 89.8% | 86.0% | ns | ns | 0.076 | 1161 |
| tweet_sentiment | 500 | 69.8% | 73.2% | 71.4% | ns | ns | 0.208 | 966 |
| review_sentiment | 356 | 93.8% | 96.3% | 95.5% | ns | ns | 0.032 | 1339 |
| sms_spam | 500 | 94.8% | 95.4% | 94.6% | ns | ns | 0.024 | 1305 |
| content_offensive | 500 | 68.4% | 72.6% | 72.2% | ns | ns | 0.232 | 1191 |
| content_hate | 500 | 57.6% | 65.6% | 72.4% | Jev | 4o-mini | 0.372 | 885 |
| message_emotion | 500 | 75.6% | 78.2% | 76.2% | ns | ns | 0.108 | 855 |

### clef (@cf/cloudflare/clef), total $0.3104

| task | n | clef | Jev | 4o-mini | vs Jev (Holm) | vs 4o-mini (Holm) | ECE | p50 ms |
|---|---|---|---|---|---|---|---|---|
| prompt_injection | 200 | 79.0% | 80.5% | 74.5% | ns | ns | 0.167 | 966 |
| civil_toxicity | 500 | 86.0% | 76.8% | 72.4% | clef | clef | 0.037 | 1167 |
| cfpb_queue_route | 500 | 82.2% | 83.8% | 77.4% | ns | clef | 0.078 | 1429 |
| banking_coarse_route | 500 | 76.2% | 70.2% | 66.4% | clef | clef | 0.091 | 1152 |
| news_topic | 500 | 91.2% | 89.8% | 86.0% | ns | clef | 0.022 | 1233 |
| tweet_sentiment | 500 | 63.2% | 73.2% | 71.4% | Jev | 4o-mini | 0.197 | 1074 |
| review_sentiment | 356 | 96.9% | 96.3% | 95.5% | ns | ns | 0.013 | 941 |
| sms_spam | 500 | 93.4% | 95.4% | 94.6% | ns | ns | 0.017 | 893 |
| content_offensive | 500 | 77.0% | 72.6% | 72.2% | ns | ns | 0.152 | 850 |
| content_hate | 500 | 61.6% | 65.6% | 72.4% | ns | 4o-mini | 0.281 | 826 |
| message_emotion | 500 | 78.4% | 78.2% | 76.2% | ns | ns | 0.029 | 770 |

## clef-flash: NOT run

Cloudflare returned HTTP 429 "daily free allocation of 10,000 neurons" after the clef run (clef itself had a few transient 529s, retried). Needs the Workers Paid plan or a next-day retry (`python3 scripts/run_clef_baseline.py --flash`, about $0.1 expected). Partial flash files were deleted; the code path is tested by a dry run only.

## Site changes this publish prep makes (for review before any push)

- New stat cards "vs gpt-6-luna" (Jev 2 wins, 9 ties, 0 losses) and "vs clef" (Jev 1 win, 8 ties, 2 losses), new table columns, phone-card lines, modal rows, a How-to-read entry with prices, source URLs and date.
- Decision page titles change from "Jev vs 4 other models" to "Jev vs 6 other models" (plus rows with price and date); the site description gains "vs gpt-6-luna vs clef".
- Decision pages for civil toxicity and banking gain a note "clef beats Jev here" (Holm-corrected).
- Five copy.json sentences edited: civil why and rowNote (clef beats Jev at 86.0%), banking why and rowNote (clef beats Jev at 76.2%), news gate ("Among APIs Jev 89.8% ties clef 91.2% after correction", replacing "Jev first among APIs", which clef's higher raw score made misleading).
- No Replace/Mix/Dont verdict, ns flag or "TF-IDF wins" card changed (they depend on Jev vs Mini and TF-IDF vs Jev only).
- Latency of the new columns is shown only as "one client, region unset, includes network".
