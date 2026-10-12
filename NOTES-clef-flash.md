# clef-flash column (2026-10-09)

Run: all 11 tasks finished in one pass (Cloudflare free quota had reset), cost $0.1164 (0.09 USD per 1M input tokens), no quota error part-way. Receipts: results/receipts/<task>.clef-flash.json; stats: results/clef-flash_baseline.json. Rendered by build_site.py because the file now exists; no code change was needed.

Prices re-read from the vendors' own pages on 2026-10-09 and stored in the result files, README and every decision page: Cloudflare clef $0.240 and clef-flash $0.090 per 1M input tokens (https://developers.cloudflare.com/workers-ai/platform/pricing/), OpenAI gpt-6-luna Standard short-context input $0.10 per 1M (https://developers.openai.com/api/docs/pricing; the page lists the model, not the Decisions API separately). Latency is shown only as "one client, region unset, includes network".

## clef-flash vs Jev (Holm-corrected, 11 tests)
Jev wins 4: prompt_injection 68.0 vs 80.5, cfpb 77.0 vs 83.8, tweet_sentiment 59.6 vs 73.2, sms_spam 90.4 vs 95.4. clef-flash wins 2: civil_toxicity 85.4 vs 76.8, banking 81.4 vs 70.2. Ties 5: news 91.2 vs 89.8, review 96.6 vs 96.3, offensive 75.2 vs 72.6, hate 60.8 vs 65.6, emotion 76.4 vs 78.2.
vs 4o-mini: wins civil, banking, news; loses prompt_injection, tweet, sms, hate.

## What changed on the built site since the two-column version
- New card "vs clef-flash": Jev 4W 5T 2L. Cards for gpt-6-luna (2W 9T 0L) and clef (1W 8T 2L) unchanged.
- New clef-flash column in the table, phone cards, modal, How-to-read entry (price, source, date), decision-page row, README table and paragraph.
- Decision page titles: "Jev vs 6 other models" becomes "Jev vs 7 other models"; the site description now ends "vs gpt-6-luna vs clef vs clef-flash".
- Decision pages for civil toxicity and banking gain a second note "clef-flash beats Jev here".
- copy.json, civil_toxicity: why and rowNote now also say clef-flash beats Jev at 85.4%.
- copy.json, banking_coarse_route: why now says clef beats Jev at 76.2% and clef-flash beats Jev at 81.4%, both trailing TF-IDF; rowNote adds clef-flash at 81.4%.
- copy.json, news_topic gate: "Among APIs Jev 89.8% ties clef and clef-flash, both 91.2%, after correction".
- Price date on all three columns is now 2026-10-09 (was 2026-10-08).
- No Replace/Mix/Don't verdict, ns flag or TF-IDF-wins card changed.
