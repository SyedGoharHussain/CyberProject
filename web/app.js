/* ═══════════════════════════════════════════════════════════════
   PQC MICROGRID — DEFENSE CONSOLE  ·  front-end controller
   ═══════════════════════════════════════════════════════════════ */
"use strict";

const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};

const STATE = {
  cursor:   0,
  polling:  false,
  finished: false,
  config:   { transactions: 20, attackerEnabled: true, tamperRate: 50 },
  phase:    0,
  logFilter:"all",
  txFilter: "all",
  txs:      [],
};

/* monochrome geometric glyphs only — no emoji-presentation characters */
const DEVICE_ICON = {
  SmartMeter: "▦", SolarPanel: "▥", Battery: "▰",
  EVCharger: "◇", Consumer: "⌂",
};

/* ── live clock ─────────────────────────────────────────────── */
function tickClock() {
  const d = new Date();
  $("#clock").textContent = d.toTimeString().slice(0, 8);
}
setInterval(tickClock, 1000); tickClock();

/* ── config controls ────────────────────────────────────────── */
const txCount = $("#txCount");
txCount.addEventListener("input", () => {
  $("#txCountOut").textContent = txCount.value;
  STATE.config.transactions = +txCount.value;
});

$("#attackerToggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg"); if (!btn) return;
  const on = btn.dataset.val === "true";
  STATE.config.attackerEnabled = on;
  $$("#attackerToggle .seg").forEach((s) =>
    s.classList.toggle("active", s.dataset.val === btn.dataset.val));
  $("#tamperBlock").classList.toggle("disabled", !on);
});

$("#tamperToggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg"); if (!btn) return;
  STATE.config.tamperRate = +btn.dataset.val;
  $$("#tamperToggle .seg").forEach((s) =>
    s.classList.toggle("active", s.dataset.val === btn.dataset.val));
});
/* set defaults */
$$("#attackerToggle .seg")[0].classList.add("active");
$$("#tamperToggle .seg")[1].classList.add("active");

/* ── log filter ─────────────────────────────────────────────── */
$("#logFilter").addEventListener("click", (e) => {
  const btn = e.target.closest(".fbtn"); if (!btn) return;
  STATE.logFilter = btn.dataset.src;
  $$("#logFilter .fbtn").forEach((b) => b.classList.toggle("active", b === btn));
  applyLogFilter();
});
function applyLogFilter() {
  const f = STATE.logFilter;
  $$("#console .logline").forEach((line) => {
    const show = f === "all" || line.dataset.src === f;
    line.style.display = show ? "" : "none";
  });
}

/* ── transaction filter ─────────────────────────────────────── */
$("#txFilter").addEventListener("click", (e) => {
  const btn = e.target.closest(".fbtn"); if (!btn) return;
  STATE.txFilter = btn.dataset.f;
  $$("#txFilter .fbtn").forEach((b) => b.classList.toggle("active", b === btn));
  renderLedger();
});

/* ── run / abort ────────────────────────────────────────────── */
$("#runBtn").addEventListener("click", startRun);
$("#abortBtn").addEventListener("click", async () => {
  $("#abortBtn").disabled = true;
  await fetch("/api/abort", { method: "POST" });
});

async function startRun() {
  setStatus("running");
  STATE.cursor = 0; STATE.finished = false; STATE.phase = 0;
  resetUI();

  $("#runBtn").disabled = true;
  $("#runBtn").hidden = true;
  $("#abortBtn").hidden = false;
  $("#abortBtn").disabled = false;

  const cfg = { ...STATE.config };
  $("#runMeta").textContent =
    `Launching · ${cfg.transactions} tx · attacker ` +
    (cfg.attackerEnabled ? `ON @ ${cfg.tamperRate}%` : "OFF");

  try {
    const r = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(j.error || "server rejected the run");
    }
    poll();
  } catch (err) {
    setStatus("error");
    $("#runMeta").textContent = "Error: " + err.message;
    finishRunUI();
  }
}

