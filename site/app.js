// RUN and TASKS are generated into site/data.js by scripts/build_site.py.
// Edit site/copy.json for wording; numbers only change by re-running the eval.

const FILTERS = [
  { id: "all", label: `All ${TASKS.length}` },
  { id: "replace", label: "Replace" },
  { id: "mix", label: "Mix" },
  { id: "dont", label: "Don't" },
  { id: "neither", label: "Neither" },
];

// Header and rows share this exact template. The old markup used <th> cells for the
// header and a CSS grid for the rows, which is why the columns never lined up.
const GRID = "minmax(0,1.7fr) 4.6rem minmax(3.6rem,0.5fr) minmax(3.6rem,0.5fr) minmax(3.6rem,0.5fr) minmax(3.6rem,0.5fr) 3.2rem minmax(5.6rem,0.75fr)";

const receiptCache = {};
let modalOpen = false;
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
  // Neither wins over ns on purpose: "the two models tie" is much less useful than
  // "neither of them can be trusted with this decision on its own".
  if (v === "neither") return { label: "Neither", cls: "verdict-dont", chip: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" };
  if (ns) return { label: "ns", cls: "verdict-mix", chip: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" };
  if (v === "replace") return { label: "Replace", cls: "verdict-replace", chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" };
  if (v === "mix") return { label: "Mix", cls: "verdict-mix", chip: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" };
  return { label: "Don't", cls: "verdict-dont", chip: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" };
}

function counts() {
  const tfidfWins = TASKS.filter((t) => t.tfidf.vsJev === "tfidf");
  // Headline card uses the same rule as the Auto slice column, so the first screen
  // and the table cannot disagree about which threshold is being talked about.
  const best = TASKS.slice().sort(
    (a, b) => b.autoSlice.acc - a.autoSlice.acc || b.autoSlice.cov - a.autoSlice.cov
  )[0];
  return {
    replace: TASKS.filter((t) => t.verdict === "replace" && !t.ns).length,
    mix: TASKS.filter((t) => t.verdict === "mix" || t.ns).length,
    dont: TASKS.filter((t) => t.verdict === "dont" && !t.ns).length,
    ns: TASKS.filter((t) => t.ns).length,
    gateHelps: TASKS.filter((t) => t.autoSlice && t.autoSlice.lift > 0).length,
    neither: TASKS.filter((t) => t.verdict === "neither").length,
    liveGold: TASKS.filter((t) => t.goldTier === "live").length,
    realGold: TASKS.filter((t) => t.goldTier !== "research").length,
    modernBeatsJev: TASKS.filter((t) => t.modern && t.modern.vsJev === "modern").length,
    jevBeatsModern: TASKS.filter((t) => t.modern && t.modern.vsJev === "jev").length,
    modernTies: TASKS.filter((t) => t.modern && t.modern.vsJev === "ns").length,
    modernModel: (TASKS.find((t) => t.modern) || {}).modern,
    tfidfWins: tfidfWins.length,
    tfidfNames: tfidfWins.map((t) => t.shortName || t.id.split("_")[0]).join(" + "),
    best,
    speed: (TASKS.reduce((s, t) => s + speedup(t), 0) / TASKS.length).toFixed(1),
  };
}

// The row button that opened the modal. Focus goes back to it on close, so a
// keyboard user lands where they left the table instead of at the top of the page.
let modalTrigger = null;

function closeModal() {
  modalOpen = false;
  receiptOpenId = null;
  render();
  const back = modalTrigger ? document.querySelector(`[data-task="${modalTrigger}"]`) : null;
  if (back) back.focus();
  modalTrigger = null;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

document.addEventListener("keydown", (ev) => {
  if (!modalOpen) return;
  if (ev.key === "Escape") {
    closeModal();
    return;
  }
  // Keep Tab inside the dialog. The page behind it is inert to the eye already;
  // this makes it inert to the keyboard as well.
  if (ev.key === "Tab") {
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) return;
    const items = Array.from(dialog.querySelectorAll(FOCUSABLE)).filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (ev.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
      ev.preventDefault();
      last.focus();
    } else if (!ev.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
      ev.preventDefault();
      first.focus();
    }
  }
});

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
          <p class="mono text-[11px] tracking-[0.18em] text-zinc-500 uppercase">whichjudge.dev · which model for this decision · n=${RUN.nMin === RUN.nMax ? RUN.n : RUN.nMin + '-' + RUN.nMax} per task · seed=${RUN.seed}</p>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">You don't need a better model. You need a quit line.</h1>
          <p class="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            Judge here means the cheap in-loop decision (route, gate, score) - not grading an agent transcript.
            Gating on Jev's confidence beats not gating on ${c.gateHelps} of ${TASKS.length} rows.
            ${(() => {
              const x = TASKS.find((t) => t.verdict === "neither");
              if (!x || !x.errors) return "";
              const worst = Object.entries(x.errors.jev.per_class).sort((a, b) => a[1].recall - b[1].recall)[0];
              return `<span class="font-medium text-red-700 dark:text-red-400">It does not rescue the row that matters most: on ${x.title.toLowerCase()}, Jev misses ${pct(worst[1].missed_rate)} of ${worst[0]} at any threshold.</span>`;
            })()}
            Grey ns = accuracy gap is noise after Holm correction.
          </p>
        </div>
        <p class="mono text-xs text-zinc-500">whichjudge.dev</p>
      </div>
    </header>

    <main class="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <section class="card-grid mb-8">
        ${(() => {
          const x = TASKS.find((t) => t.verdict === "neither");
          if (!x || !x.errors) return "";
          const worst = Object.entries(x.errors.jev.per_class).sort((a, b) => a[1].recall - b[1].recall)[0];
          return statCard("Where it fails", pct(worst[1].missed_rate) + " missed",
            x.title.toLowerCase() + ": " + worst[0] + " Jev never flags. No threshold fixes it.");
        })()}
        ${statCard("Gating beats not gating", `${c.gateHelps}/${TASKS.length}`, "Lift shown per row, from gates on the same score as ECE.")}
        ${c.modernModel ? statCard("vs a 2026 model", `${c.jevBeatsModern}W ${c.modernTies}T ${c.modernBeatsJev}L`, `Jev against ${c.modernModel.model}, Holm-corrected. ` + TASKS.filter((t) => t.modern && t.modern.vsJev !== "ns").map((t) => (t.modern.vsJev === "jev" ? "Jev wins " : "loses ") + t.title.toLowerCase()).join("; ") + ".") : ""}
        ${statCard(`TF-IDF wins ${c.tfidfWins}`, c.tfidfNames || "none", "If you have labels, skip both APIs")}
        ${statCard("Non-academic gold", `${c.realGold}/${TASKS.length}`, `${c.liveGold} live system, ${c.realGold - c.liveGold} real text. The rest are benchmarks.`)}
        ${statCard("Best case, not typical", pct(c.best.autoSlice.acc), c.best.title.toLowerCase() + " above " + c.best.autoSlice.gate + ", on " + pct(c.best.autoSlice.cov) + " of traffic. Highest on the board.")}
      </section>

      <div class="mb-4 flex flex-wrap items-center gap-2">
        ${FILTERS.map((f) => {
          const on = filter === f.id;
          return `<button type="button" data-filter="${f.id}" class="rounded-full border px-3 py-1 text-xs font-medium ${on ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900" : "border-zinc-300 bg-white text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"}">${f.label}</button>`;
        }).join("")}
      </div>

      <section class="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div class="space-y-2 p-3 md:hidden">
          ${rows.map((t) => cardHtml(t, false)).join("")}
        </div>
        <div class="hidden md:block">
          <div class="flex items-stretch border-b border-zinc-200 text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800">
            <span class="w-1 shrink-0"></span>
            <span class="grid w-full min-w-0 items-end gap-3 px-4 py-3" style="grid-template-columns: ${GRID}">
              <span>Decision</span>
              <span>vs Mini</span>
              <span class="text-right">Jev</span>
              <span class="text-right">4o-mini<br><span class="normal-case tracking-normal text-zinc-400">2024</span></span>
              <span class="text-right">5.4-mini<br><span class="normal-case tracking-normal text-zinc-400">2026</span></span>
              <span class="text-right">TF-IDF</span>
              <span class="text-right">ECE</span>
              <span class="text-right">Auto slice</span>
            </span>
          </div>
          ${rows.map((t) => rowHtml(t, false)).join("")}
        </div>
        <p class="border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500 dark:border-zinc-800">
          Accuracy recounted from stored receipts. Click a row for the full breakdown. Don't stays on the homepage. ns is grey on purpose.
        </p>
      </section>

      <section class="mt-6 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 class="text-sm font-semibold">Monthly bill on ${open.title.toLowerCase()}</h2>
        <p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Measured $/call for <span class="font-medium">${open.title.toLowerCase()}</span> (n=${open.n}) times your volume, so it answers that row only. ${open.jev.perM <= open.mini.perM ? "Jev is the cheaper API on this row" : "4o-mini is the cheaper API on this row"}, because Jev bills a fixed floor of about ${COST_CURVE ? COST_CURVE.jev_fixed_overhead_tokens : "270"} input tokens before your content. Short inputs favour Mini, long ones favour Jev. The curve below is the general answer, not this box.</p>
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

      <section class="mt-10 grid gap-4 md:grid-cols-2">
        <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 class="text-sm font-semibold">How to read this</h2>
          <ul class="mt-3 space-y-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Auto slice</span> - the strongest threshold that still leaves at least half the traffic automated, and what it buys against ungated accuracy. Picked by that rule from the measured gates, not by hand.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">ECE</span> - whether you may read the confidence as a probability. It is <em>not</em> whether gating helps. Gating only needs the model to rank its own answers, so a badly calibrated row can still gate well: banking has the worst ECE here and still gains ${(() => { const b = TASKS.find((t) => t.id === "banking_coarse_route"); return b ? (b.autoSlice.lift * 100).toFixed(1) : "0"; })()}pt. What high ECE costs you is the right to quote the number.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Replace / Mix / Don't / ns</span> - these compare Jev against 4o-mini and nothing else. They do not say whether you should automate the decision (see Auto slice), whether the confidence can be quoted (see ECE), or whether a trained classifier would beat both (see TF-IDF). Banking is Replace, has the worst ECE here, and loses to TF-IDF by 21 points. One badge cannot carry three findings.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">ns</span> - accuracy gap is noise. Do not crown a winner on 1-2pt. On the safety rows, ignore accuracy entirely and read the miss rate in red.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">Don't</span> - Mini significantly better on that dataset. Hate speech stays up on purpose, and the Civil Comments row shows the same judgement on CC0 gold where the gap disappears.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">TF-IDF</span> - $0, ~0.03ms, leftover train never overlapping the frozen 500. If it wins, skip both APIs.</li>
          </ul>
          <p class="mt-4 text-xs leading-relaxed text-zinc-500">${RUN.note}</p>
        </article>
        <article class="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 class="text-sm font-semibold">Four layers of proof</h2>
          <ol class="mt-3 space-y-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">1. Frozen inputs.</span> seed=${RUN.seed}, n=${RUN.nMin}-${RUN.nMax} per task, public gold, schema SHA on each row.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">2. Per-call receipts.</span> Full request/response + SHA-256. Open a row.</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">3. Losing rows stay up.</span> ${(() => {
              const h = TASKS.find((t) => t.id === "content_hate");
              const c = TASKS.find((t) => t.id === "civil_toxicity");
              if (!h) return "";
              const gap = ((h.mini.acc - h.jev.acc) * 100).toFixed(1);
              return `Hate speech: 4o-mini +${gap}pt` + (c ? `, next to the Civil Comments row where the same judgement on CC0 gold ties` : "") + ".";
            })()}</li>
            <li><span class="font-medium text-zinc-900 dark:text-zinc-100">4. Re-run.</span> <span class="mono text-xs">python3 scripts/verify_run.py</span> recounts accuracy. <span class="mono text-xs">python3 scripts/run_eval.py</span> hits the APIs again.</li>
          </ol>
          <p class="mt-3 mono text-[11px] break-all text-zinc-500">${RUN.runs.length} invocation(s) of run_eval.py, ${RUN.runs[0].start.slice(0, 16)}Z to ${RUN.runs[RUN.runs.length - 1].start.slice(0, 16)}Z. Each row says which one it came from.</p>
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
        <p class="max-w-xl">Independent bench. Not affiliated with TypeSafe AI. Public gold labels, not a procurement study. Do not auto-route on high ECE rows (banking, hate).</p>
        <p class="flex flex-wrap gap-x-4 gap-y-1">
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="mailto:${SITE.contact}">${SITE.contact}</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="${SITE.xUrl}" rel="noopener">@${SITE.x}</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="${SITE.repo}" rel="noopener">Source</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="terms.html">Terms</a>
          <a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800 dark:hover:text-zinc-200" href="privacy.html">Privacy</a>
        </p>
      </div>
    </footer>
    ${modalOpen && open ? modalHtml(open) : ""}
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
      modalTrigger = openId;
      sampleOpen = null;
      receiptOpenId = null;
      modalOpen = true;
      render();
      // render() rebuilt the DOM, so focus is on <body>. Put it in the dialog.
      const dialog = app.querySelector('[role="dialog"]');
      if (dialog) dialog.focus();
    });
  });
  const backdrop = app.querySelector("[data-modal-backdrop]");
  if (backdrop) {
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) closeModal();
    });
    const close = app.querySelector("[data-modal-close]");
    if (close) close.addEventListener("click", closeModal);
  }
  const loadBtn = app.querySelector("[data-load-receipts]");
  if (loadBtn) {
    loadBtn.addEventListener("click", () => {
      receiptOpenId = open.id;
      renderReceipts(open.id);
    });
  }
  document.body.style.overflow = modalOpen ? "hidden" : "";
  if (modalOpen && receiptOpenId === open.id) renderReceipts(open.id);
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
        ${x ? `The crossover is around <span class="font-medium text-zinc-900 dark:text-zinc-100">${x.content_tokens} tokens of actual input</span>, roughly ${x.content_tokens * 4} characters, after removing the ${c.mini_overhead_tokens || "~41"}-token system prompt 4o-mini adds to every call.` : ""}
        ${(() => {
          const cheaper = TASKS.filter((t) => t.jev.perM < t.mini.perM);
          return `Measured on the rows above, Jev is the cheaper API on ${cheaper.length} of ${TASKS.length}: ${cheaper.map((t) => t.title.toLowerCase()).join(", ")}. Short-text rows go to Mini.`;
        })()}
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

