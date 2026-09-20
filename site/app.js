// RUN and TASKS are generated into site/data.js by scripts/build_site.py.
// Edit site/copy.json for wording; numbers only change by re-running the eval.

const FILTERS = [
  { id: "all", label: `All ${TASKS.length}` },
  { id: "replace", label: "Replace" },
  { id: "mix", label: "Mix" },
  { id: "dont", label: "Don't" },
];

const receiptCache = {};
let receiptOpenId = null;
let sampleOpen = null;

function pct(n) {
  return (n * 100).toFixed(n >= 0.995 ? 0 : 1) + "%";
}

function usd(n) {
  const sign = n < 0 ? "-" : "";
  const v = Math.abs(n);
  if (v >= 100) return sign + "$" + v.toFixed(0);
  if (v >= 10) return sign + "$" + v.toFixed(1);
  return sign + "$" + v.toFixed(2);
}

function medianPerM() {
  const xs = TASKS.map((t) => t.jev.perM).sort((a, b) => a - b);
  const mid = xs[Math.floor(xs.length / 2)];
  return mid.toFixed(0);
}

function ms(n) {
  return Math.round(n) + "ms";
}

function shortSha(s) {
  return (s || "").slice(0, 12);
}

function deltaAcc(task) {
  return task.jev.acc - task.mini.acc;
}

function speedup(task) {
  return task.mini.p50 / task.jev.p50;
}