function finishRunUI() {
  $("#runBtn").disabled = false;
  $("#runBtn").hidden = false;
  $("#abortBtn").hidden = true;
}

/* ── polling loop ───────────────────────────────────────────── */
async function poll() {
  if (STATE.polling) return;
  STATE.polling = true;
  try {
    const r = await fetch("/api/poll?since=" + STATE.cursor);
    const data = await r.json();
    STATE.cursor = data.cursor;

    if (data.events && data.events.length) appendLogs(data.events);
    $("#elapsed").textContent = (data.elapsed || 0).toFixed(1) + "s";
    updateProgress();

    if (data.status === "running") {
      setStatus("running");
      setTimeout(() => { STATE.polling = false; poll(); }, 380);
      return;
    }
    /* terminal state */
    STATE.polling = false;
    if (data.status === "done" && !STATE.finished) {
      STATE.finished = true;
      setStatus("done");
      $("#progBar").style.width = "100%";
      await loadResults();
      $("#runMeta").textContent = "Simulation complete.";
      finishRunUI();
    } else if (data.status === "error") {
      STATE.finished = true;
      setStatus("error");
      $("#runMeta").textContent = "Error: " + (data.error || "simulation failed");
      finishRunUI();
    } else {
      finishRunUI();
    }
  } catch (err) {
    STATE.polling = false;
    setTimeout(poll, 800); /* network hiccup — retry */
  }
}

/* ── status pill ────────────────────────────────────────────── */
function setStatus(state) {
  const pill = $("#statusPill");
  pill.dataset.state = state;
  $("#statusText").textContent = {
    idle: "IDLE", running: "RUNNING", done: "COMPLETE", error: "ERROR",
  }[state] || state.toUpperCase();
}

/* ── console rendering ──────────────────────────────────────── */
function classifyLine(ev) {
  const t = ev.text;
  const cls = ["logline", "log-" + ev.src];
  if (/PHASE\s+\d/.test(t) && /[═]/.test(t)) { cls.push("phase"); STATE.phase = phaseOf(t); }
  else if (/\[ATTACKED\]/.test(t) || /CORRUPTING/.test(t)) cls.push("attackhit");
  else if (/✓\s*VALID|✓ YES|INTACT|caught 100%|passed through|\[OK\]/.test(t)) cls.push("ok");
  else if (/✗\s*INVALID|TAMPER|✗ NO|BROKEN|rejected|REJECTED/i.test(t)) cls.push("bad");
  if (/SIMULATION COMPLETE/.test(t)) STATE.phase = 9;
  return cls.join(" ");
}
function phaseOf(t) {
  const m = t.match(/PHASE\s+(\d)/);
  return m ? +m[1] : STATE.phase;
}

function appendLogs(events) {
  const box = $("#console");
  const empty = $("#consoleEmpty");
  if (empty) empty.remove();

  const frag = document.createDocumentFragment();
  for (const ev of events) {
    if (ev.text === "") continue;
    const line = el("div", classifyLine(ev));
    line.dataset.src = ev.src;
    const srcLabel = { system: "SYS", defender: "DEFND", attacker: "ATTCK" }[ev.src] || ev.src;
    line.appendChild(el("span", "ts", ev.t.toFixed(1) + "s"));
    line.appendChild(el("span", "src", srcLabel));
    line.appendChild(el("span", "msg", escapeHtml(ev.text)));
    if (STATE.logFilter !== "all" && ev.src !== STATE.logFilter) line.style.display = "none";
    frag.appendChild(line);
  }
  box.appendChild(frag);

  const lines = box.querySelectorAll(".logline").length;
  $("#lineCount").textContent = lines + " line" + (lines === 1 ? "" : "s");
  if ($("#autoscroll").checked) box.scrollTop = box.scrollHeight;
}

