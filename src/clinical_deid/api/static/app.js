// Web interface (T4.1). Plain JavaScript, no dependencies.
// Security: user and API data are only ever written with textContent or new nodes.
"use strict";

const MAX_CHARACTERS = 10000;
const CONFIGURATIONS = ["model_only", "llm_only", "cascade"];
const CATEGORIES = ["NAME", "DATE", "LOCATION", "ID", "CONTACT", "AGE", "PROFESSION", "OTHER"];

const $ = (id) => document.getElementById(id);

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

// ---------- Tabs ----------

function setupTabs() {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const select = (tab) => {
    for (const other of tabs) {
      const selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      other.tabIndex = selected ? 0 : -1;
      $(other.getAttribute("aria-controls")).hidden = !selected;
    }
    tab.focus();
    if (tab.id === "tab-comparison") loadComparison();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") select(tabs[(index + 1) % tabs.length]);
      if (event.key === "ArrowLeft") select(tabs[(index - 1 + tabs.length) % tabs.length]);
    });
  });
}

// ---------- Input ----------

function updateCharCount() {
  const length = $("note-input").value.length;
  $("char-count").textContent =
    `${length.toLocaleString("en")} / ${MAX_CHARACTERS.toLocaleString("en")} characters`;
}

function setNote(text) {
  $("note-input").value = text;
  updateCharCount();
  $("result").hidden = true;
}

async function setupExamples() {
  const select = $("example-select");
  let examples = [];
  try {
    const response = await fetch("/static/examples.json");
    if (!response.ok) throw new Error();
    examples = await response.json();
  } catch {
    select.disabled = true;
    return;
  }
  for (const example of examples) {
    const option = document.createElement("option");
    option.value = example.id;
    option.textContent = example.source === "synthetic" ? `${example.title} (synthetic)` : example.title;
    select.append(option);
  }
  select.addEventListener("change", () => {
    const example = examples.find((item) => item.id === select.value);
    if (example) setNote(example.text);
  });
}

function setupFileUpload() {
  $("file-input").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    const status = $("status");
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setStatus(status, "Only .txt files are accepted.", true);
      return;
    }
    const text = await file.text();
    if (text.length > MAX_CHARACTERS) {
      setStatus(status, `The file has ${text.length.toLocaleString("en")} characters; the limit is 10,000.`, true);
      return;
    }
    setNote(text);
    setStatus(status, "");
  });
}

// ---------- De-identify ----------

const ERROR_MESSAGES = {
  400: "The request is not valid. Check that the note is not empty.",
  401: "Your session has expired. Please log in again.",
  413: "The note is longer than 10,000 characters.",
  429: "Too many requests. Please wait a moment and try again.",
  503: "The service is temporarily unavailable. Please try again later.",
};

async function deidentify(event) {
  event.preventDefault();
  const text = $("note-input").value;
  const status = $("status");
  const button = $("submit-button");

  if (!text.trim()) {
    setStatus(status, "Paste a note, upload a .txt file or load an example first.", true);
    return;
  }
  if (text.length > MAX_CHARACTERS) {
    setStatus(status, "The note is longer than 10,000 characters.", true);
    return;
  }

  button.disabled = true;
  $("result").hidden = true;
  setStatus(status, "Processing… the first request may take a while (cold start).");
  try {
    const response = await fetch("/api/deidentify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      setStatus(status, ERROR_MESSAGES[response.status] || "Unexpected error. Please try again.", true);
      return;
    }
    showResult(await response.json());
    setStatus(status, "");
  } catch {
    setStatus(status, "Network error. Please check your connection and try again.", true);
  } finally {
    button.disabled = false;
  }
}

function showResult(body) {
  $("result-text").textContent = body.deidentified_text;
  const m = body.metrics;
  $("result-metrics").textContent =
    `${m.n_entities} entities masked · ${m.n_llm} sentences checked by the LLM · ${m.latency_ms} ms`;
  $("result").hidden = false;
  $("result-text").focus();
}

async function copyResult() {
  const button = $("copy-button");
  try {
    await navigator.clipboard.writeText($("result-text").textContent);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Copy failed";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 2000);
}

function downloadResult() {
  const blob = new Blob([$("result-text").textContent], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "deidentified.txt";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ---------- Comparison ----------

let comparisonLoaded = false;

const fmt = (value, digits = 3) => (typeof value === "number" ? value.toFixed(digits) : "—");

function buildTable(table, headers, rows) {
  table.replaceChildren();
  const head = table.createTHead().insertRow();
  for (const header of headers) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = header;
    head.append(th);
  }
  const tbody = table.createTBody();
  for (const cells of rows) {
    const row = tbody.insertRow();
    cells.forEach((cell, index) => {
      const element = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) element.scope = "row";
      element.textContent = cell;
      row.append(element);
    });
  }
}

function renderComparison(report) {
  const configs = report.configurations || {};
  const overallRows = CONFIGURATIONS.map((name) => {
    const config = configs[name] || { status: "pending" };
    if (config.status === "pending" || !config.overall) {
      return [name, "pending", "", "", "", "", ""];
    }
    const latency = config.latency_s || {};
    return [
      name,
      String(config.n_documents),
      fmt(config.overall.recall),
      fmt(config.overall.precision),
      fmt(config.overall.f1),
      `${fmt(latency.p50, 2)} / ${fmt(latency.p95, 2)}`,
      fmt(config.cost && config.cost.usd_per_document, 5),
    ];
  });
  buildTable(
    $("overall-table"),
    ["Configuration", "Documents", "Recall", "Precision", "F1", "Latency p50 / p95 (s)", "USD per document"],
    overallRows,
  );

  const categoryRows = CATEGORIES.map((category) => [
    category,
    ...CONFIGURATIONS.map((name) => {
      const perCategory = configs[name] && configs[name].per_category;
      return perCategory && perCategory[category] ? fmt(perCategory[category].recall) : "pending";
    }),
  ]);
  buildTable($("category-table"), ["Category", ...CONFIGURATIONS], categoryRows);
}

async function loadComparison() {
  if (comparisonLoaded) return;
  const status = $("comparison-status");
  setStatus(status, "Loading…");
  try {
    const response = await fetch("/api/comparison");
    if (!response.ok) throw new Error();
    renderComparison(await response.json());
    comparisonLoaded = true;
    setStatus(status, "");
  } catch {
    setStatus(status, "Could not load the comparison results.", true);
  }
}

// ---------- Start ----------

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupExamples();
  setupFileUpload();
  $("note-input").addEventListener("input", updateCharCount);
  $("deid-form").addEventListener("submit", deidentify);
  $("copy-button").addEventListener("click", copyResult);
  $("download-button").addEventListener("click", downloadResult);
  updateCharCount();
});
