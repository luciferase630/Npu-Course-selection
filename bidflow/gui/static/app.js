const output = document.getElementById("output");
const jobsEl = document.getElementById("jobs");

function print(value) {
  if (typeof value === "string") {
    output.textContent = value;
  } else {
    output.textContent = JSON.stringify(value, null, 2);
  }
}

async function api(path, payload = null) {
  const options = payload
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    : {};
  const response = await fetch(path, options);
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { ok: false, error: text };
  }
  if (!response.ok) {
    throw new Error(data.error || data.stderr || response.statusText);
  }
  return data;
}

function valueFromField(field) {
  if (field.type === "checkbox") return field.checked;
  if (field.tagName === "TEXTAREA") {
    return field.value
      .split(/\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (field.type === "number") return field.value === "" ? "" : Number(field.value);
  return field.value.trim();
}

function formPayload(form) {
  const payload = {};
  for (const field of form.querySelectorAll("input, select, textarea")) {
    if (!field.name) continue;
    const value = valueFromField(field);
    if (value === "" || (Array.isArray(value) && value.length === 0)) continue;
    payload[field.name] = value;
  }
  return payload;
}

async function submitForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const endpoint = form.dataset.endpoint;
  const payload = formPayload(form);
  try {
    const result = await api(endpoint, payload);
    print(result);
    if (result.job_id) {
      await pollJob(result.job_id);
    } else {
      await refreshJobs();
    }
  } catch (error) {
    print({ ok: false, error: String(error.message || error) });
  }
}

async function pollJob(jobId) {
  let last = null;
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const result = await api(`/api/jobs/${jobId}`);
    last = result.job;
    print(last);
    await refreshJobs();
    if (!["queued", "running"].includes(last.status)) return last;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return last;
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  jobsEl.innerHTML = "";
  for (const job of data.jobs.slice(0, 20)) {
    const item = document.createElement("div");
    item.className = "job";
    item.innerHTML = `
      <strong>${job.job_id}</strong>
      <span class="${job.status}">${job.status}</span>
      <div>${escapeHtml(job.command.join(" "))}</div>
    `;
    item.addEventListener("click", () => print(job));
    jobsEl.appendChild(item);
  }
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bindTabs() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", () => {
      for (const item of document.querySelectorAll(".tab, .panel")) {
        item.classList.remove("active");
      }
      button.classList.add("active");
      document.getElementById(button.dataset.tab).classList.add("active");
    });
  }
}

async function loadHealth() {
  const data = await api("/api/health");
  const env = data.llm_env || {};
  document.getElementById("health").textContent =
    `${data.cwd} · Python ${data.python} · LLM key ${env.OPENAI_API_KEY ? "detected" : "not detected"}`;
}

async function loadScenarios() {
  const data = await api("/api/markets/scenarios");
  const select = document.getElementById("scenarioSelect");
  select.innerHTML = "";
  for (const scenario of data.scenarios) {
    const option = document.createElement("option");
    option.value = scenario.name;
    option.textContent = `${scenario.name} (${scenario.students}×${scenario.sections})`;
    select.appendChild(option);
  }
}

async function loadAgents() {
  const data = await api("/api/agents");
  document.getElementById("agentsOut").textContent = JSON.stringify(data, null, 2);
}

function bindForms() {
  for (const form of document.querySelectorAll(".api-form")) {
    form.addEventListener("submit", submitForm);
  }
  document.getElementById("refreshJobs").addEventListener("click", refreshJobs);
  document.getElementById("loadAgents").addEventListener("click", loadAgents);
}

async function boot() {
  bindTabs();
  bindForms();
  try {
    await Promise.all([loadHealth(), loadScenarios(), loadAgents(), refreshJobs()]);
  } catch (error) {
    print({ ok: false, error: String(error.message || error) });
  }
}

boot();
