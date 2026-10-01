const $ = (sel) => document.querySelector(sel);
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"];

const state = {
  projects: [],
  currentId: null,
  sources: [],
  results: [],
  sort: { key: "published", dir: "desc" },
  lastRequest: null,
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function storeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storeSet(key, val) { try { localStorage.setItem(key, val); } catch {} }

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res;
}

function showErrors(messages) {
  const box = $("#errors");
  box.innerHTML = messages.map((m) => `<div class="error">${esc(m)}</div>`).join("");
  box.hidden = messages.length === 0;
}

const current = () => state.projects.find((p) => p.id === state.currentId);

// ---------- projects ----------
async function loadProjects() {
  state.projects = await (await api("/api/projects")).json();
  if (!current()) {
    const saved = Number(storeGet("projectId"));
    state.currentId = state.projects.some((p) => p.id === saved) ? saved : state.projects[0]?.id ?? null;
  }
  render();
}

function selectProject(id) {
  state.currentId = id;
  storeSet("projectId", String(id));
  state.results = [];
  $("#results-panel").hidden = true;
  showErrors([]);
  render();
}

function render() {
  const list = $("#project-list");
  list.innerHTML = state.projects
    .map((p) => `<li data-id="${p.id}" class="${p.id === state.currentId ? "active" : ""}">
        <span>${esc(p.name)}</span><span class="count">${p.keywords.length}</span></li>`)
    .join("");
  list.querySelectorAll("li").forEach((li) => li.addEventListener("click", () => selectProject(Number(li.dataset.id))));

  const p = current();
  $("#empty-state").hidden = !!p;
  $("#project-panel").hidden = !p;
  $("#search-panel").hidden = !p;
  if (!p) return;

  $("#project-title").textContent = p.name;
  const chips = $("#keyword-chips");
  chips.innerHTML = p.keywords.length
    ? p.keywords.map((k) => `<span class="chip">${esc(k.term)}${k.exact_match ? ' <span class="exact">exact</span>' : ""}
        <button data-kid="${k.id}" title="Remove">×</button></span>`).join("")
    : '<span class="none">No trigger words yet.</span>';
  chips.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => removeKeyword(Number(b.dataset.kid))));
  $("#search-btn").disabled = p.keywords.length === 0;
}

$("#new-project-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#new-project-name");
  try {
    const project = await (await api("/api/projects", { method: "POST", body: { name: input.value } })).json();
    input.value = "";
    state.projects.push(project);
    selectProject(project.id);
    await loadProjects();
  } catch (err) { showErrors([err.message]); }
});

$("#rename-project").addEventListener("click", async () => {
  const p = current();
  const name = prompt("New project name", p.name);
  if (!name || name === p.name) return;
  try {
    await api(`/api/projects/${p.id}`, { method: "PUT", body: { name } });
    await loadProjects();
  } catch (err) { showErrors([err.message]); }
});

$("#delete-project").addEventListener("click", async () => {
  const p = current();
  if (!confirm(`Delete project "${p.name}" and its trigger words?`)) return;
  try {
    await api(`/api/projects/${p.id}`, { method: "DELETE" });
    state.currentId = null;
    $("#results-panel").hidden = true;
    await loadProjects();
  } catch (err) { showErrors([err.message]); }
});

$("#new-keyword-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const p = current();
  const term = $("#new-keyword-term");
  const exact = $("#new-keyword-exact");
  try {
    await api(`/api/projects/${p.id}/keywords`, { method: "POST", body: { term: term.value, exact_match: exact.checked } });
    term.value = "";
    exact.checked = false;
    showErrors([]);
    await loadProjects();
    term.focus();
  } catch (err) { showErrors([err.message]); }
});

async function removeKeyword(kid) {
  try {
    await api(`/api/projects/${state.currentId}/keywords/${kid}`, { method: "DELETE" });
    await loadProjects();
  } catch (err) { showErrors([err.message]); }
}

// ---------- sources & search ----------
async function loadSources() {
  state.sources = await (await api("/api/sources")).json();
  const saved = (storeGet("sources") || "nvd").split(",");
  $("#source-list").innerHTML = state.sources
    .map((s) => `<label class="${s.enabled ? "" : "disabled"}" title="${esc(s.description)}">
        <input type="checkbox" value="${esc(s.id)}" ${s.enabled ? "" : "disabled"} ${s.enabled && saved.includes(s.id) ? "checked" : ""}>
        ${esc(s.name)}${s.enabled ? "" : ` <small>(${s.requires_auth ? "requires login – " : ""}coming soon)</small>`}
      </label>`)
    .join("");
}

$("#window").addEventListener("change", () => { $("#custom-range").hidden = $("#window").value !== "custom"; });

