"use strict";

// ---------------------------------------------------------------------------
// Recurrence Engine playground — a thin browser client for the HTTP API.
// The engine has a single source of truth (the Python service); this file only
// builds a request from the form, calls /v1/occurrences, and paints a calendar.
// ---------------------------------------------------------------------------

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DOW = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const state = {
  pattern: "weekly",
  end: "never",
  policy: "clamp",
  weekdays: new Set([0, 2, 4]),
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem("re-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  $("#theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = cur === "dark" || (cur === "auto" && prefersDark);
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("re-theme", next);
  });
}

// ---------------------------------------------------------------------------
// API base URL
// ---------------------------------------------------------------------------
function apiBase() {
  // Default: same origin as the page (the API serves this playground). Empty
  // string yields relative calls like "/v1/occurrences" — no CORS needed.
  const raw = $("#api-base").value.trim();
  return raw.replace(/\/$/, "");
}

function initApiBase() {
  const input = $("#api-base");
  input.value = localStorage.getItem("re-api-base") || "";
  input.addEventListener("change", () => {
    localStorage.setItem("re-api-base", input.value.trim());
    run();
  });
}

// ---------------------------------------------------------------------------
// Segmented controls & toggles
// ---------------------------------------------------------------------------
function initSegmented(containerSel, key, onChange) {
  $$(`${containerSel} .seg`).forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(`${containerSel} .seg`).forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state[key] = btn.dataset[Object.keys(btn.dataset)[0]];
      if (onChange) onChange();
      run();
    });
  });
}

function initWeekdays() {
  $$("#weekdays .wd").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wd = Number(btn.dataset.wd);
      if (state.weekdays.has(wd)) state.weekdays.delete(wd);
      else state.weekdays.add(wd);
      btn.classList.toggle("is-active");
      run();
    });
  });
}

function syncPatternVisibility() {
  $$(".pattern-opts").forEach((el) => {
    el.hidden = el.dataset.for !== state.pattern;
  });
}
function syncEndVisibility() {
  $$(".end-opts").forEach((el) => {
    el.hidden = el.dataset.for !== state.end;
  });
}
function syncPolicyHint() {
  const hint = $("[data-policy-hint]");
  hint.textContent =
    state.policy === "clamp"
      ? "“The 31st” lands on the last day of shorter months (Feb 28/29)."
      : "Months without the chosen day are skipped entirely.";
}

// ---------------------------------------------------------------------------
// Request assembly
// ---------------------------------------------------------------------------
function buildPattern() {
  switch (state.pattern) {
    case "one_off":
      return { type: "one_off" };
    case "daily":
      return { type: "daily", interval: Number($("#daily-interval").value) };
    case "weekly":
      return {
        type: "weekly",
        weekdays: Array.from(state.weekdays).sort((a, b) => a - b),
        interval: Number($("#weekly-interval").value),
      };
    case "monthly":
      return {
        type: "monthly",
        day: Number($("#monthly-day").value),
        interval: Number($("#monthly-interval").value),
        month_end_policy: state.policy,
      };
  }
}

function buildEnd() {
  switch (state.end) {
    case "never":
      return { type: "never" };
    case "until":
      return { type: "until", date: $("#until-date").value };
    case "count":
      return { type: "count", count: Number($("#count-value").value) };
  }
}

function buildRequest() {
  return {
    rule: {
      start: $("#start").value,
      pattern: buildPattern(),
      end: buildEnd(),
    },
    window_start: $("#window-start").value,
    window_end: $("#window-end").value,
  };
}

// ---------------------------------------------------------------------------
// Calendar rendering
// ---------------------------------------------------------------------------
function monthKey(y, m) {
  return `${y}-${m}`;
}

function renderCalendar(occurrences, windowStart, windowEnd) {
  const cal = $("#calendar");
  cal.innerHTML = "";

  if (!windowStart || !windowEnd || windowStart > windowEnd) {
    cal.innerHTML = `<div class="empty-state">Set a valid window to see occurrences.</div>`;
    return;
  }

  const occSet = new Set(occurrences);
  const start = new Date(windowStart + "T00:00:00");
  const end = new Date(windowEnd + "T00:00:00");

  // Cap the number of rendered months so an enormous window cannot freeze the
  // page; the summary still reports the true total.
  const MAX_MONTHS = 24;
  let y = start.getFullYear();
  let m = start.getMonth();
  let painted = 0;

  while ((y < end.getFullYear() || (y === end.getFullYear() && m <= end.getMonth()))) {
    if (painted >= MAX_MONTHS) break;
    cal.appendChild(renderMonth(y, m, occSet));
    painted += 1;
    m += 1;
    if (m > 11) {
      m = 0;
      y += 1;
    }
  }

  if (painted === 0) {
    cal.innerHTML = `<div class="empty-state">No months in range.</div>`;
  }
}

function renderMonth(year, month, occSet) {
  const wrap = document.createElement("div");
  wrap.className = "month";

  const title = document.createElement("h3");
  title.className = "month-name";
  title.textContent = `${MONTHS[month]} ${year}`;
  wrap.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "month-grid";

  DOW.forEach((d) => {
    const el = document.createElement("div");
    el.className = "dow";
    el.textContent = d;
    grid.appendChild(el);
  });

  const first = new Date(year, month, 1);
  const leadPad = (first.getDay() + 6) % 7; // convert Sun=0 -> Mon=0 indexing
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  for (let i = 0; i < leadPad; i++) {
    const pad = document.createElement("div");
    pad.className = "day pad";
    grid.appendChild(pad);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const cell = document.createElement("div");
    cell.className = "day";
    const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    if (occSet.has(iso)) cell.classList.add("occ");
    cell.textContent = String(d);
    grid.appendChild(cell);
  }

  wrap.appendChild(grid);
  return wrap;
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
function setStatus(kind, message) {
  const el = $("#status");
  if (!kind) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.className = `status ${kind}`;
  el.textContent = message;
}

// ---------------------------------------------------------------------------
// Main run loop (debounced)
// ---------------------------------------------------------------------------
let inflight = 0;

async function run() {
  syncPatternVisibility();
  syncEndVisibility();
  syncPolicyHint();

  const body = buildRequest();
  const windowStart = body.window_start;
  const windowEnd = body.window_end;
  const token = ++inflight;

  setStatus("loading", "Expanding…");

  try {
    const resp = await fetch(`${apiBase()}/v1/occurrences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (token !== inflight) return; // a newer request superseded this one

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      } catch (_) {
        /* keep default */
      }
      setStatus("error", `Request rejected: ${detail}`);
      $("#summary").textContent = "—";
      return;
    }

    const data = await resp.json();
    setStatus(null);
    const n = data.count;
    $("#summary").textContent = n === 1 ? "1 occurrence" : `${n} occurrences`;
    renderCalendar(data.occurrences, windowStart, windowEnd);
  } catch (e) {
    if (token !== inflight) return;
    setStatus(
      "error",
      `Could not reach the API at ${apiBase()}. Start it locally or set the endpoint below.`
    );
    $("#summary").textContent = "—";
  }
}

let debounceTimer = null;
function scheduleRun() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(run, 150);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
function init() {
  initTheme();
  initApiBase();
  initSegmented("#pattern", "pattern");
  initSegmented("#end", "end");
  initSegmented("#policy", "policy");
  initWeekdays();

  $$("input").forEach((input) => input.addEventListener("input", scheduleRun));

  syncPatternVisibility();
  syncEndVisibility();
  syncPolicyHint();
  run();
}

document.addEventListener("DOMContentLoaded", init);
