const $ = (sel) => document.querySelector(sel);
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"];

const state = {
  projects: [],
  currentId: null,
  sources: [],
  results: [],
  sort: { key: "published", dir: "desc" },
  lastRequest: null,
  seenKeywords: new Set(),
  animateRows: false,
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
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired, please sign in again");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res;
}

function showErrors(messages) {
  const box = $("#errors");
  box.innerHTML = messages.map((m) => `<div class="alert" role="alert">${esc(m)}</div>`).join("");
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

function setTitle(text) {
  const el = $("#project-title");
  if (el.textContent === text) return;
  el.textContent = text;
  el.style.animation = "none";   // replay the title entrance
  void el.offsetWidth;
  el.style.animation = "";
}

function render() {
  const list = $("#project-list");
  list.innerHTML = state.projects
    .map((p) => `<li data-id="${p.id}" tabindex="0" class="${p.id === state.currentId ? "active" : ""}"
        ${p.id === state.currentId ? 'aria-current="page"' : ""}>
        <span class="name">${esc(p.name)}</span><span class="count">${p.keywords.length}</span></li>`)
    .join("");
  list.querySelectorAll("li").forEach((li) => {
    const open = () => selectProject(Number(li.dataset.id));
    li.addEventListener("click", open);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

  const p = current();
  $("#empty-state").hidden = !!p;
  $("#project-panel").hidden = !p;
  $("#search-panel").hidden = !p;
  $("#project-actions").hidden = !p;
  setTitle(p ? p.name : "Welcome");
  if (!p) return;

  $("#keyword-count").textContent = `${p.keywords.length} word${p.keywords.length === 1 ? "" : "s"}`;
  const chips = $("#keyword-chips");
  const firstPaint = state.seenKeywords.size === 0;
  chips.innerHTML = p.keywords.length
    ? p.keywords.map((k) => `<span class="chip${!firstPaint && !state.seenKeywords.has(k.id) ? " is-new" : ""}">${esc(k.term)}${k.exact_match ? ' <span class="exact">exact</span>' : ""}
        <button data-kid="${k.id}" title="Remove" aria-label="Remove ${esc(k.term)}">×</button></span>`).join("")
    : '<span class="none">No trigger words yet — add the first one below.</span>';
  state.seenKeywords = new Set(state.projects.flatMap((proj) => proj.keywords.map((k) => k.id)));
  if (state.seenKeywords.size === 0) state.seenKeywords.add(-1);
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
  btn.classList.add("is-loading");
  btn.textContent = "Searching…";
  showSkeleton();
  $("#rate-hint").textContent = "NVD is rate-limited; large keyword lists or long ranges can take a while.";
  showErrors([]);
  try {
    const data = await (await api("/api/search", { method: "POST", body: req })).json();
    state.lastRequest = req;
    state.results = data.results;
    renderSummary(data);
    state.animateRows = true;
    renderResults();
    state.animateRows = false;
    $("#results-panel").hidden = false;
    showErrors(data.errors.map((e) => `${e.source}${e.keyword ? ` / "${e.keyword}"` : ""}: ${e.message}`));
  } catch (err) {
    $("#results-panel").hidden = true;
    showErrors([err.message]);
  } finally {
    btn.disabled = false;
    btn.classList.remove("is-loading");
    btn.textContent = "Search";
    $("#rate-hint").textContent = "";
  }
});

function showSkeleton() {
  const panel = $("#results-panel");
  panel.hidden = false;
  $("#results-range").textContent = "Searching…";
  $("#summary").innerHTML = Array.from({ length: 4 }, () =>
    '<div class="stat"><span class="skeleton w-40"></span><br><span class="skeleton w-80"></span></div>').join("");
  $("#keyword-counts").innerHTML = "";
  const widths = ["w-60", "w-40", "w-40", "w-60", "w-80", "w-100"];
  $("#results-body").innerHTML = Array.from({ length: 6 }, () =>
    `<tr>${widths.map((w) => `<td><span class="skeleton ${w}"></span></td>`).join("")}</tr>`).join("");
}

function countUp(el, target) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || target === 0) { el.textContent = target; return; }
  const duration = 700;
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderSummary(data) {
  const fmt = (d) => new Date(d).toLocaleDateString();
  $("#results-range").textContent = `${fmt(data.start)} – ${fmt(data.end)}`;
  const tiles = [{ cls: "total", label: "Total", value: data.total }].concat(
    SEVERITIES.filter((s) => data.counts_by_severity[s])
      .map((s) => ({ cls: `sev-tile-${s}`, label: s.toLowerCase(), value: data.counts_by_severity[s] })));
  $("#summary").innerHTML = tiles
    .map((t) => `<div class="stat ${t.cls}"><div class="value" data-value="${t.value}">0</div><div class="label">${esc(t.label)}</div></div>`)
    .join("");
  $("#summary").querySelectorAll(".value").forEach((el) => countUp(el, Number(el.dataset.value)));
  $("#keyword-counts").innerHTML = Object.entries(data.counts_by_keyword)
    .map(([k, n]) => `<span class="tag">${esc(k)} · <b>${n}</b></span>`).join("");
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
    ? rows.map((v) => `<tr${state.animateRows ? ' class="row-in"' : ""}>
        <td class="id"><a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.id)}</a></td>
        <td><span class="sev sev-${esc(v.severity)}">${esc(v.severity)}</span></td>
        <td class="nowrap"><span class="score">${v.cvss_score ?? "–"}</span>${v.cvss_version ? ` <span class="text-muted">v${esc(v.cvss_version)}</span>` : ""}</td>
        <td class="nowrap">${v.published ? new Date(v.published).toLocaleDateString() : "–"}</td>
        <td>${v.matched_keywords.map((k) => `<span class="tag">${esc(k)}</span>`).join("")}</td>
        <td class="desc"><div class="text" title="Click to expand">${esc(v.description)}</div>
          ${v.cwe.map((c) => `<span class="tag mono">${esc(c)}</span>`).join("")}</td>
      </tr>`).join("")
    : `<tr class="empty-row"><td colspan="6">No vulnerabilities match — try a longer time range or more trigger words.</td></tr>`;
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

$("#logout-btn").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

async function loadUser() {
  const { user } = await (await api("/api/me")).json();
  $("#current-user").textContent = user;
  $("#user-avatar").textContent = user.slice(0, 1);
}

loadUser().then(loadSources).then(loadProjects).catch((err) => showErrors([err.message]));