function buildRequest() {
  const sources = [...document.querySelectorAll("#source-list input:checked")].map((i) => i.value);
  storeSet("sources", sources.join(","));
  const req = {
    project_id: state.currentId,
    sources,
    window: $("#window").value,
    date_field: $("#date-field").value,
  };
  if (req.window === "custom") {
    req.start = $("#custom-start").value ? `${$("#custom-start").value}T00:00:00Z` : null;
    req.end = $("#custom-end").value ? `${$("#custom-end").value}T23:59:59Z` : null;
  }
  return req;
}

$("#search-btn").addEventListener("click", async () => {
  const btn = $("#search-btn");
  const req = buildRequest();
  btn.disabled = true;
  btn.textContent = "Searching…";
  $("#rate-hint").textContent = "NVD is rate-limited; large keyword lists or long ranges can take a while.";
  showErrors([]);
  try {
    const data = await (await api("/api/search", { method: "POST", body: req })).json();
    state.lastRequest = req;
    state.results = data.results;
    renderSummary(data);
    renderResults();
    $("#results-panel").hidden = false;
    showErrors(data.errors.map((e) => `${e.source}${e.keyword ? ` / "${e.keyword}"` : ""}: ${e.message}`));
  } catch (err) {
    showErrors([err.message]);
  } finally {
    btn.disabled = false;
    btn.textContent = "Search";
    $("#rate-hint").textContent = "";
  }
});

function renderSummary(data) {
  const fmt = (d) => new Date(d).toLocaleDateString();
  $("#summary").innerHTML =
    `<span class="total">${data.total} result${data.total === 1 ? "" : "s"}</span>` +
    SEVERITIES.filter((s) => data.counts_by_severity[s])
      .map((s) => `<span class="sev sev-${s}">${s} ${data.counts_by_severity[s]}</span>`).join(" ") +
    ` <span class="hint">${fmt(data.start)} – ${fmt(data.end)}</span>`;
  $("#keyword-counts").innerHTML = Object.entries(data.counts_by_keyword)
    .map(([k, n]) => `<span>${esc(k)}: <b>${n}</b></span>`).join("");
}

function sortValue(v, key) {
  if (key === "severity") return SEVERITIES.indexOf(v.severity);
  if (key === "cvss_score") return v.cvss_score ?? -1;
  if (key === "published") return v.published ? Date.parse(v.published) : 0;
  return v[key] ?? "";
}

function renderResults() {
  const q = $("#text-filter").value.trim().toLowerCase();
  const sev = $("#severity-filter").value;
  const { key, dir } = state.sort;
  const rows = state.results
    .filter((v) => !sev || v.severity === sev)
    .filter((v) => !q || [v.id, v.description, ...v.matched_keywords, ...v.cwe].join(" ").toLowerCase().includes(q))
    .sort((a, b) => {
      const x = sortValue(a, key), y = sortValue(b, key);
      const cmp = x < y ? -1 : x > y ? 1 : 0;
      return dir === "asc" ? cmp : -cmp;
    });

  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.toggle("asc", th.dataset.sort === key && dir === "asc");
    th.classList.toggle("desc", th.dataset.sort === key && dir === "desc");
  });

  $("#results-body").innerHTML = rows.length
    ? rows.map((v) => `<tr>
        <td class="id"><a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.id)}</a></td>
        <td><span class="sev sev-${esc(v.severity)}">${esc(v.severity)}</span></td>
        <td class="nowrap">${v.cvss_score ?? "–"}${v.cvss_version ? ` <span class="hint">v${esc(v.cvss_version)}</span>` : ""}</td>
        <td class="nowrap">${v.published ? new Date(v.published).toLocaleDateString() : "–"}</td>
        <td>${v.matched_keywords.map((k) => `<span class="tag">${esc(k)}</span>`).join("")}</td>
        <td class="desc"><div class="text" title="Click to expand">${esc(v.description)}</div>
          ${v.cwe.map((c) => `<span class="tag">${esc(c)}</span>`).join("")}</td>
      </tr>`).join("")
    : `<tr><td colspan="6" class="hint">No results match.</td></tr>`;
}

document.querySelectorAll("th[data-sort]").forEach((th) => th.addEventListener("click", () => {
  const key = th.dataset.sort;
  state.sort = { key, dir: state.sort.key === key && state.sort.dir === "desc" ? "asc" : "desc" };
  renderResults();
}));
$("#results-body").addEventListener("click", (e) => {
  if (e.target.classList.contains("text")) e.target.classList.toggle("open");
});
$("#text-filter").addEventListener("input", renderResults);
$("#severity-filter").addEventListener("change", renderResults);

$("#export-btn").addEventListener("click", async () => {
  if (!state.lastRequest) return;
  try {
    const res = await api("/api/search/export.csv", { method: "POST", body: state.lastRequest });
    const blob = await res.blob();
    const name = (res.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "results.csv";
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) { showErrors([err.message]); }
});

loadSources().then(loadProjects).catch((err) => showErrors([err.message]));