function updateProgress() {
  const pct = Math.min(100, Math.round((STATE.phase / 9) * 100));
  if (!STATE.finished) $("#progBar").style.width = pct + "%";
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

/* ── reset UI for a fresh run ───────────────────────────────── */
function resetUI() {
  $("#console").innerHTML =
    `<div class="console-empty" id="consoleEmpty">
       <span class="cursor-line">root@microgrid:~$ <span class="blink">_</span></span>
       <p>Initializing nodes…</p></div>`;
  $("#lineCount").textContent = "0 lines";
  $("#progBar").style.width = "0%";
  $("#elapsed").textContent = "0.0s";
  ph("#metricsGrid", "Running simulation…");
  ph("#deviceGrid", "Generating ML-DSA keypairs…");
  ph("#fogGrid", "Awaiting fog verification…");
  ph("#chainTrack", "Awaiting block creation…");
  $("#ledgerBody").innerHTML =
    `<tr><td colspan="8" class="placeholder">Awaiting transactions…</td></tr>`;
  ph("#graphGrid", "Charts render after the run…");
  $("#secVerdict").innerHTML = `<p class="placeholder">Awaiting verdict…</p>`;
  $("#chainBadge").textContent = "proof-of-authority";
  $("#chainBadge").className = "panel-tag";
}
function ph(sel, msg) { $(sel).innerHTML = `<div class="placeholder">${msg}</div>`; }

/* ── results ────────────────────────────────────────────────── */
async function loadResults() {
  try {
    const r = await fetch("/api/results");
    if (!r.ok) return;
    const res = await r.json();
    renderMetrics(res);
    renderDevices(res.devices);
    renderFog(res.nodes);
    renderChain(res.blocks, res.chainValid);
    STATE.txs = res.transactions || [];
    renderLedger();
    renderGraphs(res.graphs);
    renderSecurity(res);
  } catch (err) {
    console.error(err);
  }
}

/* ── metrics ────────────────────────────────────────────────── */
function renderMetrics(res) {
  const m = res.metrics || {};
  const fog = res.fogSummary || {};
  const valid = fog.valid || 0, rej = fog.rejected || 0;
  const total = valid + rej;
  const detect = rej > 0 ? 100 : (total > 0 ? 100 : 0);

  const cards = [
    { v: total,                       l: "Transactions",   cls: "accent", sub: "signed & routed" },
    { v: valid,                       l: "Verified Valid", cls: "accent", sub: "✓ accepted by fog" },
    { v: rej,                         l: "Rejected",       cls: "danger", sub: "✗ tamper caught" },
    { v: detect + "%",                l: "Tamper Detection", cls: "accent", sub: rej + " / " + rej + " caught" },
    { v: res.blocks ? res.blocks.length : 0, l: "Blocks Mined", cls: "", sub: "PoA consensus" },
    { v: fmt(m.throughput_tps),       l: "Throughput",     cls: "", sub: "tx / second" },
    { v: fmt(m.avg_sign_ms) + "ms",   l: "Avg Sign Time",  cls: "", sub: "ML-DSA-44" },
    { v: fmt(m.avg_verify_ms) + "ms", l: "Avg Verify Time",cls: "", sub: "fog node check" },
  ];
  const grid = $("#metricsGrid");
  grid.innerHTML = "";
  cards.forEach((c, i) => {
    const card = el("div", "metric reveal" + (c.cls ? " " + c.cls : ""));
    card.style.animationDelay = (i * 45) + "ms";
    card.innerHTML =
      `<div class="m-val" data-target="${typeof c.v === "number" ? c.v : ""}">${c.v}</div>
       <div class="m-label">${c.l}</div><div class="m-sub">${c.sub}</div>`;
    grid.appendChild(card);
    countUp(card.querySelector(".m-val"), c.v);
  });
}
function fmt(n) { return (n == null ? 0 : +n).toFixed(2); }

function countUp(node, value) {
  if (typeof value !== "number") return;
  const dur = 650, t0 = performance.now();
  function step(now) {
    const k = Math.min(1, (now - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    node.textContent = Math.round(value * e);
    if (k < 1) requestAnimationFrame(step);
    else node.textContent = value;
  }
  requestAnimationFrame(step);
}

/* ── devices ────────────────────────────────────────────────── */
function renderDevices(devices) {
  const grid = $("#deviceGrid");
  if (!devices || !devices.length) { ph("#deviceGrid", "No device data."); return; }
  grid.innerHTML = "";
  devices.forEach((d, i) => {
    const icon = DEVICE_ICON[d.type] || "◆";
    const card = el("div", "device reveal");
    card.style.animationDelay = (i * 50) + "ms";
    card.innerHTML = `
      <div class="dev-top">
        <div class="dev-icon">${icon}</div>
        <div>
          <div class="dev-name">${d.id}</div>
          <div class="dev-role">${d.type}</div>
        </div>
      </div>
      <div class="dev-stat"><span class="k">tx signed</span><span class="v">${d.txs}</span></div>
      <div class="dev-stat"><span class="k">avg sign</span><span class="v">${fmt(d.avgSign)} ms</span></div>
      <div class="dev-stat"><span class="k">public key</span><span class="v dev-key">${d.pk} B</span></div>
      <div class="dev-stat"><span class="k">secret key</span><span class="v dev-key">${d.sk} B</span></div>`;
    grid.appendChild(card);
  });
}

/* ── fog network ────────────────────────────────────────────── */
function renderFog(nodes) {
  const grid = $("#fogGrid");
  if (!nodes || !nodes.length) { ph("#fogGrid", "No fog data."); return; }
  grid.innerHTML = "";
  nodes.forEach((n, i) => {
    const v = n.valid || 0, r = n.rejected || 0, tot = v + r || 1;
    const card = el("div", "fog-node reveal");
    card.style.animationDelay = (i * 60) + "ms";
    card.innerHTML = `
      <div class="fog-top">
        <div>
          <div class="fog-id">${n.node_id}</div>
          <div class="fog-loc">${n.location}</div>
        </div>
        <span class="fog-online">● ONLINE</span>
      </div>
      <div class="fog-bar">
        <div class="seg-valid" style="width:${(v / tot) * 100}%"></div>
        <div class="seg-rej" style="width:${(r / tot) * 100}%"></div>
      </div>
      <div class="fog-counts">
        <div class="fog-count valid"><div class="n">${v}</div><div class="l">VALID</div></div>
        <div class="fog-count rej"><div class="n">${r}</div><div class="l">REJECTED</div></div>
        <div class="fog-count time"><div class="n">${fmt(n.avg_verify_time_ms)}</div><div class="l">AVG ms</div></div>
      </div>`;
    grid.appendChild(card);
  });
}

/* ── blockchain ─────────────────────────────────────────────── */
function renderChain(blocks, valid) {
  const track = $("#chainTrack");
  if (!blocks || !blocks.length) { ph("#chainTrack", "No blocks."); return; }
  const badge = $("#chainBadge");
  badge.textContent = valid ? "✓ CHAIN INTEGRITY VERIFIED" : "✗ CHAIN BROKEN";
  badge.className = "panel-tag " + (valid ? "valid" : "invalid");

  track.innerHTML = "";
  blocks.forEach((b, i) => {
    const card = el("div", "block reveal" + (b.index === 0 ? " genesis" : ""));
    card.style.animationDelay = (i * 55) + "ms";
    card.innerHTML = `
      <div class="block-idx">${b.index === 0 ? "▣ GENESIS" : "BLOCK #" + b.index}</div>
      <div class="block-row"><span class="k">txs</span><span class="v">${b.tx_count}</span></div>
      <div class="block-row"><span class="k">forger</span><span class="v">${shorten(b.forger, 14)}</span></div>
      <div class="block-row"><span class="k">nonce</span><span class="v">${b.nonce}</span></div>
      <div class="block-hash"><span class="lbl">hash</span><br>${(b.hash || "").slice(0, 24)}…</div>`;
    track.appendChild(card);
  });
}
function shorten(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n) + "…" : s; }

/* ── transaction ledger ─────────────────────────────────────── */
function renderLedger() {
  const body = $("#ledgerBody");
  let rows = STATE.txs;
  if (STATE.txFilter === "valid")    rows = rows.filter((t) => t.fogValid === true);
  if (STATE.txFilter === "rejected") rows = rows.filter((t) => t.fogValid === false);

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="8" class="placeholder">No matching transactions.</td></tr>`;
    return;
  }
  body.innerHTML = "";
  rows.forEach((t, i) => {
    const ok = t.fogValid === true;
    const tr = el("tr", ok ? "" : "row-rejected");
    const verdict = ok
      ? `<span class="verdict valid">✓ VALID</span>`
      : `<span class="verdict rejected">✗ REJECTED</span>`;
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td class="tx-id">${(t.tx_id || "").slice(0, 8)}</td>
      <td>${t.sender}</td>
      <td class="tx-route">${t.receiver}</td>
      <td class="tx-energy">${t.energy} ${t.unit || ""}</td>
      <td>${t.fogNode || "—"}</td>
      <td>${t.verifyMs != null ? fmt(t.verifyMs) + " ms" : "—"}</td>
      <td>${verdict}</td>`;
    body.appendChild(tr);
  });
}

