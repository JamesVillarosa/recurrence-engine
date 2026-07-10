"use strict";

// ---------------------------------------------------------------------------
// Cadence scheduler — browser client for the recurrence API.
// The recurrence engine has a single source of truth (the Python service);
// this file builds a rule from the form, calls /v1/occurrences, and paints the
// occurrences onto a calendar. The surrounding workspace chrome is product
// framing; the scheduler is the real, tested feature.
// ---------------------------------------------------------------------------

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WD_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DOW = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const state = {
  pattern: "monthly",
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
  const saved = localStorage.getItem("cadence-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  $("#theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = cur === "dark" || (cur === "auto" && prefersDark);
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("cadence-theme", next);
  });
}

// ---------------------------------------------------------------------------
// API base URL
// ---------------------------------------------------------------------------
function apiBase() {
  const raw = $("#api-base").value.trim();
  return raw.replace(/\/$/, "");
}
function initApiBase() {
  const input = $("#api-base");
  input.value = localStorage.getItem("cadence-api-base") || "";
  input.addEventListener("change", () => {
    localStorage.setItem("cadence-api-base", input.value.trim());
    run();
  });
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------
function initSegmented(containerSel, key) {
  $$(`${containerSel} .seg`).forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(`${containerSel} .seg`).forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state[key] = btn.dataset[Object.keys(btn.dataset)[0]];
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
function initPreviewLinks() {
  // Sidebar items that are part of the full product but out of scope for the
  // scheduler trial: keep them inert instead of navigating nowhere.
  $$("[data-preview]").forEach((el) =>
    el.addEventListener("click", (e) => e.preventDefault())
  );
}

function syncVisibility() {
  $$(".pattern-opts").forEach((el) => (el.hidden = el.dataset.for !== state.pattern));
  $$(".end-opts").forEach((el) => (el.hidden = el.dataset.for !== state.end));
  const hint = $("[data-policy-hint]");
  hint.textContent =
    state.policy === "clamp"
      ? "Clamp: lands on the last day of shorter months (Feb 28/29)."
      : "Skip: months without that day produce no occurrence.";
}

// ---------------------------------------------------------------------------
// Request assembly + human-readable summary
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
    rule: { start: $("#start").value, pattern: buildPattern(), end: buildEnd() },
    window_start: $("#window-start").value,
    window_end: $("#window-end").value,
  };
}

function ruleSummary() {
  const every = (n, unit) => (n > 1 ? `every ${n} ${unit}s` : `every ${unit}`);
  let head;
  switch (state.pattern) {
    case "one_off":
      head = `One-off on ${$("#start").value}`;
      break;
    case "daily":
      head = `Daily, ${every(Number($("#daily-interval").value), "day")}`;
      break;
    case "weekly": {
      const days = Array.from(state.weekdays).sort((a, b) => a - b).map((d) => WD_NAMES[d]);
      head = `Weekly on ${days.join(", ") || "—"}, ${every(Number($("#weekly-interval").value), "week")}`;
      break;
    }
    case "monthly":
      head = `Monthly on day ${$("#monthly-day").value} (${state.policy}), ${every(
        Number($("#monthly-interval").value), "month")}`;
      break;
  }
  let tail;
  if (state.end === "never") tail = "no end";
  else if (state.end === "until") tail = `until ${$("#until-date").value}`;
  else tail = `after ${$("#count-value").value} occurrences`;
  return `${head} · ${tail}`;
}

// ---------------------------------------------------------------------------
// Calendar rendering
// ---------------------------------------------------------------------------
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
  const MAX_MONTHS = 24;
  let y = start.getFullYear();
  let m = start.getMonth();
  let painted = 0;
  while (y < end.getFullYear() || (y === end.getFullYear() && m <= end.getMonth())) {
    if (painted >= MAX_MONTHS) break;
    cal.appendChild(renderMonth(y, m, occSet));
    painted += 1;
    m += 1;
    if (m > 11) { m = 0; y += 1; }
  }
  if (painted === 0) cal.innerHTML = `<div class="empty-state">No months in range.</div>`;
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
  const leadPad = (first.getDay() + 6) % 7; // Monday-first
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
// Status
// ---------------------------------------------------------------------------
function setStatus(kind, message) {
  const el = $("#status");
  if (!kind) { el.hidden = true; return; }
  el.hidden = false;
  el.className = `status ${kind}`;
  el.textContent = message;
}

// ---------------------------------------------------------------------------
// Main run loop (debounced)
// ---------------------------------------------------------------------------
let inflight = 0;

async function run() {
  syncVisibility();

  // Reflect the task title and rule into the calendar panel header.
  const title = $("#task-title").value.trim() || "Untitled task";
  $("#cal-title").textContent = title;
  $("#rule-summary").textContent = ruleSummary();

  const body = buildRequest();
  const windowStart = body.window_start;
  const windowEnd = body.window_end;
  const token = ++inflight;
  setStatus("loading", "Expanding rule…");

  try {
    const resp = await fetch(`${apiBase()}/v1/occurrences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (token !== inflight) return;
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      } catch (_) { /* keep default */ }
      setStatus("error", `Rule rejected: ${detail}`);
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
    setStatus("error", `Could not reach the API at ${apiBase() || "this origin"}. Try again or set the endpoint.`);
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
  initPreviewLinks();
  const newTask = $("#new-task");
  if (newTask) {
    newTask.addEventListener("click", () => {
      const title = $("#task-title");
      title.focus();
      title.select();
    });
  }
  $$("input").forEach((input) => input.addEventListener("input", scheduleRun));
  run();
}

document.addEventListener("DOMContentLoaded", init);