function verdictMeta(v, ns) {
  if (ns) return { label: "ns", cls: "verdict-mix", chip: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" };
  if (v === "replace") return { label: "Replace", cls: "verdict-replace", chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" };
  if (v === "mix") return { label: "Mix", cls: "verdict-mix", chip: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" };
  return { label: "Don't", cls: "verdict-dont", chip: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" };
}

function counts() {
  const tfidfWins = TASKS.filter((t) => t.tfidf.vsJev === "tfidf");
  // Headline card shows the task where the quit line is most defensible:
  // lowest calibration error first, then the most traffic it can auto-handle.
  const best = TASKS.slice().sort(
    (a, b) => a.ece.ece - b.ece.ece || b.gates["0.7"].cov - a.gates["0.7"].cov
  )[0];
  return {
    replace: TASKS.filter((t) => t.verdict === "replace" && !t.ns).length,
    mix: TASKS.filter((t) => t.verdict === "mix" || t.ns).length,
    dont: TASKS.filter((t) => t.verdict === "dont" && !t.ns).length,
    ns: TASKS.filter((t) => t.ns).length,
    lowEce: TASKS.filter((t) => t.ece.ece <= 0.1).length,
    tfidfWins: tfidfWins.length,
    tfidfNames: tfidfWins.map((t) => t.shortName || t.id.split("_")[0]).join(" + "),
    best,
    speed: (TASKS.reduce((s, t) => s + speedup(t), 0) / TASKS.length).toFixed(1),
  };
}

let filter = "all";
let openId = TASKS[0].id;
let monthlyCalls = 1000000;

function filtered() {
  return filter === "all" ? TASKS : TASKS.filter((t) => t.verdict === filter);
}

function loadReceipts(id) {
  if (receiptCache[id]) return Promise.resolve(receiptCache[id]);
  return fetch("receipts/" + id + ".json")
    .then((r) => {
      if (!r.ok) throw new Error("missing receipts");
      return r.json();
    })
    .then((data) => {
      receiptCache[id] = data;
      return data;
    });
}

function render() {
  const app = document.getElementById("app");
  const c = counts();
  const rows = filtered();
  const open = TASKS.find((t) => t.id === openId) || rows[0];

  app.innerHTML = `
    <header class="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div class="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-5 sm:flex-row sm:items-end sm:justify-between sm:px-6">
        <div>
          <p class="mono text-[11px] tracking-[0.18em] text-zinc-500 uppercase">whichjudge.dev · which model for this decision · n=${RUN.n} · seed=${RUN.seed}</p>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">You don't need a better model. You need a quit line.</h1>
          <p class="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            Judge here means the cheap in-loop decision (route, gate, score) — not grading an agent transcript.
            On ${c.best.title.toLowerCase()}, where confidence is best calibrated (ECE ${c.best.ece.ece}), Jev at ≥ 0.7 is
            <span class="font-medium text-zinc-900 dark:text-zinc-100">${pct(c.best.gates["0.7"].acc)} accurate on ${pct(c.best.gates["0.7"].cov)} of traffic</span>.
            Auto that slice. Mix the rest. Grey ns = accuracy gap is noise.
          </p>
        </div>
        <p class="mono text-xs text-zinc-500">whichjudge.dev</p>
      </div>
    </header>

    <main class="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <section class="card-grid mb-8">
        ${statCard("Quit line", "≥ 0.7", "Jev confidence. Below this, don't auto.")}
        ${statCard(c.best.title + " @ 0.7", pct(c.best.gates["0.7"].acc), "on " + pct(c.best.gates["0.7"].cov) + " of traffic · n=" + RUN.n)}
        ${statCard("Trustworthy gates", `${c.lowEce}/${TASKS.length}`, "ECE ≤ 0.1. The rest cannot carry a threshold.")}
        ${statCard("Don't (sig)", String(c.dont), "Hate: Mini wins. Kept on the homepage.")}
        ${statCard(`TF-IDF wins ${c.tfidfWins}`, c.tfidfNames || "none", "If you have labels, skip both APIs")}
        ${statCard("p50 vs Mini", c.speed + "×", "same client, same minute · includes RTT")}
      </section>

      <div class="mb-4 flex flex-wrap items-center gap-2">
        ${FILTERS.map((f) => {
          const on = filter === f.id;
          return `<button type="button" data-filter="${f.id}" class="rounded-full border px-3 py-1 text-xs font-medium ${on ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900" : "border-zinc-300 bg-white text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"}">${f.label}</button>`;
        }).join("")}
      </div>

      <div class="flex flex-col gap-6 md:grid md:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <section class="min-w-0 rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div class="space-y-2 p-3 md:hidden">
            ${rows.map((t) => cardHtml(t, open && open.id === t.id)).join("")}
          </div>
          <div class="table-wrapper hidden md:block">
            <table class="w-full min-w-[42rem] text-left text-sm">
              <thead class="border-b border-zinc-200 text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800">
                <tr>
                  <th class="px-4 py-3 font-medium">Decision</th>
                  <th class="px-3 py-3 font-medium">Verdict</th>
                  <th class="px-3 py-3 font-medium">Jev</th>
                  <th class="px-3 py-3 font-medium">4o-mini</th>
                  <th class="px-3 py-3 font-medium">TF-IDF</th>
                  <th class="px-3 py-3 font-medium">p50</th>
                </tr>
              </thead>
              <tbody>
                ${rows.map((t) => rowHtml(t, open && open.id === t.id)).join("")}
              </tbody>
            </table>
          </div>
          <p class="border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500 dark:border-zinc-800">
            Accuracy from ${RUN.n}×2 receipts. Don't stays on the homepage. ns is grey on purpose.
          </p>
        </section>
        <section class="min-w-0">${open ? detailHtml(open) : ""}</section>
      </div>

      <section class="mt-6 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 class="text-sm font-semibold">Monthly bill on this schema</h2>
        <p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Uses measured $/call × volume. Jev is not cheaper here: the question text is longer, so input tokens dominate. Official 40–200× / 400× claims are vs large generative models, not vs 4o-mini on these tasks.</p>
        <label class="mt-4 flex flex-col gap-2 text-sm sm:flex-row sm:items-center">
          <span class="shrink-0 text-zinc-500">Calls / month</span>
          <input id="vol" type="number" min="1000" step="1000" value="${monthlyCalls}" class="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 tabular-nums dark:border-zinc-700 dark:bg-zinc-950" />
        </label>
        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3 text-sm">
          ${metric("Jev / month", usd(open.jev.perM * monthlyCalls / 1e6))}
          ${metric("Mini / month", usd(open.mini.perM * monthlyCalls / 1e6))}
          ${metric("Delta", usd((open.jev.perM - open.mini.perM) * monthlyCalls / 1e6) + (open.jev.perM > open.mini.perM ? " Jev costs more" : " Jev cheaper"))}
        </div>
      </section>

      <section id="receipts-panel" class="mt-6"></section>

      <section class="mt-10 grid gap-4 md:grid-cols-2">
        <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 class="text-sm font-semibold">How to read this</h2>
          <ul class="mt-3 space-y-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Quit line</span> — auto only when Jev p(chosen) ≥ 0.7 (or 0.8 on offensive). Justified where ECE is low (SMS 0.013, reviews 0.019). Not justified on hate (ECE 0.19) or banking (0.22).</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Replace</span> — McNemar p<0.05 and Jev ≥ Mini. Latency is extra. Cost is not the reason (see $/M).</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">ns</span> — accuracy gap is noise. Do not crown a winner on 1–2pt.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Don't</span> — Mini significantly better. Hate-speech stays on the homepage on purpose.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">TF-IDF</span> — $0, ~0.03ms, leftover train never overlapping the frozen 500. If it wins, skip both APIs.</li>
          </ul>
          <p class="mt-4 text-xs leading-relaxed text-zinc-500">${RUN.note}</p>
        </article>
        <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 class="text-sm font-semibold">Four layers of proof</h2>
          <ol class="mt-3 space-y-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">1. Frozen inputs.</span> seed=7, n=500, public gold, schema SHA on each row.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">2. Per-call receipts.</span> Full request/response + SHA-256. Open a row.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">3. Don't stays up.</span> Hate speech: Mini +12 pts.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">4. Re-run.</span> <span class="mono text-xs">python3 scripts/verify_run.py</span> recounts accuracy. <span class="mono text-xs">python3 scripts/run_eval.py</span> hits the APIs again.</li>
          </ol>
          <p class="mt-3 mono text-[11px] break-all text-zinc-500">run ${RUN.runId}</p>
        </article>
      </section>

      ${costCurveHtml()}

      <section class="mt-6 grid gap-4 md:grid-cols-2">
        ${callCard(CALLS.reproduce)}
        ${callCard(CALLS.contribute)}
      </section>
    </main>
    <footer class="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div class="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-xs leading-relaxed text-zinc-500 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <p class="max-w-xl">Independent bench. Not affiliated with TypeSafe AI. Public gold labels, n=${RUN.n}, not a procurement study. Do not auto-route on high ECE rows (banking, hate).</p>
        <p class="flex flex-wrap gap-x-4 gap-y-1">
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="mailto:${SITE.contact}">${SITE.contact}</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="${SITE.xUrl}" rel="noopener">@${SITE.x}</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="${SITE.repo}" rel="noopener">Source</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="terms.html">Terms</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="privacy.html">Privacy</a>
        </p>
      </div>
    </footer>
  `;

  app.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      filter = btn.getAttribute("data-filter");
      const still = filtered().some((t) => t.id === openId);
      if (!still && filtered()[0]) openId = filtered()[0].id;
      render();
    });
  });
  const vol = app.querySelector("#vol");
  if (vol) {
    vol.addEventListener("change", () => {
      monthlyCalls = Math.max(1000, Number(vol.value) || 1000000);
      render();
    });
  }
  app.querySelectorAll("[data-task]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openId = btn.getAttribute("data-task");
      sampleOpen = null;
      render();
    });
  });
  const loadBtn = app.querySelector("[data-load-receipts]");
  if (loadBtn) {
    loadBtn.addEventListener("click", () => {
      receiptOpenId = open.id;
      renderReceipts(open.id);
    });
  }
  if (receiptOpenId === open.id) renderReceipts(open.id);
}

function statCard(label, value, sub) {
  return `
    <div class="rounded-xl border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
      <p class="text-[11px] tracking-wide text-zinc-500 uppercase">${label}</p>
      <p class="mt-1 text-2xl font-semibold tabular-nums">${value}</p>
      <p class="mt-1 text-xs text-zinc-500">${sub}</p>
    </div>
  `;
}

function costCurveHtml() {
  if (typeof COST_CURVE === "undefined" || !COST_CURVE) return "";
  const c = COST_CURVE;
  const rows = c.points
    .map((p) => {
      const jevWins = p.cheaper === "jev";
      return `
        <tr class="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
          <td class="px-3 py-2 tabular-nums">${p.mean_content_tokens}</td>
          <td class="px-3 py-2 tabular-nums ${jevWins ? "font-medium" : "text-zinc-500"}">$${p.jev_per_million}</td>
          <td class="px-3 py-2 tabular-nums ${jevWins ? "text-zinc-500" : "font-medium"}">$${p.mini_per_million}</td>
          <td class="px-3 py-2 text-xs ${jevWins ? "text-emerald-700 dark:text-emerald-400" : "text-zinc-500"}">${jevWins ? "Jev" : "Mini"}</td>
        </tr>`;
    })
    .join("");
  const x = c.crossover;
  return `
    <section class="mt-6 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 class="text-sm font-semibold">Neither model is simply cheaper. It depends on input length.</h2>
      <p class="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        Jev bills about <span class="font-medium text-zinc-900 dark:text-zinc-100">${c.jev_fixed_overhead_tokens} input tokens before your content</span>,
        then charges 3.6x less per token than 4o-mini and nothing for output. So short inputs favour Mini and long ones favour Jev.
        ${x ? `The crossover is around <span class="font-medium text-zinc-900 dark:text-zinc-100">${x.content_tokens} tokens</span> of content, roughly ${x.content_tokens * 4} characters.` : ""}
        Every task in the table above sits below that line, which is why Jev looks expensive here.
      </p>
      <div class="table-wrapper mt-4">
        <table class="w-full min-w-[26rem] text-left text-sm">
          <thead class="border-b border-zinc-200 text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800">
            <tr>
              <th class="px-3 py-2 font-medium">Content tokens</th>
              <th class="px-3 py-2 font-medium">Jev $/1M</th>
              <th class="px-3 py-2 font-medium">4o-mini $/1M</th>
              <th class="px-3 py-2 font-medium">Cheaper</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="mt-3 text-xs leading-relaxed text-zinc-500">
        ${c.samples_per_point} calls per point, same document sent to both. List prices:
        Jev $${c.prices_usd_per_million.jev.input}/M in and free out, 4o-mini $${c.prices_usd_per_million.mini.input}/M in and $${c.prices_usd_per_million.mini.output}/M out.
        Price and latency only, not accuracy. Receipts in <span class="mono">results/receipts/cost_curve.json</span>.
      </p>
    </section>
  `;
}

function callCard(c) {
  const href = `mailto:${SITE.contact}?subject=${encodeURIComponent(c.subject)}`;
  return `
    <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 class="text-sm font-semibold">${c.heading}</h2>
      <p class="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">${c.body}</p>
      <p class="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <a class="font-medium underline decoration-zinc-300 underline-offset-2" href="${href}">${c.cta}</a>
        <a class="text-zinc-500 underline decoration-zinc-300 underline-offset-2" href="${SITE.xUrl}" rel="noopener">or DM @${SITE.x}</a>
      </p>
    </article>
  `;
}

function cardHtml(t, on) {
  const v = verdictMeta(t.verdict, t.ns);
  const g = t.gates["0.7"] || t.gates["0.8"];
  return `
    <button type="button" data-task="${t.id}" class="flex w-full gap-3 rounded-lg border px-3 py-3 text-left ${on ? "border-zinc-900 bg-zinc-100 dark:border-zinc-100 dark:bg-zinc-800" : "border-zinc-200 dark:border-zinc-800"}">
      <span class="w-1 shrink-0 rounded-full ${v.cls}" style="background: var(--v)"></span>
      <span class="min-w-0 flex-1">
        <span class="flex flex-wrap items-center gap-2">
          <span class="font-medium">${t.title}</span>
          <span class="rounded-full px-2 py-0.5 text-[11px] font-medium ${v.chip}">${v.label}</span>
        </span>
        <span class="mt-2 grid grid-cols-3 gap-2 text-xs tabular-nums">
          <span>Jev ${pct(t.jev.acc)}</span>
          <span>Mini ${pct(t.mini.acc)}</span>
          <span>TF-IDF ${pct(t.tfidf.acc)}</span>
        </span>
        <span class="mt-1 block text-xs text-zinc-500">≥0.7 ${g ? pct(g.acc) + " on " + pct(g.cov) : "—"} · ${ms(t.jev.p50)}</span>
      </span>
    </button>
  `;
}

function rowHtml(t, on) {
  const v = verdictMeta(t.verdict, t.ns);
  const d = deltaAcc(t);
  const dLabel = (d >= 0 ? "+" : "") + (d * 100).toFixed(1) + "pt";
  return `
    <tr>
      <td colspan="6" class="p-0">
        <button type="button" data-task="${t.id}" class="flex w-full items-stretch text-left ${on ? "bg-zinc-100 dark:bg-zinc-800/80" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"}">
          <span class="w-1 shrink-0 ${v.cls}" style="background: var(--v)"></span>
          <span class="grid w-full min-w-0 grid-cols-[minmax(0,1.2fr)_auto_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(5rem,0.7fr)] items-center gap-0 px-3 py-3 sm:px-4">
            <span class="min-w-0">
              <span class="block truncate font-medium">${t.title}</span>
              <span class="block truncate text-xs text-zinc-500">${t.dataset}</span>
            </span>
            <span class="px-2"><span class="rounded-full px-2 py-0.5 text-[11px] font-medium ${v.chip}">${v.label}</span></span>
            <span class="tabular-nums">${pct(t.jev.acc)}<span class="block text-[10px] font-normal text-zinc-400">${pct(t.jev.lo)}–${pct(t.jev.hi)}</span></span>
            <span class="tabular-nums text-zinc-600 dark:text-zinc-400">${pct(t.mini.acc)} <span class="text-[11px] text-zinc-400">${dLabel}</span></span>
            <span class="tabular-nums ${t.tfidf.vsJev === "tfidf" ? "font-medium" : "text-zinc-600 dark:text-zinc-400"}">${pct(t.tfidf.acc)}<span class="block text-[10px] font-normal text-zinc-400">$0</span></span>
            <span class="mono text-xs tabular-nums text-zinc-600 dark:text-zinc-400">${ms(t.jev.p50)} <span class="text-zinc-400">/</span> ${ms(t.mini.p50)}</span>
          </span>
        </button>
      </td>
    </tr>
  `;
}

function detailHtml(t) {
  const v = verdictMeta(t.verdict, t.ns);
  const su = speedup(t).toFixed(1);
  return `
    <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-[11px] tracking-wide text-zinc-500 uppercase">${t.id}</p>
          <h2 class="mt-1 text-lg font-semibold">${t.title}</h2>
        </div>
        <span class="rounded-full px-2.5 py-1 text-xs font-medium ${v.chip}">${v.label}</span>
      </div>
      <p class="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">${t.why}</p>
      <dl class="mt-5 grid grid-cols-2 gap-3 text-sm">
        ${metric("Jev accuracy", pct(t.jev.acc) + "  [" + pct(t.jev.lo) + "–" + pct(t.jev.hi) + "]")}
        ${metric("Mini accuracy", pct(t.mini.acc) + "  [" + pct(t.mini.lo) + "–" + pct(t.mini.hi) + "]")}
        ${metric("TF-IDF + LR", pct(t.tfidf.acc) + "  [" + pct(t.tfidf.lo) + "–" + pct(t.tfidf.hi) + "] · train " + t.tfidf.trainN.toLocaleString())}
        ${metric("McNemar vs Mini", t.ns ? "ns  p=" + t.mcnemar.p : t.mcnemar.winner + "  p=" + t.mcnemar.p)}
        ${metric("TF-IDF vs Jev", t.tfidf.vsJev)}
        ${metric("Jev p50 / p95", ms(t.jev.p50) + " / " + ms(t.jev.p95))}
        ${metric("Mini p50", ms(t.mini.p50) + " · " + su + "× · RTT in")}
        ${metric("$ / million", usd(t.jev.perM) + " vs " + usd(t.mini.perM))}
        ${metric("ECE (p_chosen)", t.ece.ece.toFixed(3) + " · MCE " + t.ece.mce.toFixed(3))}
        ${metric("Replacing", t.replaces)}
      </dl>
      <div class="mt-5">
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Accuracy bar</p>
        <div class="mt-2 space-y-2">
          ${accBar("Jev", t.jev.acc, "bg-zinc-900 dark:bg-zinc-100")}
          ${accBar("Mini", t.mini.acc, "bg-zinc-400 dark:bg-zinc-500")}
          ${accBar("TF-IDF", t.tfidf.acc, "bg-sky-700 dark:bg-sky-400")}
        </div>
      </div>
      <div class="mt-5">
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Reliability · p(chosen) vs hit rate</p>
        <p class="mt-1 text-xs text-zinc-500">Diagonal = honest. Above = underconfident. Below = overconfident. ECE is the weighted gap. This is why 0.7 is a quit line on SMS and not on hate.</p>
        <div class="mt-3 grid grid-cols-5 gap-1 sm:grid-cols-10">
          ${t.ece.bins.map((b) => reliabilityCell(b)).join("")}
        </div>
      </div>
      <div class="mt-5">
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Confidence gate</p>
        <div class="mt-2 grid grid-cols-2 gap-2 text-xs">
          ${Object.entries(t.gates).map(([thr, g]) => `
            <div class="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-700">
              <p class="mono text-zinc-500">≥ ${thr}</p>
              <p class="mt-1 tabular-nums">${pct(g.acc)} acc · ${pct(g.cov)} coverage</p>
            </div>
          `).join("")}
        </div>
        <p class="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400"><span class="font-medium text-zinc-900 dark:text-zinc-100">Ship rule. </span>${t.gate}</p>
      </div>
      <p class="mt-4 mono break-all text-[11px] text-zinc-500">samples ${shortSha(t.samplesSha)} · schema ${shortSha(t.schemaSha)}</p>
      <p class="mt-1 text-xs text-zinc-500">Labels: ${t.labels}</p>
      <button type="button" data-load-receipts class="mt-4 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700">Open 500 receipts</button>
    </article>
  `;
}

function metric(k, val) {
  return `
    <div class="rounded-lg bg-zinc-50 px-3 py-2 dark:bg-zinc-800/60">
      <dt class="text-[11px] text-zinc-500">${k}</dt>
      <dd class="mt-0.5 font-medium">${val}</dd>
    </div>
  `;
}

function reliabilityCell(b) {
  const accPct = (b.acc * 100).toFixed(0);
  const confPct = (b.conf * 100).toFixed(0);
  const over = b.conf - b.acc;
  const color = over > 0.08 ? "bg-red-200 dark:bg-red-900/50" : over < -0.08 ? "bg-sky-200 dark:bg-sky-900/40" : "bg-zinc-200 dark:bg-zinc-800";
  return `<div class="rounded-md ${color} px-1 py-1.5 text-center" title="bin ${b.lo} n=${b.n}">
    <p class="mono text-[10px] text-zinc-500">${b.lo.toFixed(1)}</p>
    <p class="tabular-nums text-xs font-medium">${accPct}%</p>
    <p class="text-[10px] text-zinc-500">n=${b.n}</p>
  </div>`;
}

function accBar(name, acc, barCls) {
  return `
    <div>
      <div class="mb-1 flex justify-between text-xs text-zinc-500">
        <span>${name}</span><span class="tabular-nums">${pct(acc)}</span>
      </div>
      <div class="bar"><span class="${barCls}" style="width:${(acc * 100).toFixed(1)}%"></span></div>
    </div>
  `;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderReceipts(id) {
  const panel = document.getElementById("receipts-panel");
  if (!panel) return;
  panel.innerHTML = `<p class="text-sm text-zinc-500">Loading receipts…</p>`;
  loadReceipts(id)
    .then((data) => {
      const byMini = {};
      data.gpt4o_mini.forEach((r) => { byMini[r.id] = r; });
      const rows = data.jev.map((j) => {
        const m = byMini[j.id] || {};
        const on = sampleOpen === j.id;
        const okJ = j.pred === j.gold;
        const okM = m.pred === j.gold;
        return `
          <tr class="border-t border-zinc-200 dark:border-zinc-800 ${on ? "bg-zinc-50 dark:bg-zinc-800/50" : ""}">
            <td class="px-3 py-2 align-top">
              <button type="button" data-sample="${j.id}" class="text-left">
                <span class="mono text-[11px] text-zinc-500">#${j.id}</span>
                <span class="mt-1 block max-w-xs truncate text-xs">${esc(j.text)}</span>
              </button>
            </td>
            <td class="px-3 py-2 align-top text-xs">${esc(j.gold)}</td>
            <td class="px-3 py-2 align-top text-xs ${okJ ? "" : "text-red-600 dark:text-red-400"}">${esc(j.pred)} <span class="text-zinc-400">${(j.confidence ?? 0).toFixed(2)}</span></td>
            <td class="px-3 py-2 align-top text-xs ${okM ? "" : "text-red-600 dark:text-red-400"}">${esc(m.pred)}</td>
            <td class="mono px-3 py-2 align-top text-[11px] text-zinc-500">${shortSha(j.response_sha256)}</td>
          </tr>
          ${on ? `<tr><td colspan="5" class="bg-zinc-50 px-3 py-3 dark:bg-zinc-900">${sampleDetail(j, m)}</td></tr>` : ""}
        `;
      }).join("");
      panel.innerHTML = `
        <article class="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <h2 class="text-sm font-semibold">Receipts · ${esc(id)} · ${data.n} × 2 calls</h2>
            <p class="mono text-[11px] text-zinc-500">samples ${shortSha(data.samples_sha256)} · schema ${shortSha(data.schema_sha256)}</p>
          </div>
          <div class="table-wrapper">
            <table class="w-full min-w-[40rem] text-left text-sm">
              <thead class="text-[11px] tracking-wide text-zinc-500 uppercase">
                <tr>
                  <th class="px-3 py-2 font-medium">Sample</th>
                  <th class="px-3 py-2 font-medium">Gold</th>
                  <th class="px-3 py-2 font-medium">Jev</th>
                  <th class="px-3 py-2 font-medium">Mini</th>
                  <th class="px-3 py-2 font-medium">Jev resp SHA</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </article>
      `;
      panel.querySelectorAll("[data-sample]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const sid = Number(btn.getAttribute("data-sample"));
          sampleOpen = sampleOpen === sid ? null : sid;
          renderReceipts(id);
        });
      });
    })
    .catch(() => {
      panel.innerHTML = `<p class="text-sm text-zinc-500">Receipt JSON missing. Serve the site folder (not a lone index.html) so receipts/*.json can load.</p>`;
    });
}

function sampleDetail(j, m) {
  return `
    <div class="grid gap-3 md:grid-cols-2">
      <div>
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Jev ${esc(j.model_returned)} · ${esc(j.endpoint)}</p>
        <p class="mono mt-1 break-all text-[11px] text-zinc-500">req ${esc(j.request_sha256)}<br>resp ${esc(j.response_sha256)}</p>
        <pre class="mt-2 max-h-64 overflow-auto rounded-lg bg-zinc-100 p-2 text-[11px] leading-relaxed dark:bg-zinc-950">${esc(JSON.stringify({ request: j.request, response: j.response }, null, 2))}</pre>
      </div>
      <div>
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Mini ${esc(m.model_returned)} · ${esc(m.endpoint)}</p>
        <p class="mono mt-1 break-all text-[11px] text-zinc-500">req ${esc(m.request_sha256)}<br>resp ${esc(m.response_sha256)}</p>
        <pre class="mt-2 max-h-64 overflow-auto rounded-lg bg-zinc-100 p-2 text-[11px] leading-relaxed dark:bg-zinc-950">${esc(JSON.stringify({ request: m.request, response: m.response }, null, 2))}</pre>
      </div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", render);