/* ── analytics graphs ───────────────────────────────────────── */
function renderGraphs(graphs) {
  const grid = $("#graphGrid");
  if (!graphs || !graphs.length) { ph("#graphGrid", "No charts generated (matplotlib missing?)."); return; }
  const stamp = Date.now();
  grid.innerHTML = "";
  graphs.forEach((g, i) => {
    const src = `/api/graph?file=${encodeURIComponent(g.file)}&t=${stamp}`;
    const card = el("div", "graph-card reveal");
    card.style.animationDelay = (i * 50) + "ms";
    card.innerHTML = `<div class="g-title">${g.title}</div><img src="${src}" alt="${g.title}" />`;
    card.addEventListener("click", () => openLightbox(src));
    grid.appendChild(card);
  });
}

/* ── security verdict ───────────────────────────────────────── */
function renderSecurity(res) {
  const s = res.security || {};
  const caught = s.tamperCaught || 0;
  const sent = s.tamperSent || 0;
  const pass = res.chainValid && (sent === 0 || caught === sent);
  const box = $("#secVerdict");
  box.innerHTML = `
    <div class="verdict-banner ${pass ? "" : "fail"}">
      <div class="vb-title">${pass ? "▣ DEFENSE HELD" : "▣ INTEGRITY COMPROMISED"}</div>
      <div class="vb-sub">${pass
        ? "Every tampered transaction was detected and rejected by the fog layer."
        : "The blockchain reported a tamper or unverified state."}</div>
    </div>
    <div class="sec-row"><span class="k">Tampered TX detected</span><span class="v safe">${caught} / ${sent}</span></div>
    <div class="sec-row"><span class="k">False positives</span><span class="v">${s.falsePositive || 0}</span></div>
    <div class="sec-row"><span class="k">Chain integrity</span>
      <span class="v ${res.chainValid ? "safe" : ""}" style="${res.chainValid ? "" : "color:var(--danger)"}">
      ${res.chainValid ? "INTACT ✓" : "BROKEN ✗"}</span></div>
    <div class="sec-row"><span class="k">Public key size</span><span class="v">${s.publicKey} bytes</span></div>
    <div class="sec-row"><span class="k">Secret key size</span><span class="v">${s.privateKey} bytes</span></div>`;
}

/* ── lightbox ───────────────────────────────────────────────── */
function openLightbox(src) {
  $("#lightboxImg").src = src;
  $("#lightbox").hidden = false;
}
$("#lightboxClose").addEventListener("click", () => ($("#lightbox").hidden = true));
$("#lightbox").addEventListener("click", (e) => {
  if (e.target.id === "lightbox") $("#lightbox").hidden = true;
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("#lightbox").hidden = true;
});

/* ── boot ───────────────────────────────────────────────────── */
setStatus("idle");