function goldBadge(t) {
  const m = {
    live: ["live gold", "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"],
    real: ["real text", "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300"],
    research: ["academic", "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"],
  }[t.goldTier] || ["", ""];
  return `<span class="mr-1 rounded px-1 py-0.5 text-[10px] font-medium ${m[1]}" title="${t.goldNote}">${m[0]}</span>`;
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
        <span class="mt-1 block text-xs text-zinc-500">≥0.7 ${g ? pct(g.acc) + " on " + pct(g.cov) : "-"} · ${ms(t.jev.p50)}</span>
      </span>
    </button>
  `;
}

function rowHtml(t, on) {
  const v = verdictMeta(t.verdict, t.ns);
  const d = deltaAcc(t);
  const dLabel = (d >= 0 ? "+" : "") + (d * 100).toFixed(1) + "pt";
  return `
    <button type="button" data-task="${t.id}"
      class="flex w-full items-stretch border-b border-zinc-100 text-left last:border-0 dark:border-zinc-800 ${on ? "bg-zinc-100 dark:bg-zinc-800/80" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"}">
      <span class="w-1 shrink-0 ${v.cls}" style="background: var(--v)"></span>
      <span class="grid w-full min-w-0 items-start gap-3 px-4 py-3" style="grid-template-columns: ${GRID}">
        <span class="min-w-0">
          <span class="block font-medium leading-snug">${t.title}</span>
          <span class="block truncate text-xs text-zinc-500">${goldBadge(t)} ${t.sourceName}</span>
          ${t.rowNote ? `<span class="mt-0.5 block text-[11px] leading-snug ${t.rowNoteKind === "warn" ? "font-medium text-red-700 dark:text-red-400" : "text-zinc-500"}">${t.rowNote}</span>` : ""}
        </span>
        <span class="leading-tight">
          <span class="rounded-full px-2 py-0.5 text-[11px] font-medium ${v.chip}">${v.label}</span>
          ${t.tfidf.vsJev === "tfidf" ? `<span class="mt-1 block text-[10px] font-medium text-amber-700 dark:text-amber-500">TF-IDF wins</span>` : ""}
          ${t.modern && t.modern.vsJev === "modern" ? `<span class="mt-0.5 block text-[10px] text-zinc-500">2026 wins</span>` : ""}
        </span>
        <span class="text-right tabular-nums">${pct(t.jev.acc)}<span class="block text-[10px] font-normal text-zinc-400">${pct(t.jev.lo)}-${pct(t.jev.hi)}</span></span>
        <span class="text-right tabular-nums text-zinc-600 dark:text-zinc-400">${pct(t.mini.acc)}<span class="block text-[10px] text-zinc-400">${dLabel}</span></span>
        <span class="text-right tabular-nums ${t.modern && t.modern.vsJev === "modern" ? "font-medium" : "text-zinc-600 dark:text-zinc-400"}">${t.modern ? pct(t.modern.acc) : "-"}<span class="block text-[10px] font-normal text-zinc-400">${t.modern ? (t.modern.vsJev === "modern" ? "beats Jev" : t.modern.vsJev === "jev" ? "loses" : "ns") : ""}</span></span>
        <span class="text-right tabular-nums ${t.tfidf.vsJev === "tfidf" ? "font-medium" : "text-zinc-600 dark:text-zinc-400"}">${pct(t.tfidf.acc)}<span class="block text-[10px] font-normal text-zinc-400">$0</span></span>
        <span class="text-right tabular-nums text-zinc-600 dark:text-zinc-400">${t.ece.ece.toFixed(3)}</span>
        <span class="text-right tabular-nums">${pct(t.autoSlice.acc)}<span class="block text-[10px] font-normal text-zinc-400">on ${pct(t.autoSlice.cov)} · ${(t.autoSlice.lift * 100 >= 0 ? "+" : "") + (t.autoSlice.lift * 100).toFixed(1)}pt</span></span>
      </span>
    </button>
  `;
}


function errorProfileHtml(t) {
  if (!t.errors) return "";
  const classes = Object.keys(t.errors.jev.per_class);
  const rows = classes.map((cls) => {
    const j = t.errors.jev.per_class[cls];
    const m = t.errors.mini.per_class[cls];
    const weak = j.recall < 0.75;
    return `
      <tr class="border-t border-zinc-100 dark:border-zinc-800">
        <td class="py-1.5 pr-3 font-medium">${cls}</td>
        <td class="py-1.5 pr-3 text-right tabular-nums ${weak ? "text-red-700 dark:text-red-400" : ""}">${pct(j.recall)}</td>
        <td class="py-1.5 pr-3 text-right tabular-nums text-zinc-500">${pct(m.recall)}</td>
        <td class="py-1.5 text-right tabular-nums text-zinc-500">${j.missed} of ${j.n}</td>
      </tr>`;
  }).join("");
  return `
    <div class="mt-5">
      <p class="text-[11px] tracking-wide text-zinc-500 uppercase">Which way it is wrong</p>
      <table class="mt-2 w-full text-sm">
        <thead class="text-[11px] tracking-wide text-zinc-500 uppercase">
          <tr>
            <th class="pb-1 text-left font-medium">Class</th>
            <th class="pb-1 text-right font-medium">Jev recall</th>
            <th class="pb-1 text-right font-medium">Mini recall</th>
            <th class="pb-1 text-right font-medium">Jev missed</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="mt-2 text-xs leading-relaxed text-zinc-500">
        Accuracy averages these. When one class matters more than the other, read the row that matters.
      </p>
    </div>
  `;
}

function modalHtml(t) {
  return `
    <div data-modal-backdrop class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-900/50 p-4 backdrop-blur-sm sm:p-8">
      <div role="dialog" aria-modal="true" aria-label="${t.title}" tabindex="-1" class="relative w-full max-w-2xl outline-none">
        <button type="button" data-modal-close aria-label="Close"
          class="absolute right-3 top-3 z-10 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">Esc</button>
        ${detailHtml(t)}
        <section id="receipts-panel" class="mt-4"></section>
      </div>
    </div>
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
        ${metric("Jev accuracy", pct(t.jev.acc) + "  [" + pct(t.jev.lo) + "-" + pct(t.jev.hi) + "]")}
        ${metric("Mini accuracy", pct(t.mini.acc) + "  [" + pct(t.mini.lo) + "-" + pct(t.mini.hi) + "]")}
        ${metric("TF-IDF + LR", pct(t.tfidf.acc) + "  [" + pct(t.tfidf.lo) + "-" + pct(t.tfidf.hi) + "] · train " + t.tfidf.trainN.toLocaleString())}
        ${metric("McNemar vs Mini", t.ns ? "ns  p=" + t.mcnemar.p : t.mcnemar.winner + "  p=" + t.mcnemar.p)}
        ${metric("TF-IDF vs Jev", t.tfidf.vsJev)}
        ${t.modern ? metric("Current small model", pct(t.modern.acc) + "  [" + pct(t.modern.lo) + "-" + pct(t.modern.hi) + "] · " + t.modern.model + " · vs Jev " + t.modern.vsJev) : ""}
        ${metric("Jev p50 / p95", ms(t.jev.p50) + " / " + ms(t.jev.p95))}
        ${metric("Mini p50", ms(t.mini.p50) + " · " + su + "× · includes RTT, local to one client")}
        ${metric("$ / million", usd(t.jev.perM) + " vs " + usd(t.mini.perM))}
        ${metric("ECE (p_chosen)", t.ece.ece.toFixed(3) + " · MCE " + t.ece.mce.toFixed(3))}
        ${metric("Replacing", t.replaces)}
        ${metric("Sample size", "n=" + t.n + " · seed " + RUN.seed)}
        ${metric("Gold type", t.goldNote)}
        ${metric("Gold", `<a class="underline decoration-zinc-300 underline-offset-2" href="${t.sourceUrl}" rel="noopener">${t.sourceName}</a>` + (t.mirrorUrl ? ` via <a class="underline decoration-zinc-300 underline-offset-2" href="${t.mirrorUrl}" rel="noopener">CC0 mirror</a>` : ""))}
      </dl>
      ${errorProfileHtml(t)}
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
      <p class="mt-4 mono break-all text-[11px] text-zinc-500">samples ${shortSha(t.samplesSha)} · schema ${shortSha(t.schemaSha)} · run ${t.run.index} of ${t.run.of}, ${t.run.start.slice(0, 16)}Z</p>
      <p class="mt-1 text-xs text-zinc-500">Labels: ${t.labels}</p>
      <button type="button" data-load-receipts class="mt-4 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700">Open ${t.n * 2} receipts</button>
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
  // site/receipts is a slim copy: hashes and outcomes, not the request and response
  // bodies (those are 12 MB, and for redacted tasks the text is cleared anyway).
  // This used to render JSON.stringify of fields that are not in the file, which
  // showed an empty {} for both arms. Show what is here, link to the full receipt.
  const full = `${SITE.repo}/blob/main/results/receipts/${openId}.json`;
  const arm = (label, r) => `
      <div>
        <p class="text-[11px] tracking-wide text-zinc-500 uppercase">${label} ${esc(r.model_returned || "")}</p>
        <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
          <dt class="text-zinc-500">predicted</dt><dd class="mono">${esc(r.pred)}</dd>
          <dt class="text-zinc-500">gold</dt><dd class="mono">${esc(r.gold)}</dd>
          ${r.p_chosen != null ? `<dt class="text-zinc-500">p_chosen</dt><dd class="mono">${esc(r.p_chosen)}</dd>` : ""}
          <dt class="text-zinc-500">latency</dt><dd class="mono">${Math.round(r.latency_ms)} ms</dd>
        </dl>
        <p class="mono mt-2 break-all text-[11px] text-zinc-500">request sha256 ${esc(r.request_sha256)}<br>response sha256 ${esc(r.response_sha256)}</p>
      </div>`;
  return `
    <div class="grid gap-3 md:grid-cols-2">
      ${arm("Jev", j)}
      ${arm("4o-mini", m)}
    </div>
    <p class="mt-3 text-[12px] text-zinc-600 dark:text-zinc-400">
      Full request and response bodies, with the hashes above, are in
      <a class="underline decoration-zinc-300 underline-offset-2" href="${full}" rel="noopener">results/receipts/${openId}.json</a>.
      Run <span class="mono">scripts/verify_run.py</span> to check them.
    </p>
  `;
}

document.addEventListener("DOMContentLoaded", render);
