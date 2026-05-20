let token = localStorage.getItem("mgr_token") || "";
let currentUser = null;

const $ = (id) => document.getElementById(id);

function log(data) {
  $("log").textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function authHeaders() {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw data;
  }
  return data;
}

function updateRole() {
  const badge = $("roleBadge");
  if (!currentUser) {
    badge.textContent = "не вошли";
    badge.className = "";
    return;
  }
  badge.textContent = currentUser.is_admin ? `${currentUser.username} · admin` : currentUser.username;
  badge.className = currentUser.is_admin ? "admin" : "user";
}

async function refreshMe() {
  if (!token) {
    updateRole();
    return;
  }
  try {
    currentUser = await api("/me");
    updateRole();
  } catch (error) {
    token = "";
    currentUser = null;
    localStorage.removeItem("mgr_token");
    updateRole();
  }
}

async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      username: $("username").value,
      password: $("password").value,
    }),
  });
  token = data.token;
  currentUser = data.user;
  localStorage.setItem("mgr_token", token);
  updateRole();
  log("Вход выполнен");
}

async function register() {
  const data = await api("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username: $("username").value,
      password: $("password").value,
      admin_code: $("adminCode").value || null,
    }),
  });
  log(data);
}

function addMessage(kind, text) {
  const item = document.createElement("div");
  item.className = `message ${kind}`;
  item.textContent = text;
  $("messages").appendChild(item);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function ask() {
  const question = $("question").value.trim();
  if (!question) return;
  addMessage("user", question);
  $("question").value = "";
  const data = await api("/chat", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
  addMessage("bot", data.result.answer || JSON.stringify(data.result));
}

async function runManager(path, body = {}) {
  const data = await api(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
  log(data);
}

$("loginBtn").onclick = () => login().catch(log);
$("registerBtn").onclick = () => register().catch(log);
$("askBtn").onclick = () => ask().catch(log);
$("statusBtn").onclick = () => api("/mgr/status").then(log).catch(log);
$("runPackagesBtn").onclick = () => runManager("/mgr/run-packages").catch(log);
$("runDocsBtn").onclick = () => runManager("/mgr/run-docs").catch(log);
$("rebuildBtn").onclick = () => runManager("/mgr/rebuild").catch(log);
$("jobsBtn").onclick = () => api("/mgr/jobs").then(log).catch(log);
$("runSheetBtn").onclick = () =>
  runManager("/mgr/run-google-sheet", {
    url: $("sheetUrl").value || null,
    gid: $("sheetGid").value || "0",
    title: $("sheetTitle").value || "Google Sheet",
    code: "google_sheet",
  }).catch(log);

$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.ctrlKey) {
    ask().catch(log);
  }
});

refreshMe();
